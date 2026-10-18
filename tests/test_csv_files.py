"""Every file in data/test_csv behaves as its manifest says (see scripts/make_test_csvs.py)."""
import pytest

from scripts.check_test_csvs import FILES, check


@pytest.mark.skipif(not (FILES / "manifest.json").exists(), reason="run `make test-csvs` first")
def test_all_test_csv_files(client):
    failures = [f"{r['file']}: {p}" for r in check(client) for p in r["problems"]]
    assert not failures, "\n".join(failures)
