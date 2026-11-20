#!/usr/bin/env bash
# VM bootstrap, phase 2 — runs AS THE DESKTOP USER (no root rights needed).
# Installs bun, opencode (official installer), clones opencode source, installs deps.
set -uo pipefail

echo "== user: $(id -un) home=$HOME =="

if ! command -v bun >/dev/null 2>&1; then
  curl -fsSL https://bun.sh/install | bash
fi
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$HOME/.opencode/bin:$PATH"

grep -q 'BUN_INSTALL' "$HOME/.bashrc" 2>/dev/null || {
  printf '\nexport BUN_INSTALL="$HOME/.bun"\nexport PATH="$BUN_INSTALL/bin:$HOME/.opencode/bin:$PATH"\n' >> "$HOME/.bashrc"
}
echo "bun: $(bun --version 2>&1)"

if [ ! -x "$HOME/.opencode/bin/opencode" ]; then
  curl -fsSL https://opencode.ai/install | bash
fi
echo "opencode: $("$HOME/.opencode/bin/opencode" --version 2>&1)"

mkdir -p "$HOME/src"
cd "$HOME/src" || exit 1
if [ ! -d opencode/.git ]; then
  git clone --depth 1 https://github.com/sst/opencode.git || exit 1
fi
cd opencode || exit 1
echo "commit: $(git log -1 --oneline)"

if [ ! -d node_modules ]; then
  bun install 2>&1 | tail -6
fi
echo "PHASE2_OK"
