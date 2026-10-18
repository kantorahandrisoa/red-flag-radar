"""`make eval`: score the 300-candidate test set against its ground truth (F14).

Candidate-level metrics, since that is what a reviewer sees:
- an alert is a candidate whose best match scores >= 0.40 ("probable" or "review");
- recall = sanctioned candidates alerted with the right sanction record;
- precision = "probable" candidates whose best match is the right record.
"""
import json
import logging
import sqlite3
import time

import matplotlib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve

from . import sources, synth
from .features import exact_name_match, normalize_candidate
from .matcher import Bundle, Matcher
from .paths import DB_PATH, MODELS, REPORTS, SYNTH

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def best_matches(matcher: Matcher, cands: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    t0 = time.perf_counter()
    pairs = matcher.score(cands.to_dict("records"), min_prob=0.0)
    elapsed = time.perf_counter() - t0
    best = pairs.drop_duplicates("cand_idx").set_index("cand_idx")
    out = cands[["candidate_id"]].copy()
    out["best_sanction"] = best["sanction_id"].reindex(range(len(cands))).fillna("").to_numpy()
    out["score"] = best["prob"].reindex(range(len(cands))).fillna(0.0).to_numpy()
    out["zone"] = out["score"].map(matcher.bundle.zone)
    return out, elapsed


def baseline(sanctions: pd.DataFrame, cands: pd.DataFrame) -> pd.DataFrame:
    """Naive screening: flag only an exact normalized first + last name match."""
    by_name = {}
    for sid, f, l in zip(sanctions["sanction_id"], sanctions["first"], sanctions["last"]):
        by_name.setdefault((f, l), sid)
    rows = []
    for r in cands.to_dict("records"):
        c = normalize_candidate(r)
        sid = by_name.get((c["first"], c["last"]), "")
        rows.append({"candidate_id": r["candidate_id"], "best_sanction": sid,
                     "score": 1.0 if sid else 0.0, "zone": "probable" if sid else "cleared"})
    return pd.DataFrame(rows)


def same_person_ids(sanctions: pd.DataFrame) -> dict[str, set[str]]:
    """A person excluded twice has two records; matching either one is correct."""
    key = sanctions["first"] + "|" + sanctions["middle"] + "|" + sanctions["last"] + "|" + sanctions["state"]
    groups = sanctions.groupby(key)["sanction_id"].apply(set)
    return {sid: groups[k] for sid, k in zip(sanctions["sanction_id"], key)}


SAME_PERSON: dict[str, set[str]] = {}


def is_correct(best: str, truth_id: str) -> bool:
    return bool(truth_id) and (best == truth_id or best in SAME_PERSON.get(truth_id, ()))


def metrics(res: pd.DataFrame, truth: pd.DataFrame) -> dict:
    d = res.merge(truth, on="candidate_id")
    is_tp = d["kind"] == "true_positive"
    correct = is_tp & pd.Series([is_correct(b, t) for b, t in zip(d["best_sanction"], d["sanction_id"])],
                                index=d.index)
    alert = d["zone"] != "cleared"
    probable = d["zone"] == "probable"
    tp_alert = int((correct & alert).sum())
    tp_prob = int((correct & probable).sum())
    n_pos = int(is_tp.sum())
    return {
        "recall_alert": round(tp_alert / n_pos, 4),
        "recall_probable": round(tp_prob / n_pos, 4),
        "precision_probable": round(tp_prob / max(int(probable.sum()), 1), 4),
        "precision_alert": round(tp_alert / max(int(alert.sum()), 1), 4),
        "f1_alert": round(2 * tp_alert / (n_pos + int(alert.sum())), 4),
        "homonyms_probable": int((probable & (d["kind"] == "homonym")).sum()),
        "homonyms_alert": int((alert & (d["kind"] == "homonym")).sum()),
        "clean_alert": int((alert & (d["kind"] == "clean")).sum()),
        "zones": {z: int((d["zone"] == z).sum()) for z in ("probable", "review", "cleared")},
        "missed": d.loc[is_tp & ~(correct & alert), ["candidate_id", "sanction_id", "note", "score"]]
                   .to_dict("records"),
    }


def confusion(res: pd.DataFrame, truth: pd.DataFrame) -> dict:
    d = res.merge(truth, on="candidate_id")
    return {kind: {z: int(((d["kind"] == kind) & (d["zone"] == z)).sum()) for z in ("probable", "review", "cleared")}
            for kind in ("true_positive", "homonym", "clean")}


def pr_curve(res: pd.DataFrame, truth: pd.DataFrame) -> dict:
    d = res.merge(truth, on="candidate_id")
    y = pd.Series([is_correct(b, t) for b, t in zip(d["best_sanction"], d["sanction_id"])]).astype(int)
    p, r, t = precision_recall_curve(y, d["score"])
    keep = np.unique(np.linspace(0, len(t) - 1, min(len(t), 60)).astype(int))
    return {"ap": round(float(average_precision_score(y, d["score"])), 4),
            "points": [{"recall": round(float(r[i]), 4), "precision": round(float(p[i]), 4),
                        "threshold": round(float(t[i]), 4)} for i in keep]}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with sqlite3.connect(DB_PATH) as con:
        sanctions = pd.read_sql("SELECT * FROM sanctions", con)
    SAME_PERSON.update(same_person_ids(sanctions))
    surnames = sources.load_surname_freq()
    cands = pd.read_csv(SYNTH / "candidates_demo.csv", dtype=str, keep_default_na=False)
    truth = pd.read_csv(SYNTH / "ground_truth.csv", dtype=str, keep_default_na=False)

    report = {"thresholds": Bundle.load(MODELS / "model.pkl").thresholds, "n_candidates": len(cands),
              "truth": truth["kind"].value_counts().to_dict(), "models": {}}
    curves = {}
    for name, path in (("LightGBM (calibrated)", "model.pkl"), ("Logistic regression", "logreg.pkl")):
        bundle = Bundle.load(MODELS / path)
        matcher = Matcher(bundle, sanctions, surnames)
        res, secs = best_matches(matcher, cands)
        m = metrics(res, truth)
        m["seconds_for_300"] = round(secs, 2)
        m["model_version"] = bundle.version
        m["confusion"] = confusion(res, truth)
        curves[name] = pr_curve(res, truth)
        m["average_precision"] = curves[name]["ap"]
        report["models"][name] = m
        logging.info("%s: %s", name, {k: v for k, v in m.items() if k not in ("missed", "confusion")})
    base = baseline(sanctions, cands)
    report["models"]["Exact name baseline"] = {**metrics(base, truth), "confusion": confusion(base, truth)}
    report["pr_curve"] = curves["LightGBM (calibrated)"]["points"]
    report["pr_curves"] = curves
    logging.info("Baseline: %s", {k: v for k, v in report["models"]["Exact name baseline"].items()
                                  if k not in ("missed", "confusion")})

    # Fresh test sets never inspected while building the rules: checks the numbers above are not tuned.
    lgbm = Matcher(Bundle.load(MODELS / "model.pkl"), sanctions, surnames)
    report["robustness"] = []
    for seed in (2027, 2028, 2029):
        c2, t2, _ = synth.make_test_set(sanctions, surnames, seed=seed)
        m2 = metrics(best_matches(lgbm, c2)[0], t2)
        report["robustness"].append({"seed": seed, **{k: m2[k] for k in (
            "recall_alert", "precision_probable", "homonyms_probable", "homonyms_alert", "clean_alert")}})
    logging.info("Robustness: %s", report["robustness"])

    (REPORTS / "eval.json").write_text(json.dumps(report, indent=2))
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for name, c in curves.items():
        ax.plot([q["recall"] for q in c["points"]], [q["precision"] for q in c["points"]],
                label=f"{name} (AP {c['ap']:.2f})")
    b = report["models"]["Exact name baseline"]
    ax.scatter([b["recall_probable"]], [b["precision_probable"]], color="black", zorder=3,
               label="Exact name baseline")
    ax.set_xlabel("Recall (sanctioned investigators found)")
    ax.set_ylabel("Precision")
    ax.set_ylim(0, 1.05)
    ax.set_title("Red Flag Radar — 300 synthetic investigators")
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(REPORTS / "pr_curve.png", dpi=150)
    logging.info("Missed: %s", report["models"]["LightGBM (calibrated)"]["missed"])
    logging.info("Confusion: %s", report["models"]["LightGBM (calibrated)"]["confusion"])


if __name__ == "__main__":
    main()
