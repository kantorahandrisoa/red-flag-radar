PY ?= .venv/bin/python

.PHONY: setup data train eval test all api web test-csvs
setup:
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements.txt
data:
	$(PY) -m pipeline.build_data
train:
	$(PY) -m pipeline.train
eval:
	$(PY) -m pipeline.evaluate
test:
	$(PY) -m pytest -q
all: data train eval test
api:
	$(PY) -m uvicorn backend.app.main:app --reload --port 8000
web:
	cd frontend && npm run dev

test-csvs:
	$(PY) scripts/make_test_csvs.py
