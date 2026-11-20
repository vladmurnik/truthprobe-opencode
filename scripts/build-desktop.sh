#!/usr/bin/env bash
# Собирает desktop-приложение TruthProbe (Electron) из dev-дерева.
#
#   bash scripts/build-desktop.sh                    # платформа по умолчанию для хоста
#   bash scripts/build-desktop.sh --win              # Windows x64 (можно кросс-сборкой из WSL)
#   bash scripts/build-desktop.sh --linux
#   OPENCODE_REPO=~/src/opencode bash scripts/build-desktop.sh --win
#
# Что происходит:
#   1. `packages/cli/script/build.ts --skip-install` собирает встроенный CLI;
#   2. `electron-vite build` собирает renderer/main;
#   3. `electron-builder --dir` кладёт распакованное приложение в packages/desktop/dist.
#
# Результат: dist/win-unpacked/TruthProbe.exe (или linux-unpacked/truthprobe).
# Брендинг берётся из OPENCODE_DESKTOP_APP / OPENCODE_DESKTOP_APP_ID — см. docs/DEVELOPMENT.md.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEV=${OPENCODE_REPO:-$ROOT/.worktree/opencode}
PLATFORM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --win|--windows) PLATFORM=windows-x64; shift ;;
    --linux) PLATFORM=linux-x64; shift ;;
    --mac|--darwin) PLATFORM=darwin-arm64; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "error: unknown option $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) PLATFORM=windows-x64 ;;
    Darwin) PLATFORM=darwin-arm64 ;;
    *) PLATFORM=linux-x64 ;;
  esac
fi

[ -d "$DEV/packages/desktop" ] || {
  echo "error: нет $DEV/packages/desktop — сначала bash scripts/dev-setup.sh" >&2
  exit 1
}
command -v bun >/dev/null 2>&1 || { echo "error: нужен bun" >&2; exit 1; }

export OPENCODE_TARGET="$PLATFORM"
export OPENCODE_CHANNEL=${OPENCODE_CHANNEL:-dev}
export OPENCODE_DESKTOP_APP=${OPENCODE_DESKTOP_APP:-TruthProbe}
export OPENCODE_DESKTOP_APP_ID=${OPENCODE_DESKTOP_APP_ID:-ai.truthprobe.desktop}

echo "== платформа: $PLATFORM, приложение: $OPENCODE_DESKTOP_APP ($OPENCODE_DESKTOP_APP_ID)"
echo "== 1/3 cli"
(cd "$DEV/packages/cli" && bun run script/build.ts --skip-install)

echo "== 2/3 electron-vite"
(cd "$DEV/packages/desktop" && bun x electron-vite build)

echo "== 3/3 electron-builder --dir"
case "$PLATFORM" in
  windows-x64) FLAGS="--win --x64" ;;
  linux-x64) FLAGS="--linux --x64" ;;
  darwin-*) FLAGS="--mac" ;;
esac
(cd "$DEV/packages/desktop" && bun x electron-builder $FLAGS --publish never --dir --config electron-builder.config.ts)

echo "== готово"
ls -la "$DEV/packages/desktop/dist"/*-unpacked/ 2>/dev/null | head -8 || \
  echo "смотрите $DEV/packages/desktop/dist"
