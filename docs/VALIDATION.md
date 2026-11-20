# Валидация

Всё ниже — измеренное, не задуманное. Если чего-то не проверяли, это написано отдельным разделом.

База: `sst/opencode` @ `007afb1`. Ветка `feat/truthprobe`, четырнадцать коммитов:

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
| `3d8a5b1` | feat(truthprobe): confidence levels and sentence highlights |
| `51f6f10` | feat(truthprobe): pluggable scorer (geometric \| linear weights) |
| `699374c` | fix(schema): accept null level so unavailable verdicts decode |
| `d153658` | fix(truthprobe): make the patched tree typecheck clean |
| `3b720f0` | feat(truthprobe): per-model calibration weights |

Итог: **45 файлов, +6904 / −40**, семнадцать коммитов. Патч — `patches/truthprobe-0001.patch` (417 599 Б, `git am`).

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
(коммит `9011dfe`) завершился **success**: 7 job'ов из 7 на hosted-раннерах.
20.11.2026 то же самое повторено на патче с per-model весами —
[`44678633546`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44678633546)
(коммит `7bf2eed`), тоже **7 из 7**: сборка, установщики и truthprobe-тесты не сломались от
изменений в скорере.
Третий прогон — уже на патче с новым UI и пересобранными весами —
[`44736706708`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44736706708)
(коммит `83bb9a2`, 15 коммитов в патче): снова **7 из 7 success**, то есть `ConfidenceLine`
и `DoubtfulList` в `packages/session-ui` не сломали ни typecheck, ни сборку CLI.

| Job | Раннер | Что доказывает |
| --- | --- | --- |
| `patched tree` | `ubuntu-latest`, `windows-latest` | клон opencode на `007afb1`, `git am` патча, `bun install`, typecheck 4 пакетов, 109 truthprobe-тестов |
| `installer dry-run` | `ubuntu-latest`, `windows-latest` | `install.sh` / `install.ps1 -DryRun`: клон, `git apply --check`, 17 коммитов, без установки в систему |
| `repo tests` | `ubuntu-latest` | юнит-тесты репозитория TruthProbe |
| `end-to-end verdict` | `ubuntu-latest` | мок-провайдер с logprobs → вердикт в SQLite |
| `cli build` | `ubuntu-latest` | CLI собирается из пропатченного дерева |

Это чистые ОС, но не ручная интерактивная установка: человек не наблюдал, как установщик
отрабатывает кликами. Локальных Hyper-V/VirtualBox/VMware/Windows Sandbox на машине разработчика
по-прежнему нет.

Прогон [`44761971781`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44761971781) на `128b5f4` (патч из 17 коммитов, где формула по умолчанию
переписана на `exp(meanLp)`) снова дал **7 job'ов из 7**: пропатченное дерево на ubuntu и
windows собирается и проходит 110 truthprobe-тестов, установщики применяют 17 коммитов,
e2e-прогон через мок-провайдера кладёт вердикт в базу, CLI собирается.

Чего по-прежнему нет: запуска `install.sh` на macOS, замеров на облачных провайдерах с ключами
(OpenAI/Anthropic/Gemini) и AUROC/ECE на наборе, где есть обе метки — см. §12.

## 12. Первое измерение качества — и почему первые числа оказались браком

Скрипт `scripts/evaluate.py` считает AUROC, ECE, Brier и долю верных внутри каждого уровня на
файле строк, которые пишет `scripts/collect.py`. Формулы скорера повторяют рантайм
(`0.4·exp(meanLp) + 0.3·exp(minLp) + 0.3·phi` для `geometric`; сигмоида по
`[1, meanLp, minLp, phi, fracLow]` для линейных весов).

Первый прогон дал AUROC `geometric 0.538` / `global 0.683` / `per-model 0.866` на 720 строках
(700 верных / 20 неверных) и вывод «логпробные признаки не ловят уверенную ложь». **Этот вывод
и эти числа неверны: их источником был брак в наших собственных данных.** Разбор:

1. **Двусмысленный вопрос.** «Which is the largest planet in the Solar System: Saturn or Neptune?»
   предлагает два варианта, а эталон требовал `jupiter` — которого среди вариантов нет.
   Три модели из четырёх ответили «Saturn», то есть на заданный вопрос ответили правильно, а
   лейбл `0` поставил наш банк. Это не уверенная ложь модели, а противоречие в вопросе.
