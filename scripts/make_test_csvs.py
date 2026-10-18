"""Generate CSV files that exercise every upload path (`make test-csvs`).

Valid files carry two extra columns the API ignores: `expected` (what the
screening should say) and `case` (what the row tests). Expected values:
  probable      zone must be "probable"
  alert         zone must be "probable" or "review" (a person is asked to look)
  not_probable  zone must be "review" or "cleared" (never accused)
  cleared       zone must be "cleared"
  any           no expectation (genuinely ambiguous, shown for illustration)
Sanctioned people are real public records; every "innocent" is invented.
"""
import csv
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.features import NICKNAMES  # noqa: E402
from pipeline.paths import DB_PATH  # noqa: E402

OUT = ROOT / "data" / "test_csv"
COLS = ["candidate_id", "first_name", "middle_name", "last_name", "city", "state", "specialty", "npi",
        "expected", "case"]
PHYS = ["FAMILY_MEDICINE", "INTERNAL_MEDICINE", "PSYCHIATRY", "CARDIOLOGY", "OBGYN", "SURGERY",
        "ANESTHESIOLOGY"]
LABEL = {"FAMILY_MEDICINE": "Family Medicine", "INTERNAL_MEDICINE": "Internal Medicine",
         "PSYCHIATRY": "Psychiatry", "CARDIOLOGY": "Cardiology", "OBGYN": "Obstetrics & Gynecology",
         "SURGERY": "Surgery", "ANESTHESIOLOGY": "Anesthesiology"}
OTHER_STATE = {"CA": "VT", "NY": "NM", "FL": "ND", "TX": "ME"}
rng = random.Random(42)


def load():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM sanctions ORDER BY sanction_id")]
    leie = [r for r in rows if r["source"] == "OIG LEIE" and r["specialty"] in PHYS and r["middle"]
            and r["city"] and len(r["first"]) > 2 and len(r["last"]) > 4 and " " not in r["last"]]
    return ([r for r in leie if r["npi"]], [r for r in leie if not r["npi"]],
            [r for r in rows if r["source"] == "FDA Debarment List" and r["middle"] and " " not in r["last"]])


def t(s):
    return s.title()


def other_state(st):
    return OTHER_STATE.get(st, "WY" if st != "WY" else "VT")


def fake_npi():
    return "1" + "".join(rng.choice("0123456789") for _ in range(9))


def typo(word):
    i = len(word) - 2  # change a late letter: keeps the start of the name
    return word[:i] + ("E" if word[i] != "E" else "A") + word[i + 1:]


def row(cid, first, middle, last, city, state, spec, npi, expected, case):
    return dict(zip(COLS, [cid, first, middle, last, city, state, spec, npi, expected, case]))


