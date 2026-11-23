#!/usr/bin/env bash
# Builds the TruthProbe desktop app (Electron) from the dev tree.
#
#   bash scripts/build-desktop.sh                    # default platform for the host
#   bash scripts/build-desktop.sh --win              # Windows x64 (cross-build from WSL works)
#   bash scripts/build-desktop.sh --linux
#   OPENCODE_REPO=~/src/opencode bash scripts/build-desktop.sh --win
#
# What happens:
#   1. `packages/cli/script/build.ts --skip-install` builds the bundled CLI;
#   2. the built CLI is copied into `packages/desktop/resources/` under the name
#      `opencode-cli[.exe]` — that is where electron-builder takes the binary from
#      (`extraResources` in electron-builder.config.ts). Without this step the desktop app
#      silently packages the OLD CLI;
#   3. `electron-vite build` builds the renderer/main;
#   4. `electron-builder --dir` puts the unpacked app into packages/desktop/dist.
#
# Result: dist/win-unpacked/TruthProbe.exe (or linux-unpacked/truthprobe).
# Branding comes from OPENCODE_DESKTOP_APP / OPENCODE_DESKTOP_APP_ID — see docs/DEVELOPMENT.md.
set -euo pipefail

# The native bun lives in ~/.bun/bin and often does not make it into the PATH of a non-interactive
# `bash -lc`; without it the build fails on the preloads (`@opentui/solid/preload`).
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
  echo "error: no $DEV/packages/desktop — run bash scripts/dev-setup.sh first" >&2
  exit 1
}
command -v bun >/dev/null 2>&1 || { echo "error: bun is required" >&2; exit 1; }

export OPENCODE_TARGET="$PLATFORM"
export OPENCODE_CHANNEL=${OPENCODE_CHANNEL:-dev}
export OPENCODE_DESKTOP_APP=${OPENCODE_DESKTOP_APP:-TruthProbe}
export OPENCODE_DESKTOP_APP_ID=${OPENCODE_DESKTOP_APP_ID:-ai.truthprobe.desktop}
# CompanyName and LegalCopyright in the exe properties: the fork must not present itself as OpenCode.
export OPENCODE_DESKTOP_COMPANY=${OPENCODE_DESKTOP_COMPANY:-$OPENCODE_DESKTOP_APP}
# The file version is the product version from this repository's package.json, otherwise Windows
# shows the shell version (2.3.0) while the release tag says a completely different number.
if [ -z "${OPENCODE_VERSION:-}" ] && [ -f "$ROOT/package.json" ]; then
  OPENCODE_VERSION=$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' "$ROOT/package.json" | head -1)
fi
[ -n "${OPENCODE_VERSION:-}" ] && export OPENCODE_VERSION


echo "== platform: $PLATFORM, app: $OPENCODE_DESKTOP_APP ($OPENCODE_DESKTOP_APP_ID)"
echo "== 1/4 cli"
(cd "$DEV/packages/cli" && bun run script/build.ts --skip-install)

echo "== 2/4 staging cli into packages/desktop/resources"
CLI_DIR="$DEV/packages/cli/dist/cli-$PLATFORM"
STAGE="$DEV/packages/desktop/resources"
case "$PLATFORM" in
  windows-x64) SRC="$CLI_DIR/bin/opencode.exe"; DST="$STAGE/opencode-cli.exe" ;;
  *) SRC="$CLI_DIR/bin/opencode"; DST="$STAGE/opencode-cli" ;;
