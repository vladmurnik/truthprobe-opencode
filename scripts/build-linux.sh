#!/usr/bin/env bash
# Builds a single opencode binary for Linux x64.
#
#   OPENCODE_REPO=~/src/opencode bash scripts/build-linux.sh [--out file]
set -euo pipefail

REPO=${OPENCODE_REPO:-$HOME/src/opencode}
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=dist/opencode-truthprobe-linux-x64
if [ "${1:-}" = "--out" ]; then OUT=$2; fi
export PATH=$HOME/.bun/bin:$PATH

cd "$REPO/packages/cli"
OPENCODE_TARGET=linux-x64 OPENCODE_RELEASE=1 \
  bun run script/build.ts --single --skip-install --skip-web-ui

mkdir -p "$PROJ/$(dirname "$OUT")"
cp "$REPO/packages/cli/dist/cli-linux-x64/bin/opencode" "$PROJ/$OUT"
chmod +x "$PROJ/$OUT"
echo "built $PROJ/$OUT"
ls -la "$PROJ/$OUT"
sha256sum "$PROJ/$OUT" || shasum -a 256 "$PROJ/$OUT"
