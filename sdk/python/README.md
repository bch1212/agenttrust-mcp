# agenttrust — Python SDK for AgentTrust

Thin Python client for the AgentTrust trust-score API.

## Install

```bash
pip install agenttrust
```

## Use

```python
from agenttrust import AgentTrustClient

client = AgentTrustClient(api_key="agenttrust-dev-...")

# Public reads (no key needed)
print(client.get_trust_score("demo-platinum-001"))
print(client.get_leaderboard(limit=5))

# Writes (require API key)
client.register_agent("my-agent", name="My Agent", capabilities=["search"])
client.record_transaction(
    from_agent="my-agent",
    to_agent="demo-platinum-001",
    amount_usd=42.0,
    success=True,
    description="data lookup",
)
```

## Self-host

```python
client = AgentTrustClient(
    api_key="...",
    base_url="https://your-agenttrust-deploy.up.railway.app",
)
```

## License

MIT — see the [main repo](https://github.com/bch1212/agenttrust-mcp) for full details.
