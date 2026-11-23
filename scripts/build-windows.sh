#!/usr/bin/env bash
# Builds a single opencode.exe for Windows x64.
#
# It can also be built on Linux (cross-build): bun does not download the platform-specific
# optional dependencies of the other OS, so we install them first with a script
# install-cross-deps.py.
#
#   OPENCODE_REPO=~/src/opencode bash scripts/build-windows.sh [--out file]
set -euo pipefail

REPO=${OPENCODE_REPO:-$HOME/src/opencode}
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=dist/opencode-truthprobe-windows-x64.exe
if [ "${1:-}" = "--out" ]; then OUT=$2; fi
export PATH=$HOME/.bun/bin:$PATH

if [ "$(uname -s)" != "MINGW64_NT" ] && [ "$(uname -s)" != "MSYS_NT" ]; then
  echo "== installing windows optional dependencies =="
  OPENCODE_REPO="$REPO" python3 "$PROJ/scripts/install-cross-deps.py" win32
fi

cd "$REPO/packages/cli"
OPENCODE_TARGET=windows-x64 OPENCODE_RELEASE=1 \
  bun run script/build.ts --single --skip-install --skip-web-ui

mkdir -p "$PROJ/$(dirname "$OUT")"
cp "$REPO/packages/cli/dist/cli-windows-x64/bin/opencode.exe" "$PROJ/$OUT"
echo "built $PROJ/$OUT"
ls -la "$PROJ/$OUT"
sha256sum "$PROJ/$OUT" || shasum -a 256 "$PROJ/$OUT"
