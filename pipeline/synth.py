"""Synthetic investigator lists with a ground truth (the private side is simulated).

True positives are real public sanction records, distorted the way names get
mangled in real site lists. Homonyms are invented innocents who share a name
with a sanctioned person. The test set and the training pairs use different
seeds and disjoint pools of sanction records, so the test is never seen in training.
"""
import random
import string
import zlib

import pandas as pd

from .features import NICKNAMES
from .normalize import person, specialty

PHYSICIAN_SPECIALTIES = [
    "FAMILY_MEDICINE", "INTERNAL_MEDICINE", "PSYCHIATRY", "OBGYN", "ANESTHESIOLOGY", "SURGERY",
    "CARDIOLOGY", "ONCOLOGY", "NEUROLOGY", "PEDIATRICS", "DERMATOLOGY", "ENDOCRINOLOGY",
    "RHEUMATOLOGY", "GASTROENTEROLOGY", "PULMONOLOGY", "PAIN_MANAGEMENT", "OSTEOPATHY",
    "EMERGENCY_MEDICINE",
]
SPECIALTY_LABEL = {s: s.replace("_", " ").title().replace("Obgyn", "Obstetrics & Gynecology")
                   for s in PHYSICIAN_SPECIALTIES}
REVERSE_NICK = {}
for nick, full in NICKNAMES.items():
    REVERSE_NICK.setdefault(full, []).append(nick)
ACCENTS = {"E": "É", "A": "Á", "O": "Ó", "I": "Í", "N": "Ñ"}
CAND_COLUMNS = ["candidate_id", "first_name", "middle_name", "last_name", "city", "state",
                "specialty", "npi"]


def in_test_pool(sanction_id: str) -> bool:
    """Stable split of sanction records: 1 in 5 reserved for the test set."""
    return zlib.crc32(sanction_id.encode()) % 5 == 0


def investigator_like(sanctions: pd.DataFrame) -> pd.Series:
    phys = sanctions["specialty"].isin(PHYSICIAN_SPECIALTIES) | sanctions["specialty_raw"].str.contains(
        "PHYSICIAN|MEDICAL PRACTICE", regex=True)
    return (sanctions["source"] == "FDA Debarment List") | (phys & (sanctions["first"] != ""))


