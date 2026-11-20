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
#   make clean     удалить рабочее дерево, собранное setup
#
# Переменные:
#   TP_DIR   куда клонировать opencode (по умолчанию .worktree/opencode)
#   BASE     коммит sst/opencode, на который нарезан патч

SHELL := bash
BASE := 007afb1b0c8a36dff93d7945909d4e976545ba95
TP_DIR ?= .worktree/opencode

.PHONY: help setup test verify patch preview desktop clean

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

clean:
	rm -rf "$(TP_DIR)" scripts/.mock.log
	@echo "удалено: $(TP_DIR)"
