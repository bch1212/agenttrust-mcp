"""AgentTrust MCP — FastAPI app exposing 12 MCP tools over HTTP + JSON-RPC.

The server exposes:
  • GET  /                — service banner + tool list
  • GET  /health          — liveness check
  • POST /tools/<name>    — invoke a tool (JSON body of args)
  • POST /mcp             — JSON-RPC MCP transport (initialize/tools.list/tools.call)

Write tools require an X-API-Key header. Read tools (get_*, search_*) are public.
Daily-quota exceeded → HTTP 429 with the upgrade URL.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Awaitable, Callable, Dict, Set

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from db import init_db, seed_demo_agents
from db import keys as keys_mod
from tools import agents as agents_mod
from tools import endorsements as end_mod
from tools import transactions as tx_mod
from tools import trust as trust_mod


# ---------- DB lifecycle ----------

_DB_CONN: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = init_db()
        seed_demo_agents(_DB_CONN)
        keys_mod.seed_default_keys(_DB_CONN)
    return _DB_CONN


def reset_db_for_tests(path: str) -> sqlite3.Connection:
    """Test helper. Replaces the singleton with a fresh DB at the given path."""
    global _DB_CONN
    os.environ["AGENTTRUST_DB"] = path
    _DB_CONN = init_db(path)
    seed_demo_agents(_DB_CONN)
    keys_mod.seed_default_keys(_DB_CONN)
    return _DB_CONN


# ---------- tool registry ----------

# Tools that mutate state and require a valid API key.
WRITE_TOOLS: Set[str] = {
    "register_agent",
    "record_transaction",
    "dispute_transaction",
    "resolve_dispute",
    "endorse_agent",
    "verify_agent",
    "report_agent",
}

# Tools that anyone can call without authentication.
READ_TOOLS: Set[str] = {
    "get_agent_profile",
    "get_trust_score",
    "get_transaction_history",
    "search_agents",
    "get_leaderboard",
}

# Tools where the caller must additionally be an admin (pro-tier key).
ADMIN_TOOLS: Set[str] = {"verify_agent", "resolve_dispute"}


def _dispatch(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db()
    args = dict(args or {})

    if tool_name == "register_agent":
        return agents_mod.register_agent(
            conn,
            agent_id=args.get("agent_id", ""),
            name=args.get("name", ""),
            description=args.get("description", ""),
            capabilities=args.get("capabilities") or [],
            operator_url=args.get("operator_url", ""),
        )
    if tool_name == "get_agent_profile":
        return agents_mod.get_agent_profile(conn, args.get("agent_id", ""))
    if tool_name == "get_trust_score":
        return trust_mod.get_trust_score(conn, args.get("agent_id", ""))
    if tool_name == "record_transaction":
        return tx_mod.record_transaction(
            conn,
            from_agent=args.get("from_agent", ""),
            to_agent=args.get("to_agent", ""),
            amount_usd=float(args.get("amount_usd", 0.0)),
            success=bool(args.get("success", True)),
            description=args.get("description", ""),
            metadata=args.get("metadata") or {},
        )
    if tool_name == "dispute_transaction":
        return tx_mod.dispute_transaction(
            conn,
            tx_id=args.get("tx_id", ""),
            reporter_id=args.get("reporter_id", ""),
            reason=args.get("reason", ""),
            evidence=args.get("evidence", ""),
        )
    if tool_name == "resolve_dispute":
        return tx_mod.resolve_dispute(
            conn,
            dispute_id=args.get("dispute_id", ""),
            outcome=args.get("outcome", ""),
            notes=args.get("notes", ""),
        )
    if tool_name == "endorse_agent":
        return end_mod.endorse_agent(
            conn,
            endorser_id=args.get("endorser_id", ""),
            endorsed_id=args.get("endorsed_id", ""),
            endorsement_type=args.get("endorsement_type", "quality"),
            notes=args.get("notes", ""),
        )
    if tool_name == "get_transaction_history":
        return tx_mod.get_transaction_history(
            conn,
            agent_id=args.get("agent_id", ""),
            limit=int(args.get("limit", 25)),
            offset=int(args.get("offset", 0)),
        )
    if tool_name == "search_agents":
        return agents_mod.search_agents(
            conn,
            capabilities=args.get("capabilities") or None,
            min_trust_score=int(args.get("min_trust_score", 0)),
            verified_only=bool(args.get("verified_only", False)),
            limit=int(args.get("limit", 25)),
        )
    if tool_name == "verify_agent":
        return agents_mod.verify_agent(
            conn,
            agent_id=args.get("agent_id", ""),
            verification_type=args.get("verification_type", "operator"),
        )
    if tool_name == "get_leaderboard":
        return trust_mod.get_leaderboard(
            conn,
            category=args.get("category"),
            limit=int(args.get("limit", 10)),
        )
    if tool_name == "report_agent":
        return end_mod.report_agent(
            conn,
            reporter_id=args.get("reporter_id", ""),
            reported_id=args.get("reported_id", ""),
            reason=args.get("reason", ""),
            evidence=args.get("evidence", ""),
        )
    return {"error": "unknown_tool", "tool": tool_name}


# ---------- MCP tool descriptors (advertised over JSON-RPC tools/list) ----------

def _tool_descriptors() -> list[Dict[str, Any]]:
    return [
        {
            "name": "register_agent",
            "description": "Register a new agent. Returns an agent_token used for auth on subsequent writes.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id", "name"],
                "properties": {
                    "agent_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "operator_url": {"type": "string"},
                },
            },
        },
        {
            "name": "get_agent_profile",
            "description": "Public profile + computed trust score, tier, stats.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "get_trust_score",
            "description": "Trust score (0–1000), tier, and category breakdown.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "record_transaction",
            "description": "Record an A2A transaction (success or failure). Recomputes both sides' scores.",
            "inputSchema": {
                "type": "object",
                "required": ["from_agent", "to_agent", "amount_usd", "success"],
                "properties": {
                    "from_agent": {"type": "string"},
                    "to_agent": {"type": "string"},
                    "amount_usd": {"type": "number"},
                    "success": {"type": "boolean"},
                    "description": {"type": "string"},
                    "metadata": {"type": "object"},
                },
            },
        },
        {
            "name": "dispute_transaction",
            "description": "File a dispute for a recorded transaction. Reporter must be a counterparty.",
            "inputSchema": {
                "type": "object",
                "required": ["tx_id", "reporter_id", "reason"],
                "properties": {
                    "tx_id": {"type": "string"},
                    "reporter_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
        {
            "name": "resolve_dispute",
            "description": "Admin/operator resolves an open dispute. outcome ∈ reporter | respondent | invalid.",
            "inputSchema": {
                "type": "object",
                "required": ["dispute_id", "outcome"],
                "properties": {
                    "dispute_id": {"type": "string"},
                    "outcome": {"type": "string", "enum": ["reporter", "respondent", "invalid"]},
                    "notes": {"type": "string"},
                },
            },
        },
        {
            "name": "endorse_agent",
            "description": "Endorse another agent (quality | reliability | speed | domain).",
            "inputSchema": {
                "type": "object",
                "required": ["endorser_id", "endorsed_id", "endorsement_type"],
                "properties": {
                    "endorser_id": {"type": "string"},
                    "endorsed_id": {"type": "string"},
                    "endorsement_type": {"type": "string", "enum": ["quality", "reliability", "speed", "domain"]},
                    "notes": {"type": "string"},
                },
            },
        },
        {
            "name": "get_transaction_history",
            "description": "Paginated transaction list for an agent (most recent first).",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {
                    "agent_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 25},
                    "offset": {"type": "integer", "default": 0},
                },
            },
        },
        {
            "name": "search_agents",
            "description": "Search agents by capability, min trust score, or verification flag — ranked by score desc.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "min_trust_score": {"type": "integer", "default": 0},
                    "verified_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 25},
                },
            },
        },
        {
            "name": "verify_agent",
            "description": "Operator verification — sets verified=true and adds the verification bonus to the trust score.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id", "verification_type"],
                "properties": {
                    "agent_id": {"type": "string"},
                    "verification_type": {"type": "string"},
                },
            },
        },
        {
            "name": "get_leaderboard",
            "description": "Top-N agents — globally or filtered by capability category.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "name": "report_agent",
            "description": "File an out-of-band abuse report (separate from a transaction dispute).",
            "inputSchema": {
                "type": "object",
                "required": ["reporter_id", "reported_id", "reason"],
                "properties": {
                    "reporter_id": {"type": "string"},
                    "reported_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
    ]


# ---------- FastAPI app ----------

app = FastAPI(
    title="AgentTrust MCP",
    description="Trust scores, reputation, and transaction history for the A2A agent economy.",
    version="0.1.0",
)


@app.on_event("startup")
def _startup() -> None:
    get_db()


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "agenttrust-mcp",
        "version": "0.1.0",
        "tagline": "The trust layer for the A2A economy.",
        "tools": [t["name"] for t in _tool_descriptors()],
        "tiers": {
            "PLATINUM": ">=800",
            "GOLD": "550-799",
            "SILVER": "300-549",
            "BRONZE": "100-299",
            "NEW": "<100",
        },
        "pricing": {"free": "100 writes/day", "pro": "$9/mo unlimited"},
        "mcp_endpoint": "/mcp",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) AS c FROM agents").fetchone()["c"]
    return {"ok": True, "agents": int(n)}


def _upgrade_response() -> JSONResponse:
    upgrade = os.environ.get("AGENTTRUST_UPGRADE_URL", "https://mcpize.com/agenttrust-mcp")
    return JSONResponse(
        status_code=429,
        content={
            "error": f"Upgrade at {upgrade}",
            "tier": "free",
            "upgrade_url": upgrade,
        },
    )


def _auth_or_response(tool_name: str, x_api_key: str | None) -> JSONResponse | None:
    """Returns a JSONResponse on failure, or None if auth passes."""
    conn = get_db()
    if tool_name in READ_TOOLS:
        return None
    if tool_name not in WRITE_TOOLS:
        return JSONResponse(status_code=404, content={"error": "unknown_tool", "tool": tool_name})

    auth = keys_mod.check_and_consume(conn, x_api_key)
    if not auth.ok:
        if auth.reason == "rate_limited":
            return _upgrade_response()
        return JSONResponse(status_code=401, content={"error": auth.reason})

    if tool_name in ADMIN_TOOLS and not keys_mod.is_admin(conn, x_api_key):
        return JSONResponse(status_code=403, content={"error": "admin_key_required"})
    return None


@app.post("/tools/{tool_name}")
async def call_tool(
    tool_name: str,
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        if (await request.body()):
            body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "body_must_be_json_object"})

    auth_err = _auth_or_response(tool_name, x_api_key)
    if auth_err is not None:
        return auth_err

    try:
        result = _dispatch(tool_name, body)
    except sqlite3.IntegrityError as e:
        return JSONResponse(status_code=409, content={"error": "integrity_error", "detail": str(e)})
    return JSONResponse(status_code=200, content=result)


# ---------- JSON-RPC MCP transport ----------

@app.post("/mcp")
async def mcp_jsonrpc(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> JSONResponse:
    try:
        msg = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse_error"}, "id": None},
        )

    method = msg.get("method")
    rid = msg.get("id")

    if method == "initialize":
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agenttrust-mcp", "version": "0.1.0"},
                },
            }
        )

    if method == "tools/list":
        return JSONResponse(
            content={"jsonrpc": "2.0", "id": rid, "result": {"tools": _tool_descriptors()}}
        )

    if method == "tools/call":
        params = msg.get("params") or {}
        tool_name = params.get("name", "")
        args = params.get("arguments") or {}
        auth_err = _auth_or_response(tool_name, x_api_key)
        if auth_err is not None:
            err_body = json.loads(auth_err.body.decode())
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": auth_err.status_code, "message": err_body.get("error", "auth_failed"), "data": err_body},
                }
            )
        try:
            result = _dispatch(tool_name, args)
        except sqlite3.IntegrityError as e:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32000, "message": "integrity_error", "data": str(e)},
                }
            )
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": "error" in result,
                },
            }
        )

    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": f"method_not_found: {method}"},
        }
    )
