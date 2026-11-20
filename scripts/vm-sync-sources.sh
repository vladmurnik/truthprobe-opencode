#!/usr/bin/env bash
# Синхронизирует эталонные исходники TruthProbe и тесты в дерево opencode.
set -eu
PROJ=/mnt/c/Users/adik/Desktop/progects/opencode-truthprobe
ROOT=/home/adik/src/opencode

mkdir -p "$ROOT/packages/core/src/truthprobe" "$ROOT/packages/core/test" "$ROOT/packages/ai/test"

for f in types sentences score; do
  tr -d '\015' < "$PROJ/src/truthprobe/$f.ts" > "$ROOT/packages/core/src/truthprobe/$f.ts"
done

# core-тест: тот же файл, только импорты указывают на packages/core/src
tr -d '\015' < "$PROJ/test/score.test.ts" > "$ROOT/packages/core/test/truthprobe.test.ts"

# ai-тест протокола
tr -d '\015' < "$PROJ/test/opencode-tree/protocol.test.ts" > "$ROOT/packages/ai/test/truthprobe.test.ts"

python3 "$PROJ/patches/apply-test-exports.py"
echo "=== synced ==="
wc -l "$ROOT/packages/core/src/truthprobe/"*.ts "$ROOT/packages/core/test/truthprobe.test.ts" "$ROOT/packages/ai/test/truthprobe.test.ts"