class Generator:
    def __init__(self, sanctions: pd.DataFrame, seed: int, pool: str):
        self.rng = random.Random(seed)
        s = sanctions[sanctions["first"].str.len() > 1]
        keep = s["sanction_id"].map(in_test_pool)
        self.sanctions = s[keep] if pool == "test" else s[~keep]
        leie = sanctions[sanctions["source"] == "OIG LEIE"]
        self.places = leie[(leie["city"] != "") & (leie["state"].str.len() == 2)][["city", "state"]] \
            .drop_duplicates().values.tolist()
        self.states = sorted({st for _, st in self.places})
        self.first_names = sanctions.loc[sanctions["first"].str.len() > 2, "first"].tolist()
        self.investigators = self.sanctions[investigator_like(self.sanctions)]
        self.by_initial = {}
        for f in sorted(set(self.first_names)):
            self.by_initial.setdefault(f[0], []).append(f)
        self.n = 0

    # --- primitives -------------------------------------------------------
    def _id(self) -> str:
        self.n += 1
        return f"C{self.n:05d}"

    def _npi(self) -> str:
        return "1" + "".join(self.rng.choice(string.digits) for _ in range(9))

    def _place(self, state: str | None = None) -> tuple[str, str]:
        if state:
            same = [p for p in self.places if p[1] == state]
            if same:
                return tuple(self.rng.choice(same))
        return tuple(self.rng.choice(self.places))

    def _other_state(self, state: str) -> str:
        return self.rng.choice([s for s in self.states if s != state])

    def _typo(self, word: str) -> str:
        if len(word) < 4:
            return word
        i = self.rng.randrange(1, len(word))  # keep the first letter, as in most real typos
        op = self.rng.choice(["sub", "del", "swap", "dup"])
        if op == "sub":
            return word[:i] + self.rng.choice(string.ascii_uppercase) + word[i + 1:]
        if op == "del":
            return word[:i] + word[i + 1:]
        if op == "swap" and i < len(word) - 1:
            return word[:i] + word[i + 1] + word[i] + word[i + 2:]
        return word[:i] + word[i] + word[i:]

    def _style(self, text: str) -> str:
        """How a name may be typed in a site list: case, accents."""
        r = self.rng.random()
        if r < 0.5:
            return text.title()
        if r < 0.6:
            return text.lower()
        if r < 0.7:
            return "".join(ACCENTS.get(ch, ch) if self.rng.random() < 0.3 else ch for ch in text.title())
        return text

    def _row(self, first, middle, last, city, state, spec, npi) -> dict:
        return {
            "candidate_id": self._id(), "first_name": self._style(first), "middle_name": middle,
            "last_name": self._style(last), "city": city.title(), "state": state,
            "specialty": SPECIALTY_LABEL.get(spec, spec.replace("_", " ").title()), "npi": npi,
        }

    # --- candidate kinds --------------------------------------------------
    def true_positive(self, s: pd.Series) -> tuple[dict, list[str]]:
        rng = self.rng
        first, middle, last = s["first"], s["middle"], s["last"]
        tricks = rng.sample(["initial", "typo", "swap", "compound", "nickname", "title", "none"],
                            k=rng.choice([1, 1, 2]))
        if "nickname" in tricks and first in REVERSE_NICK:
            first = rng.choice(REVERSE_NICK[first])
        if "typo" in tricks:
            if rng.random() < 0.6:
                last = self._typo(last)
            else:
                first = self._typo(first)
        if "initial" in tricks:
            first = first[0] + ("." if rng.random() < 0.5 else "")
        if "compound" in tricks:
            parts = last.split()
            last = parts[rng.randrange(len(parts))] if len(parts) > 1 else \
                f"{last}-{rng.choice(self.sanctions['last'].tolist()).split()[0]}"
        middle = (middle[:1] if rng.random() < 0.6 else middle) if middle and rng.random() < 0.6 else ""
        if "title" in tricks:
            first = "Dr. " + first if rng.random() < 0.5 else first
            last = last + rng.choice([" MD", ", M.D.", " Jr."])

        if s["source"] == "OIG LEIE" and s["state"]:
            if rng.random() < 0.85:
                state = s["state"]
                city = s["city"] if (s["city"] and rng.random() < 0.7) else self._place(state)[0]
            else:  # moved since the exclusion
                city, state = self._place(self._other_state(s["state"]))
            spec = s["specialty"] if (s["specialty"] in PHYSICIAN_SPECIALTIES and rng.random() < 0.8) \
                else rng.choice(PHYSICIAN_SPECIALTIES + [""])
            if s["npi"]:
                npi = s["npi"] if rng.random() < 0.7 else ""
            else:
                npi = self._npi() if rng.random() < 0.5 else ""
        else:  # FDA records carry no location, specialty or NPI
            city, state = self._place()
            spec = rng.choice(PHYSICIAN_SPECIALTIES)
            npi = self._npi() if rng.random() < 0.6 else ""
        row = self._row(first, middle, last, city, state, spec, npi)
        if "swap" in tricks:
            row["first_name"], row["last_name"] = row["last_name"], row["first_name"]
        return row, tricks

    def homonym(self, s: pd.Series) -> dict:
        """An innocent doctor sharing (nearly) the name of a sanctioned person."""
        rng = self.rng
        r = rng.random()
        if r < 0.6:
            first = s["first"]
        elif r < 0.85:
            same_initial = [f for f in self.by_initial.get(s["first"][0], []) if f != s["first"]]
            first = rng.choice(same_initial) if same_initial else s["first"]
        else:
            first = self._typo(s["first"])
        if s["middle"] and rng.random() < 0.5:
            middle = rng.choice([c for c in string.ascii_uppercase if c != s["middle"][0]])
        else:
            middle = s["middle"][:1] if (s["middle"] and rng.random() < 0.3) else ""
        if s["state"] and rng.random() < 0.85:
            city, state = self._place(self._other_state(s["state"]))
        else:
            city, state = self._place(s["state"] or None)
        spec = rng.choice([p for p in PHYSICIAN_SPECIALTIES if p != s["specialty"]]) \
            if rng.random() < 0.75 else (s["specialty"] if s["specialty"] in PHYSICIAN_SPECIALTIES
                                         else rng.choice(PHYSICIAN_SPECIALTIES))
        npi = self._npi() if rng.random() < 0.7 else ""
        return self._row(first, middle, s["last"], city, state, spec, npi)

    def clean(self, surnames: list[str], weights: list[float]) -> dict:
        """A random investigator; may share a common name with someone on a list."""
        rng = self.rng
        last = rng.choices(surnames, weights=weights)[0]
        first = rng.choice(self.first_names)
        middle = rng.choice(string.ascii_uppercase) if rng.random() < 0.5 else ""
        city, state = self._place()
        return self._row(first, middle, last, city, state, rng.choice(PHYSICIAN_SPECIALTIES),
                         self._npi() if rng.random() < 0.8 else "")


