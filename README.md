# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-53%20pass-brightgreen)](docs/VALIDATION.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

Показывает, **насколько модель уверена в своём ответе**, по логвероятностям первых токенов —
без второго прохода, без самопроверки модели и без второй модели-судьи.

Патч ядра [opencode](https://github.com/sst/opencode): одно место сбора токенов, одно поле в схеме,
один бейдж в TUI.

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

### 1. Патч (нужен свой билд)

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout 007afb1
git am /path/to/patches/truthprobe-0001.patch
bun install
export OPENCODE_TRUTHPROBE=1
bun run --cwd packages/cli src/index.ts
```

### 2. Готовый бинарь

```bash
# Linux x64
curl -LO <release>/opencode-truthprobe-linux-x64 && chmod +x opencode-truthprobe-linux-x64
# Windows x64
curl -LO <release>/opencode-truthprobe-windows-x64.exe
```

Сборка из исходников — [`docs/BUILD.md`](docs/BUILD.md) (включая кросс-сборку Windows из Linux).

### Включение

- `OPENCODE_TRUTHPROBE=1` — просим `logprobs` у всех chat-completions моделей;
- либо `capabilities.logprobs: true` у конкретной модели в конфиге (переменная тогда не нужна);
- любой другой провайдер без `logprobs` → бейджа просто не будет, ошибки тоже не будет.

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
| Протокол OpenAI (гейт, тело запроса, разбор `choices[i].logprobs`) | `packages/ai/test/truthprobe.test.ts` | **8 pass / 0 fail** |
| Регрессия вокруг событий текста | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Полный прогон core | `bun run script/test.ts` | 7 272 pass / 39 fail — все 39 падают и на чистой базе (сеть: GitLab OAuth, ripgrep) |
| Патч на чистом дереве | `git am` в worktree `007afb1` | применяется без конфликтов, тесты 45 + 8 зелёные |
| Типизация | schema / ai / core / client / tui | зелёная (132 / 356+321 / 2025 / 181 / 1942 файла) |
| Сквозной прогон | мок-провайдер с настоящими `logprobs` | `logprobs: true, top_logprobs: 20` в запросе, `truthprobe` в базе |
| Живой TUI | pty-проба | бейдж и блок спорных предложений отрендерились |
| Windows-бинарь | `.exe` на моке | `status: "ok", score: 0.417, first 0.708, flagged: 1` |

Воспроизвести без ключей:

```bash
python3 scripts/mock-openai-logprobs.py 8899 &
OPENCODE_TRUTHPROBE=1 OPENCODE_CONFIG=scripts/mock-opencode.json \
  bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "capital of France?"
python3 scripts/check-db.py                  # что попало в базу
python3 scripts/tui-probe.py && python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Полные числа и история решений — [`docs/VALIDATION.md`](docs/VALIDATION.md),
пошаговое воспроизведение — [`docs/SMOKE-E2E.md`](docs/SMOKE-E2E.md).

## Устройство патча

18 файлов, +1254/−27, три коммита поверх `007afb1`. Шов тонкий и аддитивный:

| Слой | Файл | Что делает |
| --- | --- | --- |
| схема | `packages/schema/src/truthprobe.ts` | `Truthprobe.Info` — единственный новый тип |
| схема | `session-message.ts`, `session-event.ts` | optional-поле `truthprobe` в текстовом парте и в `session.text.ended` |
| протокол | `packages/ai/src/protocols/openai-chat.ts` | просит `logprobs`, парсит `choices[i].logprobs` в `providerMetadata` |
| ядро | `session/runner/publish-llm-event.ts` | копит токены, считает score, кладёт в durable-событие |
| ядро | `session/message-updater.ts` | переносит поле в парт сообщения |
| клиент | `client/src/solid/data.ts` | **не теряет** поле при живом обновлении стора |
| TUI | `tui/src/routes/session/message-parts.tsx` | бейдж + блок спорных предложений |
| скоринг | `core/src/truthprobe/*` | чистые функции, ноль внешних зависимостей |

Почему именно так и что можно было сломать — в [`PLAN.md`](PLAN.md) §11 «жизнь патча при
обновлениях»: 6 точек, которые придётся rebase-ить, и 15–30 минут на релиз upstream.

## Структура

```
src/truthprobe/           эталонная математика (типы, сегментация, скоринг)
test/score.test.ts        45 тестов без сети и без зависимостей
test/opencode-tree/       тесты, которые живут в дереве opencode
patches/                  готовый git-am патч и python-патчеры для точечных правок
scripts/                  мок-провайдер, probe, pty-проба TUI, эмулятор экрана, сборка
docs/                     приоритет, план встроенных моделей, валидация, сборка
```

## Ограничения

- Только провайдеры с `logprobs` (семейство chat-completions). Responses API, Anthropic messages,
  Gemini generate-content — пока нет; план есть в [`docs/PLAN-BUILTIN.md`](docs/PLAN-BUILTIN.md).
- Реальный шлюз `opencode.ai/inference` не проверен: нужен ключ. `scripts/probe-logprobs.py`
  печатает `ok / ignored / rejected / auth / rate` и кэширует ответ на 7 дней.
- Порог `0.45` откалиброван на моке; на живых длинных ответах требует проверки.
- Известная слабость подхода: уверенная ложь. Лечится не порогом, а вторым независимым сигналом.

## Лицензия

MIT — см. [LICENSE](LICENSE). `opencode` остаётся под своей лицензией; здесь только патч.
