import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="audienceos_test_")
os.environ["AUDIENCEOS_DATA"] = _tmp
os.environ["AUDIENCEOS_NO_KEYCHAIN"] = "1"

import pytest  # noqa: E402

from app import db, jobs  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    db.migrate()
    yield


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    monkeypatch.setattr(jobs, "start_worker", lambda: None)  # tests drive jobs synchronously
    with TestClient(main.app, headers={"x-audienceos": "1"}) as c:
        yield c


def drain():
    while jobs.run_one():
        pass
