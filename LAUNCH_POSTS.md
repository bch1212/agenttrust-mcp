# AgentTrust MCP — Launch Posts

Builder-voice drafts. Brett owns timing. Tue–Thu morning ET tends to peak for HN; weekday afternoons for Reddit.

**Suggested sequence:**
1. **Day 0:** Show HN @ 7am ET → r/ClaudeAI + r/LangChain + r/AI_Agents @ 9am ET → Twitter @ 10am ET
2. **Day 1:** Product Hunt launch (schedule for 12:01am PT)
3. **Day 7:** "What we learned" follow-up thread

---

## 1. Hacker News — Show HN

**Title** (HN is strict — no superlatives, no "best/easiest/etc."):
```
Show HN: AgentTrust – Trust scores for the agent-to-agent economy
```

**URL:** `https://github.com/bch1212/agenttrust-mcp`

**First comment (post immediately as OP):**
```
I built AgentTrust after spending a weekend wiring up an A2A flow where two of my agents had to hand off money. The receiving side had no way to ask "is this counterparty trustworthy?" — every agent I'd ever written just trusted whatever ID it was handed.

This MCP server is a credit bureau for AI agents. Every agent registers with a UUID + capability declaration, every transaction (success or failure) is recorded, and a 0–1000 trust score is recomputed live from six signals:

- Volume (log scale, 0–200): rewards activity, doesn't reward gaming
- Success rate (0–400): the heaviest weight by far. 99% success = 396 pts; 50% = 200
- Age (0–100, capped at 1 year)
- Endorsements (10 pts each, cap 200): peer signal from other agents
- Disputes: −30 each, no floor
- Verification: +100 one-time bump

Tiers: PLATINUM ≥800, GOLD ≥550, SILVER ≥300, BRONZE ≥100, NEW <100.

Twelve MCP tools: register_agent, get_trust_score, record_transaction, dispute_transaction, resolve_dispute, endorse_agent, verify_agent, search_agents, get_leaderboard, get_transaction_history, report_agent, get_agent_profile.

Reads are public (free). Writes are $9/mo or $0.001/call. SQLite-backed, async FastAPI, ~2400 lines including tests.

Live: https://agenttrust-mcp-production.up.railway.app/mcp
Repo: https://github.com/bch1212/agenttrust-mcp

Honest caveat: this is the wedge. The real product is the network — a single shared trust graph that agents query before transacting. I have ~5 demo agents seeded; the dispute resolution logic still defers to a human admin (me). I'd love feedback on the score algorithm specifically — what's missing? What's gameable?
```

---

## 2. Reddit — r/ClaudeAI

**Title:**
```
[Project] AgentTrust MCP — give your agents a way to verify counterparties before A2A transactions
```

**Body:**
```
Posting because I built a thing and the MCP community here always gives sharp feedback.

**The problem:** I have multiple agents in production that hand off work and money to each other. Until last week, every receiver just trusted whatever sender ID it got. That's not going to scale to a real A2A economy — agents need a way to say "is this counterparty good for it?" before transacting.

**What it is:** AgentTrust is an MCP server that maintains trust scores (0–1000) for registered agents. Every transaction, endorsement, dispute, and verification updates the score live. Agents query the score before deciding whether to engage.

12 MCP tools covering register / transact / dispute / endorse / verify / search / rank.

Reads are public, no key needed:
```
claude mcp add agenttrust --url https://agenttrust-mcp-production.up.railway.app/mcp
```

Or HTTP:
```
curl -X POST https://agenttrust-mcp-production.up.railway.app/tools/get_leaderboard \
  -H 'content-type: application/json' -d '{"limit":5}'
```

Writes are $9/mo or pay-per-call. The scoring algorithm is open and documented in the README — I'd genuinely like the community to poke holes in it.

Repo: https://github.com/bch1212/agenttrust-mcp
```

---

## 3. Reddit — r/AI_Agents

**Title:**
```
Built a credit-bureau for AI agents — trust scores, transaction history, peer endorsements, dispute system
```

**Body:** (same as r/ClaudeAI but lead with the "credit bureau" framing — that audience is more product-aware)

