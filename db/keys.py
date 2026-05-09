"""API key management — auth check, daily-quota tracking, and seeding."""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

from .schema import transaction


DEFAULT_DAILY_LIMITS = {
    "free": 100,
    "pro": 10**9,  # effectively unlimited
}


def seed_default_keys(conn: sqlite3.Connection) -> None:
    """Insert dev + admin keys idempotently."""
    dev_key = os.environ.get("AGENTTRUST_DEV_KEY", "agenttrust-dev-key-001")
    admin_key = os.environ.get("AGENTTRUST_ADMIN_KEY", "agenttrust-admin-key-001")
    now = time.time()
    with transaction(conn):
        for key, tier in ((dev_key, "free"), (admin_key, "pro")):
            existing = conn.execute(
                "SELECT 1 FROM api_keys WHERE key=?", (key,)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO api_keys (key, tier, call_count, daily_limit, last_reset)
                VALUES (?, ?, 0, ?, ?)
                """,
                (key, tier, DEFAULT_DAILY_LIMITS[tier], now),
            )


def get_key(conn: sqlite3.Connection, key: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM api_keys WHERE key=?", (key,)).fetchone()


def upsert_pro_key(conn: sqlite3.Connection, key: str) -> None:
    """For Stripe/admin upgrade paths."""
    now = time.time()
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO api_keys (key, tier, call_count, daily_limit, last_reset)
            VALUES (?, 'pro', 0, ?, ?)
            ON CONFLICT(key) DO UPDATE SET tier='pro', daily_limit=?
            """,
            (key, DEFAULT_DAILY_LIMITS["pro"], now, DEFAULT_DAILY_LIMITS["pro"]),
        )


def _maybe_reset_window(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
    """If 24h have passed since last_reset, zero the call_count."""
    if time.time() - float(row["last_reset"] or 0) >= 86400:
        with transaction(conn):
            conn.execute(
                "UPDATE api_keys SET call_count=0, last_reset=? WHERE key=?",
                (time.time(), row["key"]),
            )
        row = get_key(conn, row["key"])  # re-read
    return row


class AuthResult:
    __slots__ = ("ok", "reason", "tier", "remaining")

    def __init__(self, ok: bool, reason: str = "", tier: str = "", remaining: int = 0):
        self.ok = ok
        self.reason = reason
        self.tier = tier
        self.remaining = remaining


def check_and_consume(conn: sqlite3.Connection, key: Optional[str]) -> AuthResult:
    """Validate + decrement quota in a single transaction. Returns AuthResult."""
    if not key:
        return AuthResult(False, "missing_api_key")
    row = get_key(conn, key)
    if not row:
        return AuthResult(False, "invalid_api_key")
    row = _maybe_reset_window(conn, row)
    if row["call_count"] >= row["daily_limit"]:
        return AuthResult(False, "rate_limited", tier=row["tier"], remaining=0)
    with transaction(conn):
        conn.execute(
            "UPDATE api_keys SET call_count = call_count + 1 WHERE key=?", (key,)
        )
    remaining = int(row["daily_limit"]) - int(row["call_count"]) - 1
    return AuthResult(True, "", tier=row["tier"], remaining=max(0, remaining))


def is_admin(conn: sqlite3.Connection, key: Optional[str]) -> bool:
    """Admin = the AGENTTRUST_ADMIN_KEY (or any 'pro' tier key, for simplicity)."""
    if not key:
        return False
    admin_key = os.environ.get("AGENTTRUST_ADMIN_KEY", "agenttrust-admin-key-001")
    if key == admin_key:
        return True
    row = get_key(conn, key)
    return bool(row and row["tier"] == "pro")
