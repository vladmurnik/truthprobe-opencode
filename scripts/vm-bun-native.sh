#!/usr/bin/env bash
# Ставит НАТИВНЫЙ bun внутрь WSL и пересобирает зависимости opencode им.
# Причина: в PATH WSL раньше стоит /mnt/c/.../bun (Windows-бинарь), из-за чего
# postinstall вызывает CMD.EXE и падает на UNC-путях.
set -uo pipefail

export BUN_INSTALL="$HOME/.bun"
if [ ! -x "$BUN_INSTALL/bin/bun" ]; then
  curl -fsSL https://bun.sh/install | bash || exit 1
fi
BUN="$BUN_INSTALL/bin/bun"
echo "native bun: $("$BUN" --version)"
file "$BUN" | head -1

cd "$HOME/src/opencode" || exit 1
rm -rf node_modules
start=$(date +%s)
"$BUN" install 2>&1 | tail -12
echo "install_took=$(( $(date +%s) - start ))s"
"$BUN" run --cwd packages/core build 2>&1 | tail -5 || true
echo "BUN_SETUP_DONE"
