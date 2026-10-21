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

ADMIN_KEY_ENV = "AGENTTRUST_ADMIN_KEY"
DEV_KEY_ENV = "AGENTTRUST_DEV_KEY"


class AdminKeyNotConfigured(RuntimeError):
    """AGENTTRUST_ADMIN_KEY is missing or blank.

    Raised so the process refuses to start and admin actions fail closed.
    The message intentionally contains no key material.
    """


def get_admin_key() -> str:
    """Return the configured admin key.

    There is no default. A missing or blank AGENTTRUST_ADMIN_KEY raises
    AdminKeyNotConfigured.
    """
    key = (os.environ.get(ADMIN_KEY_ENV) or "").strip()
    if not key:
        raise AdminKeyNotConfigured(
            "AGENTTRUST_ADMIN_KEY is not set. Refusing to start and refusing "
            "admin actions. Set AGENTTRUST_ADMIN_KEY to a secret value; there "
            "is no default."
        )
    return key


def _optional_dev_key() -> Optional[str]:
    """Dev key is optional. Never fall back to a shared hardcoded key."""
    key = (os.environ.get(DEV_KEY_ENV) or "").strip()
    return key or None


def seed_default_keys(conn: sqlite3.Connection) -> None:
    """Insert env-provided keys idempotently.

    AGENTTRUST_ADMIN_KEY is required; this raises AdminKeyNotConfigured when
    it is missing so startup fails closed. AGENTTRUST_DEV_KEY is seeded only
    when set. No shared default keys are inserted.
    """
    admin_key = get_admin_key()
    dev_key = _optional_dev_key()
    now = time.time()
    seeds: list[tuple[str, str]] = [(admin_key, "pro")]
    if dev_key and dev_key != admin_key:
        seeds.append((dev_key, "free"))
    with transaction(conn):
        for key, tier in seeds:
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
    """Admin = the configured AGENTTRUST_ADMIN_KEY, or any pro-tier key.

    Raises AdminKeyNotConfigured when the env var is missing or blank.
    Pro-tier keys are not treated as admin until the env var is set, so a
    missing configuration cannot fall open.
    """
    admin_key = get_admin_key()
    if not key:
        return False
    if key == admin_key:
        return True
    row = get_key(conn, key)
    return bool(row and row["tier"] == "pro")
