"""Transaction recording, history, dispute lifecycle."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict

from db import queries
from .trust import recompute_and_persist, get_tier


def record_transaction(
    conn: sqlite3.Connection,
    *,
    from_agent: str,
    to_agent: str,
    amount_usd: float,
    success: bool,
    description: str,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not from_agent or not to_agent:
        return {"error": "both_parties_required"}
    if from_agent == to_agent:
        return {"error": "self_transactions_not_allowed"}
    if not queries.get_agent(conn, from_agent):
        return {"error": "from_agent_not_found", "agent_id": from_agent}
    if not queries.get_agent(conn, to_agent):
        return {"error": "to_agent_not_found", "agent_id": to_agent}
    if amount_usd < 0:
        return {"error": "amount_must_be_non_negative"}

    tx_id = queries.insert_transaction(
        conn,
        from_agent=from_agent,
        to_agent=to_agent,
        amount_usd=float(amount_usd),
        success=bool(success),
        description=description or "",
        metadata=metadata or {},
    )
    # Recompute both sides
    from_score = recompute_and_persist(from_agent, conn)
    to_score = recompute_and_persist(to_agent, conn)
    return {
        "tx_id": tx_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "amount_usd": float(amount_usd),
        "success": bool(success),
        "updated_scores": {
            from_agent: {"score": from_score, "tier": get_tier(from_score)},
            to_agent: {"score": to_score, "tier": get_tier(to_score)},
        },
    }


def get_transaction_history(
    conn: sqlite3.Connection, *, agent_id: str, limit: int = 25, offset: int = 0
) -> Dict[str, Any]:
    if not queries.get_agent(conn, agent_id):
        return {"error": "agent_not_found", "agent_id": agent_id}
    rows = queries.list_transactions_for_agent(
        conn, agent_id, limit=max(1, min(limit, 200)), offset=max(0, offset)
    )
    out = []
    for r in rows:
        out.append(
            {
                "tx_id": r["tx_id"],
                "from_agent": r["from_agent"],
                "to_agent": r["to_agent"],
                "amount_usd": float(r["amount_usd"] or 0.0),
                "success": bool(r["success"]),
                "description": r["description"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "created_at": r["created_at"],
                "disputed": bool(r["disputed"]),
            }
        )
    return {"agent_id": agent_id, "count": len(out), "limit": limit, "offset": offset, "transactions": out}


def dispute_transaction(
    conn: sqlite3.Connection,
    *,
    tx_id: str,
    reporter_id: str,
    reason: str,
    evidence: str,
) -> Dict[str, Any]:
    tx = queries.get_transaction(conn, tx_id)
    if not tx:
        return {"error": "transaction_not_found", "tx_id": tx_id}
    if not queries.get_agent(conn, reporter_id):
        return {"error": "reporter_not_found", "agent_id": reporter_id}
    # Reporter must be a counterparty.
    if reporter_id not in (tx["from_agent"], tx["to_agent"]):
        return {"error": "reporter_not_party_to_tx"}
    dispute_id = queries.insert_dispute(
        conn,
        tx_id=tx_id,
        reporter_id=reporter_id,
        reason=reason or "",
        evidence=evidence or "",
    )
    return {"dispute_id": dispute_id, "tx_id": tx_id, "status": "open"}


def resolve_dispute(
    conn: sqlite3.Connection,
    *,
    dispute_id: str,
    outcome: str,
    notes: str,
) -> Dict[str, Any]:
    """outcome ∈ {'reporter', 'respondent', 'invalid'}"""
    if outcome not in {"reporter", "respondent", "invalid"}:
        return {"error": "invalid_outcome", "valid": ["reporter", "respondent", "invalid"]}
    dispute = queries.get_dispute(conn, dispute_id)
    if not dispute:
        return {"error": "dispute_not_found", "dispute_id": dispute_id}
    if dispute["status"] != "open":
        return {"error": "dispute_already_resolved", "status": dispute["status"]}

    tx = queries.get_transaction(conn, dispute["tx_id"])
    if not tx:
        return {"error": "underlying_tx_missing"}

    # Decide which agent gets the dispute penalty applied
    reporter = dispute["reporter_id"]
    counterparty = tx["from_agent"] if reporter == tx["to_agent"] else tx["to_agent"]

    if outcome == "reporter":
        # Reporter wins → counterparty penalized
        queries.increment_dispute_count(conn, counterparty)
        new_status = "resolved_for_reporter"
    elif outcome == "respondent":
        # Respondent wins → reporter penalized for filing a frivolous dispute
        queries.increment_dispute_count(conn, reporter)
        new_status = "resolved_for_respondent"
    else:
        new_status = "resolved_invalid"

    queries.resolve_dispute_row(conn, dispute_id=dispute_id, status=new_status, notes=notes or "")

    updated = {}
    for aid in {tx["from_agent"], tx["to_agent"]}:
        new_score = recompute_and_persist(aid, conn)
        updated[aid] = {"score": new_score, "tier": get_tier(new_score)}

    return {
        "dispute_id": dispute_id,
        "outcome": outcome,
        "status": new_status,
        "updated_scores": updated,
    }
