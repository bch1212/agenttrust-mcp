"""Trust score computation, tier mapping, leaderboard."""
from __future__ import annotations

import json
import math
import sqlite3
import time
from typing import Any, Dict, List

from db import queries


# ---------- pure scoring ----------

def get_tier(score: int) -> str:
    if score >= 800:
        return "PLATINUM"
    if score >= 550:
        return "GOLD"
    if score >= 300:
        return "SILVER"
    if score >= 100:
        return "BRONZE"
    return "NEW"


def compute_trust_score(agent_id: str, conn: sqlite3.Connection) -> int:
    agent = conn.execute(
        "SELECT * FROM agents WHERE agent_id=?", (agent_id,)
    ).fetchone()
    if not agent:
        return 0

    score = 0

    # Volume: log10 scale → 1 tx≈12, 10≈40, 100≈80, 1000≈120, capped 200
    vol = int(agent["total_transactions"] or 0)
    score += min(200, int(40 * math.log10(vol + 1)))

    # Success rate (0–400) — most important factor
    if vol > 0:
        rate = int(agent["successful_transactions"] or 0) / vol
        score += int(400 * rate)

    # Age bonus (0–100) — capped at 1 year
    age_days = (time.time() - float(agent["created_at"] or time.time())) / 86400
    score += min(100, int(age_days / 3.65))

    # Endorsements (0–200) — 10 pts each, capped 200
    endorsements = queries.count_endorsements(conn, agent_id)
    score += min(200, endorsements * 10)

    # Disputes — −30 each, no floor
    score -= int(agent["dispute_count"] or 0) * 30

    # Verification — +100
    if int(agent["verified"] or 0):
        score += 100

    return max(0, min(1000, score))


def score_breakdown(agent_id: str, conn: sqlite3.Connection) -> Dict[str, int]:
    agent = conn.execute(
        "SELECT * FROM agents WHERE agent_id=?", (agent_id,)
    ).fetchone()
    if not agent:
        return {
            "volume": 0,
            "success_rate": 0,
            "age": 0,
            "endorsements": 0,
            "disputes": 0,
            "verification": 0,
            "total": 0,
        }

    vol = int(agent["total_transactions"] or 0)
    volume_pts = min(200, int(40 * math.log10(vol + 1)))
    rate_pts = int(400 * (int(agent["successful_transactions"] or 0) / vol)) if vol else 0
    age_days = (time.time() - float(agent["created_at"] or time.time())) / 86400
    age_pts = min(100, int(age_days / 3.65))
    endorsements = queries.count_endorsements(conn, agent_id)
    endorse_pts = min(200, endorsements * 10)
    dispute_pts = -int(agent["dispute_count"] or 0) * 30
    verify_pts = 100 if int(agent["verified"] or 0) else 0
    total = max(0, min(1000, volume_pts + rate_pts + age_pts + endorse_pts + dispute_pts + verify_pts))

    return {
        "volume": volume_pts,
        "success_rate": rate_pts,
        "age": age_pts,
        "endorsements": endorse_pts,
        "disputes": dispute_pts,
        "verification": verify_pts,
        "total": total,
    }


# ---------- side-effect helpers ----------

def recompute_and_persist(agent_id: str, conn: sqlite3.Connection) -> int:
    score = compute_trust_score(agent_id, conn)
    tier = get_tier(score)
    queries.update_agent_score(conn, agent_id, score, tier)
    return score


# ---------- MCP-facing handlers ----------

def get_trust_score(conn: sqlite3.Connection, agent_id: str) -> Dict[str, Any]:
    agent = queries.get_agent(conn, agent_id)
    if not agent:
        return {"error": "agent_not_found", "agent_id": agent_id}
    score = compute_trust_score(agent_id, conn)
    breakdown = score_breakdown(agent_id, conn)
    return {
        "agent_id": agent_id,
        "score": score,
        "tier": get_tier(score),
        "breakdown": breakdown,
    }


def get_leaderboard(conn: sqlite3.Connection, *, category: str = None, limit: int = 10) -> Dict[str, Any]:
    rows = queries.leaderboard(conn, category=category, limit=limit)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "agent_id": r["agent_id"],
                "name": r["name"],
                "tier": r["tier"],
                "trust_score": int(r["trust_score"] or 0),
                "verified": bool(r["verified"]),
                "total_transactions": int(r["total_transactions"] or 0),
                "capabilities": json.loads(r["capabilities"] or "[]"),
            }
        )
    return {"category": category or "all", "leaders": out}