def all_cases(with_npi, no_npi, fda):
    a, b, c, d, e, f, g, h, i, j, k = with_npi[:11]
    n1, n2, n3 = no_npi[:3]
    nick = next(r for r in with_npi[11:] if r["first"] in set(NICKNAMES.values()))
    short = next(k for k, v in NICKNAMES.items() if v == nick["first"])
    fd1, fd2 = fda[0], fda[1]
    rows = [
        row("T01", t(a["first"]), a["middle"][:1], t(a["last"]), t(a["city"]), a["state"], LABEL[a["specialty"]],
            a["npi"], "probable", "Exact copy of an OIG record, same NPI"),
        row("T02", t(n1["first"]), n1["middle"][:1], t(n1["last"]), t(n1["city"]), n1["state"],
            LABEL[n1["specialty"]], "", "alert", "Same name, middle initial, city, state, specialty; no NPI anywhere"),
        row("T03", t(b["first"]), "", t(typo(b["last"])), t(b["city"]), b["state"], LABEL[b["specialty"]], b["npi"],
            "alert", "Typo in the last name, same NPI"),
        row("T04", t(typo(c["first"])), c["middle"][:1], t(c["last"]), t(c["city"]), c["state"],
            LABEL[c["specialty"]], c["npi"], "alert", "Typo in the first name, same NPI"),
        row("T05", d["first"][0] + ".", "", t(d["last"]), t(d["city"]), d["state"], LABEL[d["specialty"]], d["npi"],
            "alert", "First name reduced to an initial"),
        row("T06", t(e["last"]), "", t(e["first"]), t(e["city"]), e["state"], LABEL[e["specialty"]], e["npi"],
            "alert", "First and last names swapped"),
        row("T07", t(short), "", t(nick["last"]), t(nick["city"]), nick["state"], LABEL[nick["specialty"]],
            nick["npi"], "alert", f"Nickname ({t(short)} for {t(nick['first'])})"),
        row("T08", t(f["first"]), "", f"{t(f['last'])}-Garcia", t(f["city"]), f["state"], LABEL[f["specialty"]],
            f["npi"], "alert", "Compound surname (married name added)"),
        row("T09", f"Dr. {t(g['first'])}", "", f"{t(g['last'])}, M.D. Jr.", t(g["city"]), g["state"],
            LABEL[g["specialty"]], g["npi"], "alert", "Title and suffixes around the name"),
        row("T10", h["first"].lower(), "", h["last"].lower().replace("E", "É").replace("e", "é"), h["city"].lower(),
            h["state"].lower(), LABEL[h["specialty"]].lower(), h["npi"], "alert", "Lowercase and accents"),
        row("T11", t(n2["first"]), "", t(n2["last"]), "Burlington", other_state(n2["state"]), LABEL[n2["specialty"]],
            "", "any", "Same name, moved to another state, no NPI: ambiguous by nature"),
        row("T12", t(fd1["first"]), fd1["middle"][:1], t(fd1["last"]), "Boston", "MA", "Internal Medicine",
            fake_npi(), "alert", "FDA debarment record (names only), same full name and middle initial"),
        row("T13", t(i["first"]), chr(((ord(i["middle"][0]) - 65 + 7) % 26) + 65), t(i["last"]), "Burlington",
            other_state(i["state"]), LABEL[next(p for p in PHYS if p != i["specialty"])], fake_npi(),
            "not_probable", "Innocent namesake: other middle initial, state, specialty and NPI"),
        row("T14", t(j["first"]), "", t(j["last"]), t(j["city"]), j["state"], LABEL[j["specialty"]], fake_npi(),
            "not_probable", "Same name and place but a different NPI"),
        row("T15", "John", "Q", "Smith", "Anchorage", "AK", "Dermatology", fake_npi(), "not_probable",
            "Very common name, no specific evidence"),
        row("T16", "Zephyrine", "", "Quarterbridge", "Helena", "MT", "Neurology", fake_npi(), "cleared",
            "Invented name, nothing similar on any list"),
        row("T17", t(fd2["first"]), "", t(fd2["last"]), "Austin", "TX", "Oncology", "", "alert",
            "FDA record, first and last name only"),
        row("T18", t(n3["first"]), n3["middle"][:1], t(n3["last"]), t(n3["city"]), n3["state"], "", "",
            "alert", "Same name, middle initial and city; specialty and NPI not provided"),
        row("T19", t(k["first"]), k["middle"][:1], t(k["last"]), "", "", "", k["npi"], "probable",
            "Only the name and the NPI are given; NPI matches"),
    ]
    return rows, [a, b, d]


