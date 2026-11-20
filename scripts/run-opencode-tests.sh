#!/usr/bin/env bash
# Прогоняет тесты TruthProbe внутри дерева opencode.
#
#   OPENCODE_REPO=~/src/opencode bash scripts/run-opencode-tests.sh
#
# Скрипт синхронизирует эталонные исходники из src/truthprobe в дерево,
# поэтому падение тестов всегда означает падение реального кода патча.
set -euo pipefail

REPO=${OPENCODE_REPO:-$HOME/src/opencode}
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PATH=$HOME/.bun/bin:$PATH

if [ ! -d "$REPO/packages/core" ]; then
  echo "opencode checkout not found: $REPO (set OPENCODE_REPO)" >&2
  exit 1
fi

echo "== sync sources =="
for f in types sentences score; do
  tr -d '\015' < "$PROJ/src/truthprobe/$f.ts" > "$REPO/packages/core/src/truthprobe/$f.ts"
done
tr -d '\015' < "$PROJ/test/score.test.ts" > "$REPO/packages/core/test/truthprobe.test.ts"
tr -d '\015' < "$PROJ/test/opencode-tree/protocol.test.ts" > "$REPO/packages/ai/test/truthprobe.test.ts"
python3 "$PROJ/patches/apply-test-exports.py"

echo "== typecheck =="
(cd "$REPO" && bun run --cwd packages/ai typecheck && bun run --cwd packages/core typecheck)

echo "== core scoring tests =="
(cd "$REPO/packages/core" && bun test test/truthprobe.test.ts)

echo "== protocol tests =="
(cd "$REPO/packages/ai" && bun test test/truthprobe.test.ts)

echo "== session regression subset =="
(cd "$REPO/packages/core" && bun test test/session*.test.ts test/projector*.test.ts test/message*.test.ts)

echo "all green"
