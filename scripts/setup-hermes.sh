#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-default}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON="$ROOT/.venv/bin/python"
SERVER="$ROOT/server.py"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes Agent is not installed or not on PATH." >&2
  exit 1
fi

if [ ! -x "$PYTHON" ]; then
  echo "Missing $PYTHON" >&2
  echo "Run: python3 -m venv \"$ROOT/.venv\" && \"$ROOT/.venv/bin/python\" -m pip install -r \"$ROOT/requirements.txt\"" >&2
  exit 1
fi

hermes --profile "$PROFILE" mcp add artcraft \
  --command "$PYTHON" \
  --connect-timeout 30 \
  --args "$SERVER"
hermes --profile "$PROFILE" config set mcp_servers.artcraft.timeout 300
hermes --profile "$PROFILE" mcp test artcraft

echo
echo "ArtCraft MCP configured for Hermes profile: $PROFILE"
echo "Run /reload-mcp in Hermes or restart that profile's process/gateway."
