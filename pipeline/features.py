"""Phonetic blocking (F5) and pair features for the identity model (section 7)."""
import math
from collections import defaultdict

import numpy as np
import pandas as pd
from metaphone import doublemetaphone
from rapidfuzz.distance import JaroWinkler

from .normalize import clean_npi, person, specialty, surname_parts

FEATURES = [
    "sim_nom", "sim_prenom", "initiale_ok", "inversion", "phonetique_ok", "npi_egal",
    "npi_manquant", "etat_egal", "ville_egale", "specialite_ok", "rarete_nom", "deuxieme_prenom",
]
NAN = float("nan")

NICKNAMES = {
    "BILL": "WILLIAM", "WILL": "WILLIAM", "WM": "WILLIAM", "BOB": "ROBERT", "ROB": "ROBERT",
    "BOBBY": "ROBERT", "JIM": "JAMES", "JIMMY": "JAMES", "JAS": "JAMES", "MIKE": "MICHAEL",
    "DAVE": "DAVID", "DAN": "DANIEL", "DANNY": "DANIEL", "TOM": "THOMAS", "TONY": "ANTHONY",
    "CHRIS": "CHRISTOPHER", "JOE": "JOSEPH", "JOS": "JOSEPH", "RICK": "RICHARD", "DICK": "RICHARD",
    "RICH": "RICHARD", "STEVE": "STEVEN", "LIZ": "ELIZABETH", "BETH": "ELIZABETH",
    "KATE": "KATHERINE", "KATHY": "KATHERINE", "PEGGY": "MARGARET", "MAGGIE": "MARGARET",
    "SUE": "SUSAN", "JENNY": "JENNIFER", "JEN": "JENNIFER", "CHUCK": "CHARLES",
    "CHAS": "CHARLES", "CHARLIE": "CHARLES", "ED": "EDWARD", "TED": "EDWARD", "GREG": "GREGORY",
    "MATT": "MATTHEW", "PAT": "PATRICK", "SAM": "SAMUEL", "BEN": "BENJAMIN", "ANDY": "ANDREW",
    "ALEX": "ALEXANDER", "NICK": "NICHOLAS", "LARRY": "LAWRENCE", "JERRY": "GERALD",
    "KEN": "KENNETH", "RON": "RONALD", "DON": "DONALD", "TIM": "TIMOTHY", "JEFF": "JEFFREY",
}


def canonical_first(first: str) -> str:
    return NICKNAMES.get(first, first)


def phonetic_keys(name: str) -> set[str]:
    keys = set()
    for part in surname_parts(name):
        keys.update(k for k in doublemetaphone(part) if k)
    return keys


class SurnameRarity:
    """-log10 of the surname's share of the US population (higher = rarer)."""

    UNKNOWN_PROP100K = 0.02  # rarer than any surname in the Census list

    def __init__(self, freq: pd.DataFrame):
        self.prop = dict(zip(freq["name"].astype(str), freq["prop100k"].astype(float)))

    def __call__(self, last: str) -> float:
        parts = surname_parts(last)
        if not parts:
            return NAN
        if len(parts) > 1:  # a compound surname is as rare as its rarest part
            props = [self.prop.get(p, self.UNKNOWN_PROP100K) for p in parts]
            prop = min(props)
        else:
            prop = self.prop.get(parts[0], self.UNKNOWN_PROP100K)
        return round(-math.log10(prop / 1e5), 3)


def prefix_keys(last: str, first: str) -> set[str]:
    """Extra blocking keys, robust to typos that change the sound of a surname:
    surname prefix + first initial, and surname initial + first-name prefix."""
    keys = set()
    if len(last) >= 4 and first:
        keys.add(f"P:{last[:4]}:{first[:1]}")
    if last and len(first) >= 3:
        keys.add(f"F:{last[:1]}:{first[:3]}")
    return keys


class Blocker:
    """Index sanctions by Double Metaphone codes of each surname part, plus a prefix key."""

    def __init__(self, sanctions: pd.DataFrame):
        self.index: dict[str, list[int]] = defaultdict(list)
        for i, (last, first) in enumerate(zip(sanctions["last"], sanctions["first"])):
            for k in phonetic_keys(last) | prefix_keys(last, first):
                self.index[k].append(i)

    def candidates(self, cand: dict) -> list[int]:
        keys = phonetic_keys(cand["last"]) | phonetic_keys(cand["first"])  # first: swapped names
        keys |= prefix_keys(cand["last"], cand["first"]) | prefix_keys(cand["first"], cand["last"])
        out = set()
        for k in keys:
            out.update(self.index.get(k, ()))
        return sorted(out)


