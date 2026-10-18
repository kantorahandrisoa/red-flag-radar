"""Name, place and specialty normalization (requirement F2)."""
import re
import unicodedata

TITLES = {
    "DR", "DOCTOR", "MD", "DO", "PHD", "MR", "MRS", "MS", "MISS", "RN", "NP", "PA",
    "DDS", "DMD", "PHARMD", "DPM", "FACP", "FACS", "MPH", "MBA", "PROF", "LPN", "APRN",
}
SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}


def clean(text) -> str:
    """Uppercase, strip accents and punctuation (hyphens become spaces), collapse spaces."""
    if text is None:
        return ""
    text = str(text)
    if text.lower() in ("nan", "none"):
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("'", "").replace("’", "").replace(".", "")  # M.D. -> MD
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_titles(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in TITLES and t not in SUFFIXES]


def split_full_name(full: str) -> tuple[str, str, str]:
    """Parse a free-text name into (first, middle, last).

    "Smith, John A." -> last first; otherwise "John A. Smith" -> first ... last.
    """
    if full is None:
        return "", "", ""
    raw = str(full)
    if "," in raw:
        last_part, rest = raw.split(",", 1)
        last = " ".join(strip_titles(clean(last_part).split()))
        rest_tokens = strip_titles(clean(rest).split())
        first = rest_tokens[0] if rest_tokens else ""
        middle = " ".join(rest_tokens[1:])
        return first, middle, last
    tokens = strip_titles(clean(raw).split())
    if not tokens:
        return "", "", ""
    if len(tokens) == 1:
        return "", "", tokens[0]
    return tokens[0], " ".join(tokens[1:-1]), tokens[-1]


def person(first="", middle="", last="") -> dict:
    """Normalize separate name fields; titles/suffixes are dropped from every field."""
    f = strip_titles(clean(first).split())
    m = strip_titles(clean(middle).split())
    l = strip_titles(clean(last).split())
    # "John A" given as first name: move trailing tokens to middle.
    if len(f) > 1 and not m:
        f, m = f[:1], f[1:]
    return {"first": " ".join(f), "middle": " ".join(m), "last": " ".join(l)}


def surname_parts(last: str) -> list[str]:
    """Compound surnames ("GARCIA LOPEZ") also match on each part."""
    parts = [p for p in last.split() if len(p) > 1]
    return parts or ([last] if last else [])


def clean_npi(npi) -> str:
    digits = re.sub(r"\D", "", str(npi or ""))
    return digits if len(digits) == 10 and digits != "0" * 10 else ""


# Coarse specialty vocabulary shared by LEIE and candidate lists.
SPECIALTY_MAP = {
    "FAMILY_MEDICINE": ["GENERAL PRACTICE", "FAMILY PRACTICE", "FAMILY MEDICINE", "GENERAL PRACTICE FP"],
    "INTERNAL_MEDICINE": ["INTERNAL MEDICINE"],
    "PSYCHIATRY": ["PSYCHIATRY", "PSYCHIATRIST"],
    "OBGYN": ["GYN OBS", "OBSTETRICS", "GYNECOLOGY", "OB GYN", "OBGYN"],
    "ANESTHESIOLOGY": ["ANESTHESIOLOGY", "ANESTHESIA"],
    "SURGERY": ["SURGERY", "GENERAL SURGERY", "SURGEON"],
    "CARDIOLOGY": ["CARDIOLOGY", "CARDIOVASCULAR"],
    "ONCOLOGY": ["ONCOLOGY", "HEMATOLOGY ONCOLOGY", "HEMATOLOGY"],
    "NEUROLOGY": ["NEUROLOGY"],
    "PEDIATRICS": ["PEDIATRICS"],
    "DERMATOLOGY": ["DERMATOLOGY"],
    "ENDOCRINOLOGY": ["ENDOCRINOLOGY"],
    "RHEUMATOLOGY": ["RHEUMATOLOGY"],
    "GASTROENTEROLOGY": ["GASTROENTEROLOGY"],
    "PULMONOLOGY": ["PULMONARY", "PULMONOLOGY"],
    "PAIN_MANAGEMENT": ["PAIN MANAGEMENT"],
    "RADIOLOGY": ["RADIOLOGY"],
    "OPHTHALMOLOGY": ["OPHTHALMOLOGY"],
    "UROLOGY": ["UROLOGY"],
    "PODIATRY": ["PODIATRY"],
    "OSTEOPATHY": ["OSTEOPATHY"],
    "EMERGENCY_MEDICINE": ["EMERGENCY MEDICINE"],
    "NURSING": ["NURSE", "NURSING", "NURSES AIDE"],
    "PHARMACY": ["PHARMACIST", "PHARMACY"],
    "DENTISTRY": ["DENTIST", "DENTAL"],
    "PSYCHOLOGY": ["PSYCHOLOGY", "PSYCHOLOGIST"],
}


def specialty(text) -> str:
    """Map a free-text specialty to the coarse vocabulary ("" when unknown)."""
    t = clean(text)
    if not t:
        return ""
    for canon, keys in SPECIALTY_MAP.items():
        if any(k in t for k in keys):
            return canon
    return t
