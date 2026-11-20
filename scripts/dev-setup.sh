#!/usr/bin/env bash
# Разворачивает пропатченное дерево opencode — то, в котором живёт TruthProbe.
#
#   bash scripts/dev-setup.sh                 # в .worktree/opencode
#   bash scripts/dev-setup.sh --dir ~/src/tp  # в свой каталог
#   bash scripts/dev-setup.sh --check         # только проверить, что патч ложится
#   bash scripts/dev-setup.sh --skip-install  # без bun install (быстро, для чтения кода)
#
# Что делает:
#   1. клонирует sst/opencode на коммит, под который нарезан патч (BASE);
#   2. применяет patches/truthprobe-0001.patch через `git am`;
#   3. ставит зависимости (`bun install`);
#   4. гоняет truthprobe-тесты, чтобы сразу знать, что дерево живое.
#
# Идемпотентен: повторный запуск на готовом дереве только проверяет состояние.
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
  command -v "$1" >/dev/null 2>&1 || { echo "error: нужен $1" >&2; exit 1; }
}
need git
[ -f "$PATCH" ] || { echo "error: нет $PATCH" >&2; exit 1; }

export PATH="$HOME/.bun/bin:$PATH"

if [ "$CHECK" = "1" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  echo "== проверяю патч на чистой базе $BASE"
  git clone -q --filter=blob:none --no-checkout "$UPSTREAM" "$TMP/opencode"
  git -C "$TMP/opencode" checkout -q "$BASE"
  git -C "$TMP/opencode" apply --check "$PATCH" && echo "OK: патч ложится без конфликтов"
  exit 0
fi

if [ -d "$DIR/.git" ]; then
  echo "== дерево уже есть: $DIR"
  if git -C "$DIR" log --oneline -1 | grep -q "per-model calibration\|TruthProbe"; then
    echo "== патч уже применён, пропускаю клонирование и git am"
  else
    echo "== применяю патч к существующему дереву"
    git -C "$DIR" -c user.name=TruthProbe -c user.email=dev@localhost am "$PATCH" ||
      git -C "$DIR" apply "$PATCH"
  fi
else
  echo "== клонирую $UPSTREAM → $DIR"
  mkdir -p "$(dirname "$DIR")"
  git clone --filter=blob:none --no-checkout "$UPSTREAM" "$DIR"
  git -C "$DIR" checkout -q "$BASE"
  echo "== применяю $(basename "$PATCH")"
  git -C "$DIR" -c user.name=TruthProbe -c user.email=dev@localhost am "$PATCH" ||
    git -C "$DIR" apply "$PATCH"
fi

if [ "$SKIP_INSTALL" = "0" ]; then
  command -v bun >/dev/null 2>&1 || { echo "error: нужен bun (https://bun.sh)" >&2; exit 1; }
  echo "== bun install"
  (cd "$DIR" && bun install)
  echo "== truthprobe-тесты"
  (cd "$DIR" && bun test test/truthprobe | tail -5)
else
  echo "== зависимости не ставил (--skip-install)"
fi

cat <<EOF

готово. дерево: $DIR

  cd "$DIR"
  bun test test/truthprobe                              # юнит-тесты патча
  bun run --cwd packages/cli src/index.ts run "..."     # запуск CLI из исходников
  TRUTHPROBE_SCORER=linear:weights.json ...             # свои веса скорера

дальше: docs/DEVELOPMENT.md — карта «что где менять».
EOF