2. **Обрыв по `max_tokens`.** Остальные «негативы» — ответы, обрезанные на 80 токенах посреди
   формулы (`60 × (1 + `), либо на середине числа (`198` вместо `1989`). Модель не ошибалась;
   ошибались мы, считая обрезку ошибкой.

Что сделано, чтобы это не повторялось:

- **`scripts/audit-bank.py`** — аудит банка по собранным строкам: если несколько разных моделей
  независимо сходятся на ответе, которого нет в эталоне, пункт помечается как брак банка
  (плюс отдельная проверка «вопрос предлагает `X or Y`, а эталон вне этих вариантов»).
  Выходит с кодом 1 при находках, годится как гейт. На старом банке он нашёл ровно 4 пункта.
- **`collect.py`**: ответ с `finish_reason == "length"` помечается `truncated`, и `label=0`
  из обрыва не ставится — иначе веса учатся на нашей жадности, а не на ошибках модели.
- Четыре вопроса банка переписаны без ложного выбора, семь промптов пересобраны с
  `max_tokens 220`.

После очистки (файлы перезаписаны, старые строки по исправленным вопросам удалены):

| файл | строк | с меткой | верных | неверных | `geometric` ECE | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| `data/rows-hard.jsonl` (`T=0.8`) | 752 | 739 | 739 | **0** | 0.493 | 0.269 |
| `data/rows-hard-t1.jsonl` (`T=1.0`) | 752 | 741 | 741 | **0** | 0.519 | 0.299 |

Числа ECE в этой таблице сняты на **старой** формуле (`0.4·geo + 0.3·worst + 0.3·phi`); после §14
та же выборка даёт ECE 0.160 / Brier 0.044.

`evaluate.py` теперь честно печатает `AUROC n/a (one class)`, а `calibrate.py --fit` отказывается
обучать веса. **Итог: качество калибровки на сегодня не измерено — негативов нет.** Это
неприятный, но настоящий результат; прежние 0.866 отозваны.

Что при этом остаётся верным и измеренным на 739 строках: до §14 `geometric` систематически
**занижала** уверенность (ECE 0.493 при Brier 0.269) — именно этот перекос и исправлен заменой
формулы (§14: ECE 0.160, Brier 0.044). Уровни `likely/uncertain/risky` на этом наборе дают 100%
верных ответов — то есть плашка «спорное предложение» срабатывает на правильных ответах чаще,
чем хотелось бы; это отдельная задача про пороги, а не про формулу.

## 13. Нарочная ложь: что скорер видит, а что нет (проверено, с оговоркой)

Настоящих негативов добыть не удалось. Четыре банка и 1 440 запросов к четырём моделям шлюза
(`particle`, `deepseek-v4.1-flash`, `deepseek-v4-flash`, `glm-5.3-flash`) дали **ноль** неверных
ответов: модели либо отвечают верно, либо возвращают пустой content. Ни канонические факты, ни
классические провалы (буквы в `strawberry`, день недели по дате, 8371×4629) их не ломают.

Единственная ложь, в которой мы уверены на 100%, — заказанная: `scripts/make-liar-bank.py`
просит модель ответить неправильно, ответ по-прежнему генерирует модель со своими настоящими
logprobs. Ложь при этом не наша выдумка: мы знаем правду из постановки вопроса.

| Набор | Строк | Правдивых | Ложных |
| --- | --- | --- | --- |
| `data/rows-lie-vs-truth.jsonl` (34 вопроса × 4 модели, T=0.8) | 626 | 544 | 82 |

### Что показал замер

| Режим | AUROC | ECE | Brier |
| --- | --- | --- | --- |
| `geometric` (то, что работает сейчас) | **0.388** | 0.368 | 0.292 |
| `fitted` (4 признака, out-of-fold, 5 фолдов) | **0.774** | 0.282 | 0.181 |

AUROC 0.388 — **хуже случайного**: встроенная формула даёт заказанной лжи *больше* уверенности, чем
правдивым ответам. Причина видна в признаках: у лжи `phi` = 0.468 против 0.125 у правды (первый
токен после странной инструкции менее предсказуем), а `phi` входит в формулу с весом 0.3.
`meanLp` при этом почти не различается (−0.306 против −0.224).

