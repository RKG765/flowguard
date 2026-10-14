"""Fixtures for core API tests: an isolated data dir, a TestClient with the real app (migrations run at startup),
and one logged-in Bearer token per role."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))
from apihelpers import PASSWORDS, bearer, login  # noqa: E402

from core.config import load_settings  # noqa: E402
from core.main import create_app  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return load_settings(data_dir=str(tmp_path / "data"), start_receiver=False)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def tokens(client):
    r = client.post("/api/setup", json={"username": "admin", "password": PASSWORDS["admin"]})
    assert r.status_code == 201, r.text
    admin = login(client, "admin")
    for role in ("analyst", "viewer"):
        r = client.post("/api/users", json={"username": role, "password": PASSWORDS[role], "role": role}, headers=bearer(admin))
        assert r.status_code == 201, r.text
    return {"admin": admin, "analyst": login(client, "analyst"), "viewer": login(client, "viewer")}
