# Валидация

Всё ниже — измеренное, не задуманное. Если чего-то не проверяли, это написано отдельным разделом.

База: `sst/opencode` @ `007afb1`. Ветка `feat/truthprobe`, семь коммитов:

| Коммит | Что |
| --- | --- |
| `3ccda6c` | feat(truthprobe): score answers from token logprobs |
| `a9db0da` | fix(tui): apply truthprobe metadata from session.text.ended events |
| `2870f64` | test(truthprobe): cover segmentation, scoring and protocol parsing |
| `f043425` | feat(truthprobe): probe providers and enable logprobs automatically |
| `3126939` | feat(truthprobe): show confidence in the desktop session UI |
| `335305a` | feat(truthprobe): list doubtful sentences in the desktop footer |
| `6017d75` | feat(desktop): let a fork brand the desktop app |
| `a478531` | fix(truthprobe): keep logprobs that arrive without text, align tokens, always publish a verdict |
| `5a335e3` | fix(truthprobe): say so when tokens do not match the answer text |

Итог: **38 файлов, +2280 / −40**, девять коммитов. Патч — `patches/truthprobe-0001.patch` (3735 строк, `git am`).

## 1. Слои патча

| # | Файл | Роль |
| --- | --- | --- |
| 1 | `packages/schema/src/truthprobe.ts` | `Truthprobe.Info`: статус, score, risk, first, sentences, flagged |
| 2 | `packages/schema/src/index.ts` | экспорт модуля |
| 3 | `packages/schema/src/model.ts` | `capabilities.logprobs?: boolean` |
| 4 | `packages/schema/src/session-message.ts` | `truthprobe` в `AssistantText` |
| 5 | `packages/schema/src/session-event.ts` | `truthprobe` в durable `session.text.ended` |
| 6 | `packages/ai/src/schema/options.ts` | тот же флаг в `Capabilities`, который видит `request.model` |
| 7 | `packages/ai/src/protocols/openai-chat.ts` | `logprobs`/`top_logprobs` в запросе, разбор `choices[i].logprobs` |
| 8 | `packages/core/src/truthprobe/{types,sentences,score}.ts` | чистая математика |
| 9 | `packages/core/src/session/runner/publish-llm-event.ts` | накопление токенов и публикация score |
| 10 | `packages/core/src/session/message-updater.ts` | перенос поля в парт |
| 11 | `packages/client/src/solid/data.ts` | живое обновление стора без потери поля |
| 12 | `packages/client/**` (generated) | типы API |
| 13 | `packages/tui/src/routes/session/message-parts.tsx` | бейдж и блок спорных предложений |
| 14 | `packages/core/test/truthprobe.test.ts` | 45 тестов |
| 15 | `packages/ai/test/truthprobe.test.ts` | 8 тестов |
| 16 | `packages/core/src/plugin/truthprobe.ts` | автопроверка провайдера по `http.request` |
| 17 | `packages/core/src/truthprobe/capability.ts` | статусы, TTL, классификация, кэш |
| 18 | `packages/ai/src/protocols/truthprobe-capability.ts` | чтение кэша вердиктов в протоколе |
| 19 | `packages/core/src/model.ts` | `mergeCapabilities` проносит `logprobs` |
| 20 | `packages/core/test/truthprobe-capability.test.ts` | 32 теста |
| 21 | `packages/session-ui/src/message/message-content.tsx` | чип `confidence` в футере ответа (desktop и веб) |
| 22 | `packages/session-ui/src/timeline-next/tools/assistant-content.tsx`, `packages/session-ui/src/message/current-message.tsx` | проброс `truthprobe` в текстовый парт |
| 23 | `packages/session-ui/src/message/doubtful.ts` | список спорных предложений для футера |
| 24 | `packages/session-ui/src/message/doubtful.test.ts` | 6 тестов маппинга |

## 2. Тесты

```
45 pass / 0 fail   104 expect   packages/core/test/truthprobe.test.ts
32 pass / 0 fail    70 expect   packages/core/test/truthprobe-capability.test.ts
 8 pass / 0 fail    23 expect   packages/ai/test/truthprobe.test.ts
 6 pass / 0 fail    14 expect   packages/session-ui/src/message/doubtful.test.ts
```

Что покрыто:

- `isContentToken`: пробелы, пунктуация, символы, `minChars`.
- `normalizedEntropy` / `phi`: уверенный токен, деградация без top-K, два равных кандидата,
  монотонность по вероятности победителя, нормировка на `ln K`, отсечение `topK`,
  игнорирование `NaN`/`-Infinity`, кламп в 0..1.
