"""SQLite schema, connection helper, and demo seeding for AgentTrust."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, List


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    capabilities TEXT,
    operator_url TEXT,
    agent_token TEXT UNIQUE,
    created_at REAL,
    last_active REAL,
    trust_score INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'NEW',
    total_transactions INTEGER DEFAULT 0,
    successful_transactions INTEGER DEFAULT 0,
    total_volume_usd REAL DEFAULT 0.0,
    dispute_count INTEGER DEFAULT 0,
    verified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id TEXT PRIMARY KEY,
    from_agent TEXT,
    to_agent TEXT,
    amount_usd REAL,
    success INTEGER,
    description TEXT,
    metadata TEXT,
    created_at REAL,
    disputed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS endorsements (
    id TEXT PRIMARY KEY,
    endorser_id TEXT,
    endorsed_id TEXT,
    endorsement_type TEXT,
    notes TEXT,
    created_at REAL,
    weight INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS disputes (
    id TEXT PRIMARY KEY,
    tx_id TEXT,
    reporter_id TEXT,
    reason TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'open',
    created_at REAL,
    resolved_at REAL,
    resolver_notes TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    reporter_id TEXT,
    reported_id TEXT,
    reason TEXT,
    evidence TEXT,
    created_at REAL,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    call_count INTEGER DEFAULT 0,
    daily_limit INTEGER DEFAULT 100,
    last_reset REAL
);

CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_agent);
CREATE INDEX IF NOT EXISTS idx_tx_to ON transactions(to_agent);
CREATE INDEX IF NOT EXISTS idx_endorse_endorsed ON endorsements(endorsed_id);
CREATE INDEX IF NOT EXISTS idx_disputes_tx ON disputes(tx_id);
CREATE INDEX IF NOT EXISTS idx_agents_tier ON agents(tier);
CREATE INDEX IF NOT EXISTS idx_agents_score ON agents(trust_score);
"""


def _db_path() -> str:
    return os.environ.get("AGENTTRUST_DB", "./agenttrust.db")


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or _db_path()
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Atomic write block. Rolls back on exception."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = get_conn(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


SEED_AGENTS: List[dict] = [
    {
        "agent_id": "demo-platinum-001",
        "name": "AlphaAgent",
        "description": "Top-tier reference agent — full transaction history, endorsements, verified.",
        "capabilities": ["payments", "data-broker", "research"],
        "tier": "PLATINUM",
        "trust_score": 920,
        "total_transactions": 1450,
        "successful_transactions": 1432,
        "total_volume_usd": 184_000.0,
        "verified": 1,
    },
    {
        "agent_id": "demo-gold-001",
        "name": "BetaAgent",
        "description": "Established agent with strong history and verified operator.",
        "capabilities": ["analytics", "research"],
        "tier": "GOLD",
        "trust_score": 650,
        "total_transactions": 220,
        "successful_transactions": 208,
        "total_volume_usd": 22_400.0,
        "verified": 1,
    },
    {
        "agent_id": "demo-silver-001",
        "name": "GammaAgent",
        "description": "Mid-tier agent, decent track record, no disputes.",
        "capabilities": ["scraping", "analytics"],
        "tier": "SILVER",
        "trust_score": 400,
        "total_transactions": 65,
        "successful_transactions": 58,
        "total_volume_usd": 4_900.0,
        "verified": 0,
    },
    {
        "agent_id": "demo-bronze-001",
        "name": "DeltaAgent",
        "description": "Junior agent with a small handful of completed transactions.",
        "capabilities": ["chat", "summarization"],
        "tier": "BRONZE",
        "trust_score": 150,
        "total_transactions": 12,
        "successful_transactions": 9,
        "total_volume_usd": 380.0,
        "verified": 0,
    },
    {
        "agent_id": "demo-new-001",
        "name": "EpsilonAgent",
        "description": "Brand-new registration — no transactions yet.",
        "capabilities": ["search"],
        "tier": "NEW",
        "trust_score": 0,
        "total_transactions": 0,
        "successful_transactions": 0,
        "total_volume_usd": 0.0,
        "verified": 0,
    },
]


def seed_demo_agents(conn: sqlite3.Connection) -> None:
    """Idempotent: insert demo agents only if absent."""
    now = time.time()
    with transaction(conn):
        for spec in SEED_AGENTS:
            existing = conn.execute(
                "SELECT 1 FROM agents WHERE agent_id=?", (spec["agent_id"],)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, name, description, capabilities, operator_url,
                    agent_token, created_at, last_active, trust_score, tier,
                    total_transactions, successful_transactions, total_volume_usd,
                    dispute_count, verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec["agent_id"],
                    spec["name"],
                    spec["description"],
                    json.dumps(spec["capabilities"]),
                    f"https://demo-operator.test/{spec['agent_id']}",
                    f"demo-token-{spec['agent_id']}-{uuid.uuid4().hex[:8]}",
                    now - 86400 * 200,  # 200 days old for non-NEW; NEW can stay
                    now,
                    spec["trust_score"],
                    spec["tier"],
                    spec["total_transactions"],
                    spec["successful_transactions"],
                    spec["total_volume_usd"],
                    0,
                    spec["verified"],
                ),
            )
