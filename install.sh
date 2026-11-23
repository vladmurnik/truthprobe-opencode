#!/usr/bin/env bash
#
# TruthProbe installer for opencode.
#
#   curl -fsSL https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.sh | bash
#
#   bash install.sh                          # into ./opencode-truthprobe
#   bash install.sh ~/src/opencode-tp        # into a directory of your choice
#   bash install.sh --dir ~/src/tp --dry-run # only check that the patch applies
#   bash install.sh --uninstall              # revert the tree to the base commit
#   bash install.sh --scorer weights.json    # install your own scorer weights
#
# What it does:
#   1. clones sst/opencode at the commit the patch is cut against;
#   2. applies patches/truthprobe-0001.patch (git am, falling back to git apply);
#   3. installs dependencies and prints the version;
#   4. with --scorer, copies the weights and prints the environment line.
#
# Requires: git, bun (https://bun.sh), curl or wget. Nothing outside the install directory
# is touched: the git identity is set locally when needed.
set -euo pipefail

BASE=007afb1b0c8a36dff93d7945909d4e976545ba95
BASE_SHORT=007afb1
UPSTREAM=https://github.com/sst/opencode.git
REPO=https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master
RELEASES=https://github.com/vladmurnik/truthprobe-opencode/releases/latest/download
PATCH_NAME=patches/truthprobe-0001.patch
# The patch is fetched from the branch and its code is then executed (bun install + build),
# so we verify the bytes against a pinned sum instead of trusting the URL.
PATCH_SHA256="4436386b5457eb2cb2187054c064187e7e70e8bcda3d99c4214ee392df606f34"

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
  download() { curl -fsSL --retry 3 --retry-delay 2 --retry-connrefused "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  # wget --tries only covers network errors, not an HTTP 503 from the CDN,
  # so the retry loop is explicit here.
  download() {
    local attempt=1
    while [ "$attempt" -le 3 ]; do
      wget -q --timeout=20 --tries=1 -O "$2" "$1" && [ -s "$2" ] && return 0
      attempt=$((attempt + 1))
      sleep 2
    done
    return 1
  }
else
  die "curl or wget is required"
fi

# raw.githubusercontent.com occasionally answers 503 Backend.max_conn reached, which
# killed the Windows CI job. The release asset serves the same bytes, so a second
# source is enough; the pinned checksum still decides whether the file is trusted.
fetch_patch() {
  download "$REPO/$PATCH_NAME" "$1" 2>/dev/null && [ -s "$1" ] && return 0
  note "raw.githubusercontent.com failed, trying the release asset"
  download "$RELEASES/${PATCH_NAME##*/}" "$1" 2>/dev/null && [ -s "$1" ]
}

# The patch is not merely copied: `git am` and the following build execute it. So
# a missing sha256sum/shasum is an environment error, not a reason to skip verification.
# GitHub does not always serve an unadvertised object: `--depth 1` for a specific SHA
# can answer "Server does not allow request for unadvertised object". Then
# we fetch the whole history - the base is only needed for verification anyway.
fetch_base() {
  git fetch -q --depth 1 origin "$BASE" 2>/dev/null && return 0
  git fetch -q origin || return 1
  git cat-file -e "$BASE^{commit}" 2>/dev/null
}

verify_patch() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$PATCH_SHA256" "$1" | sha256sum -c - >/dev/null 2>&1 ||
      die "patch checksum does not match the one pinned in this script"
  elif command -v shasum >/dev/null 2>&1; then
    [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" = "$PATCH_SHA256" ] ||
      die "patch checksum does not match the one pinned in this script"
  else
    die "sha256sum or shasum is required: the patch cannot be verified without one"
  fi
}
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
    note "no truthprobe commits found - the patch looks already reverted"
    exit 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    step "dry run: would reset --hard $BASE_SHORT, tree left untouched"
    exit 0
  fi
  if [ -n "$(git status --porcelain)" ] && [ "${TRUTHPROBE_ALLOW_DIRTY:-0}" != "1" ]; then
    die "$DIR has uncommitted changes; commit them or set TRUTHPROBE_ALLOW_DIRTY=1"
  fi
  note "reverting the patch commits; the tree returns to $BASE_SHORT"
  note "uncommitted edits to tracked files will be lost; the opencode config and data are untouched"
  git reset --hard "$BASE"
  git log --oneline -1
  bold "==> patch reverted"
  exit 0
fi

# The check must not touch $DIR: fetch + reset --hard + checkout -B move
# the branch and wipe local commits, and a "dry run" after that is no longer a check.
if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run: checking $PATCH_NAME against $BASE_SHORT in a temporary clone"
  CHECK="$(mktemp -d)"
  PATCH="$(mktemp)"
  trap 'rm -rf "$CHECK"; rm -f "$PATCH"' EXIT
  cd "$CHECK"
  git init -q
  git remote add origin "$UPSTREAM"
  fetch_base || die "failed to download $BASE_SHORT"
  git checkout -q -B truthprobe FETCH_HEAD
  fetch_patch "$PATCH" || die "patch download failed: $REPO/$PATCH_NAME and $RELEASES/${PATCH_NAME##*/}"
  verify_patch "$PATCH"
  if ! git apply --check --whitespace=nowarn "$PATCH"; then
    die "the patch does not apply to $BASE_SHORT"
  fi
  step "dry run: patch applies, $DIR untouched"
  printf '\nNothing was changed. Real install:\n\n  bash install.sh --dir %s\n\n' "$DIR"
  exit 0
fi

step "fetching sst/opencode @ ${BASE_SHORT}"
if [ -d "$DIR/.git" ] && git -C "$DIR" rev-parse --git-dir >/dev/null 2>&1; then
  cd "$DIR"
  head="$(git rev-parse HEAD 2>/dev/null || true)"
  if [ "$head" = "$BASE" ] || git log --oneline -n 40 | grep -qi truthprobe; then
    note "reusing the tree at $DIR (${head:0:7})"
  else
    note "tree at ${head:0:7}, switching to $BASE_SHORT"
    if [ -n "$(git status --porcelain)" ] && [ "${TRUTHPROBE_ALLOW_DIRTY:-0}" != "1" ]; then
      die "$DIR has uncommitted changes; commit them or set TRUTHPROBE_ALLOW_DIRTY=1"
    fi
    fetch_base || die "failed to download $BASE_SHORT"
    git reset -q --hard FETCH_HEAD
    git checkout -q -B truthprobe
  fi
else
  mkdir -p "$DIR"
  cd "$DIR"
  git init -q
  git remote add origin "$UPSTREAM" 2>/dev/null || git remote set-url origin "$UPSTREAM"
  fetch_base || die "failed to download $BASE_SHORT"
  git checkout -q -B truthprobe FETCH_HEAD
  note "cloned into $(pwd)"
fi

if git log --oneline -n 40 | grep -qi truthprobe; then
  step "patch already applied, skipping"
else
  step "downloading $PATCH_NAME"
  PATCH="$(mktemp)"
  trap 'rm -f "$PATCH"' EXIT
  fetch_patch "$PATCH" || die "patch download failed: $REPO/$PATCH_NAME and $RELEASES/${PATCH_NAME##*/}"
  verify_patch "$PATCH"

  step "checking patch"
  if ! git apply --check --whitespace=nowarn "$PATCH"; then
    die "the patch does not apply to $BASE_SHORT; the tree is unchanged"
  fi
  note "the patch applies to this tree"

  step "applying patch"
  git config user.name >/dev/null 2>&1 || git config user.name "TruthProbe"
  git config user.email >/dev/null 2>&1 || git config user.email "truthprobe@localhost"
  if ! git am --whitespace=nowarn "$PATCH"; then
    git am --abort 2>/dev/null || true
    note "git am failed, applying as a plain diff"
    git apply --whitespace=nowarn "$PATCH"
  fi
  git log --oneline -1
fi

if [ -n "$SCORER" ]; then
  step "installing custom scorer weights"
  [ -f "$SCORER" ] || die "weights file not found: $SCORER"
  mkdir -p .truthprobe
  cp "$SCORER" .truthprobe/weights.json
  note "weights: $(pwd)/.truthprobe/weights.json"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run: dependencies and build skipped"
  cat <<EOF

Ready to install. Next:

  bash install.sh --dir $DIR     # install dependencies and check that it runs

EOF
  exit 0
fi

step "installing dependencies (a few minutes)"
bun install

step "smoke test"
bun run --cwd packages/cli src/index.ts --version

bold "==> done"
cat <<EOF

Run:

  cd $DIR
  bun run --cwd packages/cli src/index.ts

Confidence numbers:

  Under an answer a line like "answer confidence 71% - uncertain" appears.
  The provider is probed automatically: the first request to each model asks for logprobs,
  and if the provider returns them, percentages start with the next request.
  Which models support it - see docs/MODEL-SUPPORT.md; to probe yours:

    python3 scripts/probe-logprobs.py --base <url>/v1 --key <key> --models a,b --md

  Verdicts: ~/.local/share/opencode/truthprobe/capabilities.json
  (Windows: %APPDATA%\\opencode\\truthprobe\\).
  Disable: OPENCODE_TRUTHPROBE=off
EOF

if [ -n "$SCORER" ]; then
  cat <<EOF

Your scorer weights are enabled permanently for this install:

  export TRUTHPROBE_SCORER=linear:$(pwd)/.truthprobe/weights.json

(fitting weights: python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json)
EOF
fi
