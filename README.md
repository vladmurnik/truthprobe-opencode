# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-85%20pass-brightgreen)](docs/VALIDATION.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

[English](README.en.md) · **Русский**

Показывает, **насколько модель уверена в своём ответе**, по логвероятностям первых токенов —
без второго прохода, без самопроверки модели и без второй модели-судьи.

Патч ядра [opencode](https://github.com/sst/opencode): одно место сбора токенов, одно поле в схеме,
один бейдж в TUI и один чип в сессионном UI desktop-приложения (Electron).

```
   What is the capital of France and how many people live there?

   first-sentence confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 40% · 1 doubtful sentence
     ! #2 8%: It is home to about 2 million people.
     Build · Mock 1 · 59ms · 1333.3 tok/s
```

## Зачем

Идея не наша: **«The First Token Knows: Single-Decode Confidence for Hallucination Detection»**
(M. Gabriel, P. Wang, [arXiv 2605.05166](https://arxiv.org/abs/2605.05166)) показала, что
нормированная энтропия распределения **первого** токена работает как self-consistency, но стоит
одного жадного декода вместо 10+ сэмплов и кластеризации. В экосистеме opencode этого не было
вообще: в дереве `sst/opencode` ноль упоминаний `logprob`, а хуки плагинов не дают доступа
к токенам — поэтому и нужен патч ядра, а не плагин.

Обзор статей и инструментов — в [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md).

## Что показывает

| Уровень | Где | Что видно |
| --- | --- | --- |
| **L1** | строка перед ответом | уверенность в первом предложении: «сходу ли модель знает» |
| **L2** | блок после ответа | уверенность по всему ответу и число спорных предложений |
| **L3** | подсветка | каждое спорное предложение: номер, процент, текст |

Уверенность — не приговор: бывает уверенная ложь (`docs/PRIOR-ART.md`, ECLIPSE 2512.03107).
Поэтому в UI написано `confidence`, а не `truth`.

## Установка

Две команды, клонировать этот репозиторий не нужно:

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.ps1 | iex
```

Оба установщика забирают `sst/opencode`, закреплённый на `007afb1`, применяют
`patches/truthprobe-0001.patch`, ставят зависимости и печатают версию сборки. Нужны `git` и
[`bun`](https://bun.sh); вне целевого каталога ничего не меняется — git-идентичность, если её нет,
задаётся локально в нём. Каталог можно назвать своим: `bash install.sh my-opencode`
(`.\install.ps1 -Dir my-opencode`).

### Патч вручную

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout 007afb1
git am /path/to/patches/truthprobe-0001.patch
bun install
bun run --cwd packages/cli src/index.ts
```

Ключи и провайдеры проверяются сами: при первом запросе к chat-completions модели ядро
отправляет одну посылку на один токен с текстом `ping` и, если провайдер вернул `logprobs`,
включает их для этого провайдера. Переменные окружения не нужны.

### Готовый бинарь

```bash
# Linux x64
curl -LO <release>/opencode-truthprobe-linux-x64 && chmod +x opencode-truthprobe-linux-x64
# Windows x64
curl -LO <release>/opencode-truthprobe-windows-x64.exe
```

Сборка из исходников — [`docs/BUILD.md`](docs/BUILD.md) (включая кросс-сборку Windows из Linux).

### Desktop-приложение

Тот же бейдж живёт и в Electron-приложении: чип `confidence` в футере ответа рисует общий компонент
`@opencode/session-ui`, поэтому правка одна на desktop и на веб-интерфейс. Запуск из того же дерева:

```bash
bun run dev:desktop
```

### Включение

Автоматически. Плагин `opencode.truthprobe` слушает `http.request` — единственное место, где
одновременно видны модель и уже авторизованный URL, — и параллельно отправляет одну
проверочную посылку: `{"messages":[{"role":"user","content":"ping"}], "max_tokens":1, "logprobs":true}`.
Данные переписки в ней не участвуют. Ответ модели проверку не ждёт: хук только кладёт событие
в очередь, сеть работает в отдельной fiber.

Вердикт пишется в `<data>/truthprobe/capabilities.json` (Linux: `~/.local/share/opencode/truthprobe/`,
Windows: `%APPDATA%\opencode\truthprobe\`) и живёт: `ok`/`ignored`/`rejected`/`unsupported` — 7 дней,
`auth` — час (ключ могли добавить), сетевые и 5xx — не кэшируются вовсе.

| Статус | Значит | Что делает бейдж |
| --- | --- | --- |
| `ok` | в ответе реально был `logprobs.content` | включается и у следующих запросов |
| `ignored` | 200, но поля нет — шлюз молча вырезал | не включается, повтор через 7 дней |
| `rejected` | 400/422 с упоминанием `logprob` | не включается, повтор через 7 дней |
| `auth` | 401/403 | не включается, перепроверка через час |
| `unsupported` | 404/405/501 или иная 400 | не включается, повтор через 7 дней |

Ручные способы остаются и старше автоматики:

- `capabilities.logprobs: true` у модели в конфиге — решает пользователь, автопроверка не спорит;
- `OPENCODE_TRUTHPROBE=1` — просим `logprobs` у всех chat-completions моделей;
- `OPENCODE_TRUTHPROBE_PROBE=off` — выключить только автопроверку (сеть не трогаем).

Посмотреть вердикты: `cat <data>/truthprobe/capabilities.json`.

## Как считается

```
φ_first        = 1 − H_norm(top-K первых токенов)      K = 20
H_norm         = −Σ q ln q / ln K,   q = softmax(logprob)
score_sentence = 0.4 · geo(exp(lp)) + 0.3 · exp(minLp) + 0.3 · φ_first
risk           = 1 − score            флаг при risk ≥ 0.45
score_answer   = 0.6 · globalGeo + 0.4 · mean(score_sentence)
```

Три сигнала на предложение: средняя уверенность (геометрическое среднее), худший токен (именно он
выдаёт придуманное число или имя) и энтропия первого токена. Сегментация — по `. ! ? …` с учётом
десятичных дробей, сокращений и CJK-терминаторов; блоки кода выбрасываются целиком.

Состояния: `ok` — токены совпали с текстом; `partial` — дрейф смещений; `unavailable` — токенов нет.

## Проверки

| Что | Как | Результат |
| --- | --- | --- |
| Скоринг и сегментация | `bun test test/score.test.ts` | **45 pass / 0 fail**, 104 expect |
| Логика автопроверки (TTL, классификация ответов, кэш) | `bun test test/capability.test.ts` | **32 pass / 0 fail**, 70 expect |
| Протокол OpenAI (гейт, тело запроса, разбор `choices[i].logprobs`) | `packages/ai/test/truthprobe.test.ts` | **8 pass / 0 fail** |
| Автовключение без переменных окружения | мок + два прогона подряд | RUN1: проба → `{"status":"ok"}`; RUN2: **2 из 2** запросов с `logprobs: true, top_logprobs: 20` |
| Регрессия вокруг событий текста | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Полный прогон core | `bun run script/test.ts` | 7 272 pass / 39 fail — все 39 падают и на чистой базе (сеть: GitLab OAuth, ripgrep) |
| Патч на чистом дереве | `git am` в worktree `007afb1` | применяется без конфликтов, тесты 45 + 8 зелёные |
| Типизация | schema / ai / core / client / tui | зелёная (132 / 357+322 / 2 030 / 181 / 1 942 файла) |
| Типизация UI-пакетов | session-ui / app / desktop | зелёная (380 / 2 443 / 3 567 файлов, desktop — 2 проекта) |
| Сквозной прогон | мок-провайдер с настоящими `logprobs` | `logprobs: true, top_logprobs: 20` в запросе, `truthprobe` в базе |
| Живой TUI | pty-проба | бейдж и блок спорных предложений отрендерились |
| Desktop UI | чип `confidence` в общем компоненте `@opencode/session-ui` | типизация desktop (3 567 файлов) зелёная; строка `confidence NN%` в футере ответа |
| Windows-бинарь | `.exe` на моке | `status: "ok", score: 0.417, first 0.708, flagged: 1` |

Воспроизвести без ключей:

```bash
python3 scripts/mock-openai-logprobs.py 8899 &
OPENCODE_CONFIG=scripts/mock-opencode.json \
  bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "capital of France?"
python3 scripts/check-db.py                  # что попало в базу
python3 scripts/tui-probe.py && python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Полные числа и история решений — [`docs/VALIDATION.md`](docs/VALIDATION.md),
пошаговое воспроизведение — [`docs/SMOKE-E2E.md`](docs/SMOKE-E2E.md).

## Устройство патча

27 файлов, +1961/−27, пять коммитов поверх `007afb1`. Шов тонкий и аддитивный:

| Слой | Файл | Что делает |
| --- | --- | --- |
| схема | `packages/schema/src/truthprobe.ts` | `Truthprobe.Info` — единственный новый тип |
| схема | `session-message.ts`, `session-event.ts` | optional-поле `truthprobe` в текстовом парте и в `session.text.ended` |
| протокол | `packages/ai/src/protocols/openai-chat.ts` | просит `logprobs`, парсит `choices[i].logprobs` в `providerMetadata` |
| протокол | `packages/ai/src/protocols/truthprobe-capability.ts` | читает кэш вердиктов, чтобы включить сбор без конфига |
| ядро | `plugin/truthprobe.ts` + `truthprobe/capability.ts` | автопроверка провайдера по `http.request`, кэш вердиктов |
| ядро | `model.ts` | `mergeCapabilities` больше не теряет `logprobs` |
| ядро | `session/runner/publish-llm-event.ts` | копит токены, считает score, кладёт в durable-событие |
| ядро | `session/message-updater.ts` | переносит поле в парт сообщения |
| клиент | `client/src/solid/data.ts` | **не теряет** поле при живом обновлении стора |
| TUI | `tui/src/routes/session/message-parts.tsx` | бейдж + блок спорных предложений |
| desktop | `session-ui/src/message/message-content.tsx` | чип `confidence` в футере ответа — общий для desktop-приложения и веба |
| скоринг | `core/src/truthprobe/*` | чистые функции, ноль внешних зависимостей |

Почему именно так и что можно было сломать — в [`PLAN.md`](PLAN.md) §11 «жизнь патча при
обновлениях»: 6 точек, которые придётся rebase-ить, и 15–30 минут на релиз upstream.

## Структура

```
src/truthprobe/           эталонная математика (типы, сегментация, скоринг) и логика автопроверки
src/opencode-tree/        эталонные копии файлов, которые живут в дереве opencode
test/score.test.ts        45 тестов без сети и без зависимостей
test/capability.test.ts   32 теста статусов, TTL и кэша автопроверки
test/opencode-tree/       тесты, которые живут в дереве opencode
patches/                  готовый git-am патч и python-патчеры для точечных правок
scripts/                  мок-провайдер, probe, pty-проба TUI, эмулятор экрана, сборка
install.sh / install.ps1  установка в две команды: патч поверх sst/opencode @ 007afb1
docs/                     приоритет, план встроенных моделей, валидация, сборка
```

## Ограничения

- Только провайдеры с `logprobs` (семейство chat-completions). Responses API, Anthropic messages,
  Gemini generate-content — пока нет; план есть в [`docs/PLAN-BUILTIN.md`](docs/PLAN-BUILTIN.md).
- Первый запрос к новому провайдеру ещё идёт без `logprobs`: вердикт появляется после пробы,
  то есть со второго запроса. Первый ответ бейджа не получит.
- Реальный шлюз `opencode.ai/inference` не проверен: нет ключа. Автопроверка справится сама —
  `scripts/probe-logprobs.py` нужен только чтобы посмотреть вердикт вручную.
- Порог `0.45` откалиброван на моке; на живых длинных ответах требует проверки.
- Известная слабость подхода: уверенная ложь. Лечится не порогом, а вторым независимым сигналом.

## Лицензия

MIT — см. [LICENSE](LICENSE). `opencode` остаётся под своей лицензией; здесь только патч.
