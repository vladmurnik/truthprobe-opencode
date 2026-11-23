#!/usr/bin/env bash
# Regenerates patches/truthprobe-0001.patch from the dev tree you work in.
#
#   bash scripts/make-patch.sh --from ~/src/opencode
#   OPENCODE_REPO=~/src/opencode bash scripts/make-patch.sh
#
# The patch is always cut as `BASE..HEAD`: that way it applies both through `git am`
# and through `git apply`, and stays a set of separate commits instead of "one diff".
#
#     BASE=007afb1b0c8a36dff93d7945909d4e976545ba95
#
# The script commits nothing: commit your changes in the dev tree first.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BASE=${TRUTHPROBE_BASE:-007afb1b0c8a36dff93d7945909d4e976545ba95}
DEV=${OPENCODE_REPO:-}
OUT="$ROOT/patches/truthprobe-0001.patch"

while [ $# -gt 0 ]; do
  case "$1" in
    --from) DEV="${2:?--from needs a path}"; shift 2 ;;
    --from=*) DEV="${1#--from=}"; shift ;;
    --out) OUT="${2:?--out needs a path}"; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "error: unknown option $1" >&2; exit 2 ;;
  esac
done

[ -n "$DEV" ] || { echo "error: specify the dev tree: --from <path> or OPENCODE_REPO=<path>" >&2; exit 2; }
[ -d "$DEV/.git" ] || { echo "error: $DEV is not a git repository" >&2; exit 2; }

if [ -n "$(git -C "$DEV" status --porcelain)" ]; then
  echo "error: $DEV has uncommitted changes — commit them first" >&2
  git -C "$DEV" status --short | head -10 >&2
  exit 1
fi

git -C "$DEV" cat-file -e "$BASE^{commit}" 2>/dev/null || {
  echo "error: base $BASE is not in $DEV (a full sst/opencode clone is required)" >&2
  exit 1
}

# Guard against stray files: the patch must only touch `packages/**` and
# `bun.lock`. Otherwise an artifact such as a copy of the patch itself sneaks in — that is
# what happened in 0.13.8: 3 735 lines of itself inside commit 10/27.
STRAY=$(git -C "$DEV" diff --name-only "$BASE..HEAD" | grep -v '^packages/' | grep -v '^bun\.lock$' || true)
if [ -n "$STRAY" ]; then
  echo "error: the patch touches paths outside packages/ and bun.lock:" >&2
  printf '  %s\n' $STRAY >&2
  echo "remove them from the $BASE..HEAD history and try again" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
git -C "$DEV" format-patch "$BASE..HEAD" --stdout >"$OUT"

COMMITS=$(git -C "$DEV" rev-list --count "$BASE..HEAD")
BYTES=$(wc -c <"$OUT" | tr -d ' ')
# `grep -c '^diff --git'` counts headers, not files: a file touched in two
# commits yields two `diff --git` entries. We count unique paths (b/<path>).
FILES=$(grep '^diff --git ' "$OUT" | sed -e 's#^diff --git .* b/##' -e 's#^"##' -e 's#"$##' | sort -u | wc -l | tr -d ' ')
# The hash pinned in the installers: without it, after every patch regeneration
# `install.sh --dry-run` and `install.ps1 -DryRun` fail the checksum match and CI goes red.
SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
sed -i.bak -E "s/^PATCH_SHA256=\"[0-9a-f]+\"/PATCH_SHA256=\"$SHA\"/" "$ROOT/install.sh"
rm -f "$ROOT/install.sh.bak"
sed -i.bak "s/[0-9a-f]\{64\}/$SHA/g" "$ROOT/install.ps1"
rm -f "$ROOT/install.ps1.bak"

echo "done: $OUT"
echo "  sha256: $SHA (pinned in install.sh and install.ps1)"
echo "  commits: $COMMITS, files: $FILES, bytes: $BYTES"
echo "  base: $BASE"
echo
echo "check locally:  make verify   (or bash scripts/dev-setup.sh --check)"
