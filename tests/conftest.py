"""Shared fixture: the API running on a throwaway copy of the database."""
import importlib
import shutil

import pytest
from fastapi.testclient import TestClient

from pipeline.paths import DATA


@pytest.fixture(scope="session")
def client(tmp_path_factory, monkeypatch_module):
    db = tmp_path_factory.mktemp("db") / "radar.db"
    shutil.copy(DATA / "radar.db", db)
    monkeypatch_module.setenv("RADAR_DB", str(db))
    import pipeline.paths
    import backend.app.db
    import backend.app.main
    for m in (pipeline.paths, backend.app.db, backend.app.main):
        importlib.reload(m)
    with TestClient(backend.app.main.app) as c:
        yield c


@pytest.fixture(scope="session")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


