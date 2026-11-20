#!/usr/bin/env bash
#
# TruthProbe installer for opencode.
#
#   curl -fsSL https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.sh | bash
#   bash install.sh [target-dir]
#
# What it does:
#   1. fetches sst/opencode at the exact base commit the patch was built on;
#   2. applies patches/truthprobe-0001.patch (git am, or git apply as a fallback);
#   3. runs `bun install` and prints the binary version.
#
# Requirements: git, bun (https://bun.sh), curl or wget.
# Nothing outside the target directory is modified: git identity, if missing,
# is set locally in that directory only.
set -euo pipefail

BASE=007afb1b0c8a36dff93d7945909d4e976545ba95
BASE_SHORT=007afb1
UPSTREAM=https://github.com/sst/opencode.git
REPO=https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master
PATCH_NAME=patches/truthprobe-0001.patch
DIR="${1:-${TRUTHPROBE_DIR:-opencode-truthprobe}}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { bold "==> $*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

step "checking requirements"
command -v git >/dev/null 2>&1 || die "git is required"
command -v bun >/dev/null 2>&1 || die "bun is required (https://bun.sh)"
if command -v curl >/dev/null 2>&1; then
  download() { curl -fsSL "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  download() { wget -qO "$2" "$1"; }
else
  die "curl or wget is required"
fi
printf '    git %s\n    bun %s\n' "$(git --version | awk '{print $3}')" "$(bun --version)"

step "fetching sst/opencode @ ${BASE_SHORT} into $DIR"
if [ -d "$DIR/.git" ] && git -C "$DIR" rev-parse --git-dir >/dev/null 2>&1; then
  printf '    reusing existing checkout\n'
  cd "$DIR"
  git fetch -q --depth 1 origin "$BASE" 2>/dev/null || true
else
  mkdir -p "$DIR"
  cd "$DIR"
  git init -q
  git remote add origin "$UPSTREAM" 2>/dev/null || git remote set-url origin "$UPSTREAM"
  git fetch -q --depth 1 origin "$BASE"
  git checkout -q -B truthprobe FETCH_HEAD
fi

if git log --oneline -n 20 2>/dev/null | grep -qi truthprobe; then
  step "patch already applied, skipping"
else
  step "downloading $PATCH_NAME"
  PATCH="$(mktemp)"
  trap 'rm -f "$PATCH"' EXIT
  download "$REPO/$PATCH_NAME" "$PATCH"
  [ -s "$PATCH" ] || die "patch download failed: $REPO/$PATCH_NAME"

  step "applying patch"
  # git am needs committer identity; keep it local so the user's global config is untouched.
  git config user.name >/dev/null 2>&1 || git config user.name "TruthProbe"
  git config user.email >/dev/null 2>&1 || git config user.email "truthprobe@localhost"

  if ! git am --whitespace=nowarn "$PATCH"; then
    git am --abort 2>/dev/null || true
    printf '    git am failed, retrying as a plain diff\n'
    git apply --whitespace=nowarn "$PATCH"
  fi
fi

step "installing dependencies (a few minutes)"
bun install

step "smoke test"
bun run --cwd packages/cli src/index.ts --version

bold "==> done"
cat <<'EOF'

Run it:

  cd <target-dir>
  bun run --cwd packages/cli src/index.ts

Providers are probed automatically: the first chat-completions request sends one
"ping" with max_tokens: 1 and logprobs: true, and if the provider answers with
logprobs, confidence is enabled for it from the next request on. Verdicts live in
~/.local/share/opencode/truthprobe/capabilities.json (%APPDATA%\opencode\truthprobe\
on Windows). Turn the probe off with OPENCODE_TRUTHPROBE_PROBE=off.

Tests:

  bun test test/score.test.ts        # scoring and segmentation
  bun test test/capability.test.ts   # probe verdicts, TTL, cache
EOF
