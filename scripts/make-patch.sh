#!/usr/bin/env bash
# Пересобирает patches/truthprobe-0001.patch из dev-дерева, где вы работаете.
#
#   bash scripts/make-patch.sh --from ~/src/opencode
#   OPENCODE_REPO=~/src/opencode bash scripts/make-patch.sh
#
# Патч всегда нарезается как `BASE..HEAD`: так он применяется и через `git am`,
# и через `git apply`, и остаётся набором отдельных коммитов, а не «одним diff».
#
#     BASE=007afb1b0c8a36dff93d7945909d4e976545ba95
#
# Скрипт ничего не коммитит: сначала закоммитьте изменения в dev-дереве.
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

[ -n "$DEV" ] || { echo "error: укажите dev-дерево: --from <path> или OPENCODE_REPO=<path>" >&2; exit 2; }
[ -d "$DEV/.git" ] || { echo "error: $DEV — не git-репозиторий" >&2; exit 2; }

if [ -n "$(git -C "$DEV" status --porcelain)" ]; then
  echo "error: в $DEV есть незакоммиченные изменения — сначала закоммитьте их" >&2
  git -C "$DEV" status --short | head -10 >&2
  exit 1
fi

git -C "$DEV" cat-file -e "$BASE^{commit}" 2>/dev/null || {
  echo "error: базы $BASE нет в $DEV (нужен полный клон sst/opencode)" >&2
  exit 1
}

# Гейт против посторонних файлов: патч должен трогать только `packages/**` и
# `bun.lock`. Иначе в него уезжает артефакт вроде копии самого патча — так и
# вышло в 0.13.8: 3 735 строк самого себя внутри коммита 10/27.
STRAY=$(git -C "$DEV" diff --name-only "$BASE..HEAD" | grep -v '^packages/' | grep -v '^bun\.lock$' || true)
if [ -n "$STRAY" ]; then
  echo "error: патч трогает пути вне packages/ и bun.lock:" >&2
  printf '  %s\n' $STRAY >&2
  echo "уберите их из истории $BASE..HEAD и повторите" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
git -C "$DEV" format-patch "$BASE..HEAD" --stdout >"$OUT"

COMMITS=$(git -C "$DEV" rev-list --count "$BASE..HEAD")
BYTES=$(wc -c <"$OUT" | tr -d ' ')
# `grep -c '^diff --git'` считает заголовки, а не файлы: файл, тронутый в двух
# коммитах, даёт два `diff --git`. Считаем уникальные пути (b/<path>).
FILES=$(grep '^diff --git ' "$OUT" | sed -e 's#^diff --git .* b/##' -e 's#^"##' -e 's#"$##' | sort -u | wc -l | tr -d ' ')
echo "готово: $OUT"
echo "  коммитов: $COMMITS, файлов: $FILES, байт: $BYTES"
echo "  база: $BASE"
echo
echo "проверить локально:  make verify   (или bash scripts/dev-setup.sh --check)"
