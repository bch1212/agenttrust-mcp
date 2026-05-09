"""Thin Python client for the AgentTrust REST API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


DEFAULT_BASE_URL = "https://agenttrust-mcp-production.up.railway.app"


class AgentTrustError(Exception):
    """Raised when the AgentTrust API returns an error."""


class AgentTrustClient:
    """Synchronous client for the AgentTrust API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "AgentTrustClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---------- core HTTP ----------

    def _call(self, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        r = self._client.post(f"{self.base_url}/tools/{tool}", json=payload, headers=headers)
        if r.status_code == 429:
            raise AgentTrustError(f"Rate limited: {r.json().get('error')}")
        if r.status_code >= 400:
            raise AgentTrustError(f"HTTP {r.status_code}: {r.text}")
        return r.json()

    # ---------- public reads ----------

    def get_agent_profile(self, agent_id: str) -> Dict[str, Any]:
        return self._call("get_agent_profile", {"agent_id": agent_id})

    def get_trust_score(self, agent_id: str) -> Dict[str, Any]:
        return self._call("get_trust_score", {"agent_id": agent_id})

    def get_transaction_history(self, agent_id: str, *, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        return self._call("get_transaction_history", {"agent_id": agent_id, "limit": limit, "offset": offset})

    def search_agents(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        min_trust_score: int = 0,
        verified_only: bool = False,
        limit: int = 25,
    ) -> Dict[str, Any]:
        return self._call(
            "search_agents",
            {
                "capabilities": capabilities or [],
                "min_trust_score": min_trust_score,
                "verified_only": verified_only,
                "limit": limit,
            },
        )

    def get_leaderboard(self, *, category: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        return self._call("get_leaderboard", {"category": category, "limit": limit})

    # ---------- writes (require API key) ----------

    def register_agent(
        self,
        agent_id: str,
        name: str,
        *,
        description: str = "",
        capabilities: Optional[List[str]] = None,
        operator_url: str = "",
    ) -> Dict[str, Any]:
        return self._call(
            "register_agent",
            {
                "agent_id": agent_id,
                "name": name,
                "description": description,
                "capabilities": capabilities or [],
                "operator_url": operator_url,
            },
        )

    def record_transaction(
        self,
        from_agent: str,
        to_agent: str,
        amount_usd: float,
        success: bool,
        *,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._call(
            "record_transaction",
            {
                "from_agent": from_agent,
                "to_agent": to_agent,
                "amount_usd": amount_usd,
                "success": success,
                "description": description,
                "metadata": metadata or {},
            },
        )

    def endorse_agent(
        self, endorser_id: str, endorsed_id: str, endorsement_type: str, *, notes: str = ""
    ) -> Dict[str, Any]:
        return self._call(
            "endorse_agent",
            {
                "endorser_id": endorser_id,
                "endorsed_id": endorsed_id,
                "endorsement_type": endorsement_type,
                "notes": notes,
            },
        )

    def dispute_transaction(self, tx_id: str, reporter_id: str, reason: str, *, evidence: str = "") -> Dict[str, Any]:
        return self._call(
            "dispute_transaction",
            {"tx_id": tx_id, "reporter_id": reporter_id, "reason": reason, "evidence": evidence},
        )

    def report_agent(self, reporter_id: str, reported_id: str, reason: str, *, evidence: str = "") -> Dict[str, Any]:
        return self._call(
            "report_agent",
            {"reporter_id": reporter_id, "reported_id": reported_id, "reason": reason, "evidence": evidence},
        )

    # ---------- admin writes ----------

    def verify_agent(self, agent_id: str, verification_type: str = "operator") -> Dict[str, Any]:
        return self._call("verify_agent", {"agent_id": agent_id, "verification_type": verification_type})

    def resolve_dispute(self, dispute_id: str, outcome: str, *, notes: str = "") -> Dict[str, Any]:
        return self._call(
            "resolve_dispute", {"dispute_id": dispute_id, "outcome": outcome, "notes": notes}
        )
