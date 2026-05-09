"""Agent registration, profiles, search, verification."""
from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Dict, List

from db import queries
from .trust import compute_trust_score, get_tier, recompute_and_persist


def register_agent(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    name: str,
    description: str,
    capabilities: List[str] | None,
    operator_url: str,
) -> Dict[str, Any]:
    if not agent_id or not name:
        return {"error": "agent_id_and_name_required"}
    if queries.get_agent(conn, agent_id):
        return {"error": "agent_already_exists", "agent_id": agent_id}
    token = f"at_{secrets.token_urlsafe(24)}"
    queries.insert_agent(
        conn,
        agent_id=agent_id,
        name=name,
        description=description or "",
        capabilities=capabilities or [],
        operator_url=operator_url or "",
        agent_token=token,
    )
    return {"agent_id": agent_id, "agent_token": token, "tier": "NEW", "trust_score": 0}


def get_agent_profile(conn: sqlite3.Connection, agent_id: str) -> Dict[str, Any]:
    row = queries.get_agent(conn, agent_id)
    if not row:
        return {"error": "agent_not_found", "agent_id": agent_id}
    score = compute_trust_score(agent_id, conn)
    return {
        "agent_id": row["agent_id"],
        "name": row["name"],
        "description": row["description"],
        "capabilities": json.loads(row["capabilities"] or "[]"),
        "operator_url": row["operator_url"],
        "created_at": row["created_at"],
        "last_active": row["last_active"],
        "trust_score": score,
        "tier": get_tier(score),
        "stats": {
            "total_transactions": int(row["total_transactions"] or 0),
            "successful_transactions": int(row["successful_transactions"] or 0),
            "total_volume_usd": float(row["total_volume_usd"] or 0.0),
            "dispute_count": int(row["dispute_count"] or 0),
        },
        "verified": bool(row["verified"]),
    }


def search_agents(
    conn: sqlite3.Connection,
    *,
    capabilities: List[str] | None = None,
    min_trust_score: int = 0,
    verified_only: bool = False,
    limit: int = 25,
) -> Dict[str, Any]:
    rows = queries.search_agents(
        conn,
        capabilities=capabilities,
        min_trust_score=min_trust_score,
        verified_only=verified_only,
        limit=limit,
    )
    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append(
            {
                "agent_id": r["agent_id"],
                "name": r["name"],
                "description": r["description"],
                "tier": r["tier"],
                "trust_score": int(r["trust_score"] or 0),
                "verified": bool(r["verified"]),
                "capabilities": json.loads(r["capabilities"] or "[]"),
            }
        )
    return {"count": len(results), "results": results}


def verify_agent(
    conn: sqlite3.Connection, *, agent_id: str, verification_type: str
) -> Dict[str, Any]:
    if not queries.get_agent(conn, agent_id):
        return {"error": "agent_not_found", "agent_id": agent_id}
    queries.update_agent_verified(conn, agent_id, 1)
    new_score = recompute_and_persist(agent_id, conn)
    return {
        "agent_id": agent_id,
        "verified": True,
        "verification_type": verification_type,
        "new_trust_score": new_score,
        "new_tier": get_tier(new_score),
    }
