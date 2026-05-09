"""End-to-end HTTP tests for the FastAPI surface and JSON-RPC MCP transport."""
from __future__ import annotations

import json


def _key(write: bool = True, admin: bool = False) -> dict:
    if admin:
        return {"X-API-Key": "test-admin-key"}
    if write:
        return {"X-API-Key": "test-dev-key"}
    return {}


def test_health_includes_seeded_agents(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["agents"] >= 5  # five demo agents seeded


def test_root_advertises_tools(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "register_agent" in body["tools"]
    assert "get_leaderboard" in body["tools"]
    assert body["pricing"]["pro"].startswith("$9")


def test_register_agent_then_profile(client):
    r = client.post(
        "/tools/register_agent",
        headers=_key(),
        json={
            "agent_id": "agent-alpha",
            "name": "Alpha",
            "description": "Alpha test agent",
            "capabilities": ["search", "rag"],
            "operator_url": "https://alpha.test",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_id"] == "agent-alpha"
    assert data["agent_token"].startswith("at_")
    assert data["tier"] == "NEW"

    r2 = client.post("/tools/get_agent_profile", json={"agent_id": "agent-alpha"})
    assert r2.status_code == 200
    profile = r2.json()
    assert profile["name"] == "Alpha"
    assert "search" in profile["capabilities"]
    assert profile["stats"]["total_transactions"] == 0


def test_register_requires_api_key(client):
    r = client.post(
        "/tools/register_agent",
        json={"agent_id": "no-key", "name": "X"},
    )
    assert r.status_code == 401


def test_read_tool_does_not_require_api_key(client):
    r = client.post("/tools/get_agent_profile", json={"agent_id": "demo-platinum-001"})
    assert r.status_code == 200
    body = r.json()
    # Score is recomputed live on every read, so the tier reflects current data,
    # not the seed value. We just assert auth-free access works and the tier is set.
    assert body["tier"] in {"PLATINUM", "GOLD", "SILVER", "BRONZE", "NEW"}
    assert body["verified"] is True


def test_record_transaction_updates_both_sides_and_score(client):
    # Register two fresh agents
    for aid in ("buyer", "seller"):
        client.post("/tools/register_agent", headers=_key(), json={"agent_id": aid, "name": aid})

    r = client.post(
        "/tools/record_transaction",
        headers=_key(),
        json={
            "from_agent": "buyer",
            "to_agent": "seller",
            "amount_usd": 50.0,
            "success": True,
            "description": "first deal",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tx_id"].startswith("tx_")
    assert "buyer" in body["updated_scores"] and "seller" in body["updated_scores"]

    profile = client.post("/tools/get_agent_profile", json={"agent_id": "seller"}).json()
    assert profile["stats"]["total_transactions"] == 1
    assert profile["stats"]["successful_transactions"] == 1
    assert profile["trust_score"] > 0


def test_endorsement_increases_score(client):
    for aid in ("e1", "e2"):
        client.post("/tools/register_agent", headers=_key(), json={"agent_id": aid, "name": aid})

    before = client.post("/tools/get_trust_score", json={"agent_id": "e2"}).json()["score"]
    r = client.post(
        "/tools/endorse_agent",
        headers=_key(),
        json={
            "endorser_id": "e1",
            "endorsed_id": "e2",
            "endorsement_type": "quality",
            "notes": "great work",
        },
    )
    assert r.status_code == 200
    after = client.post("/tools/get_trust_score", json={"agent_id": "e2"}).json()["score"]
    assert after >= before + 10


def test_self_endorsement_rejected(client):
    client.post("/tools/register_agent", headers=_key(), json={"agent_id": "solo", "name": "Solo"})
    r = client.post(
        "/tools/endorse_agent",
        headers=_key(),
        json={"endorser_id": "solo", "endorsed_id": "solo", "endorsement_type": "quality"},
    )
    assert r.status_code == 200
    assert r.json()["error"] == "self_endorsement_not_allowed"


def test_dispute_lifecycle_resolved_for_reporter(client):
    for aid in ("buyer2", "seller2"):
        client.post("/tools/register_agent", headers=_key(), json={"agent_id": aid, "name": aid})

    tx_id = client.post(
        "/tools/record_transaction",
        headers=_key(),
        json={
            "from_agent": "buyer2",
            "to_agent": "seller2",
            "amount_usd": 100.0,
            "success": True,
            "description": "scammed",
        },
    ).json()["tx_id"]

    dispute = client.post(
        "/tools/dispute_transaction",
        headers=_key(),
        json={
            "tx_id": tx_id,
            "reporter_id": "buyer2",
            "reason": "non-delivery",
            "evidence": "no payload received",
        },
    ).json()
    assert dispute["status"] == "open"

    # Non-admin cannot resolve.
    r_unauth = client.post(
        "/tools/resolve_dispute",
        headers=_key(write=True),
        json={"dispute_id": dispute["dispute_id"], "outcome": "reporter", "notes": "evidence checks out"},
    )
    assert r_unauth.status_code == 403

    # Admin resolves in reporter's favor → seller2 should be penalized.
    r = client.post(
        "/tools/resolve_dispute",
        headers=_key(admin=True),
        json={"dispute_id": dispute["dispute_id"], "outcome": "reporter", "notes": "evidence ok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved_for_reporter"

    seller_profile = client.post("/tools/get_agent_profile", json={"agent_id": "seller2"}).json()
    assert seller_profile["stats"]["dispute_count"] == 1


def test_search_agents_filters_by_capability_and_score(client):
    rows = client.post(
        "/tools/search_agents",
        json={"capabilities": ["payments"], "min_trust_score": 500, "verified_only": True, "limit": 5},
    ).json()
    assert rows["count"] >= 1
    assert all("payments" in r["capabilities"] for r in rows["results"])
    assert all(r["trust_score"] >= 500 for r in rows["results"])
    assert all(r["verified"] for r in rows["results"])


def test_leaderboard_orders_by_score(client):
    lb = client.post("/tools/get_leaderboard", json={"limit": 5}).json()
    leaders = lb["leaders"]
    assert len(leaders) >= 1
    scores = [a["trust_score"] for a in leaders]
    assert scores == sorted(scores, reverse=True)


def test_verify_agent_requires_admin_and_boosts_score(client):
    client.post("/tools/register_agent", headers=_key(), json={"agent_id": "verify-me", "name": "V"})

    r_unauth = client.post(
        "/tools/verify_agent",
        headers=_key(write=True),
        json={"agent_id": "verify-me", "verification_type": "operator"},
    )
    assert r_unauth.status_code == 403

    r = client.post(
        "/tools/verify_agent",
        headers=_key(admin=True),
        json={"agent_id": "verify-me", "verification_type": "operator"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["new_trust_score"] >= 100


def test_report_agent_creates_report(client):
    for aid in ("rpt-r", "rpt-d"):
        client.post("/tools/register_agent", headers=_key(), json={"agent_id": aid, "name": aid})
    r = client.post(
        "/tools/report_agent",
        headers=_key(),
        json={"reporter_id": "rpt-r", "reported_id": "rpt-d", "reason": "spam", "evidence": "logs"},
    )
    assert r.status_code == 200
    assert r.json()["report_id"].startswith("rpt_")


def test_rate_limit_returns_429_with_upgrade_url(client, fresh_db):
    # Drop the dev key's daily limit to 2 for fast exhaustion.
    db = fresh_db.get_db()
    db.execute("UPDATE api_keys SET daily_limit=2, call_count=0 WHERE key='test-dev-key'")
    db.commit()

    for i in range(2):
        r = client.post(
            "/tools/register_agent",
            headers=_key(),
            json={"agent_id": f"rate-{i}", "name": f"R{i}"},
        )
        assert r.status_code == 200, r.text

    r = client.post(
        "/tools/register_agent",
        headers=_key(),
        json={"agent_id": "rate-overflow", "name": "RO"},
    )
    assert r.status_code == 429
    body = r.json()
    assert "Upgrade at" in body["error"]
    assert body["upgrade_url"]


def test_mcp_jsonrpc_tools_list_and_call(client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert r.status_code == 200
    data = r.json()
    assert {t["name"] for t in data["result"]["tools"]} >= {
        "register_agent", "get_trust_score", "get_leaderboard"
    }

    r2 = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_leaderboard", "arguments": {"limit": 3}},
        },
    )
    assert r2.status_code == 200
    payload = r2.json()
    inner = json.loads(payload["result"]["content"][0]["text"])
    assert "leaders" in inner
    assert len(inner["leaders"]) <= 3


def test_dispute_requires_party_to_tx(client):
    for aid in ("a", "b", "outsider"):
        client.post("/tools/register_agent", headers=_key(), json={"agent_id": aid, "name": aid})
    tx_id = client.post(
        "/tools/record_transaction",
        headers=_key(),
        json={"from_agent": "a", "to_agent": "b", "amount_usd": 5.0, "success": True, "description": "x"},
    ).json()["tx_id"]

    r = client.post(
        "/tools/dispute_transaction",
        headers=_key(),
        json={"tx_id": tx_id, "reporter_id": "outsider", "reason": "I want in"},
    )
    assert r.status_code == 200
    assert r.json()["error"] == "reporter_not_party_to_tx"
