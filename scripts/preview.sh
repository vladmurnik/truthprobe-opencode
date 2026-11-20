#!/usr/bin/env bash
# Один запрос к CLI на мок-провайдере: видно вердикт TruthProbe без ключей и сети.
#
#   bash scripts/preview.sh
#   bash scripts/preview.sh "Сколько сердец у осьминога?"
#   TP_DIR=~/src/opencode bash scripts/preview.sh "..."
#
# Поднимает scripts/mock-openai-logprobs.py на 8899, ждёт /v1/models, запускает
# opencode с scripts/mock-opencode.json и включённым OPENCODE_TRUTHPROBE=1.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TP_DIR=${TP_DIR:-$ROOT/.worktree/opencode}
PY=${PYTHON:-python3}
PORT=${MOCK_PORT:-8899}
PROMPT=${1:-"What is the capital of France? Answer in two sentences."}

[ -d "$TP_DIR/packages/cli" ] || {
  echo "error: нет $TP_DIR/packages/cli — сначала bash scripts/dev-setup.sh" >&2
  exit 1
}
command -v "$PY" >/dev/null 2>&1 || { echo "error: нужен python3" >&2; exit 1; }

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
  echo "error: мок не поднялся, лог:" >&2
  cat "$LOG" >&2
  exit 1
}

# Порт мока зашит в конфиг; если он другой — подменяем на лету.
CONF=$(mktemp --suffix=.json)
sed "s|127.0.0.1:8899|127.0.0.1:$PORT|" "$ROOT/scripts/mock-opencode.json" >"$CONF"
trap 'cleanup; rm -f "$CONF"' EXIT

echo "== запрос: $PROMPT"
OPENCODE_TRUTHPROBE=1 OPENCODE_CONFIG="$CONF" \
  bun run --cwd "$TP_DIR/packages/cli" src/index.ts run --model mock/mock-1 "$PROMPT"
echo
echo "== вердикт в базе:"
"$PY" "$ROOT/scripts/inspect-db.py" 2>/dev/null | tail -5 || true
