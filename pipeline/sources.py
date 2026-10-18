"""Download public sanction lists into a single schema (requirements F1, F3).

Every raw download is kept under data/raw/ with its retrieval date, so a run
is reproducible even if a website changes or is offline: when a download
fails, or RADAR_OFFLINE is set, the most recent snapshot on disk is used.
"""
import hashlib
import io
import logging
import os
import re
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests

from .normalize import clean_npi, person, specialty
from .paths import RAW

log = logging.getLogger(__name__)

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
FDA_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/fda-debarment-list-drug-product-applications"
)
CENSUS_URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 (RedFlagRadar research prototype)"}

SCHEMA = [
    "sanction_id", "source", "first", "middle", "last", "display_name", "city", "state",
    "specialty", "specialty_raw", "npi", "sanction_type", "severity", "sanction_date",
    "end_term", "source_url", "fetched_at", "import_version",
]

# Social Security Act section 1128 exclusion authorities, in plain words.
LEIE_TYPES = {
    "1128a1": "Mandatory exclusion: program-related conviction",
    "1128a2": "Mandatory exclusion: patient abuse or neglect",
    "1128a3": "Mandatory exclusion: health care fraud felony",
    "1128a4": "Mandatory exclusion: controlled substance felony",
    "1128b4": "Permissive exclusion: license revocation or suspension",
    "1128b14": "Permissive exclusion: student loan default",
}


def stable_id(prefix: str, *fields: str) -> str:
    """Id derived from the record itself, so it survives list updates (audit trail)."""
    return f"{prefix}-" + hashlib.sha1("|".join(fields).encode()).hexdigest()[:10].upper()


def _snapshot(name: str, url: str, suffix: str) -> tuple[bytes, str]:
    """Download url to data/raw/<name>_<date>.<suffix>; fall back to the newest snapshot."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = RAW / f"{name}_{today}.{suffix}"
    if not target.exists() and not os.environ.get("RADAR_OFFLINE"):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            target.write_bytes(r.content)
        except requests.RequestException as exc:
            log.warning("Download of %s failed (%s); using last snapshot", url, exc)
    snaps = sorted(RAW.glob(f"{name}_*.{suffix}"))
    if not snaps:
        raise RuntimeError(f"No snapshot available for {name}")
    latest = snaps[-1]
    fetched = latest.stem.split("_")[-1]
    return latest.read_bytes(), fetched


def load_leie() -> pd.DataFrame:
    content, fetched = _snapshot("leie", LEIE_URL, "csv")
    d = pd.read_csv(io.BytesIO(content), dtype=str).fillna("")
    d = d[d["LASTNAME"].str.strip() != ""].reset_index(drop=True)  # individuals only
    rows = []
    for i, r in d.iterrows():
        p = person(r["FIRSTNAME"], r["MIDNAME"], r["LASTNAME"])
        code = r["EXCLTYPE"].strip()
        date = r["EXCLDATE"]
        rows.append({
            "sanction_id": stable_id("LEIE", p["last"], p["first"], p["middle"], r["NPI"], date,
                                     r["STATE"], r["ADDRESS"], code),
            "source": "OIG LEIE",
            **p,
            "display_name": " ".join(x for x in (p["first"], p["middle"], p["last"]) if x).title(),
            "city": person(last=r["CITY"])["last"],
            "state": r["STATE"].strip().upper(),
            "specialty": specialty(r["SPECIALTY"]) or specialty(r["GENERAL"]),
            "specialty_raw": " / ".join(x for x in (r["GENERAL"], r["SPECIALTY"]) if x.strip()),
            "npi": clean_npi(r["NPI"]),
            "sanction_type": LEIE_TYPES.get(code, f"Exclusion ({code})"),
            "severity": "high",
            "sanction_date": f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else "",
            "end_term": "Until reinstated",
            "source_url": LEIE_URL,
            "fetched_at": fetched,
            "import_version": f"leie-{fetched}",
        })
    # The file holds a few strictly identical rows; one record each is enough.
    return pd.DataFrame(rows, columns=SCHEMA).drop_duplicates("sanction_id").reset_index(drop=True)


def load_fda() -> pd.DataFrame:
    content, fetched = _snapshot("fda_debarment", FDA_URL, "html")
    tables = pd.read_html(io.BytesIO(content), extract_links="body")
    t = next(t for t in tables if "Last Name" in t.columns)
    rows = []
    for i, r in t.iterrows():
        text = lambda col: (r[col][0] if isinstance(r[col], tuple) else r[col]) or ""
        links = [r[c][1] for c in t.columns if isinstance(r[c], tuple) and r[c][1]]
        p = person(first=text("First & Middle Names"), last=text("Last Name"))
        if not p["last"]:
            continue
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text("Effective Date"))
        rows.append({
            "sanction_id": stable_id("FDA", p["last"], p["first"], p["middle"], text("Effective Date")),
            "source": "FDA Debarment List",
            **p,
            "display_name": " ".join(x for x in (p["first"], p["middle"], p["last"]) if x).title(),
            "city": "", "state": "", "specialty": "", "specialty_raw": "", "npi": "",
            "sanction_type": "FDA debarment (drug product applications)",
            "severity": "high",
            "sanction_date": f"{m[3]}-{m[1]}-{m[2]}" if m else "",
            "end_term": text("End/Term of Debarment").rstrip("^%*").strip(),
            "source_url": next((l for l in links if "federalregister" in l), FDA_URL),
            "fetched_at": fetched,
            "import_version": f"fda-{fetched}",
        })
    return pd.DataFrame(rows, columns=SCHEMA)


def load_surname_freq() -> pd.DataFrame:
    """Census 2010 surname frequency per 100k people (rarity feature)."""
    out = RAW / "census_surnames.csv"
    if not out.exists():
        content, _ = _snapshot("census_names", CENSUS_URL, "zip")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            c = pd.read_csv(z.open("Names_2010Census.csv"), usecols=["name", "prop100k"])
        c = c[c["name"].astype(str) != "ALL OTHER NAMES"]
        c.to_csv(out, index=False)
        for z in RAW.glob("census_names_*.zip"):  # keep only the small extract in git
            z.unlink()
    return pd.read_csv(out, keep_default_na=False)