- `tokensWithOffsets`: накопление смещений.
- `codeRanges` / `splitSentences`: десятичные дроби, сокращения (`т.е.`, `e.g.`, `etc.`, `См.`),
  многоточие, CJK без пробелов, пустая строка, закрытый/незакрытый fence, пустой ввод,
  совпадение `start`/`end` с исходной строкой, последовательность индексов.
- `scoreAnswer`: обе деградации (`no logprobs`, `no content tokens`), `partial` при дрейфе,
  `risk = 1 − score`, порядок «уверенный > сомнительный», выбор первого содержательного токена,
  изоляция предложений, `minLp`/`meanLp`, настройка порога, `globalWeight = 1`, детерминизм,
  края (score 1 и risk ≈ 1), совпадение границ с сегментатором.
- Протокол: приоритет `capabilities.logprobs` над env, значения env (`1/on/true` vs остальные),
  состав полей `truthprobeBody`, разбор `content[] → {token, logprob, top}`, сохранение `logprob: 0`,
  отсутствие `top` при пустом `top_logprobs`.

Что покрыто (автопроверка, `truthprobe-capability.test.ts`):

- `ttl`: 7 дней для `ok`/`ignored`/`rejected`/`unsupported`, час для `auth`, ноль для `error`.
- `fresh` / `enabled`: границы TTL, запись из будущего, `error` никогда не свежий, включает только `ok`.
- `parse` / `serialize`: битый JSON, `null`, чужие и неполные записи отбрасываются, стабильный порядок
  ключей, `setEntry` не мутирует вход.
- `probeBody`: ровно один токен, фиксированный `ping`, `logprobs: true`, настраиваемый `topK`.
- `classify`: `ok` только при непустом `logprobs.content`; `ignored` при 200 без поля; `auth` на 401/403;
  `error` на 429/5xx (не кэшируется); `rejected` только если в 400/422 упомянут `logprob`;
  `unsupported` на 404/405/501 и на «другую» 400.
- `originOf` / `modelFromBody`: в кэш не попадают путь, query и ключи; модель читается из тела.

Что покрыто (desktop, `doubtful.test.ts`):

- `percentOf`: округление, нечисла и `null` дают `?`.
- `doubtfulSentences`: пустая проба и `status: "unavailable"` дают пустой список, берутся только
  предложения с `flag`, нумерация начинается с 1, текст обрезается до 96 символов, битые `i`/`score`
  не ломают рендер.

## 3. Полные прогоны

| Пакет | Команда | Результат |
| --- | --- | --- |
| core (весь) | `bun run script/test.ts` | **7 272 pass / 350 skip / 39 fail**, 96 831 expect, 328 файлов, 205 s — все 39 падений чужие, см. §4 |
| ai (весь) | `bun test --timeout 30000` | **2 276 pass / 0 fail / 29 skip**, 9 377 expect, 7.7 s |
| schema | `bun test` | **95 pass / 0 fail**, 231 ms |
| регрессия сессий | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail**, 30 s |
| типизация | schema / ai / core / client / tui | 132 / 357+322 / 2 030 / 181 / 1 942 файла, 0 ошибок |
| типизация UI | session-ui / app / desktop | 382 / 2 445 / 3 569 файлов (desktop — 2 проекта), 0 ошибок |

Отдельно проверено, что **патч самодостаточен**: на чистом worktree `007afb1` (37 файлов,
+2139/−34, без моих рабочих копий) `git am patches/truthprobe-0001.patch` применяется без
конфликтов, `typecheck` пакетов ai и core — 0 ошибок, тесты в применённом дереве — **45 pass / 0 fail**,
**32 pass / 0 fail** и **8 pass / 0 fail**. То есть зелёные тесты не зависят от локального состояния
моей машины.

## 4. Про 39 падений в полном прогоне core

39 падений распадаются на две группы, и обе **воспроизводятся на чистой базе `007afb1` без патча**:

| Группа | Провалилось | Почему |
| --- | --- | --- |
| `plugin/provider-gitlab-oauth.test.ts` | 11 | ходят на `gitlab.com` и ждут сеть (PKCE-обмен, калбэки, EADDRINUSE). На чистой базе: 11 fail / 8 pass — то же самое |
| `tool-search.test.ts` + `tool-ripgrep*.test.ts` | 28 | пробуют скачать бинарь ripgrep: `test attempted network request: GET https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/...`. На чистой базе: `tool-search` 14 fail / 4 pass, `ripgrep` 14 fail / 2 pass — то же самое |

