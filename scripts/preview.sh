#!/usr/bin/env bash
# One CLI request against the mock provider: the TruthProbe verdict without keys or network.
#
#   bash scripts/preview.sh
#   bash scripts/preview.sh "How many hearts does an octopus have?"
#   TP_DIR=~/src/opencode bash scripts/preview.sh "..."
#
# Starts scripts/mock-openai-logprobs.py on 8899, waits for /v1/models, launches
# opencode with scripts/mock-opencode.json and OPENCODE_TRUTHPROBE=1 enabled.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TP_DIR=${TP_DIR:-$ROOT/.worktree/opencode}
PY=${PYTHON:-python3}
PORT=${MOCK_PORT:-8899}
PROMPT=${1:-"What is the capital of France? Answer in two sentences."}

[ -d "$TP_DIR/packages/cli" ] || {
  echo "error: no $TP_DIR/packages/cli — run bash scripts/dev-setup.sh first" >&2
  exit 1
}
command -v "$PY" >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

LOG=$(mktemp)
"$PY" "$ROOT/scripts/mock-openai-logprobs.py" "$PORT" >"$LOG" 2>&1 &
MOCK=$!
cleanup() { kill "$MOCK" >/dev/null 2>&1 || true; rm -f "$LOG"; }
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then break; fi
  sleep 0.25
done
curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1 || {
  echo "error: the mock did not come up, log:" >&2
  cat "$LOG" >&2
  exit 1
}

# The mock port is hardcoded into the config; if it differs — substitute it on the fly.
CONF=$(mktemp --suffix=.json)
sed "s|127.0.0.1:8899|127.0.0.1:$PORT|" "$ROOT/scripts/mock-opencode.json" >"$CONF"
trap 'cleanup; rm -f "$CONF"' EXIT

echo "== request: $PROMPT"
OPENCODE_TRUTHPROBE=1 OPENCODE_CONFIG="$CONF" \
  bun run --cwd "$TP_DIR/packages/cli" src/index.ts run --model mock/mock-1 "$PROMPT"
echo
echo "== verdict in the database:"
"$PY" "$ROOT/scripts/inspect-db.py" 2>/dev/null | tail -5 || true