Обученные веса на тех же четырёх признаках дают 0.774 out-of-fold — то есть сигнал в logprobs
есть, но встроенная эвристика его не использует, а частично разворачивает.

По моделям (fitted, out-of-fold): `glm-5.3-flash` 0.863 (62 негатива), `deepseek-v4.1-flash` 0.629
(6 негативов), `particle` 0.522 (10), `deepseek-v4-flash` — негативов меньше пяти, не считаем.
Разброс объясняется тем, что почти все негативы дал один `glm-5.3-flash`: остальные модели
отказывались врать и отвечали верно (такие строки `--auto-label` помечает 1, а не 0).

Воспроизведение: `python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl`.

### Чего этот замер НЕ доказывает

Нарочная ложь — не самопроизвольная галлюцинация. Модель, которой велели соврать, знает правду и
видит странную инструкцию; её первый токен отражает инструкцию, а не факт. Поэтому 0.774 нельзя
читать как «TruthProbe ловит выдумку в обычном разговоре». Это разные задачи, и вторая
по-прежнему не измерена — для неё нужны настоящие ошибки моделей, которых этот источник не даёт.

Практический вывод, который был сделан из этого замера и затем реализован: `phi` в формуле по
умолчанию оказалась не просто лишней, а вредной — её вклад разворачивал оценку. Формула переписана
на `exp(meanLp)`, замер и обоснование — в §14 ниже.

## 14. Формула по умолчанию: `exp(meanLp)` вместо `0.4·geo + 0.3·worst + 0.3·φ` (проверено)

Замер §13 показал, что встроенная формула ставит ложным ответам *большую* уверенность, чем
правдивым (AUROC 0.388 — ниже случайного). Причина не в данных: `phi` (уверенность первого токена)
у заказанной лжи вчетверо выше, потому что странная инструкция делает первый токен непредсказуемым,
а формула читает это как «увереннее» и даёт этому слагаемому вес 0.3.

Сравнение фиксированных формул, без обучения. ECE — по 10 бинам.

Набор `data/rows-lie-vs-truth.jsonl`: 626 строк, 544 правдивых, 82 заказанно-ложных.

| формула | AUROC | ECE | Brier | средняя оценка |
| --- | --- | --- | --- | --- |
| прежняя `0.4·geo + 0.3·worst + 0.3·φ` | 0.388 | 0.368 | 0.292 | 0.501 |
| **`exp(meanLp)`** | **0.597** | **0.098** | **0.127** | 0.806 |
| `0.9·geo + 0.1·worst` | 0.583 | 0.129 | 0.139 | 0.768 |
| `0.8·geo + 0.2·worst` | 0.572 | 0.164 | 0.154 | 0.730 |
| `geo · (1 − fracLow)` | 0.608 | 0.176 | 0.157 | 0.728 |
| `exp(minLp)` | 0.507 | 0.463 | 0.422 | — |
| `φ` | 0.199 | 0.768 | 0.766 | — |

Контрольная проверка на наборе без негативов — `data/rows-hard.jsonl`, 739 полностью верных строк.
Здесь хорошая формула не должна систематически занижать уверенность:

| формула | ECE | Brier | средняя оценка |
| --- | --- | --- | --- |
| прежняя | 0.493 | 0.269 | 0.507 |
| **`exp(meanLp)`** | **0.160** | **0.044** | 0.840 |
| `0.9·geo + 0.1·worst` | 0.201 | 0.063 | 0.799 |
| `0.8·geo + 0.2·worst` | 0.242 | 0.088 | 0.758 |
| `geo · (1 − fracLow)` | 0.225 | 0.085 | 0.775 |

**Решение:** по умолчанию считается только геометрическое среднее вероятностей токенов ответа,
`exp(meanLp)`. `phi` и худший токен остаются в наборе признаков — их используют обученные веса
(`TRUTHPROBE_SCORER=linear:...`), но эвристика по умолчанию на них больше не опирается.

**Что изменилось в коде** (патч, 17 коммитов):

