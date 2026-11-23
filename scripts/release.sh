#!/usr/bin/env bash
#
# Публикует GitHub Release для уже существующего тега и вкладывает в него патч.
#
#   bash scripts/release.sh                      # тег = последний, нужен токен
#   bash scripts/release.sh v0.13.15             # конкретный тег
#   bash scripts/release.sh v0.13.15 --dry-run   # только показать, что будет сделано
#
# Токен берётся из GITHUB_TOKEN или GH_TOKEN; нужен scope, разрешающий создание
# релизов (`repo` для классического PAT). Скрипт ничего не собирает и не меняет в
# рабочем дереве: он проверяет, что патч совпадает с закреплённой суммой, берёт
# описание из верхней записи CHANGELOG.md и отправляет три запроса к API:
#
#   1. POST /repos/<owner>/<repo>/releases   — создать черновик-релиз;
#   2. POST .../releases/<id>/assets?...     — загрузить patches/truthprobe-0001.patch;
#   3. PATCH .../releases/<id>               — снять draft, когда ассет на месте.
#
# Повторный запуск для того же тега обновляет существующий релиз, а не падает.

set -euo pipefail
cd "$(dirname "$0")/.."

PATCH="patches/truthprobe-0001.patch"
ASSET_NAME="truthprobe-0001.patch"
DRY=0
TAG=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "неизвестный флаг: $arg" >&2; exit 2 ;;
    *) TAG="$arg" ;;
  esac
done

die() { echo "ошибка: $*" >&2; exit 1; }
say() { echo "== $*"; }

[ -f "$PATCH" ] || die "нет $PATCH — сначала make patch"
[ -f CHANGELOG.md ] || die "нет CHANGELOG.md"

if [ -z "$TAG" ]; then
  TAG=$(git describe --tags --abbrev=0 2>/dev/null) || die "нет тегов; укажите тег явно"
fi
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || die "тег $TAG не существует локально"
say "тег: $TAG ($(git rev-list -n1 "$TAG" | cut -c1-7))"

SHA=$(sha256sum "$PATCH" | cut -d' ' -f1)
PIN=$(sed -n 's/^PATCH_SHA256="\([0-9a-f]\{64\}\)".*/\1/p' install.sh)
[ -n "$PIN" ] || die "в install.sh нет PATCH_SHA256"
[ "$PIN" = "$SHA" ] || die "сумма патча $SHA не совпадает с пином install.sh ($PIN) — перегенерируйте патч"
say "sha256: $SHA (совпадает с install.sh)"

REMOTE=$(git remote get-url origin 2>/dev/null) || die "нет remote origin"
SLUG=$(printf '%s' "$REMOTE" | sed -E 's#^git@github\.com:##; s#^https?://github\.com/##; s#\.git$##; s#/$##')
case "$SLUG" in
  */*) ;;
  *) die "не разобрать owner/repo из $REMOTE" ;;
esac
say "репозиторий: $SLUG"

TOKEN=${GITHUB_TOKEN:-${GH_TOKEN:-}}
if [ "$DRY" -eq 0 ] && [ -z "$TOKEN" ]; then
  die "нет GITHUB_TOKEN/GH_TOKEN; для просмотра без токена добавьте --dry-run"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Описание релиза = запись CHANGELOG.md с заголовком "# <версия тега>". Если такой
# записи нет (тег старше журнала), берём верхнюю — и говорим об этом.
VER=${TAG#v}
awk -v ver="$VER" '
  /^# /{ if (found) exit; if ($2 == ver) {found=1; print; next} }
  found {print}
' CHANGELOG.md > "$TMP/notes.md"
if [ -s "$TMP/notes.md" ]; then
  say "описание: $(wc -l < "$TMP/notes.md" | tr -d ' ') строк из записи $VER в CHANGELOG.md"
else
  awk 'BEGIN{n=0} /^# /{n++} n==1{print} n==2{exit}' CHANGELOG.md > "$TMP/notes.md"
  [ -s "$TMP/notes.md" ] || die "не удалось взять описание из CHANGELOG.md"
  say "описание: записи $VER нет, беру верхнюю ($(wc -l < "$TMP/notes.md" | tr -d ' ') строк) — проверьте, что она про этот тег"
fi

python3 - "$TAG" "$TMP/notes.md" "$TMP/body.json" <<'PY'
import json, sys
tag, notes_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(notes_path, encoding="utf-8").read()
payload = {
    "tag_name": tag,
    "name": f"TruthProbe {tag}",
    "body": body,
    "draft": True,
    "prerelease": False,
}
open(out, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False))
PY

API="https://api.github.com/repos/$SLUG/releases"

if [ "$DRY" -eq 0 ]; then
  RELEASE_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
    "$API/tags/$TAG" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("id") or "")
except Exception:
    print("")')
else
  RELEASE_ID=""
fi

if [ -n "$RELEASE_ID" ]; then
  say "релиз для $TAG уже есть (id $RELEASE_ID) — обновляю описание"
  if [ "$DRY" -eq 0 ]; then
    curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
      -H "Content-Type: application/json" --data-binary "@$TMP/body.json" "$API/$RELEASE_ID" >/dev/null
  fi
  ASSET_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
    "$API/$RELEASE_ID/assets" | python3 -c 'import json,sys
for a in json.load(sys.stdin):
    if a.get("name") == "truthprobe-0001.patch":
        print(a["id"])
        break')
  if [ -n "$ASSET_ID" ]; then
    say "ассет уже загружен (id $ASSET_ID) — удаляю перед повторной загрузкой"
    [ "$DRY" -eq 1 ] || curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.github+json" "$API/assets/$ASSET_ID" >/dev/null
  fi
  UPLOAD="https://uploads.github.com/repos/$SLUG/releases/$RELEASE_ID/assets?name=$ASSET_NAME"
else
  if [ "$DRY" -eq 1 ]; then
    echo "   (dry-run: создали бы черновик через POST $API)"
    RELEASE_ID="<id>"
  else
    RELEASE_ID=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
      -H "Content-Type: application/json" --data-binary "@$TMP/body.json" "$API" | python3 -c 'import json,sys
d=json.load(sys.stdin)
if "id" not in d:
    sys.exit("ответ без id: %s" % d)
print(d["id"])')
    say "создан черновик релиза (id $RELEASE_ID)"
  fi
  UPLOAD="https://uploads.github.com/repos/$SLUG/releases/$RELEASE_ID/assets?name=$ASSET_NAME"
fi

say "загружаю $PATCH ($(wc -c < "$PATCH" | tr -d ' ') Б) как $ASSET_NAME"
if [ "$DRY" -eq 1 ]; then
  echo "   (dry-run: POST $UPLOAD с телом $PATCH)"
  echo "   (dry-run: PATCH $API/$RELEASE_ID, чтобы снять draft)"
  echo "== dry-run: ничего не отправлено"
  exit 0
fi

curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/octet-stream" --data-binary "@$PATCH" "$UPLOAD" \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
if "id" not in d:
    sys.exit("загрузка ассета не удалась: %s" % d)
print("== ассет загружен: %s, %s Б" % (d.get("name"), d.get("size")))'

curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" -d '{"draft": false}' "$API/$RELEASE_ID" \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
print("== релиз опубликован: %s" % d.get("html_url", "(нет html_url)"))'
