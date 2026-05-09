#!/usr/bin/env bash
# Deploy AgentTrust MCP to Railway. Run this from your Mac (Cowork sandbox can't reach Railway API).
#
# Prereqs:
#   • Railway CLI installed:  brew install railway
#   • The shared deploy-secrets file at the project root.
#
# What it does:
#   1. Loads RAILWAY_TOKEN from ../.deploy-secrets.env (and exports it as RAILWAY_API_TOKEN).
#   2. Creates the Railway project + service if missing.
#   3. Sets AGENTTRUST_DEV_KEY, AGENTTRUST_ADMIN_KEY, AGENTTRUST_UPGRADE_URL.
#   4. Deploys via nixpacks.
#   5. Prints the public URL.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="$(cd "$PROJECT_ROOT/.." && pwd)/.deploy-secrets.env"
SERVICE_NAME="${SERVICE_NAME:-agenttrust-mcp}"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "✗ Missing $SECRETS_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$SECRETS_FILE"; set +a

if [[ -z "${RAILWAY_TOKEN:-}" ]]; then
  echo "✗ RAILWAY_TOKEN not found in $SECRETS_FILE" >&2
  exit 1
fi

# Memory says: use RAILWAY_API_TOKEN, and unset RAILWAY_TOKEN to avoid the dual-set conflict.
export RAILWAY_API_TOKEN="$RAILWAY_TOKEN"
unset RAILWAY_TOKEN

if ! command -v railway >/dev/null 2>&1; then
  echo "✗ Railway CLI not found. Install with: brew install railway" >&2
  exit 1
fi

cd "$PROJECT_ROOT"

# Initialize / link
if [[ ! -f .railway.json ]] && [[ ! -d .railway ]]; then
  echo "→ Creating Railway project: $SERVICE_NAME"
  railway init --name "$SERVICE_NAME" || true
fi

# Pick reasonable defaults for env
DEV_KEY="${AGENTTRUST_DEV_KEY:-agenttrust-dev-key-$(openssl rand -hex 4)}"
ADMIN_KEY="${AGENTTRUST_ADMIN_KEY:-agenttrust-admin-key-$(openssl rand -hex 4)}"
UPGRADE_URL="${AGENTTRUST_UPGRADE_URL:-https://mcpize.com/agenttrust-mcp}"

echo "→ Setting environment variables"
railway variables --set "AGENTTRUST_DEV_KEY=$DEV_KEY" || true
railway variables --set "AGENTTRUST_ADMIN_KEY=$ADMIN_KEY" || true
railway variables --set "AGENTTRUST_UPGRADE_URL=$UPGRADE_URL" || true
railway variables --set "AGENTTRUST_DB=/data/agenttrust.db" || true

echo "→ Deploying via nixpacks"
railway up --service "$SERVICE_NAME" --detach || railway up --detach

echo "→ Resolving public URL"
sleep 6
railway domain || true

cat <<EOF

✓ AgentTrust MCP deployed.

Save these somewhere safe:
  Dev key   : $DEV_KEY
  Admin key : $ADMIN_KEY

Sanity check after the URL is live:
  curl https://<your-railway-url>/health

Add to a Claude client:
  claude mcp add agenttrust-mcp --url https://<your-railway-url>/mcp
EOF
