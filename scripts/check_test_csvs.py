"""Upload every file in data/test_csv and check the API's answer against the manifest.

    python scripts/check_test_csvs.py [--base-url http://localhost]

Note: each upload creates a screening on the target server; reset the demo
data afterwards if you run it against the live site.
"""
import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "data" / "test_csv"
ACCEPT = {
    "probable": {"probable"},
    "alert": {"probable", "review"},
    "not_probable": {"review", "cleared"},
    "cleared": {"cleared"},
    "any": {"probable", "review", "cleared"},
}


class HttpClient:
    """requests with a base URL, shaped like FastAPI's TestClient."""

    def __init__(self, base: str):
        import requests
        self.base, self.s = base.rstrip("/"), requests.Session()

    def post(self, path, **kw):
        return self.s.post(self.base + path, timeout=120, **kw)

    def get(self, path, **kw):
        return self.s.get(self.base + path, timeout=120, **kw)


def expectations(path: Path) -> dict[str, tuple[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["candidate_id"]: (r.get("expected", "any"), r.get("case", ""))
                for r in csv.DictReader(fh) if r.get("candidate_id")}


def check(client, files_dir: Path = FILES) -> list[dict]:
    manifest = json.loads((files_dir / "manifest.json").read_text())
    results = []
    for name, exp in manifest.items():
        path = files_dir / name
        t0 = time.perf_counter()
        r = client.post("/api/screenings", files={"file": (name, path.read_bytes(), "text/csv")},
                        data={"name": f"test: {name}", "user": "csv-check"})
        secs = time.perf_counter() - t0
        problems = []
        if r.status_code != exp["status"]:
            problems.append(f"HTTP {r.status_code}, expected {exp['status']}: {r.text[:120]}")
        elif r.status_code != 200:
            if exp.get("detail") and exp["detail"].lower() not in r.json().get("detail", "").lower():
                problems.append(f"message '{r.json().get('detail')}' lacks '{exp['detail']}'")
        else:
            s = r.json()
            if s["n_candidates"] != exp["rows"]:
                problems.append(f"{s['n_candidates']} rows, expected {exp['rows']}")
            if exp.get("max_seconds") and secs > exp["max_seconds"]:
                problems.append(f"took {secs:.1f}s > {exp['max_seconds']}s")
            if exp.get("check_rows"):
                detail = client.get(f"/api/screenings/{s['id']}").json()
                want = expectations(path)
                for c in detail["candidates"]:
                    expected, case = want.get(c["candidate_id"], ("any", ""))
                    if c["zone"] not in ACCEPT[expected]:
                        problems.append(f"{c['candidate_id']} ({case}): zone {c['zone']} "
                                        f"score {c['score']:.2f}, expected {expected}")
            if exp.get("check_export_safe"):
                text = client.get(f"/api/screenings/{s['id']}/export.csv").text
                for row in csv.reader(io.StringIO(text)):
                    if any(cell and cell[0] in "=+-@" for cell in row):
                        problems.append(f"unsafe cell exported: {row}")
        results.append({"file": name, "status": r.status_code, "seconds": round(secs, 2), "problems": problems})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost")
    args = ap.parse_args()
    results = check(HttpClient(args.base_url))
    for res in results:
        mark = "OK  " if not res["problems"] else "FAIL"
        print(f"{mark} {res['file']:<34} HTTP {res['status']}  {res['seconds']:>6.2f}s")
        for p in res["problems"]:
            print(f"       - {p}")
    failed = sum(bool(r["problems"]) for r in results)
    print(f"\n{len(results) - failed}/{len(results)} files behave as expected")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
