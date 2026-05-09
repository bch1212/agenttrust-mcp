"""Shared fixtures: temp DB per test, FastAPI TestClient with the singleton reset."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# Ensure project root is importable when running pytest from anywhere.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture()
def fresh_db(monkeypatch):
    fd, path = tempfile.mkstemp(prefix="agenttrust_test_", suffix=".db")
    os.close(fd)
    monkeypatch.setenv("AGENTTRUST_DB", path)
    monkeypatch.setenv("AGENTTRUST_DEV_KEY", "test-dev-key")
    monkeypatch.setenv("AGENTTRUST_ADMIN_KEY", "test-admin-key")

    import server  # noqa: WPS433
    server.reset_db_for_tests(path)
    yield server
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient
    return TestClient(fresh_db.app)


@pytest.fixture()
def conn(fresh_db):
    return fresh_db.get_db()