esac
[ -f "$SRC" ] || { echo "error: no $SRC — the CLI build produced no binary" >&2; exit 1; }
mkdir -p "$STAGE"
cp -f "$SRC" "$DST"
# The stamp is `<CLI version>+<sha256[:12]>`, and both halves are mandatory:
#
#   * the version before the plus is exactly what the CLI reports about itself and writes into `service.json`.
#     The desktop app compares it with the one it passed to the service and, on a mismatch,
#     stops the service and starts a new one. The whole stamp will never match
#     there, so the app went into a restart loop until the 120 s timeout;
#   * the fingerprint after the plus is the key of the `%APPDATA%\ai.truthprobe.desktop\cli\` directory.
#     Without it a rebuilt CLI never reaches the user: the app
#     reuses the binary unpacked the last time.
#
# We ask the binary itself for the version: the version file next to the build is sometimes
# shortened (e.g. `0.0.0-dev`), while `--version` prints exactly the line
# the service is later compared against.
CLI_VERSION=""
if "$DST" --version >/dev/null 2>&1; then
  CLI_VERSION=$("$DST" --version 2>/dev/null | tr -d '\r' | sed -n 's/.* v\([0-9][^ ]*\).*/\1/p' | head -1)
fi
if [ -z "$CLI_VERSION" ] && [ -f "$CLI_DIR/opencode-cli.version" ]; then
  CLI_VERSION=$(tr -d '\r\n' <"$CLI_DIR/opencode-cli.version")
fi
if [ -z "$CLI_VERSION" ]; then
  echo "error: could not determine the CLI version ($DST --version and $CLI_DIR/opencode-cli.version are empty)" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  STAMP=$(sha256sum "$DST" | cut -c1-12)
else
  STAMP=$(shasum -a 256 "$DST" | cut -c1-12)
fi
printf '%s\n' "${CLI_VERSION}+${STAMP}" >"$STAGE/opencode-cli.version"
echo "   $(basename "$DST"): $(wc -c <"$DST") bytes, version $CLI_VERSION, stamp $(cat "$STAGE/opencode-cli.version")"

echo "== 3/4 electron-vite"
(cd "$DEV/packages/desktop" && bun x electron-vite build)

echo "== 4/4 electron-builder --dir"
case "$PLATFORM" in
  windows-x64) FLAGS="--win --x64" ;;
  linux-x64) FLAGS="--linux --x64" ;;
  darwin-*) FLAGS="--mac" ;;
esac
# An already unpacked Electron (e.g. downloaded once into ~/el) saves network:
# otherwise electron-builder pulls ~100 MB before every cross-build.
EXTRA=""
ELECTRON_DIST=${OPENCODE_ELECTRON_DIST:-$HOME/el}
if [ -d "$ELECTRON_DIST" ]; then
  EXTRA="--config.electronDist=$ELECTRON_DIST"
fi
(cd "$DEV/packages/desktop" && bun x electron-builder $FLAGS $EXTRA --publish never --dir --config electron-builder.config.ts)

# electron-builder signs by itself if a certificate is set: WIN_CSC_LINK (path/URL to a .pfx)
# and WIN_CSC_KEY_PASSWORD. Without them the file stays unsigned, and that must be said out loud,
# instead of passing the build off as ready for distribution.
echo "== signing"
BIN=$(ls "$DEV/packages/desktop/dist"/*-unpacked/*.exe 2>/dev/null | head -1)
case "$BIN" in
  *.exe) ;;
  *) BIN=$(ls "$DEV/packages/desktop/dist"/*-unpacked/opencode-truthprobe "$DEV/packages/desktop/dist"/*-unpacked/truthprobe 2>/dev/null | head -1) ;;
esac
if [ -n "$BIN" ]; then
  if [ -n "${WIN_CSC_LINK:-${CSC_LINK:-}}" ]; then
    echo "   certificate is set (${WIN_CSC_LINK:-$CSC_LINK}); check the signature status on Windows:"
    echo "   powershell -NoProfile -Command \"(Get-AuthenticodeSignature '$(wslpath -w "$BIN" 2>/dev/null || echo "$BIN")').Status\""
  else
    echo "   WARNING: WIN_CSC_LINK is not set — $BIN is unsigned (NotSigned)."
    echo "   The installer will show \"unknown publisher\"; see docs/DEVELOPMENT.md, the \"Signing\" section."
  fi
fi


echo "== done"
ls -la "$DEV/packages/desktop/dist"/*-unpacked/ 2>/dev/null | head -8 || \
  echo "see $DEV/packages/desktop/dist"