def _jw(a: str, b: str) -> float:
    return JaroWinkler.similarity(a, b) if a and b else NAN


def _surname_sim(a: str, b: str) -> float:
    if not a or not b:
        return NAN
    best = _jw(a, b)
    for pa in surname_parts(a):
        for pb in surname_parts(b):
            best = max(best, _jw(pa, pb))
    return best


def _first_sim(a: str, b: str) -> float:
    if len(a) <= 1 or len(b) <= 1:  # an initial alone says nothing beyond initiale_ok
        return NAN
    if canonical_first(a) == canonical_first(b):
        return 1.0
    return _jw(a, b)


def _first_compatible(a: str, b: str) -> bool:
    """Same first name, a known nickname, or an initial consistent with it."""
    if not a or not b:
        return False
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    return _first_sim(a, b) >= 0.85


def _eq(a: str, b: str) -> float:
    return NAN if not a or not b else float(a == b)


def pair_features(c: dict, s: dict, rarity: SurnameRarity) -> dict:
    """Features for one (candidate, sanction) pair; both dicts are already normalized."""
    straight = _surname_sim(c["last"], s["last"])
    swapped_last = _surname_sim(c["first"], s["last"])
    inversion = (
        not straight >= 0.9
        and swapped_last >= 0.92
        and _first_compatible(c["last"], s["first"])
    )
    if inversion:
        c_first, c_last = c["last"], c["first"]
    else:
        c_first, c_last = c["first"], c["last"]

    npi = _eq(c["npi"], s["npi"])
    city = NAN
    if c["city"] and s["city"]:
        city = float(_jw(c["city"], s["city"]) >= 0.93)
    mid = NAN
    if c["middle"] and s["middle"]:
        mid = float(c["middle"][0] == s["middle"][0])
    return {
        "sim_nom": _surname_sim(c_last, s["last"]),
        "sim_prenom": _first_sim(c_first, s["first"]),
        "initiale_ok": float(bool(c_first) and bool(s["first"]) and c_first[0] == s["first"][0]),
        "inversion": float(inversion),
        "phonetique_ok": float(bool(phonetic_keys(c_last) & phonetic_keys(s["last"]))),
        "npi_egal": npi,
        "npi_manquant": float(npi != npi),
        "etat_egal": _eq(c["state"], s["state"]),
        "ville_egale": city,
        "specialite_ok": _eq(c["specialty"], s["specialty"]),
        "rarete_nom": rarity(s["last"]),
        "deuxieme_prenom": mid,
    }


def normalize_candidate(row: dict) -> dict:
    """Bring a raw candidate row (CSV columns) into the normalized form used for matching."""
    if row.get("full_name") and not row.get("last_name"):
        from .normalize import split_full_name
        f, m, l = split_full_name(row["full_name"])
        p = {"first": f, "middle": m, "last": l}
    else:
        p = person(row.get("first_name", ""), row.get("middle_name", ""), row.get("last_name", ""))
    return {
        **p,
        "city": person(last=row.get("city", ""))["last"],
        "state": str(row.get("state", "") or "").strip().upper()[:2],
        "specialty": specialty(row.get("specialty", "")),
        "npi": clean_npi(row.get("npi", "")),
    }


def exact_name_match(c: dict, s: dict) -> bool:
    """Naive baseline: identical normalized first and last name."""
    return bool(c["last"]) and c["first"] == s["first"] and c["last"] == s["last"]


def build_pairs(cands: list[dict], sanctions: pd.DataFrame, blocker: Blocker,
                rarity: SurnameRarity) -> tuple[pd.DataFrame, np.ndarray]:
    """All blocked pairs as a feature frame; returns (frame with cand_idx/sanction_idx, X)."""
    srecs = sanctions[["first", "middle", "last", "city", "state", "specialty", "npi"]].to_dict("records")
    rows = []
    for ci, c in enumerate(cands):
        for si in blocker.candidates(c):
            s = srecs[si]
            # Phonetic blocks can be broad; skip pairs whose surnames are clearly different.
            if not (_surname_sim(c["last"], s["last"]) >= 0.8 or _surname_sim(c["first"], s["last"]) >= 0.8):
                continue
            f = pair_features(c, s, rarity)
            f["cand_idx"], f["sanction_idx"] = ci, si
            rows.append(f)
    df = pd.DataFrame(rows, columns=["cand_idx", "sanction_idx", *FEATURES])
    return df, df[FEATURES].to_numpy(dtype=float)