Итого **0 падений, связанных с патчем**. Знаменатель здоровый: 7 272 pass, в том числе 811 в
классе событий, которые патч трогает (см. §2), и весь пакет ai — 2 276 pass / 0 fail.

## 5. Сквозной прогон (мок-провайдер, без ключей)

Мок отдаёт SSE с настоящими `logprobs` и `top_logprobs`. Проверено трижды:

1. `bun run --cwd packages/cli src/index.ts` (Linux, из исходников);
2. собранный `dist/cli-linux-x64/bin/opencode` (один файл, 216 MB);
3. `dist/opencode-truthprobe-windows-x64.exe` на Windows 11 (233 MB).

Запрос, который увидел мок:

```json
{ "logprobs": true, "top_logprobs": 20, "stream": true }
```

Что легло в базу (`session_message.data.content[].truthprobe`, Windows-прогон):

```json
{
  "status": "ok",
  "score": 0.4166,
  "risk": 0.5834,
  "first": { "score": 0.7076, "entropy": 0.2924, "token": "The" },
  "sentences": [
    { "i": 0, "text": "The capital of France is Paris.", "score": 0.8761, "minLp": -0.08, "tokens": 6, "flag": false },
    { "i": 1, "text": "It is home to about 2 million people.", "score": 0.1119, "minLp": -2.9, "tokens": 7, "flag": true }
  ],
  "flagged": 1
}
```

### 5.1 Автопроверка провайдера (без единой переменной окружения)

Мок поднимался на `:8899`, кэш `~/.local/share/opencode/truthprobe/` удалялся, `OPENCODE_TRUTHPROBE`,
`OPENCODE_TRUTHPROBE_CACHE` и `OPENCODE_TRUTHPROBE_PROBE` снимались из окружения. Два прогона подряд:

```
RUN1 (кэш пуст)
  stream=2 with-logprobs=0 probes=1
  проба: {"logprobs": true, "top_logprobs": 3, "stream": false}
  кэш:   {"mock/mock-1": {"status":"ok","endpoint":"http://127.0.0.1:8899","model":"mock-1"}}

RUN2 (кэш прогрет)
  stream=2 with-logprobs=2 probes=0
  оба запроса: {"logprobs": true, "top_logprobs": 20, "stream": true}
```

То есть вердикт переживает перезапуск процесса: второй прогон просит `logprobs` с первого же
запроса и ничего не переспрашивает. `truthprobe` при этом доезжает до `session_part`
(`status: ok`) — бейдж работает без ручной настройки.

Побочно найдено и исправлено: `Model.mergeCapabilities` не пробрасывал `logprobs`, поэтому
`capabilities.logprobs` из конфига молча терялось.

Кэш проверяется по `providerID/modelID`, а если такой записи нет — по любой свежей записи того же
провайдера: поддержка logprobs — свойство эндпоинта, и алиас модели не должен гасить бейдж.

## 6. Живой рендер TUI (pty)

```
  ┃  What is the capital of France and how many people live there?
     first-sentence confidence 71%
     The capital of France is Paris. It is home to about 2 million people.
     answer confidence 40% · 1 doubtful sentence
       ! #2 8%: It is home to about 2 million people.
     Build · Mock 1 · 59ms · 1333.3 tok/s
```

Числа совпадают с данными парта (0.708 → 71%, 0.399 → 40%, 0.079 → 8%).

**Баг, найденный здесь:** бейдж не появлялся, пока сессия не перезагружена. Виноват не компонент,
а стор `packages/client/src/solid/data.ts`: обработчик `session.text.ended` копировал только
`text.text`. Исправлено коммитом `a9db0da`.

**Баг, найденный тестами:** токен, начинающийся с пробела на границе предложений
(`" Плохо"` сразу после точки), терялся — привязка шла по `start`, а пробел уже был «съеден»
предыдущим предложением. Теперь привязка по пересечению диапазонов.

## 7. Сборка

| Платформа | Команда | Артефакт | Размер |
| --- | --- | --- | --- |
| Linux x64 | `OPENCODE_TARGET=linux-x64 … --single` | `dist/cli-linux-x64/bin/opencode` | 216 MB, 13.0 s |
| Windows x64 | `OPENCODE_TARGET=windows-x64 … --single` | `opencode.exe` | 233 MB, sha256 `396be271…` |

