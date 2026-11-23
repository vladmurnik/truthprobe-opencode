#!/usr/bin/env bash
# Sets up the patched opencode tree — the one TruthProbe lives in.
#
#   bash scripts/dev-setup.sh                 # into .worktree/opencode
#   bash scripts/dev-setup.sh --dir ~/src/tp  # into a custom directory
#   bash scripts/dev-setup.sh --check         # only verify that the patch applies
#   bash scripts/dev-setup.sh --skip-install  # no bun install (fast, for reading code)
#
# What it does:
#   1. clones sst/opencode at the commit the patch is cut against (BASE);
#   2. applies patches/truthprobe-0001.patch via `git am`;
#   3. installs the dependencies (`bun install`);
#   4. runs the truthprobe tests so you know right away that the tree is alive.
#
# Idempotent: a repeated run on a ready tree only checks its state.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UPSTREAM=${TRUTHPROBE_UPSTREAM:-https://github.com/sst/opencode.git}
BASE=${TRUTHPROBE_BASE:-007afb1b0c8a36dff93d7945909d4e976545ba95}
PATCH="$ROOT/patches/truthprobe-0001.patch"
DIR="$ROOT/.worktree/opencode"
CHECK=0
SKIP_INSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="${2:?--dir needs a path}"; shift 2 ;;
    --dir=*) DIR="${1#--dir=}"; shift ;;
    --check) CHECK=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --base) BASE="${2:?--base needs a commit}"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "error: unknown option $1" >&2; exit 2 ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: $1 is required" >&2; exit 1; }
}
need git
[ -f "$PATCH" ] || { echo "error: no $PATCH" >&2; exit 1; }

export PATH="$HOME/.bun/bin:$PATH"

if [ "$CHECK" = "1" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  echo "== checking the patch against a clean base $BASE"
  git clone -q --filter=blob:none --no-checkout "$UPSTREAM" "$TMP/opencode"
  git -C "$TMP/opencode" checkout -q "$BASE"
  git -C "$TMP/opencode" apply --check "$PATCH" && echo "OK: the patch applies without conflicts"
  exit 0
fi

if [ -d "$DIR/.git" ]; then
  echo "== tree already present: $DIR"
  if git -C "$DIR" apply --reverse --check "$PATCH" >/dev/null 2>&1; then
    echo "== patch already applied (the reverse apply succeeds), skipping git am"
  else
    echo "== applying the patch to the existing tree"
    git -C "$DIR" -c user.name=TruthProbe -c user.email=dev@localhost am "$PATCH" || {
      git -C "$DIR" am --abort 2>/dev/null || true
      git -C "$DIR" apply "$PATCH"
    }
  fi
else
  echo "== cloning $UPSTREAM → $DIR"
  mkdir -p "$(dirname "$DIR")"
  git clone --filter=blob:none --no-checkout "$UPSTREAM" "$DIR"
  git -C "$DIR" checkout -q "$BASE"
  echo "== applying $(basename "$PATCH")"
  git -C "$DIR" -c user.name=TruthProbe -c user.email=dev@localhost am "$PATCH" || {
    git -C "$DIR" am --abort 2>/dev/null || true
    git -C "$DIR" apply "$PATCH"
  }
fi

if [ "$SKIP_INSTALL" = "0" ]; then
  command -v bun >/dev/null 2>&1 || { echo "error: bun is required (https://bun.sh)" >&2; exit 1; }
  echo "== bun install"
  (cd "$DIR" && bun install)
  echo "== truthprobe tests"
  (cd "$DIR" && bun test test/truthprobe | tail -5)
else
  echo "== dependencies were not installed (--skip-install)"
fi

cat <<EOF

done. tree: $DIR

  cd "$DIR"
  bun test test/truthprobe                              # unit tests of the patch
  bun run --cwd packages/cli src/index.ts run "..."     # run the CLI from sources
  TRUTHPROBE_SCORER=linear:weights.json ...             # custom scorer weights

next: docs/DEVELOPMENT.md — the map of "what to change and where".
EOF