def make_test_set(sanctions: pd.DataFrame, surname_freq: pd.DataFrame, seed: int = 2026,
                  n_total: int = 300, n_tp: int = 30, n_hom: int = 40):
    """300 candidates + ground truth + a later sanction for the re-screening scenario."""
    g = Generator(sanctions, seed, pool="test")
    inv = g.investigators
    fda = inv[inv["source"] == "FDA Debarment List"]
    leie = inv[inv["source"] == "OIG LEIE"]
    n_fda = min(6, len(fda))
    tp_src = pd.concat([fda.sample(n_fda, random_state=seed),
                        leie.sample(n_tp - n_fda, random_state=seed)])
    rows, truth = [], []
    for _, s in tp_src.iterrows():
        row, tricks = g.true_positive(s)
        rows.append(row)
        truth.append({"candidate_id": row["candidate_id"], "sanction_id": s["sanction_id"],
                      "kind": "true_positive", "note": "+".join(tricks)})
    hom_src = pd.concat([fda.drop(tp_src.index, errors="ignore").sample(min(8, len(fda) - n_fda), random_state=seed + 1),
                         leie.drop(tp_src.index, errors="ignore").sample(n_hom - min(8, len(fda) - n_fda), random_state=seed + 1)])
    for _, s in hom_src.iterrows():
        row = g.homonym(s)
        rows.append(row)
        truth.append({"candidate_id": row["candidate_id"], "sanction_id": "",
                      "kind": "homonym", "note": f"shares name with {s['sanction_id']}"})
    top = surname_freq.head(3000)
    while len(rows) < n_total:
        row = g.clean(top["name"].tolist(), top["prop100k"].tolist())
        rows.append(row)
        truth.append({"candidate_id": row["candidate_id"], "sanction_id": "", "kind": "clean", "note": ""})

    order = list(range(len(rows)))
    g.rng.shuffle(order)
    cands = pd.DataFrame([rows[i] for i in order], columns=CAND_COLUMNS)
    truth = pd.DataFrame([truth[i] for i in order])
    ids = [f"INV-{i + 1:03d}" for i in range(len(cands))]  # ids must not reveal the kind
    cands["candidate_id"] = truth["candidate_id"] = ids

    # Re-screening scenario: one clean investigator is sanctioned after the trial starts.
    target = cands[truth["kind"] == "clean"].iloc[0]
    later = pd.DataFrame([{
        "sanction_id": "LEIE-DEMO-0001", "source": "OIG LEIE",
        **person(target["first_name"], target["middle_name"], target["last_name"]),
        "display_name": f"{target['first_name']} {target['last_name']}".title(),
        "city": person(last=target["city"])["last"], "state": target["state"],
        "specialty": specialty(target["specialty"]), "specialty_raw": target["specialty"].upper(),
        "npi": target["npi"],
        "sanction_type": "Mandatory exclusion: health care fraud felony (SYNTHETIC DEMO RECORD)",
        "severity": "high", "sanction_date": "2026-10-18", "end_term": "Until reinstated",
        "source_url": "https://oig.hhs.gov/exclusions/", "fetched_at": "2026-10-18",
        "import_version": "leie-demo-update",
    }])
    return cands, truth, later