Кросс-сборка под Windows из Linux требует платформенных optional-зависимостей:
`scripts/install-cross-deps.py win32` поставил 187 пакетов (включая `@opencode/pty-win32-x64`,
`@opentui/core-win32-x64`, `@parcel/watcher-win32-x64`, `@ff-labs/fff-bin-win32-x64`).
Подробности и грабли — `docs/BUILD.md`.

`bunx oxlint` не запускался: конфиг репозитория требует плагин `@oxlint/plugins`, которого нет
в зависимостях. Ограничение окружения, не кода.

## 8. Чего НЕ проверено

1. **Реальный шлюз `opencode.ai/inference`.** Нет ключа ни в VM, ни на хосте. Неизвестно,
   пропускает ли шлюз `logprobs`/`top_logprobs` (может 400 или молча вырезать).
   Готов `scripts/probe-logprobs.py` (статусы `ok / ignored / rejected / auth / rate`, кэш 7 дней).
2. **Тихая деградация в UI.** Если провайдер проигнорирует `logprobs`, токенов не будет и бейджа
   не будет вовсе — без явного `unavailable` в интерфейсе. Для честной плашки нужно передавать
   факт запроса через `providerMetadata` даже при пустом ответе; не сделано.
3. **Порог на живых ответах.** `riskyThreshold = 0.45` проверен на моке и одном реальном тексте.
   Кривой precision/recall на размеченном наборе нет.

## 9. Как включить

```bash
bun run --cwd packages/cli src/index.ts     # ничего не настраиваем: провайдер проверяется сам
# посмотреть вердикты:
cat ~/.local/share/opencode/truthprobe/capabilities.json
```

Ручные переключатели (все опциональны): `capabilities.logprobs: true` у модели в конфиге,
`OPENCODE_TRUTHPROBE=1` для принудительного сбора у всех chat-completions моделей,
`OPENCODE_TRUTHPROBE_PROBE=off` чтобы выключить только автопроверку.

## 10. Отдельное desktop-приложение

Сборка форка как самостоятельной программы проверена тем же рецептом, что и портативная папка:

```bash
cd packages/desktop
export OPENCODE_TARGET=windows-x64 OPENCODE_CHANNEL=dev \
       OPENCODE_DESKTOP_APP=TruthProbe OPENCODE_DESKTOP_APP_ID=ai.truthprobe.desktop
bun x electron-vite build
bun x electron-builder --win --x64 --publish never --dir --config electron-builder.config.ts
```

| Что | Результат |
| --- | --- |
| артефакт | `dist/win-unpacked/TruthProbe.exe`, `resources/opencode-cli.exe` (наш CLI), `app-update.yml` нет |
| заголовок окна | `TruthProbe` (проверено `MainWindowTitle` после запуска) |
| данные | `%APPDATA%\ai.truthprobe.desktop`, сайдкар CLI в `cli/<version>-x64/` |
| процессы | 5 × `TruthProbe` + 1 × `opencode-cli` |

Без `--config` electron-builder берёт свои умолчания и кладёт исполняемый файл под именем npm-пакета —
это не сборка форка, а случайная. Переменные читаются в `src/main/constants.ts` (брэнд
`OPENCODE_DESKTOP_APP(_ID)`) и в `electron-builder.config.ts` (`brand()`: appId, productName,
`publish: null`).

## 9. Живой шлюз free-pi: цифры на particle и deepseek (измерено)

Шлюз `http://127.0.0.1:8790/v1`, провайдер `@ai-sdk/openai-compatible`, кэш автопроверки
`{"freepi/particle":{"status":"ok"}}`. Сборка `0.0.0-dev-202611191618`, канал `dev`, проверка через
парты в базе после живых прогонов CLI.

**Что выяснилось про транспорт.** Шлюз присылает logprobs **отдельным чанком с пустой дельтой**:

```
1) {"delta":{"content":"Hi"},       "logprobs":null}
2) {"delta":{} ,                    "logprobs":{"content":[{"token":"Hi","logprob":-0.0016,...}]}}
3) {"delta":{"content":"."},        "logprobs":null}
4) {"delta":{} ,                    "logprobs":{"content":[{"token":".","logprob":-1.209,...}]}}
```

Плюс внутренние токены (`<​/think>`, `<​/end​-of​-sentence​>`) вообще не имеют видимого
текста. До `a478531` токены вешались только на чанк с текстом, поэтому карта токенов всегда была
пуста и парт получал `unavailable` — это и было «не вижу цифр».

