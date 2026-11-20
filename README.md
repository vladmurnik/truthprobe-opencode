# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-91%20pass-brightgreen)](docs/VALIDATION.md)
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
| **L1** | строка перед ответом | уверенность в **первом токене**: «сходу ли модель знает» |
| **L2** | блок после ответа | уверенность по всему ответу, уровень и число спорных предложений |
| **L3** | список под ответом (TUI и desktop) | каждое спорное предложение: номер, процент, уровень, начало текста |

Уверенность — не приговор: бывает уверенная ложь (`docs/PRIOR-ART.md`, ECLIPSE 2512.03107).
Поэтому в UI написано `confidence`, а не `truth`.

### Шкала уверенности

Число рядом с ответом — это уровень, а не просто процент: `answer confidence 71% · uncertain`.

| уровень | score | как читать |
| --- | --- | --- |
| `safe` | ≥ 90% | модель шла почти без колебаний |
| `likely` | 75–90% | уверенный ответ |
| `uncertain` | 55–75% | заметные колебания |
| `risky` | 35–55% | шаткий ответ, стоит перепроверить |
| `unreliable` | < 35% | модель фактически угадывала |

`risky` и `unreliable` подсвечиваются плашкой: у `risky` янтарная левая граница и слабый фон,
у `unreliable` — красная. Порог «спорного» предложения по умолчанию 45% риска; его можно
сдвинуть переменными `TRUTHPROBE_RISKY_THRESHOLD` и `TRUTHPROBE_SHAKY_THRESHOLD` (0..1,
некорректное значение игнорируется).

**Важно:** проценты — уверенность модели в собственных токенах, а не вероятность того, что
ответ правдив. Детерминированный шлюз (logprob ≈ −0.001) даёт `safe` на любом тексте,
включая выдуманный.

Какие модели отдают logprobs, а какие не покажут цифры никогда —
[`docs/MODEL-SUPPORT.md`](docs/MODEL-SUPPORT.md).

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

Флаги установщика:

| флаг | что делает |
| --- | --- |
| `--dir DIR` | куда ставить (`-Dir` в PowerShell) |
| `--dry-run` | скачать и проверить, что патч ложится; зависимости не ставить |
| `--uninstall` | снять коммиты патча и вернуть дерево к базовому коммиту |
| `--scorer FILE` | положить свои веса скорера в `.truthprobe/weights.json` |

### Сменный скорер

Проценты по умолчанию считает встроенная эвристика `geometric`
(`0.4·геом.среднее + 0.3·худший токен + 0.3·уверенность первого токена`). Её можно заменить
своей моделью, не пересобирая патч:

```bash
# 1. обучить линейную модель на размеченных предложениях
python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json

# 2. включить её
export TRUTHPROBE_SCORER=linear:/path/to/truthprobe-weights.json
```

Формат набора и метрики — [`docs/CALIBRATION.md`](docs/CALIBRATION.md). Веса проверяются при
загрузке: нет файла, битый JSON или нечисловой коэффициент — печатается одно предупреждение и
включается встроенная формула, оценка не ломается. Признаки, которые видит модель:
`meanLp` (ln геом. среднего), `minLp` (ln худшего токена), `meanPhi` (уверенность первого токена
по top-K), `fracLow` (доля токенов с вероятностью ниже 0.5).

Свой скорер на другом языке — через `scripts/calibrate.py --fit` получить веса либо подставить
свою формулу в `packages/core/src/truthprobe/scorer.ts` (там один интерфейс `Scorer`).

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

Публичных сборок **нет**: ни один бинарь не опубликован и контрольных сумм мы не выдаём. Собирать
надо из дерева, которое поставил `install.sh`:

```bash
cd opencode-truthprobe
bun run --cwd packages/cli script/build.ts        # dist/cli-<target>/bin/opencode
```

Кросс-сборка Windows из Linux и варианты таргетов — [`docs/BUILD.md`](docs/BUILD.md).

### Desktop-приложение

Тот же бейдж живёт и в Electron-приложении: чип `confidence` в футере ответа рисует общий компонент
`@opencode/session-ui`, поэтому правка одна на desktop и на веб-интерфейс. Запуск из того же дерева:

```bash
bun run dev:desktop
```

#### Отдельно от opencode

Приложение можно собрать как самостоятельную программу — со своим именем, своим каталогом данных
и без чужого автообновления. Достаточно двух переменных на сборке:

