# AgentTrust MCP — Publish Handoff

## Already Live
- **Production API**: https://agenttrust-mcp-production.up.railway.app
- **MCP endpoint**: https://agenttrust-mcp-production.up.railway.app/mcp
- **PyPI**: [`agentreputation`](https://pypi.org/project/agentreputation/) v0.1.0 — `pip install agentreputation`
- **GitHub**: https://github.com/bch1212/agenttrust-mcp

## One-step Action Brett Needs to Take

The npm publish + Anthropic MCP Registry submission is fully automated via `.github/workflows/publish-mcp.yml` — it just needs the `NPM_TOKEN` secret on this repo.

Copy the same `NPM_TOKEN` Brett uses for `bch1212/injectshield`:

```
gh secret set NPM_TOKEN --repo bch1212/agenttrust-mcp --body "<value-from-injectshield>"
```

Then trigger the workflow:

```
gh workflow run publish-mcp.yml --repo bch1212/agenttrust-mcp
# or push a tag:
git tag mcp-v0.1.0 && git push origin mcp-v0.1.0
```

After it runs:
- `agenttrust-mcp@0.1.0` will be on npm
- `io.github.bch1212/agenttrust` will appear in the Anthropic MCP Registry
- `mcpName` ownership claim is in `packages/agenttrust-mcp/package.json`

## Trust-score & Tier System
See `README.md` for the algorithm. Tiers: PLATINUM ≥800, GOLD 550–799, SILVER 300–549, BRONZE 100–299, NEW <100.

## Pricing
Free read tier (no key); $9/mo Pro tier (unlimited writes); pay-per-call $0.001/write.

## Saved Production Keys
- Dev key: `agenttrust-dev-114ee51b9dfe`
- Admin key: `agenttrust-admin-5586ba510956f99e`

These are also in `.keys.txt` (gitignored). Stored as Railway env vars.
