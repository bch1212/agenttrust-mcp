"""Peer endorsements and abuse reports."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict

from db import queries
from .trust import recompute_and_persist, get_tier


VALID_TYPES = {"quality", "reliability", "speed", "domain"}


def endorse_agent(
    conn: sqlite3.Connection,
    *,
    endorser_id: str,
    endorsed_id: str,
    endorsement_type: str,
    notes: str,
) -> Dict[str, Any]:
    if endorser_id == endorsed_id:
        return {"error": "self_endorsement_not_allowed"}
    if endorsement_type not in VALID_TYPES:
        return {"error": "invalid_endorsement_type", "valid": sorted(VALID_TYPES)}
    if not queries.get_agent(conn, endorser_id):
        return {"error": "endorser_not_found", "agent_id": endorser_id}
    if not queries.get_agent(conn, endorsed_id):
        return {"error": "endorsed_not_found", "agent_id": endorsed_id}

    eid = queries.insert_endorsement(
        conn,
        endorser_id=endorser_id,
        endorsed_id=endorsed_id,
        endorsement_type=endorsement_type,
        notes=notes or "",
    )
    new_score = recompute_and_persist(endorsed_id, conn)
    return {
        "endorsement_id": eid,
        "endorsed_id": endorsed_id,
        "new_trust_score": new_score,
        "new_tier": get_tier(new_score),
    }


def report_agent(
    conn: sqlite3.Connection,
    *,
    reporter_id: str,
    reported_id: str,
    reason: str,
    evidence: str,
) -> Dict[str, Any]:
    if reporter_id == reported_id:
        return {"error": "self_report_not_allowed"}
    if not queries.get_agent(conn, reporter_id):
        return {"error": "reporter_not_found", "agent_id": reporter_id}
    if not queries.get_agent(conn, reported_id):
        return {"error": "reported_not_found", "agent_id": reported_id}
    rid = queries.insert_report(
        conn,
        reporter_id=reporter_id,
        reported_id=reported_id,
        reason=reason or "",
        evidence=evidence or "",
    )
    return {"report_id": rid, "status": "open"}
