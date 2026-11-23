#!/usr/bin/env bash
# Сверяет заголовочные числа в доках с самим патчем.
#
# Зачем: `CONTRIBUTING.md` требует, чтобы каждая цифра имела команду, которой её
# получили, но до сих пор все числа в README/CHANGELOG/VALIDATION правились руками.
# В 0.13.8 так и проехало расхождение на 3 735 строк.
#
# Что проверяется (только то, что выводимо из файла патча):
#   * число коммитов  — из заголовков `Subject: [PATCH n/M]`;
#   * число файлов    — уникальные пути в `diff --git ... b/<path>`;
#   * размер в байтах — `wc -c` самого файла.
#
# Запуск: bash scripts/check-docs.sh   (или make docs-check)
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PATCH="$ROOT/patches/truthprobe-0001.patch"

[ -f "$PATCH" ] || { echo "error: нет $PATCH" >&2; exit 1; }

BYTES=$(wc -c <"$PATCH" | tr -d ' ')
FILES=$(grep '^diff --git ' "$PATCH" | sed -e 's#^diff --git .* b/##' -e 's#^"##' -e 's#"$##' | sort -u | wc -l | tr -d ' ')
COMMITS=$(grep -c '^Subject: \[PATCH ' "$PATCH" || true)
LAST=$(grep '^Subject: \[PATCH ' "$PATCH" | tail -1 | sed -e 's#^Subject: \[PATCH [0-9]*/##' -e 's#\].*##')
BYTES_SPACED=$(printf '%s' "$BYTES" | sed -e :a -e 's/\(.*[0-9]\)\([0-9]\{3\}\)/\1 \2/;ta')

if [ "$COMMITS" != "$LAST" ]; then
  echo "error: заголовков PATCH n/M — $COMMITS, а последний объявляет M=$LAST" >&2
  exit 1
fi

fail=0
check() {
  local file=$1 what=$2 needle=$3
  if ! grep -Fq -- "$needle" "$file"; then
    echo "error: $file — не найдено «$needle» ($what)" >&2
    fail=1
  fi
}

check "$ROOT/README.md" "файлы" "$FILES файла"
check "$ROOT/README.en.md" "файлы" "$FILES files"
check "$ROOT/docs/VALIDATION.md" "итог" "**$FILES файла,"
check "$ROOT/docs/VALIDATION.md" "байты" "$BYTES_SPACED Б"
check "$ROOT/docs/VALIDATION.md" "блок замера" "коммитов: $COMMITS, файлов: $FILES, байт: $BYTES"
check "$ROOT/CHANGELOG.md" "байты" "$BYTES_SPACED Б"

if [ "$fail" -ne 0 ]; then
  echo >&2
  echo "патч: $COMMITS коммитов, $FILES файлов, $BYTES Б ($BYTES_SPACED Б с пробелами)" >&2
  echo "поправьте доки под эти числа или перегенерируйте патч (make patch)" >&2
  exit 1
fi

echo "доки сходятся с патчем: коммитов $COMMITS, файлов $FILES, байт $BYTES"
