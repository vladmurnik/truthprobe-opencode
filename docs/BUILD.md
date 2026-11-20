# Сборка бинарей

Обычная сборка opencode компилирует всё в один исполняемый файл (`--single`), и патч переживает
это без изменений: `truthprobe` доезжает до базы и до TUI так же, как в `bun run src/index.ts`.

## Linux x64

```bash
OPENCODE_REPO=~/src/opencode bash scripts/build-linux.sh
# → dist/opencode-truthprobe-linux-x64
```

Эквивалент вручную:

```bash
cd packages/cli
OPENCODE_TARGET=linux-x64 OPENCODE_RELEASE=1 \
  bun run script/build.ts --single --skip-install --skip-web-ui
```

Проверено: **216 MB**, ~13 s, бинарь отвечает на мок-провайдере и пишет `truthprobe` в базу.

## Windows x64

```bash
OPENCODE_REPO=~/src/opencode bash scripts/build-windows.sh
# → dist/opencode-truthprobe-windows-x64.exe
```

Проверено: **233 MB** (`sha256 396be271…`), `opencode.exe --version` → `v0.0.0-feat-truthprobe-…`,
ответ на мок-провайдере с `status: "ok", score: 0.417, first.score: 0.708, flagged: 1`.

### Если собираешь Windows-бинарь из Linux/WSL

`bun install` на Linux не скачивает платформенные optional-зависимости чужой ОС, а сборщик их
требует (`@opencode/pty-win32-x64`, `@opentui/core-win32-x64`, `@parcel/watcher-win32-x64`,
`@ff-labs/fff-bin-win32-x64` и остальные). Скрипт решает это разом:

```bash
OPENCODE_REPO=~/src/opencode python3 scripts/install-cross-deps.py win32
```

Он читает `optionalDependencies` **всех** пакетов в bun-хранилище (включая scoped-каталоги),
скачивает недостающие win32-пакеты с npm и распаковывает рядом с их родителем, как это делает
сам bun. Идемпотентен: повторный запуск ничего не качает.

Подводные камни, на которые уже наступили:

- `pkg.parent` у scoped-пакета — это каталог `@scope`, а не `node_modules`; распаковка
  «рядом с родителем» без этой поправки создаёт `@scope/@scope/name`.
- Часть зависимостей (`@parcel/watcher-win32-x64`) объявлена не в корневом `package.json`,
  а внутри `.bun/@parcel+watcher@2.5.1/node_modules/@parcel/watcher`, поэтому обход должен быть
  рекурсивным, а не по одному уровню.

## Кросс-сборка macOS

Не проверялась. По аналогии: `install-cross-deps.py darwin` + `OPENCODE_TARGET=darwin-arm64`.
