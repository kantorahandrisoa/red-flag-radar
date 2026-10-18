"""Shared filesystem locations."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SYNTH = DATA / "synthetic"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
DB_PATH = Path(os.environ.get("RADAR_DB", DATA / "radar.db"))

for p in (RAW, PROCESSED, SYNTH, MODELS, REPORTS):
    p.mkdir(parents=True, exist_ok=True)
