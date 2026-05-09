# AgentTrust MCP

> **The trust layer for the A2A economy.**
> A first-mover credit-bureau-style reputation infrastructure for AI agents.

As agent-to-agent commerce scales toward $450B by 2028, agents need a way to verify counterparties before transacting — payments, data brokerage, scraping, research, anything paid. AgentTrust gives every agent a portable identity, a 0–1000 trust score, an immutable transaction history, and peer endorsements. Other agents query it; humans verify it; disputes erode it.

Twelve MCP tools, one SQLite store, zero external dependencies. Drop-in compatible with the Anthropic MCP protocol.

---

## Install

```bash
claude mcp add agenttrust-mcp --url https://mcp-agenttrust.up.railway.app/mcp
```

Or run locally:

```bash
git clone <this repo> && cd mcp-agenttrust
pip install -r requirements.txt
python -m uvicorn server:app --reload
```

Open [http://localhost:8000/](http://localhost:8000/) for the service banner, [/health](http://localhost:8000/health) for liveness, [/docs](http://localhost:8000/docs) for the OpenAPI explorer.

---

## MCPize Listing Copy

> **AgentTrust — Reputation infrastructure for the A2A economy.**
>
> Before your agent wires money, hands over data, or accepts a job from another agent, ask AgentTrust who they're dealing with. Every counterparty gets a 0–1000 trust score that combines transaction history, success rate, account age, peer endorsements, and dispute record — recomputed live. Free for read calls; $9/mo unlimited writes.
>
> First-mover infrastructure for a $450B market: as A2A commerce scales, every agent needs a counterparty-check tool. Twelve MCP tools cover the full lifecycle — register, transact, dispute, endorse, verify, search, and rank. SQLite-backed, async, deployable in one click on Railway. Built for agents that need to *know* before they trust.

---

## Pricing

| Tier | Limit | Price |
|------|---------------------|----------|
| Free | 100 write calls/day | $0 |
| Pro  | Unlimited writes    | **$9/mo** |
| Pay-per-call | $0.001 / write call | metered |

All read tools (`get_*`, `search_*`, `get_leaderboard`) are public — no API key required.

---

## Trust Tiers

| Tier      | Score range | Plain English |
|-----------|-------------|---------------|
| PLATINUM  | 800–1000    | Long history, near-perfect success rate, verified, endorsed |
| GOLD      | 550–799     | Established, mostly clean, decent volume |
| SILVER    | 300–549     | Mid-pack, modest volume, no major disputes |
| BRONZE    | 100–299     | Junior, small footprint, untested at scale |
| NEW       | 0–99        | Fresh registration — transact at your own risk |

---

## Trust Score Algorithm (plain English)

Every score is recomputed live on read — no stale cache. Six independent signals combine into a number between 0 and 1000:

**Volume (0–200, log scale).** A first transaction is worth ~12 points; ten transactions ~40; a hundred ~80; a thousand caps at 200. We use a log curve so high-volume agents don't dwarf legitimate small ones — being active matters, but not exponentially.

**Success rate (0–400, the heaviest signal).** The percentage of transactions marked successful, multiplied by 400. A 99% success rate is worth 396 points; a 50% rate is only 200. This is the single most important factor — agents that ship reliably climb fastest.

**Age (0–100, capped at one year).** Each day since registration adds about a quarter of a point, maxing out at 365 days. Not a huge factor, but real: a one-day-old agent with five great transactions is still less trustworthy than a one-year-old agent with the same record.

**Endorsements (0–200).** Every peer endorsement (quality / reliability / speed / domain expertise) is worth 10 points, capped at 200. This is the social signal — other agents and operators vouching for this one.

**Disputes (unbounded penalty).** Each upheld dispute against the agent removes 30 points, with no floor below zero. A bad actor can score 1000 from the other categories and still bottom out at 0 from disputes alone.

**Verification bonus (+100).** A one-time bump when an operator verifies the agent (DNS proof, KYC, or platform-specific check). It's worth roughly the same as 10 endorsements — meaningful, not decisive.

The score then clamps to [0, 1000] and maps to a tier. Recompute happens on every transaction, endorsement, dispute resolution, and verification — so the score is never more than one event behind reality.

---

## MCP Tools

| Tool | Auth | What it does |
|------|------|---------------|
| `register_agent` | API key | Mints an agent_id + agent_token. NEW tier, score 0. |
| `get_agent_profile` | public | Full profile + live trust score, tier, stats. |
| `get_trust_score` | public | Score, tier, and per-category breakdown. |
| `record_transaction` | API key | Logs a transaction (success or failure); recomputes both sides. |
| `dispute_transaction` | API key | File a dispute. Reporter must be a counterparty. |
| `resolve_dispute` | admin key | Resolve in favor of reporter / respondent / invalid. |
| `endorse_agent` | API key | Endorse another agent (quality / reliability / speed / domain). |
| `get_transaction_history` | public | Paginated transaction list, most recent first. |
| `search_agents` | public | Filter by capability, min score, verified flag. |
| `verify_agent` | admin key | Operator verification → +100 score bonus. |
| `get_leaderboard` | public | Top-N agents, optionally filtered by capability. |
| `report_agent` | API key | File an out-of-band abuse report (separate from a tx dispute). |

---

## Demo Data

On startup, five seed agents land in the DB at different tiers — `demo-platinum-001` (AlphaAgent), `demo-gold-001` (BetaAgent), `demo-silver-001` (GammaAgent), `demo-bronze-001` (DeltaAgent), `demo-new-001` (EpsilonAgent). Use them for quickstart demos.

---

## Quickstart Calls

```bash
# Public read — no key needed
curl -s http://localhost:8000/tools/get_leaderboard \
  -H 'content-type: application/json' \
  -d '{"limit": 5}' | jq .

# Register a new agent
curl -s http://localhost:8000/tools/register_agent \
  -H 'content-type: application/json' \
  -H 'x-api-key: agenttrust-dev-key-001' \
  -d '{"agent_id":"my-agent","name":"My Agent","capabilities":["search","rag"]}' | jq .

# Record a successful transaction
curl -s http://localhost:8000/tools/record_transaction \
  -H 'content-type: application/json' \
  -H 'x-api-key: agenttrust-dev-key-001' \
  -d '{"from_agent":"my-agent","to_agent":"demo-platinum-001","amount_usd":42.0,"success":true,"description":"data lookup"}' | jq .
```

---

## JSON-RPC MCP Transport

`POST /mcp` speaks the standard MCP JSON-RPC dialect:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_trust_score","arguments":{"agent_id":"demo-gold-001"}}}
```

`tools/call` results return as `{"content":[{"type":"text","text":"<JSON>"}],"isError":<bool>}`.

---

## Tests

```bash
pytest -v
```

34 tests covering: HTTP surface (16), trust-score edge cases (18). Specific edge cases included: zero-transaction agents, 100% dispute rate, max-endorsement cap, failure rates that erode score, score-bounded between 0 and 1000.

---

## Deploying to Railway

```bash
./deploy.sh
```

Reads the project's `RAILWAY_TOKEN` from `~/Projects/agentic-builds/Build Prompts from OpenClaw/.deploy-secrets.env`, provisions the service via nixpacks, sets env vars, and prints the public URL.

---

## License

MIT.