**Замер 1 — `freepi/particle`.** Ответ про Эйфелеву башню, три предложения:

```json
{"status":"ok","score":0.8152,"risk":0.1848,
 "first":{"score":0.9620,"entropy":0.0380,"token":"The"},
 "sentences":[{"i":0,"score":0.7108,"risk":0.2892,"meanLp":0.8767,"minLp":-1.4335,"phi":0.9620,"tokens":20,"flag":false}]}
```

`sentences` непустые, `status: ok` — уровень предложений работает.

**Замер 2 — `freepi/deepseek-v4.1-flash`.** Ответ про Канберру:

```json
{"status":"ok","score":0.6893,"risk":0.3107,
 "first":{"score":0.8123,"entropy":0.1877,"token":"Capital"},
 "sentences":[{"i":0,"text":"**Capital:** Canberra.","score":0.5151,"risk":0.4849,"flag":true}]}
```

Первый флаг на живом ответе: риск `0.4849` выше порога `0.45`.

**Чего эти замеры не доказывают.** Ни один из них не размечен: мы не знаем, было ли первое
предложение правдой. Числа подтверждают только, что сигнал доезжает до UI и что порог срабатывает.
Калибровка — отдельный, пока не выполненный шаг, см. [`CALIBRATION.md`](CALIBRATION.md).

**Известное ограничение точности.** На этом шлюзе распределение почти детерминированное
(`logprob` лучшего токена порядка `-0.001`), поэтому `phi ≈ 1` и `answer confidence` уходит к
`99.9997%`. Высокие проценты здесь означают «модель шла ровно», а не «ответ верный».

## 10. Полный прогон монорепо: найденный баг схемы (19.11.2026)

До этого проверялись только truthprobe-файлы. Полный `bun test` в `packages/core` (7 713 тестов,
331 файл) дал **218 падений** в сюитах `SessionRunnerLLM` и соседях с ошибкой:

```
SchemaError: Expected Truthprobe.Level | undefined
  at ["content"][0]["truthprobe"]["level"]
```

Причина: `scoreAnswer` кладёт `level: null`, когда сигнала нет (`status: "unavailable"`), а схема
принимала только пять литералов или `undefined`. Любой парт с вердиктом `unavailable` не проходил
декодирование — то есть в реальной работе это ломало как раз те ответы, где цифр нет.

Фикс: `level: optional(Schema.NullOr(Level))` в `packages/schema/src/truthprobe.ts`, плюс
`level?: TruthprobeLevel | null` в клиентских типах. После фикса:

| Прогон | pass | skip | fail |
| --- | --- | --- | --- |
| до фикса | 7 144 | 351 | 218 |
| после фикса | 7 300 | 351 | 62 |

Оставшиеся 62 падения к патчу отношения не имеют: `tool-search` скачивает ripgrep с github.com,
`provider-gitlab-oauth` ходит на gitlab.com, `cross-spawn`/MCP зависят от spawn — в harness
исходящая сеть заблокирована (`test attempted network request: GET https://github.com/...`).

## 11. CI на чужих чистых машинах (проверено)

19.11.2026 прогон GitHub Actions
[`44593481931`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44593481931)
(коммит `ee82265`) завершился **success**: 7 job'ов из 7 на hosted-раннерах.

| Job | Раннер | Что доказывает |
| --- | --- | --- |
| `patched tree` | `ubuntu-latest`, `windows-latest` | клон opencode на `007afb1`, `git am` патча, `bun install`, typecheck 4 пакетов, 97 truthprobe-тестов |
| `installer dry-run` | `ubuntu-latest`, `windows-latest` | `install.sh` / `install.ps1 -DryRun`: клон, `git apply --check`, 13 коммитов, без установки в систему |
| `repo tests` | `ubuntu-latest` | юнит-тесты репозитория TruthProbe |
| `end-to-end verdict` | `ubuntu-latest` | мок-провайдер с logprobs → вердикт в SQLite |
| `cli build` | `ubuntu-latest` | CLI собирается из пропатченного дерева |

Это чистые ОС, но не ручная интерактивная установка: человек не наблюдал, как установщик
отрабатывает кликами. Локальных Hyper-V/VirtualBox/VMware/Windows Sandbox на машине разработчика
по-прежнему нет.

Чего по-прежнему нет: запуска `install.sh` на macOS, замеров на облачных провайдерах с ключами
(OpenAI/Anthropic/Gemini) и калибровки AUROC/ECE на размеченном наборе.
