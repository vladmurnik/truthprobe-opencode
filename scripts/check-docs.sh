#!/usr/bin/env bash
# Checks that the headline numbers in the docs match the patch file itself.
#
# Why: CONTRIBUTING.md requires every number to have a command that produced it,
# but until 0.13.10 the numbers in README/CHANGELOG/VALIDATION were edited by hand.
# In 0.13.8 that let a 3 735-line drift through.
#
# What is checked (only what is derivable from the patch file):
#   * commit count - from the `Subject: [PATCH n/M]` headers;
#   * file count   - unique paths in `diff --git ... b/<path>`;
#   * size in bytes - `wc -c` of the file itself.
#
# The docs are bilingual: README.md/CHANGELOG.md/docs/VALIDATION.md are English,
# their Russian translations live in README.ru.md and docs/ru/. Byte counts are
# compared with separators removed, so `347 540 B`, `347,540 bytes` and `347540`
# all satisfy the same check.
#
# Usage: bash scripts/check-docs.sh   (or make docs-check)
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PATCH="$ROOT/patches/truthprobe-0001.patch"

[ -f "$PATCH" ] || { echo "error: no $PATCH" >&2; exit 1; }

BYTES=$(wc -c <"$PATCH" | tr -d ' ')
FILES=$(grep '^diff --git ' "$PATCH" | sed -e 's#^diff --git .* b/##' -e 's#^"##' -e 's#"$##' | sort -u | wc -l | tr -d ' ')
COMMITS=$(grep -c '^Subject: \[PATCH ' "$PATCH" || true)
LAST=$(grep '^Subject: \[PATCH ' "$PATCH" | tail -1 | sed -e 's#^Subject: \[PATCH [0-9]*/##' -e 's#\].*##')
BYTES_SPACED=$(printf '%s' "$BYTES" | sed -e :a -e 's/\(.*[0-9]\)\([0-9]\{3\}\)/\1 \2/;ta')

if [ "$COMMITS" != "$LAST" ]; then
  echo "error: PATCH n/M headers - $COMMITS, but the last one declares M=$LAST" >&2
  exit 1
fi

fail=0

# Text needle in one file.
check() {
  local file=$1 what=$2 needle=$3
  if [ ! -f "$file" ]; then
    echo "error: $file - missing ($what)" >&2
    fail=1
    return
  fi
  if ! grep -Fq -- "$needle" "$file"; then
    echo "error: $file - no \"$needle\" ($what)" >&2
    fail=1
  fi
}

# A number that may be written with any digit separators (space, comma, NBSP).
check_number() {
  local file=$1 what=$2 number=$3
  if [ ! -f "$file" ]; then
    echo "error: $file - missing ($what)" >&2
    fail=1
    return
  fi
  local flat
  flat=$(tr -d ' ,\302\240' <"$file")
  # Plain bash matching, not `grep -q`: with `pipefail` the early exit of grep
  # kills tr with SIGPIPE and the pipeline reports failure even on a match.
  case $flat in
    *"$number"*) ;;
    *)
      echo "error: $file - no number $number ($what)" >&2
      fail=1
      ;;
  esac
}

# --- English docs
check "$ROOT/README.md" "files" "$FILES files"
check_number "$ROOT/README.md" "bytes" "$BYTES"
check "$ROOT/docs/VALIDATION.md" "files" "**$FILES files,"
check "$ROOT/docs/VALIDATION.md" "bytes" "$BYTES_SPACED B"
check "$ROOT/docs/VALIDATION.md" "measurement block" "commits: $COMMITS, files: $FILES, bytes: $BYTES"
check "$ROOT/CHANGELOG.md" "files" "$FILES files"
check_number "$ROOT/CHANGELOG.md" "bytes" "$BYTES"

# --- Russian translations
check "$ROOT/README.ru.md" "файлы" "$FILES файла"
check_number "$ROOT/README.ru.md" "байты" "$BYTES"
check "$ROOT/docs/ru/VALIDATION.md" "итог" "**$FILES файла,"
check "$ROOT/docs/ru/VALIDATION.md" "блок замера" "коммитов: $COMMITS, файлов: $FILES, байт: $BYTES"
check "$ROOT/docs/ru/CHANGELOG.md" "файлы" "$FILES файла"
check "$ROOT/docs/ru/CHANGELOG.md" "байты" "$BYTES_SPACED Б"

if [ "$fail" -ne 0 ]; then
  echo >&2
  echo "patch: $COMMITS commits, $FILES files, $BYTES bytes ($BYTES_SPACED bytes with separators)" >&2
  echo "update the docs to these numbers, or regenerate the patch (make patch)" >&2
  exit 1
fi

echo "docs match the patch: commits $COMMITS, files $FILES, bytes $BYTES"
