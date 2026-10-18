import math

import pandas as pd

from pipeline.features import Blocker, SurnameRarity, normalize_candidate, pair_features

RARITY = SurnameRarity(pd.DataFrame({"name": ["SMITH", "PETROLA"], "prop100k": [828.19, 0.5]}))


def rec(first, last, middle="", city="", state="", specialty="", npi=""):
    return {"first": first, "middle": middle, "last": last, "city": city, "state": state,
            "specialty": specialty, "npi": npi}


def test_exact_match_features():
    s = rec("JOHN", "SMITH", "A", "BOSTON", "MA", "CARDIOLOGY", "1234567890")
    f = pair_features(s, s, RARITY)
    assert f["sim_nom"] == 1 and f["sim_prenom"] == 1 and f["npi_egal"] == 1
    assert f["etat_egal"] == 1 and f["ville_egale"] == 1 and f["deuxieme_prenom"] == 1
    assert f["inversion"] == 0 and f["npi_manquant"] == 0


def test_missing_values_stay_missing():
    f = pair_features(rec("JOHN", "SMITH"), rec("JOHN", "SMITH"), RARITY)
    assert math.isnan(f["npi_egal"]) and f["npi_manquant"] == 1
    assert math.isnan(f["etat_egal"]) and math.isnan(f["deuxieme_prenom"])


def test_swapped_names_with_initial_and_typo():
    s = rec("JAMES", "PETROLA")
    assert pair_features(rec("PETROLA", "J"), s, RARITY)["inversion"] == 1
    assert pair_features(rec("PETROLA", "JRMES"), s, RARITY)["inversion"] == 1


def test_nickname_counts_as_same_first_name():
    assert pair_features(rec("BILL", "SMITH"), rec("WILLIAM", "SMITH"), RARITY)["sim_prenom"] == 1


def test_rarity_orders_common_and_rare_names():
    assert RARITY("SMITH") < RARITY("PETROLA") < RARITY("UNKNOWNNAME")


def test_blocker_finds_typos_and_swaps():
    sanctions = pd.DataFrame([rec("ROGELIO", "MABUNGA"), rec("JAMES", "PETROLA"), rec("ANN", "LEE")])
    b = Blocker(sanctions)
    assert 0 in b.candidates(normalize_candidate({"first_name": "Rogelio", "last_name": "Mabungv"}))
    assert 1 in b.candidates(normalize_candidate({"first_name": "Petrola", "last_name": "James"}))
    assert 2 not in b.candidates(normalize_candidate({"first_name": "Rogelio", "last_name": "Mabungv"}))
