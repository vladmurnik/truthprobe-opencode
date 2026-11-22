# TruthProbe — короткие команды для разработки.
#
# Всё, что делает `make`, — это вызов скриптов из `scripts/`. Так один и тот же
# набор работает в Linux/macOS/WSL (bash) и в PowerShell (см. scripts/*.ps1).
#
#   make setup     развернуть пропатченное дерево opencode и поставить зависимости
#   make test      юнит-тесты репозитория (без клонирования opencode, ~2 с)
#   make verify    тесты + проверка, что патч ложится на чистую базу
#   make patch     перегенерировать patches/truthprobe-0001.patch из dev-дерева
#   make preview   поднять мок-провайдер и прогнать один запрос через CLI
#   make desktop   собрать desktop-приложение (нужен установленный bun)
#   make desktop-install  поставить собранное приложение и сбросить кеш CLI
#                  (FROM=<win-unpacked> TO=<каталог> bash scripts/install-desktop.sh)
#   make clean     удалить рабочее дерево, собранное setup
#   make eval      AUROC/ECE/Brier по размеченным строкам (data/eval-fixture.jsonl)
#   make weights   обучить веса на data/rows-lie-vs-truth.jsonl (нужен python3)
#   make data      собрать новые строки с шлюза (нужен COLLECT_URL и ключ)
#
# Переменные:
#   TP_DIR   куда клонировать opencode (по умолчанию .worktree/opencode)
#   BASE     коммит sst/opencode, на который нарезан патч (= TRUTHPROBE_BASE)
#   WEIGHTS  JSON с весами для linear-скорера (make eval WEIGHTS=weights.json)

SHELL := bash
BASE ?= $(or $(TRUTHPROBE_BASE),007afb1b0c8a36dff93d7945909d4e976545ba95)
export TRUTHPROBE_BASE := $(BASE)
TP_DIR ?= .worktree/opencode

.PHONY: help setup test verify patch preview desktop desktop-install clean eval weights data

help:
	@sed -n '2,20p' Makefile

setup:
	bash scripts/dev-setup.sh --dir "$(TP_DIR)"

test:
	bun test test

verify: test
	bash scripts/dev-setup.sh --check --dir "$(TP_DIR)"

patch:
	bash scripts/make-patch.sh --from "$(TP_DIR)"

preview:
	bash scripts/preview.sh

desktop:
	bash scripts/build-desktop.sh

desktop-install:
	bash scripts/install-desktop.sh $(if $(FROM),--from $(FROM),) $(if $(TO),--to $(TO),)

clean:
	rm -rf "$(TP_DIR)" scripts/.mock.log
	@echo "удалено: $(TP_DIR)"

eval:
	python3 scripts/evaluate.py data/eval-fixture.jsonl $(if $(WEIGHTS),--weights $(WEIGHTS),)

weights:
	python3 scripts/calibrate.py data/rows-lie-vs-truth.jsonl --fit --by-model --out data/weights.json
	@echo "готово: data/weights.json — включить так: TRUTHPROBE_SCORER=linear:data/weights.json"

data:
	python3 scripts/collect.py --url "$${COLLECT_URL:-http://127.0.0.1:3001/v1}" \
		--provider "$${COLLECT_PROVIDER:-freepi}" \
		--models "$${COLLECT_MODELS:-particle,deepseek-v4.1-flash,deepseek-v4-flash,glm-5.3-flash}" \
		--prompts data/qa-hard2-bank.jsonl --auto-label data/qa-hard2-bank.jsonl \
		--samples "$${COLLECT_SAMPLES:-4}" --temperature 0.8 --max-tokens 200 --workers 6 \
		--out "$${COLLECT_OUT:-data/rows-new.jsonl}" --resume
	@echo "дальше: python3 scripts/audit-bank.py data/rows-new.jsonl data/qa-hard2-bank.jsonl"
