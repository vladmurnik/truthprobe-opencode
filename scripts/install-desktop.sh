#!/usr/bin/env bash
# Ставит собранное desktop-приложение TruthProbe и сбрасывает кеш CLI.
#
#   bash scripts/install-desktop.sh --from <win-unpacked> [--to <каталог>] [--dry-run]
#
# Зачем нужен сброс кеша: приложение кеширует встроенный CLI в
# %APPDATA%\ai.truthprobe.desktop\cli\<version>-x64 и переиспользует его, пока строка версии
# не изменится. Если штамп не пересобрали, установка молча продолжает работать старым CLI —
# ровно это и случилось со сборкой 22.11.2026.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
FROM="${OPENCODE_REPO:-$ROOT/.worktree/opencode}/packages/desktop/dist/win-unpacked"
TO=""
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM=$2; shift 2 ;;
    --to) TO=$2; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "error: unknown option $1" >&2; exit 2 ;;
  esac
done

WINPROFILE=""
if [ -x /mnt/c/Windows/System32/cmd.exe ]; then
  WINPROFILE=$(/mnt/c/Windows/System32/cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r' || true)
fi

if [ -z "$TO" ]; then
  case "$WINPROFILE" in
    [A-Za-z]:\\*)
      TO="/mnt/c/${WINPROFILE#*:}"
      TO=$(printf '%s' "$TO" | tr '\\' '/' | tr -s '/')/AppData/Local/Programs/TruthProbe
      ;;
    *) TO="$HOME/.local/opt/TruthProbe" ;;
  esac
fi

[ -f "$FROM/TruthProbe.exe" ] || [ -f "$FROM/truthprobe" ] || {
  echo "error: в $FROM нет собранного приложения — сначала bash scripts/build-desktop.sh --win" >&2
  exit 1
}

CLI_CACHE=""
case "$WINPROFILE" in
  [A-Za-z]:\\*)
    CLI_CACHE="/mnt/c/${WINPROFILE#*:}/AppData/Roaming/ai.truthprobe.desktop/cli"
    CLI_CACHE=$(printf '%s' "$CLI_CACHE" | tr '\\' '/' | tr -s '/')
    ;;
esac

STAMP=$( [ -f "$FROM/resources/opencode-cli.version" ] && tr -d '\r\n' <"$FROM/resources/opencode-cli.version" || echo "нет штампа" )

echo "== откуда: $FROM"
echo "== куда:   $TO"
echo "== CLI:    $STAMP"
echo "== кеш CLI: ${CLI_CACHE:-не найден}"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "== dry run: копирование и сброс кеша не выполнялись"
  exit 0
fi

# Приложение держит exe и resources открытыми, поэтому сначала закрываем его.
# Одиночные слэши обязательны: WSL передаёт `//IM` в Windows буквально, и taskkill
# отвечает «Invalid argument/option» — установка падала на заблокированных файлах.
if command -v taskkill.exe >/dev/null 2>&1; then
  taskkill.exe /IM TruthProbe.exe /F >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    tasklist.exe /FI "IMAGENAME eq TruthProbe.exe" 2>/dev/null | grep -q TruthProbe || break
    sleep 1
  done
fi

mkdir -p "$TO"
cp -a "$FROM/." "$TO/"
echo "== установлено: $(ls -la "$TO/TruthProbe.exe" 2>/dev/null || ls -la "$TO/truthprobe" 2>/dev/null)"

if [ -n "$CLI_CACHE" ] && [ -d "$CLI_CACHE" ]; then
  rm -rf "$CLI_CACHE"/* || true
  echo "== кеш CLI очищен: приложение развернёт $STAMP при следующем запуске"
fi
