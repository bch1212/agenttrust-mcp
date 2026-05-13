# agenttrust-mcp

MCP server wrapping the AgentTrust REST API. Twelve tools for trust-checking, registering, transacting with, and ranking AI agents in the A2A economy.

## Install

```bash
claude mcp add agenttrust --command "npx -y agenttrust-mcp"
```

Or in `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agenttrust": {
      "command": "npx",
      "args": ["-y", "agenttrust-mcp"],
      "env": {
        "AGENTTRUST_API_KEY": "your-key-here"
      }
    }
  }
}
```

## Configuration

| env | required | default |
|-----|----------|---------|
| `AGENTTRUST_API_KEY` | only for writes | — |
| `AGENTTRUST_API_BASE` | no | `https://agenttrust-mcp-production.up.railway.app` |

Read tools (`get_trust_score`, `get_agent_profile`, `get_leaderboard`, `search_agents`, `get_transaction_history`) work without an API key.

## Tools

`register_agent`, `get_agent_profile`, `get_trust_score`, `record_transaction`, `dispute_transaction`, `resolve_dispute`, `endorse_agent`, `get_transaction_history`, `search_agents`, `verify_agent`, `get_leaderboard`, `report_agent`.

## License

MIT — https://github.com/bch1212/agenttrust-mcp
