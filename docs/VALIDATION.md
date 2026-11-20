# Валидация

Всё ниже — измеренное, не задуманное. Если чего-то не проверяли, это написано отдельным разделом.

База: `sst/opencode` @ `007afb1`. Ветка `feat/truthprobe`, три коммита:

| Коммит | Что |
| --- | --- |
| `3ccda6c` | feat(truthprobe): score answers from token logprobs |
| `a9db0da` | fix(tui): apply truthprobe metadata from session.text.ended events |
| `2870f64` | test(truthprobe): cover segmentation, scoring and protocol parsing |

Итог: **18 файлов, +1254 / −27**. Патч — `patches/truthprobe-0001.patch` (1983 строки, `git am`).

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

## 2. Тесты

```
45 pass / 0 fail   104 expect   packages/core/test/truthprobe.test.ts
 8 pass / 0 fail    23 expect   packages/ai/test/truthprobe.test.ts
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

## 3. Полные прогоны

| Пакет | Команда | Результат |
| --- | --- | --- |
| core (весь) | `bun run script/test.ts` | **7 272 pass / 350 skip / 39 fail**, 96 831 expect, 328 файлов, 205 s — все 39 падений чужие, см. §4 |
| ai (весь) | `bun test --timeout 30000` | **2 276 pass / 0 fail / 29 skip**, 9 377 expect, 7.7 s |
| schema | `bun test` | **95 pass / 0 fail**, 231 ms |
| регрессия сессий | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail**, 30 s |
| типизация | schema / ai / core / client / tui | 132 / 356+321 / 2025 / 181 / 1942 файла, 0 ошибок |

Отдельно проверено, что **патч самодостаточен**: на чистом worktree `007afb1` (18 файлов,
+1254/−27, без моих рабочих копий) `git am patches/truthprobe-0001.patch` применяется без
конфликтов, `typecheck` пакетов ai и core — 0 ошибок, тесты в применённом дереве — **45 pass / 0 fail**
и **8 pass / 0 fail**. То есть зелёные тесты не зависят от локального состояния моей машины.

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
export OPENCODE_TRUTHPROBE=1        # гейт в протоколе
# или capabilities.logprobs: true у модели в конфиге
bun run --cwd packages/cli src/index.ts
```
