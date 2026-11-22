#!/usr/bin/env bash
#
# TruthProbe installer for opencode.
#
#   curl -fsSL https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.sh | bash
#
#   bash install.sh                          # в ./opencode-truthprobe
#   bash install.sh ~/src/opencode-tp        # в свой каталог
#   bash install.sh --dir ~/src/tp --dry-run # только проверить, что патч ляжет
#   bash install.sh --uninstall              # вернуть дерево к базовому коммиту
#   bash install.sh --scorer weights.json    # положить свои веса скорера
#
# Что делает:
#   1. качает sst/opencode на том коммите, под который нарезан патч;
#   2. применяет patches/truthprobe-0001.patch (git am, затем git apply);
#   3. ставит зависимости и печатает версию;
#   4. при --scorer копирует веса и печатает строку окружения.
#
# Нужны: git, bun (https://bun.sh), curl или wget. Ничего вне каталога установки
# не меняется: git identity при необходимости ставится локально.
set -euo pipefail

BASE=007afb1b0c8a36dff93d7945909d4e976545ba95
BASE_SHORT=007afb1
UPSTREAM=https://github.com/sst/opencode.git
REPO=https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master
PATCH_NAME=patches/truthprobe-0001.patch
# Патч тянется с ветки, а потом его код исполняется (bun install + сборка),
# поэтому сверяем байты с закреплённой суммой, а не доверяем URL.
PATCH_SHA256="1ecd3350b7b937b256a421c0a732bb4de4eed9f01fd5630bb36f259bee611ec7"

