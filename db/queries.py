"""All SQL queries as named functions. Keeps SQL out of business logic."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from .schema import transaction


# ---------- agents ----------

def insert_agent(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    name: str,
    description: str,
    capabilities: List[str],
    operator_url: str,
    agent_token: str,
) -> None:
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO agents (
                agent_id, name, description, capabilities, operator_url,
                agent_token, created_at, last_active, trust_score, tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                name,
                description,
                json.dumps(capabilities),
                operator_url,
                agent_token,
                now,
                now,
                0,
                "NEW",
            ),
        )


def get_agent(conn: sqlite3.Connection, agent_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM agents WHERE agent_id=?", (agent_id,)
    ).fetchone()


def update_agent_score(
    conn: sqlite3.Connection, agent_id: str, score: int, tier: str
) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE agents SET trust_score=?, tier=?, last_active=? WHERE agent_id=?",
            (score, tier, time.time(), agent_id),
        )


def update_agent_verified(conn: sqlite3.Connection, agent_id: str, verified: int) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE agents SET verified=?, last_active=? WHERE agent_id=?",
            (verified, time.time(), agent_id),
        )


def search_agents(
    conn: sqlite3.Connection,
    *,
    capabilities: Optional[List[str]] = None,
    min_trust_score: int = 0,
    verified_only: bool = False,
    limit: int = 50,
) -> List[sqlite3.Row]:
    sql = "SELECT * FROM agents WHERE trust_score >= ?"
    params: List[Any] = [min_trust_score]
    if verified_only:
        sql += " AND verified=1"
    if capabilities:
        # Match if ANY listed capability appears in the JSON array.
        clauses = []
        for cap in capabilities:
            clauses.append("capabilities LIKE ?")
            params.append(f'%"{cap}"%')
        sql += " AND (" + " OR ".join(clauses) + ")"
    sql += " ORDER BY trust_score DESC LIMIT ?"
    params.append(limit)
    return list(conn.execute(sql, params).fetchall())


def leaderboard(
    conn: sqlite3.Connection,
    *,
    category: Optional[str] = None,
    limit: int = 10,
) -> List[sqlite3.Row]:
    sql = "SELECT * FROM agents"
    params: List[Any] = []
    if category:
        sql += " WHERE capabilities LIKE ?"
        params.append(f'%"{category}"%')
    sql += " ORDER BY trust_score DESC LIMIT ?"
    params.append(limit)
    return list(conn.execute(sql, params).fetchall())


# ---------- transactions ----------

def insert_transaction(
    conn: sqlite3.Connection,
    *,
    from_agent: str,
    to_agent: str,
    amount_usd: float,
    success: bool,
    description: str,
    metadata: Dict[str, Any] | None = None,
) -> str:
    tx_id = f"tx_{uuid.uuid4().hex}"
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO transactions (
                tx_id, from_agent, to_agent, amount_usd, success,
                description, metadata, created_at, disputed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                tx_id,
                from_agent,
                to_agent,
                amount_usd,
                1 if success else 0,
                description,
                json.dumps(metadata or {}),
                now,
            ),
        )
        # Update both sides' counters
        conn.execute(
            """
            UPDATE agents
               SET total_transactions = total_transactions + 1,
                   successful_transactions = successful_transactions + ?,
                   total_volume_usd = total_volume_usd + ?,
                   last_active = ?
             WHERE agent_id = ?
            """,
            (1 if success else 0, amount_usd, now, from_agent),
        )
        conn.execute(
            """
            UPDATE agents
               SET total_transactions = total_transactions + 1,
                   successful_transactions = successful_transactions + ?,
                   total_volume_usd = total_volume_usd + ?,
                   last_active = ?
             WHERE agent_id = ?
            """,
            (1 if success else 0, amount_usd, now, to_agent),
        )
    return tx_id


def get_transaction(conn: sqlite3.Connection, tx_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM transactions WHERE tx_id=?", (tx_id,)).fetchone()


def list_transactions_for_agent(
    conn: sqlite3.Connection, agent_id: str, *, limit: int = 25, offset: int = 0
) -> List[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM transactions
             WHERE from_agent = ? OR to_agent = ?
             ORDER BY created_at DESC
             LIMIT ? OFFSET ?
            """,
            (agent_id, agent_id, limit, offset),
        ).fetchall()
    )


def mark_transaction_disputed(conn: sqlite3.Connection, tx_id: str) -> None:
    with transaction(conn):
        conn.execute("UPDATE transactions SET disputed=1 WHERE tx_id=?", (tx_id,))


# ---------- disputes ----------

def insert_dispute(
    conn: sqlite3.Connection,
    *,
    tx_id: str,
    reporter_id: str,
    reason: str,
    evidence: str,
) -> str:
    dispute_id = f"dsp_{uuid.uuid4().hex}"
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO disputes (id, tx_id, reporter_id, reason, evidence, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            (dispute_id, tx_id, reporter_id, reason, evidence, now),
        )
        conn.execute("UPDATE transactions SET disputed=1 WHERE tx_id=?", (tx_id,))
    return dispute_id


def get_dispute(conn: sqlite3.Connection, dispute_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()


def resolve_dispute_row(
    conn: sqlite3.Connection,
    *,
    dispute_id: str,
    status: str,
    notes: str,
) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE disputes SET status=?, resolved_at=?, resolver_notes=? WHERE id=?",
            (status, time.time(), notes, dispute_id),
        )


def increment_dispute_count(conn: sqlite3.Connection, agent_id: str, by: int = 1) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE agents SET dispute_count = dispute_count + ? WHERE agent_id = ?",
            (by, agent_id),
        )


# ---------- endorsements ----------

def insert_endorsement(
    conn: sqlite3.Connection,
    *,
    endorser_id: str,
    endorsed_id: str,
    endorsement_type: str,
    notes: str,
    weight: int = 1,
) -> str:
    eid = f"end_{uuid.uuid4().hex}"
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO endorsements (id, endorser_id, endorsed_id, endorsement_type, notes, created_at, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (eid, endorser_id, endorsed_id, endorsement_type, notes, now, weight),
        )
    return eid


def count_endorsements(conn: sqlite3.Connection, agent_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM endorsements WHERE endorsed_id=?", (agent_id,)
    ).fetchone()
    return int(row["c"]) if row else 0


# ---------- reports ----------

def insert_report(
    conn: sqlite3.Connection,
    *,
    reporter_id: str,
    reported_id: str,
    reason: str,
    evidence: str,
) -> str:
    rid = f"rpt_{uuid.uuid4().hex}"
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO reports (id, reporter_id, reported_id, reason, evidence, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'open')
            """,
            (rid, reporter_id, reported_id, reason, evidence, now),
        )
    return rid
