#!/usr/bin/env bash
# VM (WSL2 Ubuntu) bootstrap for opencode-truthprobe.
# Idempotent: safe to re-run.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
HOME_DIR="${HOME:-/home/$(id -un)}"

echo "== host =="
. /etc/os-release
echo "$PRETTY_NAME | $(uname -m) | $(nproc) cpu | $(free -m | awk '/^Mem:/{print $2}') MB ram"

echo "== base packages =="
sudo apt-get update -qq
sudo apt-get install -y -qq curl unzip git build-essential >/dev/null

echo "== bun =="
if ! command -v bun >/dev/null 2>&1; then
  curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
fi
export BUN_INSTALL="$HOME_DIR/.bun"
export PATH="$BUN_INSTALL/bin:$HOME_DIR/.opencode/bin:$PATH"
grep -q 'BUN_INSTALL/bin' "$HOME_DIR/.bashrc" 2>/dev/null || \
  printf '\nexport BUN_INSTALL="$HOME/.bun"\nexport PATH="$BUN_INSTALL/bin:$HOME/.opencode/bin:$PATH"\n' >> "$HOME_DIR/.bashrc"
echo "bun: $(bun --version)"

echo "== opencode =="
if [ ! -x "$HOME_DIR/.opencode/bin/opencode" ]; then
  curl -fsSL https://opencode.ai/install | bash >/dev/null 2>&1
fi
"$HOME_DIR/.opencode/bin/opencode" --version

echo "== source =="
mkdir -p "$HOME_DIR/src"
cd "$HOME_DIR/src"
if [ ! -d opencode/.git ]; then
  git clone --depth 1 https://github.com/sst/opencode.git
fi
cd opencode
echo "commit: $(git log -1 --oneline)"

echo "== deps =="
if [ ! -d node_modules ]; then
  bun install --frozen-lockfile 2>&1 | tail -5
fi

echo "OK"