```
A2A commerce is starting to happen for real, and the missing piece I keep hitting is: how does Agent A decide whether to trust Agent B? There's no shared reputation layer. Every product builds its own.

So I built AgentTrust as an MCP server that any agent can call.

[…rest of r/ClaudeAI body…]

What I want feedback on: is "trust score 0–1000 from six signals" the right primitive, or should this be more like a graph (who-vouched-for-whom) so agents can compute personalized scores against their own threshold? Genuinely undecided.
```

---

## 4. Twitter / X (single tweet)

```
Built AgentTrust: a credit bureau for AI agents. ☁️

Every agent gets a 0–1000 trust score from transaction history, success rate, peer endorsements, disputes. Recomputed live. 12 MCP tools.

Free to query. $9/mo for writes.

https://github.com/bch1212/agenttrust-mcp
```

**Thread (optional):**
```
1/ The score is 6 signals. Success rate is 0–400 (heaviest). Volume is log-scale 0–200. Endorsements 0–200 capped. Disputes −30 each, no floor. Verification +100. Age 0–100 capped at 1yr.

2/ Tiers: PLATINUM 800+, GOLD 550+, SILVER 300+, BRONZE 100+, NEW <100. Score recomputes on every transaction, endorsement, dispute, and verification — never more than one event behind.

3/ Reads are public; writes need an API key. Pay-per-call ($0.001/write) or $9/mo unlimited. SQLite-backed, FastAPI, deployable on Railway in one command.

4/ Honest caveat: this only works if multiple agents use the same instance. The wedge is being first. The real product is the network. https://github.com/bch1212/agenttrust-mcp
```

---

## 5. Product Hunt

**Tagline:** Trust scores for the AI-agent economy

**Description:**
```
Like a credit bureau for AI agents. AgentTrust maintains a 0–1000 trust score for every registered agent, recomputed live from transaction history, success rate, peer endorsements, disputes, and operator verification. Twelve MCP tools cover the full lifecycle — register, transact, dispute, endorse, verify, search, and rank. Reads are free; writes are $9/mo. SQLite-backed, deployable in one click.

Built for the moment when agent-to-agent commerce stops being a demo and starts being real money. First-mover infrastructure.
```

**Topics:** AI Agents, Developer Tools, MCP, APIs, Open Source

**Maker comment:**
```
Built this because every A2A flow I've shipped has had the same gap: the receiving agent has no way to verify the sender before transacting. AgentTrust is the smallest possible thing that closes that gap — register your agent, log transactions, the score updates live. The score algorithm is fully documented and intentionally open to scrutiny.

Free read tier means any agent can integrate in <5 minutes. The paid tier funds the open source.
```

---

## 6. LinkedIn

```
We're going to need a reputation layer for AI agents soon, and I don't want to be the one who realizes that the day after my agent wires $50K to the wrong counterparty.

Built AgentTrust this week — an MCP server that gives every registered agent a 0–1000 trust score, recomputed live from six signals: transaction history, success rate, account age, peer endorsements, disputes, and operator verification.

Twelve tools, standard MCP protocol, drops into Claude / Cursor / Continue / any MCP client. Reads are free; writes are $9/mo.

If you're building anything in the agent-to-agent space, this is the kind of infrastructure I want to see standardized. Open source, MIT licensed, repo + algorithm both fully open.

https://github.com/bch1212/agenttrust-mcp
```

---

## 7. Discord (general MCP communities)

```
Hey folks — just shipped AgentTrust MCP, a trust-score / reputation server for AI agents. Twelve tools (register, transact, dispute, endorse, verify, search, etc.). Trust score 0–1000 recomputed live from six signals. Reads are public/free; writes are paid.

`claude mcp add agenttrust --url https://agenttrust-mcp-production.up.railway.app/mcp`

Repo: https://github.com/bch1212/agenttrust-mcp

Genuinely looking for feedback on the scoring algorithm — README has the full breakdown. If anyone's building A2A flows where multiple agents transact, would love to know what additional signals you'd want.
```

---

## Notes for Brett
- All posts assume the Railway deployment stays live at `agenttrust-mcp-production.up.railway.app`
- Once npm publish lands, update HN/Reddit posts to mention `npm i agenttrust-mcp` and `claude mcp add agenttrust --command "npx -y agenttrust-mcp"`
- The Anthropic MCP Registry submission via OIDC is one workflow run away — adds significant credibility for the launch
