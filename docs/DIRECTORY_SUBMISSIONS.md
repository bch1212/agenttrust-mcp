# AgentTrust MCP — Directory Submission Status

## Auto-indexed (no action needed)
- **GitHub topics**: `mcp`, `model-context-protocol`, `mcp-server` set on bch1212/agenttrust-mcp — Glama, Smithery, mcp.so, PulseMCP all crawl by topic.
- **glama.json**: present at repo root; Glama treats this as an explicit "yes-index-me" signal.
- **awesome-mcp-servers**: PR open at https://github.com/punkpeye/awesome-mcp-servers/pull/6117

## Pending on npm publish
Once `agenttrust-mcp` lands on npm (workflow ready, needs NPM_TOKEN secret):
- **Anthropic MCP Registry** auto-publishes via `.github/workflows/publish-mcp.yml` (OIDC + server.json submission)
- **Smithery** auto-imports from npm packages with the `mcp-server` keyword
- **Glama** auto-imports from packages tagged `model-context-protocol`

## No public API — manual web form (Brett owns)
- mcp.so — submit via https://mcp.so/submit (form)
- PulseMCP — submit via https://pulsemcp.com/submit (form, Cloudflare-protected)
- MCPize — submit via https://mcpize.com/submit (form, paid placement)

Submission copy ready in `docs/MCPIZE_LISTING.md`.