DIR="${TRUTHPROBE_DIR:-opencode-truthprobe}"
DRY_RUN=0
UNINSTALL=0
SCORER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="${2:?--dir needs a path}"; shift 2 ;;
    --dir=*) DIR="${1#--dir=}"; shift ;;
    --scorer) SCORER="${2:?--scorer needs a path}"; shift 2 ;;
    --scorer=*) SCORER="${1#--scorer=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    -*) printf 'error: unknown option %s\n' "$1" >&2; exit 2 ;;
    *) DIR="$1"; shift ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { bold "==> $*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
note() { printf '    %s\n' "$*"; }

step "checking requirements"
command -v git >/dev/null 2>&1 || die "git is required"
if command -v curl >/dev/null 2>&1; then
  download() { curl -fsSL "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  download() { wget -qO "$2" "$1"; }
else
  die "curl or wget is required"
fi
note "git $(git --version | awk '{print $3}')"
if [ "$UNINSTALL" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  command -v bun >/dev/null 2>&1 || die "bun is required (https://bun.sh)"
  note "bun $(bun --version)"
fi

if [ "$UNINSTALL" -eq 1 ]; then
  step "uninstalling from $DIR"
  [ -d "$DIR/.git" ] || die "$DIR is not a git checkout"
  cd "$DIR"
  if ! git log --oneline -n 40 | grep -qi truthprobe; then
    note "commitы truthprobe не найдены — похоже, патч уже снят"
    exit 0
  fi
  note "снимаю коммиты патча, дерево возвращается к $BASE_SHORT"
  note "несохранённые правки tracked-файлов будут потеряны; конфиг opencode и данные не трогаются"
  git reset --hard "$BASE"
  git log --oneline -1
  bold "==> патч снят"
  exit 0
fi

step "fetching sst/opencode @ ${BASE_SHORT}"
if [ -d "$DIR/.git" ] && git -C "$DIR" rev-parse --git-dir >/dev/null 2>&1; then
  cd "$DIR"
  head="$(git rev-parse HEAD 2>/dev/null || true)"
  if [ "$head" = "$BASE" ] || git log --oneline -n 40 | grep -qi truthprobe; then
    note "переиспользую дерево $DIR (${head:0:7})"
  else
    note "дерево на ${head:0:7}, переключаю на $BASE_SHORT"
    if [ -n "$(git status --porcelain)" ] && [ "${TRUTHPROBE_ALLOW_DIRTY:-0}" != "1" ]; then
      die "в $DIR есть незакоммиченные изменения; закоммитьте их или задайте TRUTHPROBE_ALLOW_DIRTY=1"
    fi
    git fetch -q --depth 1 origin "$BASE"
    git reset -q --hard FETCH_HEAD
    git checkout -q -B truthprobe
  fi
else
  mkdir -p "$DIR"
  cd "$DIR"
  git init -q
  git remote add origin "$UPSTREAM" 2>/dev/null || git remote set-url origin "$UPSTREAM"
  git fetch -q --depth 1 origin "$BASE"
  git checkout -q -B truthprobe FETCH_HEAD
  note "склонировано в $(pwd)"
fi

if git log --oneline -n 40 | grep -qi truthprobe; then
  step "patch already applied, skipping"
else
  step "downloading $PATCH_NAME"
  PATCH="$(mktemp)"
  trap 'rm -f "$PATCH"' EXIT
  download "$REPO/$PATCH_NAME" "$PATCH"
  [ -s "$PATCH" ] || die "patch download failed: $REPO/$PATCH_NAME"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$PATCH_SHA256" "$PATCH" | sha256sum -c - >/dev/null 2>&1 ||
      die "контрольная сумма патча не совпала с закреплённой в скрипте"
  elif command -v shasum >/dev/null 2>&1; then
    [ "$(shasum -a 256 "$PATCH" | cut -d' ' -f1)" = "$PATCH_SHA256" ] ||
      die "контрольная сумма патча не совпала с закреплённой в скрипте"
  else
    note "sha256sum/shasum не найден — проверка контрольной суммы пропущена"
  fi

  step "checking patch"
  if ! git apply --check --whitespace=nowarn "$PATCH"; then
    die "патч не ложится на $BASE_SHORT; дерево не изменено"
  fi
  note "патч ложится на это дерево"

  if [ "$DRY_RUN" -eq 1 ]; then
    step "dry run: patch applies, tree left untouched"
    printf '\nНичего не изменено. Реальная установка:\n\n  bash install.sh --dir %s\n\n' "$DIR"
    exit 0
  fi

  step "applying patch"
  git config user.name >/dev/null 2>&1 || git config user.name "TruthProbe"
  git config user.email >/dev/null 2>&1 || git config user.email "truthprobe@localhost"
  if ! git am --whitespace=nowarn "$PATCH"; then
    git am --abort 2>/dev/null || true
    note "git am не смог, применяю как обычный diff"
    git apply --whitespace=nowarn "$PATCH"
  fi
  git log --oneline -1
fi

if [ -n "$SCORER" ]; then
  step "installing custom scorer weights"
  [ -f "$SCORER" ] || die "нет файла весов: $SCORER"
  mkdir -p .truthprobe
  cp "$SCORER" .truthprobe/weights.json
  note "веса: $(pwd)/.truthprobe/weights.json"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run: dependencies and build skipped"
  cat <<EOF

Готово к установке. Дальше:

  bash install.sh --dir $DIR     # поставить зависимости и проверить запуск

EOF
  exit 0
fi

step "installing dependencies (a few minutes)"
bun install

step "smoke test"
bun run --cwd packages/cli src/index.ts --version

bold "==> done"
cat <<EOF

Запуск:

  cd $DIR
  bun run --cwd packages/cli src/index.ts

Цифры уверенности:

  Под ответом появится строка вида "answer confidence 71% · uncertain".
  Провайдер проверяется сам: первый запрос к каждой модели идёт с logprobs,
  и если провайдер их отдаёт, со следующего запроса включаются проценты.
  Какие модели умеют — см. docs/MODEL-SUPPORT.md; проверить свою:

    python3 scripts/probe-logprobs.py --base <url>/v1 --key <key> --models a,b --md

  Вердикты: ~/.local/share/opencode/truthprobe/capabilities.json
  (Windows: %APPDATA%\\opencode\\truthprobe\\).
  Выключить: OPENCODE_TRUTHPROBE=off
EOF

if [ -n "$SCORER" ]; then
  cat <<EOF

Свои веса скорера включены навсегда для этой установки:

  export TRUTHPROBE_SCORER=linear:$(pwd)/.truthprobe/weights.json

(обучение весов: python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json)
EOF
fi
