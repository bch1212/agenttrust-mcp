"""AgentTrust Python SDK — thin REST client for the AgentTrust MCP API.

Usage:
    from agenttrust import AgentTrustClient

    client = AgentTrustClient(api_key="agenttrust-dev-...")
    score = client.get_trust_score("demo-platinum-001")
    leaders = client.get_leaderboard(limit=5)
"""
from .client import AgentTrustClient

__version__ = "0.1.0"
__all__ = ["AgentTrustClient"]
