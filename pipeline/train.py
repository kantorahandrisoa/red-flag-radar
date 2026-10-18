"""`make train`: generate labeled training pairs, fit the models, calibrate.

Training pairs come from the *training* pool of sanction records and a
different seed than the 300-candidate test set, which is never used here.
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import sources
from .features import FEATURES, Blocker, SurnameRarity, build_pairs, normalize_candidate, pair_features
from .matcher import PROBABLE, REVIEW, Bundle
from .paths import DB_PATH, MODELS
from .synth import Generator

SEED = 7
# Matching evidence may only ever raise the score; missing data and swaps are left free.
MONOTONE = {"sim_nom": 1, "sim_prenom": 1, "initiale_ok": 1, "phonetique_ok": 1, "npi_egal": 1,
            "etat_egal": 1, "ville_egale": 1, "specialite_ok": 1, "rarete_nom": 1, "deuxieme_prenom": 1}


def tune_thresholds(p: np.ndarray, y: np.ndarray) -> dict:
    """Review threshold = best F2 (recall weighted 2x) on held-out training pairs, never the test set."""
    best, review = -1.0, REVIEW
    for t in np.unique(np.round(p, 3)):
        flagged = p >= t
        tp = float((flagged & (y == 1)).sum())
        prec, rec = tp / max(flagged.sum(), 1), tp / max((y == 1).sum(), 1)
        f2 = 5 * prec * rec / max(4 * prec + rec, 1e-9)
        if f2 > best and t <= REVIEW:
            best, review = f2, float(t)
    return {"probable": PROBABLE, "review": round(max(review, 0.05), 3)}


def training_pairs(sanctions: pd.DataFrame, surnames: pd.DataFrame, n_each: int = 3000,
                   max_neg: int = 25) -> pd.DataFrame:
    g = Generator(sanctions, SEED, pool="train")
    sid_to_idx = {s: i for i, s in enumerate(sanctions["sanction_id"])}
    inv = g.investigators
    fda = inv[inv["source"] == "FDA Debarment List"]
    # 10% of positives and hard negatives come from name-only (FDA) records.
    tp_src = pd.concat([fda.sample(int(n_each * 0.1), replace=True, random_state=SEED),
                        g.sanctions.sample(int(n_each * 0.9), random_state=SEED)])
    hom_src = pd.concat([fda.sample(int(n_each * 0.1), replace=True, random_state=SEED + 1),
                         g.sanctions.sample(int(n_each * 0.9), random_state=SEED + 1)])
    raw, pos = [], []
    for _, s in tp_src.iterrows():
        raw.append(g.true_positive(s)[0])
        pos.append(sid_to_idx[s["sanction_id"]])
    for _, s in hom_src.iterrows():
        raw.append(g.homonym(s))
        pos.append(-1)
    top = surnames.head(3000)
    for _ in range(n_each):
        raw.append(g.clean(top["name"].tolist(), top["prop100k"].tolist()))
        pos.append(-1)

    cands = [normalize_candidate(r) for r in raw]
    rarity = SurnameRarity(surnames)
    pairs, _ = build_pairs(cands, sanctions, Blocker(sanctions), rarity)
    pos = np.array(pos)
    pairs["label"] = (pairs["sanction_idx"].to_numpy() == pos[pairs["cand_idx"].to_numpy()]).astype(int)

    # Cap negatives per candidate so common surnames do not dominate.
    neg = pairs[pairs["label"] == 0].sample(frac=1.0, random_state=SEED)
    neg = neg.groupby("cand_idx").head(max_neg)
    found = set(zip(pairs.loc[pairs["label"] == 1, "cand_idx"], pairs.loc[pairs["label"] == 1, "sanction_idx"]))
    srecs = sanctions[["first", "middle", "last", "city", "state", "specialty", "npi"]].to_dict("records")
    missed = [{**pair_features(cands[ci], srecs[si], rarity), "cand_idx": ci, "sanction_idx": si, "label": 1}
              for ci, si in enumerate(pos) if si >= 0 and (ci, si) not in found]
    out = pd.concat([pairs[pairs["label"] == 1], neg, pd.DataFrame(missed)], ignore_index=True)
    logging.info("Training pairs: %d positives (%d outside blocks), %d negatives",
                 out["label"].sum(), len(missed), (out["label"] == 0).sum())
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with sqlite3.connect(DB_PATH) as con:
        sanctions = pd.read_sql("SELECT * FROM sanctions", con)
        data_version = con.execute("SELECT data_version FROM imports ORDER BY id DESC LIMIT 1").fetchone()[0]
    surnames = sources.load_surname_freq()
    pairs = training_pairs(sanctions, surnames)
    X, y, groups = pairs[FEATURES].to_numpy(float), pairs["label"].to_numpy(), pairs["cand_idx"].to_numpy()

    fit_idx, cal_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED).split(X, y, groups))
    lgbm = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=30,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.9, random_state=SEED,
                          monotone_constraints=[MONOTONE.get(f, 0) for f in FEATURES], verbose=-1)
    lgbm.fit(X[fit_idx], y[fit_idx])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(lgbm.predict_proba(X[cal_idx])[:, 1], y[cal_idx])

    logreg = make_pipeline(SimpleImputer(strategy="constant", fill_value=0, add_indicator=True),
                           StandardScaler(), LogisticRegression(max_iter=2000, random_state=SEED))
    logreg.fit(X[fit_idx], y[fit_idx])
    iso_lr = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso_lr.fit(logreg.predict_proba(X[cal_idx])[:, 1], y[cal_idx])

    thresholds = tune_thresholds(iso.predict(lgbm.predict_proba(X[cal_idx])[:, 1]), y[cal_idx])
    thresholds_lr = tune_thresholds(iso_lr.predict(logreg.predict_proba(X[cal_idx])[:, 1]), y[cal_idx])
    logging.info("Thresholds: %s (logreg %s)", thresholds, thresholds_lr)

    version = "lgbm-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    Bundle(lgbm, iso, version, thresholds).save(MODELS / "model.pkl")
    Bundle(logreg, iso_lr, version.replace("lgbm", "logreg"), thresholds_lr).save(MODELS / "logreg.pkl")
    (MODELS / "model_card.json").write_text(json.dumps({
        "model_version": version, "data_version": data_version, "features": FEATURES,
        "n_pairs": int(len(y)), "n_positive": int(y.sum()), "seed": SEED,
        "calibration": "isotonic on 25% held-out candidates",
        "thresholds": thresholds,
        "threshold_rule": "review = max F2 on held-out training pairs (capped at 0.40); "
                          "probable = calibrated probability 0.90",
        "monotone_constraints": MONOTONE,
    }, indent=2))
    logging.info("Saved %s", version)


if __name__ == "__main__":
    main()
