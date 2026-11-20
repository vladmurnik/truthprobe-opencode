#!/usr/bin/env bash
set -uo pipefail
export PATH="$HOME/.bun/bin:$PATH"
cd "$HOME/src/opencode" || exit 1
echo "bun=$(command -v bun) ver=$(bun --version)"
bun install 2>&1 | tail -8
echo "INSTALL_EXIT=${PIPESTATUS[0]}"
bun run --cwd packages/core build 2>&1 | tail -4
echo DONE