def write(name, rows, cols=COLS, encoding="utf-8", bom=False):
    path = OUT / name
    with open(path, "w", newline="", encoding="utf-8-sig" if bom else encoding) as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with_npi, no_npi, fda = load()
    cases, (a, b, d) = all_cases(with_npi, no_npi, fda)
    manifest = {}

    write("01_all_cases.csv", cases)
    manifest["01_all_cases.csv"] = {"status": 200, "rows": len(cases), "check_rows": True}

    full = [{"candidate_id": "F01", "full_name": f"{t(a['last'])}, {t(a['first'])} {a['middle'][:1]}",
             "state": a["state"], "npi": a["npi"], "expected": "probable", "case": "full_name as 'Last, First M'"},
            {"candidate_id": "F02", "full_name": f"Dr {t(b['first'])} {t(b['last'])} MD", "state": b["state"],
             "npi": b["npi"], "expected": "alert", "case": "full_name as 'Dr First Last MD'"},
            {"candidate_id": "F03", "full_name": "Zephyrine Quarterbridge", "state": "MT", "npi": "",
             "expected": "cleared", "case": "full_name, invented person"}]
    write("02_full_name_only.csv", full, ["candidate_id", "full_name", "state", "npi", "expected", "case"])
    manifest["02_full_name_only.csv"] = {"status": 200, "rows": 3, "check_rows": True}

    write("03_names_only.csv", [dict(r) for r in cases if r["candidate_id"] in ("T05", "T06", "T16")],
          ["candidate_id", "first_name", "last_name", "expected", "case"])
    manifest["03_names_only.csv"] = {"status": 200, "rows": 3, "check_rows": False,
                                     "note": "Only names: scores are lower, nothing to confirm identity"}

    # Headers in another order, other case, with spaces, plus unknown columns.
    path = OUT / "04_messy_headers.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Site ID", "NPI", "Last Name", "First Name", "State", "Notes", "candidate_id"])
        w.writerow(["S-17", a["npi"], t(a["last"]), t(a["first"]), a["state"], "PI since 2019", "H01"])
        w.writerow(["S-18", "", "Quarterbridge", "Zephyrine", "MT", "", "H02"])
    manifest["04_messy_headers.csv"] = {"status": 200, "rows": 2, "check_rows": False,
                                        "note": "Header case/spaces normalized; unknown columns ignored"}

    write("05_utf8_bom_accents.csv", [dict(cases[9]), row("B02", "José", "", "Muñoz-Peña", "San Juan", "PR",
                                                          "Pediatrics", "", "any", "Accents in an invented name")],
          bom=True)
    manifest["05_utf8_bom_accents.csv"] = {"status": 200, "rows": 2, "check_rows": False}

    blanks = [row("M01", t(d["first"]), "", t(d["last"]), "", "", "", "", "alert", "Names only, everything else blank"),
              row("M02", "", "", t(d["last"]), "", d["state"], "", "", "any", "Missing first name"),
              row("M03", t(d["first"]), "", "", "", "", "", "", "cleared", "Missing last name"),
              row("", "Zephyrine", "", "Quarterbridge", "", "", "", "", "cleared", "Missing candidate_id (ROW-xxxx given)")]
    write("06_missing_values.csv", blanks)
    manifest["06_missing_values.csv"] = {"status": 200, "rows": 4, "check_rows": False}

    npis = [row("N01", t(a["first"]), "", t(a["last"]), "", "", "", a["npi"], "probable", "NPI matches"),
            row("N02", t(a["first"]), "", t(a["last"]), "", "", "", f"{a['npi'][:3]}-{a['npi'][3:6]}-{a['npi'][6:]}",
                "probable", "Same NPI written with dashes"),
            row("N03", t(a["first"]), "", t(a["last"]), "", "", "", "123", "any", "Invalid NPI (too short), ignored"),
            row("N04", t(a["first"]), "", t(a["last"]), "", "", "", "0000000000", "any", "Placeholder NPI, ignored"),
            row("N05", t(a["first"]), "", t(a["last"]), "", "", "", fake_npi(), "not_probable", "A different valid NPI")]
    write("07_npi_formats.csv", npis)
    manifest["07_npi_formats.csv"] = {"status": 200, "rows": 5, "check_rows": True}

    tricky = [row("Q01", "Mary-Kate", "", "O'Brien", "St. Louis", "MO", "Internal Medicine, Hospitalist", "",
                  "cleared", "Apostrophe, hyphen, comma inside a quoted field"),
              row("Q02", "Ana", "", "de la Cruz", "Coeur d'Alene", "ID", "Cardiology", "", "any",
                  "Particle surname, apostrophe in city"),
              row("Q03", "  John  ", "", "  Doe  ", " Reno ", " nv ", "", "", "any", "Leading/trailing spaces")]
    write("08_quotes_and_punctuation.csv", tricky)
    manifest["08_quotes_and_punctuation.csv"] = {"status": 200, "rows": 3, "check_rows": False}

    inject = [row("X01", "=HYPERLINK(\"http://evil.example\",\"click\")", "", "Smith", "", "", "", "", "any",
                  "Formula in a name: exported with a leading quote"),
              row("X02", "+1+1", "", "-Doe", "", "", "@SUM(A1)", "", "any", "Cells starting with + - @")]
    write("09_csv_injection.csv", inject)
    manifest["09_csv_injection.csv"] = {"status": 200, "rows": 2, "check_rows": False, "check_export_safe": True}

    big = []
    for n in range(5000):
        r = dict(cases[n % len(cases)])
        r["candidate_id"] = f"L{n + 1:05d}"
        big.append(r)
    write("10_limit_5000_rows.csv", big)
    manifest["10_limit_5000_rows.csv"] = {"status": 200, "rows": 5000, "check_rows": False, "max_seconds": 60}

    # --- files that must be refused --------------------------------------
    write("err_01_no_name_columns.csv", [{"city": "Boston", "state": "MA"}], ["city", "state"])
    manifest["err_01_no_name_columns.csv"] = {"status": 422, "detail": "first_name and last_name"}
    write("err_02_header_only.csv", [], COLS)
    manifest["err_02_header_only.csv"] = {"status": 422, "detail": "no rows"}
    write("err_03_too_many_rows.csv", big + [dict(big[0], candidate_id="L05001")])
    manifest["err_03_too_many_rows.csv"] = {"status": 422, "detail": "Too many rows"}
    write("err_04_latin1_encoding.csv", [row("E01", "José", "", "Muñoz", "", "", "", "", "any", "")],
          encoding="latin-1")
    manifest["err_04_latin1_encoding.csv"] = {"status": 422, "detail": "UTF-8"}
    (OUT / "err_05_not_a_csv.csv").write_bytes(bytes(range(256)) * 8)
    manifest["err_05_not_a_csv.csv"] = {"status": 422}
    (OUT / "err_06_empty_file.csv").write_bytes(b"")
    manifest["err_06_empty_file.csv"] = {"status": 422}
    # Over 2 MB: generated on demand, not committed (see .gitignore).
    with open(OUT / "err_07_too_large.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write("first_name,last_name,notes\n")
        while fh.tell() < 2_200_000:
            fh.write("John,Smith," + "x" * 200 + "\n")
    manifest["err_07_too_large.csv"] = {"status": 413}

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(manifest)} files to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
