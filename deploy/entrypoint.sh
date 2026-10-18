#!/bin/sh
set -e
# First start: build the sanction database from the committed snapshots.
if [ ! -f "$RADAR_DB" ]; then
  python -m pipeline.build_data
fi
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
