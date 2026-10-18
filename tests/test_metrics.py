import pandas as pd

from pipeline.evaluate import metrics
from pipeline.matcher import zone


def test_zones():
    assert zone(0.95) == "probable" and zone(0.5) == "review" and zone(0.1) == "cleared"


def test_candidate_level_metrics():
    truth = pd.DataFrame({"candidate_id": ["a", "b", "c", "d"], "sanction_id": ["S1", "S2", "", ""],
                          "kind": ["true_positive", "true_positive", "homonym", "clean"], "note": ""})
    res = pd.DataFrame({"candidate_id": ["a", "b", "c", "d"], "best_sanction": ["S1", "S9", "S3", ""],
                        "score": [0.95, 0.5, 0.92, 0.0], "zone": ["probable", "review", "probable", "cleared"]})
    m = metrics(res, truth)
    assert m["recall_alert"] == 0.5          # b points to the wrong record
    assert m["precision_probable"] == 0.5    # a right, c a homonym
    assert m["homonyms_probable"] == 1 and m["clean_alert"] == 0
