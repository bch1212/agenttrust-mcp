"""Fail-closed behavior when AGENTTRUST_ADMIN_KEY is missing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from db.keys import AdminKeyNotConfigured, get_admin_key, is_admin, seed_default_keys
from db.schema import init_db


def test_get_admin_key_missing(monkeypatch):
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    with pytest.raises(AdminKeyNotConfigured, match="AGENTTRUST_ADMIN_KEY is not set"):
        get_admin_key()


def test_get_admin_key_blank(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ADMIN_KEY", "   ")
    with pytest.raises(AdminKeyNotConfigured):
        get_admin_key()


def test_seed_refuses_without_admin_key_and_inserts_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    monkeypatch.setenv("AGENTTRUST_DEV_KEY", "dev-only")
    conn = init_db(str(tmp_path / "t.db"))
    try:
        with pytest.raises(AdminKeyNotConfigured):
            seed_default_keys(conn)
        count = conn.execute("SELECT COUNT(*) AS c FROM api_keys").fetchone()["c"]
        assert count == 0
    finally:
        conn.close()


def test_seed_does_not_invent_a_dev_key(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTTRUST_ADMIN_KEY", "configured-admin")
    monkeypatch.delenv("AGENTTRUST_DEV_KEY", raising=False)
    conn = init_db(str(tmp_path / "t.db"))
    try:
        seed_default_keys(conn)
        rows = conn.execute("SELECT key, tier FROM api_keys ORDER BY tier").fetchall()
        assert [(row["key"], row["tier"]) for row in rows] == [("configured-admin", "pro")]
    finally:
        conn.close()


def test_is_admin_fails_closed_even_for_pro_tier(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    conn = init_db(str(tmp_path / "t.db"))
    try:
        conn.execute(
            """
            INSERT INTO api_keys (key, tier, call_count, daily_limit, last_reset)
            VALUES ('some-pro-key', 'pro', 0, 100, 0)
            """
        )
        conn.commit()
        with pytest.raises(AdminKeyNotConfigured):
            is_admin(conn, "some-pro-key")
    finally:
        conn.close()


def test_startup_refuses_without_admin_key(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTTRUST_DB", str(tmp_path / "nostart.db"))
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    monkeypatch.setenv("AGENTTRUST_DEV_KEY", "dev-for-test")

    import server

    previous = server._DB_CONN
    server._DB_CONN = None
    try:
        with pytest.raises(AdminKeyNotConfigured):
            with TestClient(server.app):
                pass
    finally:
        current = server._DB_CONN
        if current is not None and current is not previous:
            current.close()
        server._DB_CONN = previous


def test_admin_action_fails_closed_when_env_removed(client, monkeypatch):
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    response = client.post(
        "/tools/verify_agent",
        headers={"X-API-Key": "test-admin-key"},
        json={"agent_id": "demo-new-001", "verification_type": "operator"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "admin_key_not_configured"
    assert "default" in body["detail"]
    assert "test-admin-key" not in response.text

    health = client.get("/health")
    assert health.status_code == 200


def test_admin_jsonrpc_fails_closed_when_env_removed(client, monkeypatch):
    monkeypatch.delenv("AGENTTRUST_ADMIN_KEY", raising=False)
    response = client.post(
        "/mcp",
        headers={"X-API-Key": "test-admin-key"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "resolve_dispute",
                "arguments": {"dispute_id": "missing", "outcome": "invalid"},
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["error"]["message"] == "admin_key_not_configured"
    assert payload["error"]["code"] == 503
