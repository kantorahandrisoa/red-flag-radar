"""Scoring engine shared by the evaluation and the API (F6, F7, F8).

The model is the only component that computes a score; turning a score into a
decision is always left to a human reviewer.
"""
import pickle
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import FEATURES, Blocker, SurnameRarity, build_pairs, normalize_candidate

PROBABLE, REVIEW = 0.90, 0.40
ZONES = ("probable", "review", "cleared")


def zone(p: float, probable: float = PROBABLE, review: float = REVIEW) -> str:
    if p >= probable:
        return "probable"
    if p >= review:
        return "review"
    return "cleared"


@dataclass
class Bundle:
    """Everything needed to score: booster for SHAP, isotonic map for calibrated probabilities."""
    lgbm: object
    iso: object
    version: str
    thresholds: dict | None = None  # {"probable": .., "review": ..}, tuned at training time

    def zone(self, p: float) -> str:
        t = self.thresholds or {"probable": PROBABLE, "review": REVIEW}
        return zone(p, t["probable"], t["review"])

    def predict(self, X: np.ndarray) -> np.ndarray:
        raw = self.lgbm.predict_proba(X)[:, 1]
        return np.clip(self.iso.predict(raw), 0.0, 1.0)

    def save(self, path) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path) -> "Bundle":
        with open(path, "rb") as f:
            return pickle.load(f)


class Matcher:
    def __init__(self, bundle: Bundle, sanctions: pd.DataFrame, surname_freq: pd.DataFrame):
        self.bundle = bundle
        self.sanctions = sanctions.reset_index(drop=True)
        self.rarity = SurnameRarity(surname_freq)
        self.blocker = Blocker(self.sanctions)
        self._explainer = None

    def score(self, raw_candidates: list[dict], min_prob: float = 0.05) -> pd.DataFrame:
        """Pairs scored above min_prob, with sanction ids; one row per (candidate, sanction)."""
        cands = [normalize_candidate(r) for r in raw_candidates]
        pairs, X = build_pairs(cands, self.sanctions, self.blocker, self.rarity)
        if pairs.empty:
            return pairs.assign(prob=[], sanction_id=[])
        pairs["prob"] = self.bundle.predict(X)
        pairs = pairs[pairs["prob"] >= min_prob].copy()
        pairs["sanction_id"] = self.sanctions["sanction_id"].to_numpy()[pairs["sanction_idx"]]
        return pairs.sort_values(["cand_idx", "prob"], ascending=[True, False])

    def explain(self, features: dict, top: int = 5) -> list[dict]:
        """Top SHAP contributions of one pair, as plain-language reasons."""
        import shap
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.bundle.lgbm)
        x = np.array([[features[f] for f in FEATURES]], dtype=float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            values = np.asarray(self._explainer.shap_values(x))
        values = values[-1] if values.ndim == 3 else values  # older shap returns one array per class
        values = values.reshape(-1)
        order = np.argsort(-np.abs(values))
        reasons = []
        for i in order[:top]:
            if abs(values[i]) < 0.05:
                break
            value = features[FEATURES[i]]
            if value != value and values[i] > 0:
                continue  # absent data is not evidence for a match; do not present it as such
            text = reason_text(FEATURES[i], value)
            if text:
                reasons.append({"feature": FEATURES[i], "effect": round(float(values[i]), 3),
                                "direction": "raises" if values[i] > 0 else "lowers", "text": text})
        return reasons


def reason_text(name: str, v: float) -> str:
    missing = v != v
    if name == "npi_egal":
        return "No NPI available on both sides" if missing else ("Same NPI number" if v == 1 else "Different NPI number")
    if name == "npi_manquant":
        return "NPI missing on one side, so it cannot confirm identity" if v == 1 else ""
    if name == "sim_nom":
        if missing:
            return ""
        return ("Same last name (or one part of a compound name)" if v >= 0.99 else
                "Very similar last name (possible typo or variant)" if v >= 0.9 else
                "Last name only partly similar")
    if name == "sim_prenom":
        if missing:
            return "Only a first initial is available"
        return ("Same first name (or a known nickname)" if v >= 0.99 else
                "Similar first name" if v >= 0.9 else "Different first name")
    if name == "initiale_ok":
        return "First initial matches" if v == 1 else "First initial differs"
    if name == "inversion":
        return "First and last names appear swapped" if v == 1 else ""
    if name == "phonetique_ok":
        return "Last names sound alike" if v == 1 else "Last names sound different"
    if name == "etat_egal":
        return "Sanction record has no state to compare" if missing else ("Same state" if v == 1 else "Different state")
    if name == "ville_egale":
        return "No city to compare" if missing else ("Same city" if v == 1 else "Different city")
    if name == "specialite_ok":
        return "No specialty to compare" if missing else ("Same specialty" if v == 1 else "Different specialty")
    if name == "rarete_nom":
        if missing:
            return ""
        # v = -log10(share of US population): Smith ~2.1, 1 in 100k people = 5.
        return ("Rare last name: a coincidence is unlikely" if v >= 4.5 else
                "Common last name: many people share it" if v <= 3.0 else "Moderately common last name")
    if name == "deuxieme_prenom":
        return "" if missing else ("Middle initial matches" if v == 1 else "Middle initial differs")
    return ""
