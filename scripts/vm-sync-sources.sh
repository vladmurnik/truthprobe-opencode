#!/usr/bin/env bash
# Syncs the reference TruthProbe sources and tests into the opencode tree.
set -eu
PROJ=/mnt/c/Users/adik/Desktop/progects/opencode-truthprobe
ROOT=/home/adik/src/opencode

mkdir -p "$ROOT/packages/core/src/truthprobe" "$ROOT/packages/core/test" "$ROOT/packages/ai/test"

for f in types sentences score; do
  tr -d '\015' < "$PROJ/src/truthprobe/$f.ts" > "$ROOT/packages/core/src/truthprobe/$f.ts"
done

# core test: the same file, only the imports point to packages/core/src
tr -d '\015' < "$PROJ/test/score.test.ts" > "$ROOT/packages/core/test/truthprobe.test.ts"

# ai protocol test
tr -d '\015' < "$PROJ/test/opencode-tree/protocol.test.ts" > "$ROOT/packages/ai/test/truthprobe.test.ts"

python3 "$PROJ/patches/apply-test-exports.py"
echo "=== synced ==="
wc -l "$ROOT/packages/core/src/truthprobe/"*.ts "$ROOT/packages/core/test/truthprobe.test.ts" "$ROOT/packages/ai/test/truthprobe.test.ts"
