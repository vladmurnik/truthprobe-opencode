#!/usr/bin/env bash
#
# Publishes a GitHub Release for an already existing tag and attaches the patch to it.
#
#   bash scripts/release.sh                      # tag = the latest one, a token is required
#   bash scripts/release.sh v0.13.15             # a specific tag
#   bash scripts/release.sh v0.13.15 --dry-run   # only show what would be done
#
# The token comes from GITHUB_TOKEN or GH_TOKEN; it needs a scope that allows creating
# releases (`repo` for a classic PAT). The script builds nothing and changes nothing in
# the working tree: it verifies that the patch matches the pinned hash, takes the
# description from the top CHANGELOG.md entry and sends three API requests:
#
#   1. POST /repos/<owner>/<repo>/releases   — create a draft release;
#   2. POST .../releases/<id>/assets?...     — upload patches/truthprobe-0001.patch;
#   3. PATCH .../releases/<id>               — drop the draft once the asset is in place.
#
# A repeated run for the same tag updates the existing release instead of failing.

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
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) TAG="$arg" ;;
  esac
done

die() { echo "error: $*" >&2; exit 1; }
say() { echo "== $*"; }

[ -f "$PATCH" ] || die "no $PATCH — run make patch first"
[ -f CHANGELOG.md ] || die "no CHANGELOG.md"

if [ -z "$TAG" ]; then
  TAG=$(git describe --tags --abbrev=0 2>/dev/null) || die "no tags; specify the tag explicitly"
fi
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || die "tag $TAG does not exist locally"
say "tag: $TAG ($(git rev-list -n1 "$TAG" | cut -c1-7))"

SHA=$(sha256sum "$PATCH" | cut -d' ' -f1)
PIN=$(sed -n 's/^PATCH_SHA256="\([0-9a-f]\{64\}\)".*/\1/p' install.sh)
[ -n "$PIN" ] || die "there is no PATCH_SHA256 in install.sh"
[ "$PIN" = "$SHA" ] || die "patch hash $SHA does not match the install.sh pin ($PIN) — regenerate the patch"
say "sha256: $SHA (matches install.sh)"

REMOTE=$(git remote get-url origin 2>/dev/null) || die "no origin remote"
SLUG=$(printf '%s' "$REMOTE" | sed -E 's#^git@github\.com:##; s#^https?://github\.com/##; s#\.git$##; s#/$##')
case "$SLUG" in
  */*) ;;
  *) die "cannot parse owner/repo from $REMOTE" ;;
esac
say "repository: $SLUG"

TOKEN=${GITHUB_TOKEN:-${GH_TOKEN:-}}
if [ "$DRY" -eq 0 ] && [ -z "$TOKEN" ]; then
  die "no GITHUB_TOKEN/GH_TOKEN; to preview without a token add --dry-run"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# The release description = the CHANGELOG.md entry headed "# <tag version>". If there is no such
# entry (the tag predates the changelog), take the top one — and say so.
VER=${TAG#v}
awk -v ver="$VER" '
  /^# /{ if (found) exit; if ($2 == ver) {found=1; print; next} }
  found {print}
' CHANGELOG.md > "$TMP/notes.md"
if [ -s "$TMP/notes.md" ]; then
  say "description: $(wc -l < "$TMP/notes.md" | tr -d ' ') lines from the $VER entry in CHANGELOG.md"
else
  awk 'BEGIN{n=0} /^# /{n++} n==1{print} n==2{exit}' CHANGELOG.md > "$TMP/notes.md"
  [ -s "$TMP/notes.md" ] || die "could not take the description from CHANGELOG.md"
  say "description: there is no $VER entry, taking the top one ($(wc -l < "$TMP/notes.md" | tr -d ' ') lines) — check that it is about this tag"
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
  say "a release for $TAG already exists (id $RELEASE_ID) — updating the description"
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
    say "asset already uploaded (id $ASSET_ID) — deleting it before re-uploading"
    [ "$DRY" -eq 1 ] || curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.github+json" "$API/assets/$ASSET_ID" >/dev/null
  fi
  UPLOAD="https://uploads.github.com/repos/$SLUG/releases/$RELEASE_ID/assets?name=$ASSET_NAME"
else
  if [ "$DRY" -eq 1 ]; then
    echo "   (dry-run: would have created a draft via POST $API)"
    RELEASE_ID="<id>"
  else
    RELEASE_ID=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
      -H "Content-Type: application/json" --data-binary "@$TMP/body.json" "$API" | python3 -c 'import json,sys
d=json.load(sys.stdin)
if "id" not in d:
    sys.exit("response without id: %s" % d)
print(d["id"])')
    say "draft release created (id $RELEASE_ID)"
  fi
  UPLOAD="https://uploads.github.com/repos/$SLUG/releases/$RELEASE_ID/assets?name=$ASSET_NAME"
fi

say "uploading $PATCH ($(wc -c < "$PATCH" | tr -d ' ') B) as $ASSET_NAME"
if [ "$DRY" -eq 1 ]; then
  echo "   (dry-run: POST $UPLOAD with the body $PATCH)"
  echo "   (dry-run: PATCH $API/$RELEASE_ID to drop the draft)"
  echo "== dry-run: nothing was sent"
  exit 0
fi

curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/octet-stream" --data-binary "@$PATCH" "$UPLOAD" \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
if "id" not in d:
    sys.exit("asset upload failed: %s" % d)
print("== asset uploaded: %s, %s B" % (d.get("name"), d.get("size")))'

curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" -d '{"draft": false}' "$API/$RELEASE_ID" \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
print("== release published: %s" % d.get("html_url", "(no html_url)"))'