```bash
cd packages/desktop
export OPENCODE_TARGET=windows-x64 OPENCODE_CHANNEL=dev \
       OPENCODE_DESKTOP_APP=TruthProbe OPENCODE_DESKTOP_APP_ID=ai.truthprobe.desktop
bun x electron-vite build
bun x electron-builder --win --x64 --publish never --dir --config electron-builder.config.ts
```

`--config` обязателен: без него electron-builder берёт свои умолчания и исполняемый файл называется
по имени npm-пакета. Результат — `dist/win-unpacked` (портативная папка, ~830 MB): её можно положить
куда угодно и запускать `TruthProbe.exe`. Заголовок окна, AppUserModelID, каталог
`%APPDATA%\ai.truthprobe.desktop` и имя установщика берутся из этих двух переменных; без них сборка
остаётся обычным opencode.

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
| Список спорных предложений в desktop | `bun test src/message/doubtful.test.ts` из `packages/session-ui` | **6 pass / 0 fail**, 14 expect |
| Протокол OpenAI (гейт, тело запроса, разбор `choices[i].logprobs`) | `packages/ai/test/truthprobe.test.ts` | **8 pass / 0 fail** |
| Автовключение без переменных окружения | мок + два прогона подряд | RUN1: проба → `{"status":"ok"}`; RUN2: **2 из 2** запросов с `logprobs: true, top_logprobs: 20` |
| Регрессия вокруг событий текста | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Полный прогон core | `bun test` в `packages/core` (7 713 тестов, 331 файл) | 7 300 pass / 351 skip / 62 fail — ни одного в truthprobe: `tool-search` качает ripgrep с github.com, `provider-gitlab-oauth` ходит на gitlab.com, `cross-spawn`/MCP зависят от spawn; в окружении зарезана исходящая сеть |
| Тесты TruthProbe, текущая сборка | `bun test` четырёх truthprobe-файлов | **97 pass / 0 fail** |
| Патч на чистом дереве | `git am` в worktree `007afb1` | применяется без конфликтов, тесты 45 + 8 зелёные |
| Типизация | schema / ai / core / client / tui | зелёная (132 / 357+322 / 2 030 / 181 / 1 942 файла) |
| Типизация UI-пакетов | session-ui / app / desktop | зелёная (382 / 2 445 / 3 569 файлов, desktop — 2 проекта) |
| Сквозной прогон | мок-провайдер с настоящими `logprobs` | `logprobs: true, top_logprobs: 20` в запросе, `truthprobe` в базе |
| Живой TUI | pty-проба | бейдж и блок спорных предложений отрендерились |
| Desktop UI | чип `confidence` в общем компоненте `@opencode/session-ui` | типизация desktop (3 567 файлов) зелёная; чип `confidence NN%` и список спорных предложений в футере |
| Отдельное desktop-приложение | сборка с `OPENCODE_DESKTOP_APP`/`OPENCODE_DESKTOP_APP_ID` | `TruthProbe.exe`, заголовок окна `TruthProbe`, userData `ai.truthprobe.desktop`, сайдкар CLI рядом, `app-update.yml` нет |
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

## Что реально проверено (статистика на 19.11.2026)

Срез сделан на сборке `0.0.0-dev-202611191814`, Windows 11, локальный шлюз free-pi.
Всё в таблице — замеры, а не ожидания.

| Что | Как проверяли | Результат |
| --- | --- | --- |
| Тесты truthprobe | `bun test` четырёх файлов в `packages/core/test` | **97 pass, 0 fail** |
| Тесты всего монорепо | `bun test` в `packages/core` — 7713 тестов, 331 файл | **7300 pass, 351 skip, 62 fail** |
| Ответ `freepi/particle` | живой запрос через боевой бинарь | `score 0.7595 · likely`, предложение `#0 0.603 · uncertain` |
| Ответ `freepi/deepseek-v4.1-flash` | живой запрос | `score 0.6893`, первый флаг `0.4849` |
| Сменный скорер | `TRUTHPROBE_SCORER=linear:weights.json` | score сместился с `0.7595` до `0.9992` — подмена реально работает |
| Установщик Windows | `install.ps1 -Dir <пусто> -DryRun` | клон, `git apply --check`, 12 коммитов применились, ошибок нет |
| Сборка desktop | electron-builder | приложение 246 МБ, вложенный CLI 279 МБ |

