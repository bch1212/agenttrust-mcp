#!/usr/bin/env node
// AgentTrust MCP server — wraps the AgentTrust REST API as twelve MCP tools.
//
// Tools:
//   • register_agent, get_agent_profile, get_trust_score
//   • record_transaction, dispute_transaction, resolve_dispute
//   • endorse_agent, get_transaction_history, search_agents
//   • verify_agent, get_leaderboard, report_agent
//
// Environment:
//   AGENTTRUST_API_KEY    Required only for write tools.
//   AGENTTRUST_API_BASE   Defaults to the public managed deployment.

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

const API_BASE =
  process.env.AGENTTRUST_API_BASE ||
  "https://agenttrust-mcp-production.up.railway.app";
const API_KEY = process.env.AGENTTRUST_API_KEY || "";
const PKG_VERSION = "0.1.0";

const TOOLS = [
  {
    name: "register_agent",
    description:
      "Register a new agent with a UUID, name, and capability declaration. Returns an agent_token. Required for write tools.",
    inputSchema: {
      type: "object",
      required: ["agent_id", "name"],
      properties: {
        agent_id: { type: "string" },
        name: { type: "string" },
        description: { type: "string" },
        capabilities: { type: "array", items: { type: "string" } },
        operator_url: { type: "string" },
      },
    },
  },
  {
    name: "get_agent_profile",
    description:
      "Public read. Returns full profile + recomputed trust score, tier, and stats for the named agent.",
    inputSchema: {
      type: "object",
      required: ["agent_id"],
      properties: { agent_id: { type: "string" } },
    },
  },
  {
    name: "get_trust_score",
    description:
      "Public read. Returns trust score (0–1000), tier (PLATINUM/GOLD/SILVER/BRONZE/NEW), and category breakdown.",
    inputSchema: {
      type: "object",
      required: ["agent_id"],
      properties: { agent_id: { type: "string" } },
    },
  },
  {
    name: "record_transaction",
    description:
      "Record an A2A transaction (success or failure). Recomputes both sides' trust scores. Both parties must already be registered.",
    inputSchema: {
      type: "object",
      required: ["from_agent", "to_agent", "amount_usd", "success"],
      properties: {
        from_agent: { type: "string" },
        to_agent: { type: "string" },
        amount_usd: { type: "number" },
        success: { type: "boolean" },
        description: { type: "string" },
        metadata: { type: "object" },
      },
    },
  },
  {
    name: "dispute_transaction",
    description:
      "File a dispute on a transaction. Reporter must be a counterparty (from_agent or to_agent).",
    inputSchema: {
      type: "object",
      required: ["tx_id", "reporter_id", "reason"],
      properties: {
        tx_id: { type: "string" },
        reporter_id: { type: "string" },
        reason: { type: "string" },
        evidence: { type: "string" },
      },
    },
  },
  {
    name: "resolve_dispute",
    description:
      "Admin-only. Resolve an open dispute. Outcome ∈ {reporter, respondent, invalid}.",
    inputSchema: {
      type: "object",
      required: ["dispute_id", "outcome"],
      properties: {
        dispute_id: { type: "string" },
        outcome: { type: "string", enum: ["reporter", "respondent", "invalid"] },
        notes: { type: "string" },
      },
    },
  },
  {
    name: "endorse_agent",
    description:
      "Endorse another agent in one of four categories: quality, reliability, speed, domain. Each endorsement adds 10 points (cap 200).",
    inputSchema: {
      type: "object",
      required: ["endorser_id", "endorsed_id", "endorsement_type"],
      properties: {
        endorser_id: { type: "string" },
        endorsed_id: { type: "string" },
        endorsement_type: {
          type: "string",
          enum: ["quality", "reliability", "speed", "domain"],
        },
        notes: { type: "string" },
      },
    },
  },
  {
    name: "get_transaction_history",
    description:
      "Public read. Paginated transaction list for an agent, most recent first.",
    inputSchema: {
      type: "object",
      required: ["agent_id"],
      properties: {
        agent_id: { type: "string" },
        limit: { type: "integer", default: 25 },
        offset: { type: "integer", default: 0 },
      },
    },
  },
  {
    name: "search_agents",
    description:
      "Public read. Search agents by capability filter, minimum trust score, or verified flag. Ranked by score desc.",
    inputSchema: {
      type: "object",
      properties: {
        capabilities: { type: "array", items: { type: "string" } },
        min_trust_score: { type: "integer", default: 0 },
        verified_only: { type: "boolean", default: false },
        limit: { type: "integer", default: 25 },
      },
    },
  },
  {
    name: "verify_agent",
    description:
      "Admin-only. Operator-verifies an agent (DNS, KYC, or platform check). +100 bonus to trust score.",
    inputSchema: {
      type: "object",
      required: ["agent_id", "verification_type"],
      properties: {
        agent_id: { type: "string" },
        verification_type: { type: "string" },
      },
    },
  },
  {
    name: "get_leaderboard",
    description:
      "Public read. Top-N agents by trust score, optionally filtered by capability category.",
    inputSchema: {
      type: "object",
      properties: {
        category: { type: "string" },
        limit: { type: "integer", default: 10 },
      },
    },
  },
  {
    name: "report_agent",
    description:
      "File an out-of-band abuse report (separate from a transaction dispute).",
    inputSchema: {
      type: "object",
      required: ["reporter_id", "reported_id", "reason"],
      properties: {
        reporter_id: { type: "string" },
        reported_id: { type: "string" },
        reason: { type: "string" },
        evidence: { type: "string" },
      },
    },
  },
];

const WRITE_TOOLS = new Set([
  "register_agent",
  "record_transaction",
  "dispute_transaction",
  "resolve_dispute",
  "endorse_agent",
  "verify_agent",
  "report_agent",
]);

async function callApi(
  toolName: string,
  args: Record<string, unknown>
): Promise<unknown> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (WRITE_TOOLS.has(toolName)) {
    if (!API_KEY) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `${toolName} requires an API key. Set AGENTTRUST_API_KEY.`
      );
    }
    headers["x-api-key"] = API_KEY;
  }
  const res = await fetch(`${API_BASE}/tools/${toolName}`, {
    method: "POST",
    headers,
    body: JSON.stringify(args),
  });
  const text = await res.text();
  if (res.status === 429) {
    throw new McpError(
      ErrorCode.InvalidRequest,
      `Rate limited. Upgrade at https://mcpize.com/agenttrust-mcp`
    );
  }
  if (!res.ok) {
    throw new McpError(
      ErrorCode.InternalError,
      `AgentTrust API error ${res.status}: ${text}`
    );
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const server = new Server(
  { name: "@agenttrust/mcp", version: PKG_VERSION },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  if (!TOOLS.find((t) => t.name === name)) {
    throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
  }
  const result = await callApi(name, (args as Record<string, unknown>) || {});
  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
  };
});

const transport = new StdioServerTransport();
await server.connect(transport);
