# API: FastAPI + model. Sanction lists come from the dated snapshots in data/raw.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline pipeline
COPY backend backend
COPY models models
COPY reports reports
COPY data/raw data/raw
COPY data/synthetic data/synthetic
COPY deploy/entrypoint.sh /entrypoint.sh
ENV RADAR_DB=/data/radar.db RADAR_OFFLINE=1 PYTHONUNBUFFERED=1
RUN useradd -m radar && mkdir -p /data && chown -R radar /data /app/data
USER radar
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
