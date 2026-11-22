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
#   2. собранный CLI копируется в `packages/desktop/resources/` под именем
#      `opencode-cli[.exe]` — именно оттуда electron-builder берёт бинарь
#      (`extraResources` в electron-builder.config.ts). Без этого шага desktop
#      молча упаковывает СТАРЫЙ CLI;
#   3. `electron-vite build` собирает renderer/main;
#   4. `electron-builder --dir` кладёт распакованное приложение в packages/desktop/dist.
#
# Результат: dist/win-unpacked/TruthProbe.exe (или linux-unpacked/truthprobe).
# Брендинг берётся из OPENCODE_DESKTOP_APP / OPENCODE_DESKTOP_APP_ID — см. docs/DEVELOPMENT.md.
set -euo pipefail

# Нативный bun лежит в ~/.bun/bin и часто не попадает в PATH неинтерактивного
# `bash -lc`; без него сборка падает на preload'ах (`@opentui/solid/preload`).
if [ -x "$HOME/.bun/bin/bun" ]; then
  export PATH="$HOME/.bun/bin:$PATH"
fi

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
echo "== 1/4 cli"
(cd "$DEV/packages/cli" && bun run script/build.ts --skip-install)

echo "== 2/4 staging cli into packages/desktop/resources"
CLI_DIR="$DEV/packages/cli/dist/cli-$PLATFORM"
STAGE="$DEV/packages/desktop/resources"
case "$PLATFORM" in
  windows-x64) SRC="$CLI_DIR/bin/opencode.exe"; DST="$STAGE/opencode-cli.exe" ;;
  *) SRC="$CLI_DIR/bin/opencode"; DST="$STAGE/opencode-cli" ;;
esac
[ -f "$SRC" ] || { echo "error: нет $SRC — сборка CLI не дала бинарь" >&2; exit 1; }
mkdir -p "$STAGE"
cp -f "$SRC" "$DST"
# Штамп версии — это то, по чему приложение кеширует CLI
# (%APPDATA%\ai.truthprobe.desktop\cli\<version>-<arch>). Если штамп не меняется,
# свежесобранный бинарь не доезжает до пользователя: приложение переиспользует
# старый из кеша. Поэтому к версии из сборки добавляется отпечаток содержимого,
# и любая пересборка CLI меняет ключ кеша.
UPSTREAM=""
if [ -f "$CLI_DIR/opencode-cli.version" ]; then
  UPSTREAM=$(tr -d '\r\n' <"$CLI_DIR/opencode-cli.version")
fi
if command -v sha256sum >/dev/null 2>&1; then
  STAMP=$(sha256sum "$DST" | cut -c1-12)
else
  STAMP=$(shasum -a 256 "$DST" | cut -c1-12)
fi
printf '%s\n' "${UPSTREAM:-0.0.0-dev}+${STAMP}" >"$STAGE/opencode-cli.version"
echo "   $(basename "$DST"): $(wc -c <"$DST") bytes, штамп $(cat "$STAGE/opencode-cli.version")"

echo "== 3/4 electron-vite"
(cd "$DEV/packages/desktop" && bun x electron-vite build)

echo "== 4/4 electron-builder --dir"
case "$PLATFORM" in
  windows-x64) FLAGS="--win --x64" ;;
  linux-x64) FLAGS="--linux --x64" ;;
  darwin-*) FLAGS="--mac" ;;
esac
(cd "$DEV/packages/desktop" && bun x electron-builder $FLAGS --publish never --dir --config electron-builder.config.ts)

echo "== готово"
ls -la "$DEV/packages/desktop/dist"/*-unpacked/ 2>/dev/null | head -8 || \
  echo "смотрите $DEV/packages/desktop/dist"
