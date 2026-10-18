"""`make data`: import the sanction lists into SQLite and build the synthetic test set."""
import logging
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from . import sources, synth
from .paths import DB_PATH, SYNTH


def write_sanctions(con: sqlite3.Connection, sanctions: pd.DataFrame, versions: list[str]) -> None:
    sanctions.to_sql("sanctions", con, if_exists="replace", index=False)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_sanction_id ON sanctions(sanction_id)")
    con.execute("""CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY, imported_at TEXT, data_version TEXT, n_records INTEGER, detail TEXT)""")
    con.execute(
        "INSERT INTO imports (imported_at, data_version, n_records, detail) VALUES (?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), "+".join(versions),
         len(sanctions), sanctions.groupby("source").size().to_json()),
    )
    con.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    leie, fda = sources.load_leie(), sources.load_fda()
    surnames = sources.load_surname_freq()
    sanctions = pd.concat([leie, fda], ignore_index=True)
    versions = sorted(sanctions["import_version"].unique())
    with sqlite3.connect(DB_PATH) as con:
        write_sanctions(con, sanctions, versions)
    logging.info("Sanctions: %s", sanctions.groupby("source").size().to_dict())

    cands, truth, later = synth.make_test_set(sanctions, surnames)
    cands.to_csv(SYNTH / "candidates_demo.csv", index=False)
    truth.to_csv(SYNTH / "ground_truth.csv", index=False)
    later.to_csv(SYNTH / "later_sanction_demo.csv", index=False)
    logging.info("Test set: %s", truth["kind"].value_counts().to_dict())


if __name__ == "__main__":
    main()
