# TruthProbe — short commands for development.
#
# All `make` does is call the scripts in `scripts/`. That way one and the same
# set works on Linux/macOS/WSL (bash) and in PowerShell (see scripts/*.ps1).
#
#   make setup     set up the patched opencode tree and install the dependencies
#   make test      unit tests of the repository (no opencode clone, ~2 s)
#   make verify    tests + check that the patch applies to a clean base
#   make docs-check  verify the numbers in the docs (commits/files/bytes) against the patch itself
#   make patch     regenerate patches/truthprobe-0001.patch from the dev tree
#   make preview   start the mock provider and run one request through the CLI
#   make desktop   build the desktop app (needs bun installed)
#   make desktop-install  install the built app and reset the CLI cache
#                  (FROM=<win-unpacked> TO=<directory> bash scripts/install-desktop.sh)
#   make release   publish a GitHub Release for the latest tag and attach the patch
#                  (needs GITHUB_TOKEN; without it: bash scripts/release.sh --dry-run)
#   make clean     remove the working tree created by setup
#   make eval      AUROC/ECE/Brier over labeled rows (data/eval-fixture.jsonl)
#   make weights   train weights on data/rows-lie-vs-truth.jsonl (needs python3)
#   make data      collect new rows from the gateway (needs COLLECT_URL and a key)
#
# Variables:
#   TP_DIR   where to clone opencode (default .worktree/opencode)
#   BASE     the sst/opencode commit the patch is cut against (= TRUTHPROBE_BASE)
#   WEIGHTS  JSON with weights for the linear scorer (make eval WEIGHTS=weights.json)

SHELL := bash
BASE ?= $(or $(TRUTHPROBE_BASE),007afb1b0c8a36dff93d7945909d4e976545ba95)
export TRUTHPROBE_BASE := $(BASE)
TP_DIR ?= .worktree/opencode

.PHONY: help setup test verify docs-check patch preview desktop desktop-install release clean eval weights data

help:
	@sed -n '2,20p' Makefile

setup:
	bash scripts/dev-setup.sh --dir "$(TP_DIR)"

test:
	bun test test

verify: test docs-check
	bash scripts/dev-setup.sh --check --dir "$(TP_DIR)"

docs-check:
	bash scripts/check-docs.sh

patch:
	bash scripts/make-patch.sh --from "$(TP_DIR)"

preview:
	bash scripts/preview.sh

desktop:
	bash scripts/build-desktop.sh

desktop-install:
	bash scripts/install-desktop.sh $(if $(FROM),--from $(FROM),) $(if $(TO),--to $(TO),)

release:
	bash scripts/release.sh $(if $(TAG),$(TAG),) $(if $(DRY),--dry-run,)

clean:
	rm -rf "$(TP_DIR)" scripts/.mock.log
	@echo "removed: $(TP_DIR)"

eval:
	python3 scripts/evaluate.py data/eval-fixture.jsonl $(if $(WEIGHTS),--weights $(WEIGHTS),)

weights:
	python3 scripts/calibrate.py data/rows-lie-vs-truth.jsonl --fit --by-model --out data/weights.json
	@echo "done: data/weights.json — enable it like this: TRUTHPROBE_SCORER=linear:data/weights.json"

data:
	python3 scripts/collect.py --url "$${COLLECT_URL:-http://127.0.0.1:3001/v1}" \
		--provider "$${COLLECT_PROVIDER:-freepi}" \
		--models "$${COLLECT_MODELS:-particle,deepseek-v4.1-flash,deepseek-v4-flash,glm-5.3-flash}" \
		--prompts data/qa-hard2-bank.jsonl --auto-label data/qa-hard2-bank.jsonl \
		--samples "$${COLLECT_SAMPLES:-4}" --temperature 0.8 --max-tokens 200 --workers 6 \
		--out "$${COLLECT_OUT:-data/rows-new.jsonl}" --resume
	@echo "next: python3 scripts/audit-bank.py data/rows-new.jsonl data/qa-hard2-bank.jsonl"