**Про 62 падения в монорепо:** ни одно не относится к truthprobe. Причины видны в логе и не связаны
с патчем: `tool-search` тянет ripgrep с github.com, `provider-gitlab-oauth` ходит на gitlab.com,
`cross-spawn` и MCP-тесты зависят от spawn — в этом окружении исходящая сеть для тестов зарезана
(`test attempted network request: GET https://github.com/...`).

Чего мы **не** проверяли, и врать об этом не будем:

- **Чистые виртуальные машины.** На машине разработчика нет Hyper-V, VirtualBox, VMware и Windows
  Sandbox — установщик и приложение прогонялись только на одной Windows 11. Установка «с нуля» на
  чистой ОС не подтверждена.
- **Linux и macOS.** `install.sh` ни разу не запускался: проверен только `install.ps1`.
- **Облачные провайдеры с ключами.** OpenAI, Anthropic, Gemini не проверялись — только локальный
  шлюз free-pi. Вывод об их поддержке основан на формате протокола, а не на замерах.
- **Калибровка.** `calibrate.py --demo --fit` даёт `AUROC 1.000 / ECE 0.039` на синтетике; это
  свойство синтетики, а не качество скорера. На реальных размеченных данных AUROC/ECE не измерены.

## Устройство патча

43 файла, +6565/−40, двенадцать коммитов поверх `007afb1`. Шов тонкий и аддитивный:

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
| desktop | `desktop/src/main/constants.ts`, `electron.vite.config.ts`, `electron-builder.config.ts` | брэнд сборки: имя, AppUserModelID, userData, установщик, отказ от чужого updater'а |
| app | `app/src/brand.ts`, `app.tsx`, `session/route.tsx` | заголовок окна и вкладки из того же значения |
| TUI | `tui/src/routes/session/message-parts.tsx` | бейдж + блок спорных предложений |
| desktop | `session-ui/src/message/message-content.tsx` | чип `confidence` в футере ответа — общий для desktop-приложения и веба |
| desktop | `session-ui/src/message/doubtful.ts` | список спорных предложений: нумерация, процент, обрезка до 96 символов |
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
- Границы уровней `0.90 / 0.75 / 0.55 / 0.35` выбраны по здравому смыслу, а не по размеченным
  данным: на живых длинных ответах их стоит перепроверить. Переопределяются
  `TRUTHPROBE_RISKY_THRESHOLD` и `TRUTHPROBE_SHAKY_THRESHOLD`.
- Известная слабость подхода: уверенная ложь. Лечится не порогом, а вторым независимым сигналом.

## Лицензия

MIT — см. [LICENSE](LICENSE). `opencode` остаётся под своей лицензией; здесь только патч.

## Что ещё не сделано (честный список)

План работ на 0.5 — [`docs/ROADMAP.md`](docs/ROADMAP.md): шкала уровней, заметная подсветка,
матрица поддерживаемых моделей, установка одним скриптом, сменный ML-скоринг.

Эти пункты из ревью закрыты **не** были, и мы не делаем вид, что они закрыты:

- **Калибровка.** AUROC, ECE и precision/recall не измерены: размеченного набора нет. Протокол и
  скрипт лежат в [`docs/CALIBRATION.md`](docs/CALIBRATION.md) и `scripts/calibrate.py`.
- **Поддержка logprobs наследуется по провайдеру.** Если автопроверка подтвердила одну модель шлюза,
  остальные модели того же провайдера тоже получают `logprobs`. Это сделано осознанно: у free-pi
  кэш содержит только `freepi/particle`, и без наследования `deepseek-*` остались бы без цифр.
  Обратная сторона — провайдер, у которого часть моделей поле не знает, получит 400; лечится
  `OPENCODE_TRUTHPROBE=off` или записью в `capabilities.json`.
- **`temperature > 0`.** `top_logprobs` при ненулевой температуре — сглаженное распределение, а не
  уверенность модели. Мы это не блокируем и не помечаем `partial`; числа остаются числами, но
  трактовать их как «уверенность» при `temperature > 0` нельзя.
- **`top_logprobs` не настраивается.** `TRUTHPROBE_TOP_K = 20` — константа, уменьшить трафик нельзя.
- **Два экземпляра TTL.** `core/src/truthprobe/capability.ts` и `ai/src/protocols/truthprobe-capability.ts`
  дублируют логику свежести; теста на рассинхрон нет.