- `packages/core/src/truthprobe/scorer.ts` — `geometricScorer()` возвращает `clamp01(exp(meanLp))`;
  шапка файла объясняет замер и почему `phi` убрана.
- `packages/core/src/truthprobe/score.ts` — удалено слагаемое худшего токена и `phi` из формулы
  по умолчанию; `phi` по-прежнему считается и попадает в поле `phi` каждого предложения.
- `packages/core/test/truthprobe-scorer.test.ts` — тест «встроенная формула = геометрическое
  среднее» и новый тест «`phi` и худший токен больше не влияют на встроенную оценку».

**Воспроизведение:**

```bash
python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl              # geometric 0.597 / 0.098 / 0.127
python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl --variants   # вся таблица формул
python3 scripts/evaluate.py data/rows-hard.jsonl                          # ECE 0.160 на верных ответах
```

### Чего это не доказывает

- 0.597 — всё ещё слабое разделение, а набор негативов один и узкий: заказанная ложь, а не
  самопроизвольная галлюцинация. Переносить это число на реальные разговоры нельзя.
- Разница между `exp(meanLp)` и `geo·(1 − fracLow)` (0.597 против 0.608) лежит в пределах шума на
  82 негативах; выбрана более простая формула, а не «лучшая по третьему знаку».
- Уровни и пороги (§7) не менялись: изменилась только оценка, а значит `safe/likely/uncertain/...`
  на тех же ответах теперь будут выше. Это ожидаемо (прежняя формула занижала), но означает, что
  калибровка порогов на новых данных — отдельная задача.

## 15. Текстовый признак `digitDensity`: единственный с измеримым вкладом (проверено)

Скорер по умолчанию смотрит только на logprobs и игнорирует текст. Проверили два класса текстовых
признаков на 626 строках `data/rows-lie-vs-truth.jsonl` (544 правды / 82 заказанной лжи;
out-of-fold, 5 фолдов, seed 7): хеджирование («probably», «I think») и долю цифр в ответе.

| модель | AUROC | ECE | Brier |
| --- | --- | --- | --- |
| рантайм `exp(meanLp)` | 0.597 | 0.098 | 0.127 |
| fit: meanLp | 0.587 | 0.358 | 0.241 |
| fit: meanLp + hedge | 0.587 | 0.358 | 0.241 |
| fit: meanLp + numeric | 0.633 | 0.350 | 0.236 |
| fit: meanLp + minLp + phi + fracLow | 0.774 | 0.282 | 0.181 |
| fit: все пять + digitDensity | **0.808** | 0.274 | 0.181 |

- Хеджирование на этом наборе не измеримо: у правды и лжи его доля одинакова и равна 0.0000
  (ответы короткие, хеджирующих слов нет). В доках называется непроверенным, а не «не работает».
- `digitDensity` = доля символов-цифр в видимом ответе: правда 0.6465, ложь 0.5122. Измеримый
  вклад: +0.046 AUROC поверх голого `meanLp`, +0.034 поверх полного набора признаков.

Внедрено во все три слоя, чтобы числа не расходились:

- Рантайм (`packages/core/src/truthprobe/score.ts`): `digitDensity(text)` = `#{цифры}/#{все символы}`
  кладётся в `ScorerFeatures.digitDensity`. В оценку по умолчанию НЕ входит.
- `scripts/collect.py` считает то же из поля `answer`, `scripts/enrich-digits.py` досчитывает
  признак в уже собранных строках (идемпотентно, `--check` для проверки).
- `scripts/calibrate.py --fit` добавляет шестую координату (у `global` на 626 строках
  `digitDensity = 0.698`); `scripts/evaluate.py` читает вес опционально, поэтому старые файлы
  весов работают как раньше.

Воспроизведение: `python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl` — fitted out-of-fold
AUROC **0.809** с признаком против **0.774** без него; `python3 scripts/calibrate.py
data/rows-lie-vs-truth.jsonl --fit --by-model` печатает ту же таблицу по моделям.

Чего это не доказывает: прирост измерен на одном наборе с одним классом негативов (заказанная
ложь). На самопроизвольной галлюцинации наборов нет, поэтому переносить +0.034 на реальные
разговоры нельзя. Формула по умолчанию не менялась — веса подключаются только через
`TRUTHPROBE_SCORER=linear:<файл>`.
