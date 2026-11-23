# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-92%20pass-brightgreen)](docs/VALIDATION.md)
[![CI](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml/badge.svg)](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

[English](README.en.md) · **Русский**

**TruthProbe нужен, чтобы увидеть, где именно модель галлюцинирует или врёт.** Он не выносит
вердикт «правда/ложь» за вас — он показывает **место в ответе**, где модель шла неуверенно:
подсвечивает конкретные предложения и называет их уверенность, чтобы вы проверяли не весь ответ,
а два-три подозрительных утверждения.

Показывает, **насколько модель уверена в своём ответе**, по логвероятностям первых токенов —
без второго прохода, без самопроверки модели и без второй модели-судьи.

Патч ядра [opencode](https://github.com/sst/opencode): одно место сбора токенов, одно поле в схеме,
один бейдж в TUI и один чип в сессионном UI desktop-приложения (Electron).

```
   What is the capital of France and how many people live there?

   first-token confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 44% ▰▰░░░ · risky · 1 doubtful sentence
     ▌ #2 ▰░░░░ 16% · unreliable: It is home to about 2 million people.
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
Что улучшаем дальше и по каким числам это проверяем — в [`docs/ROADMAP.md`](docs/ROADMAP.md).

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
сдвинуть `TRUTHPROBE_RISKY_THRESHOLD` (0..1, некорректное значение игнорируется).
`TRUTHPROBE_SHAKY_THRESHOLD` удалена в 0.13.8: ни переменной, ни поля `shakyThreshold`
больше нет (`docs/VALIDATION.md` §23, пункт 8).

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
| `--scorer FILE` | положить свои веса скорера в `.truthprobe/weights.json` и напечатать строку `TRUTHPROBE_SCORER=linear:$PWD/.truthprobe/weights.json` (сам файл рантайм не читает: веса включаются только переменной окружения) |

### Сменный скорер

По умолчанию оценку считает встроенная формула `geometric` — `exp(meanLp)`, геометрическое среднее
вероятностей содержательных токенов. Прежняя эвристика `0.4·гео + 0.3·худший токен + 0.3·уверенность
первого токена` давала AUROC 0.388 (хуже случайного) на наборе из 626 строк, поэтому из формулы она
убрана и осталась только в признаках (`docs/VALIDATION.md` §14).

Заменить формулу можно, не пересобирая патч:

```bash
# 1. обучить линейную модель на размеченных предложениях
python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json

# 2. включить её
export TRUTHPROBE_SCORER=linear:/path/to/truthprobe-weights.json
```

Веса могут зависеть от модели: обучение с `--by-model` пишет бандл (`make weights` делает это на
`data/rows-lie-vs-truth.jsonl`), а рантайм выбирает набор по `providerID/modelID` и падает обратно
на формулу по умолчанию, если для этой модели весов нет.

Формат набора и метрики — [`docs/CALIBRATION.md`](docs/CALIBRATION.md). Веса проверяются при
загрузке: нет файла, битый JSON или нечисловой коэффициент — печатается одно предупреждение и
включается встроенная формула, оценка не ломается. Признаки, которые видит модель:
`meanLp` (ln геом. среднего), `minLp` (ln худшего токена), `meanPhi` (уверенность первого токена
по top-K), `fracLow` (доля токенов с вероятностью ниже 0.5), `digitDensity` (доля цифр в тексте).

Свой скорер на другом языке — либо `scripts/calibrate.py --fit` для весов, либо своя реализация
интерфейса `Scorer` в `packages/core/src/truthprobe/scorer.ts`.

### Проверка обученного детектора: отрицательный результат

Мы собрали 265 размеченных ответов (76 выдумок, 189 верных, 4 модели, 68 вопросов) и попробовали
обучить детектор на признаках, которые скорер и так считает. Результат отрицательный: OOF AUROC
обученной логистики **0.783** (пять продуктовых признаков) и **0.815** (26 признаков без длины)
против **0.799** у встроенной формулы `1 − exp(meanLp)`; доверительные интервалы на разницу
накрывают ноль (`−0.057…+0.020` и `−0.036…+0.069`). Если убрать линейный вклад длины ответа,
качество падает до случайного — **0.541**. Внутри отдельных категорий вопросов AUROC 0.33–0.47,
то есть на уровне случая или хуже. Ранее опубликованные веса `data/weights-detector.json` отозваны:
метрика 0.881 была посчитана на повреждённом наборе. Все числа и разбор —
[`docs/LEARNED-WEIGHTS.md`](docs/LEARNED-WEIGHTS.md).

### Патч вручную

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout 007afb1
# identity только для этой команды: без неё git am падает с "empty ident name"
git -c user.name=TruthProbe -c user.email=truthprobe@localhost am /path/to/patches/truthprobe-0001.patch
bun install
bun run --cwd packages/cli src/index.ts
```

Ключи и провайдеры проверяются сами: при первом запросе к chat-completions модели ядро
отправляет одну посылку на один токен с текстом `ping` и, если провайдер вернул `logprobs`,
включает их для этой пары `провайдер/модель`. Переменные окружения не нужны.

### Готовый бинарь

Публичных сборок **нет**: ни один бинарь не опубликован, скачивать нечего. Контрольная сумма
есть только у той сборки, на которой снимались числа этого репозитория: полный `sha256`
`396be271b40c96da602d208df35d27ec947b4716aa4b29de7a5afc9a15b1eb8d` записан в
[`docs/BUILD.md`](docs/BUILD.md). Собирать надо из дерева, которое поставил `install.sh`:

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
по имени npm-пакета. Результат — `dist/win-unpacked` (портативная папка, ≈877 MB: 246 MB приложение,
279 MB вложенный CLI и остальное): её можно положить
куда угодно и запускать `TruthProbe.exe`. Заголовок окна, AppUserModelID, каталог
`%APPDATA%\ai.truthprobe.desktop` и имя установщика берутся из этих двух переменных; без них сборка
остаётся обычным opencode.

**Сборка не подписана.** `TruthProbe.exe` собирается без сертификата: в свойствах файла
`Signature: NotSigned`, и SmartScreen встретит первого пользователя предупреждением
«неизвестный издатель». Метаданные при этом свои (`ProductName`, `CompanyName`,
`LegalCopyright` — `TruthProbe`, `FileVersion` — версия продукта). Как собрать подписанную
сборку — `docs/DEVELOPMENT.md`, раздел «Подпись».

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

Одна формула, применённая дважды — к каждому предложению и ко всему ответу. Энтропия, худший токен
и доля низких вероятностей остаются **признаками** для обученных весов, но в оценку по умолчанию
не входят: замер показал, что энтропия первого токена разворачивает результат (`docs/VALIDATION.md` §14).

<p align="center">
<b><i>s</i><sub>i</sub> = exp(<i>ℓ̄</i><sub>i</sub>)</b>
&nbsp;&nbsp;&nbsp;где&nbsp;&nbsp;&nbsp;
<i>ℓ̄</i><sub>i</sub> = (ℓ<sub>i,1</sub> + ℓ<sub>i,2</sub> + … + ℓ<sub>i,n</sub>) / <i>n</i><sub>i</sub>
</p>

<p align="center">
<b><i>S</i> = 0.6 · <i>S</i><sub>all</sub> + 0.4 · (<i>s</i><sub>1</sub> + <i>s</i><sub>2</sub> + … + <i>s</i><sub>m</sub>) / <i>m</i></b>
&nbsp;&nbsp;&nbsp;&nbsp;
<i>r</i><sub>i</sub> = 1 − <i>s</i><sub>i</sub>
&nbsp;&nbsp;&nbsp;&nbsp;
<i>r</i> = 1 − <i>S</i>
</p>

| Обозначение | Что это |
| :--- | --- |
| <i>s</i><sub>i</sub> | уверенность i-го предложения, от 0 до 1 |
| <i>r</i><sub>i</sub> | риск i-го предложения, 1 − <i>s</i><sub>i</sub> |
| ℓ<sub>i,k</sub> | `logprob` k-го содержательного токена предложения i |
| <i>ℓ̄</i><sub>i</sub> | среднее ℓ<sub>i,k</sub> по содержательным токенам предложения |
| <i>n</i><sub>i</sub> | число содержательных токенов в предложении i |
| <i>m</i> | число предложений в ответе |
| <i>S</i><sub>all</sub> | та же формула, но по всем содержательным токенам ответа |
| <i>S</i>, <i>r</i> | итог по ответу и его риск; 0.6 / 0.4 — `globalWeight` |

Иначе говоря, **уверенность = средняя вероятность токенов**, а не «самый слабый токен». Порог
плашки — <i>r</i> > 0.45; уровни — `safe ≥0.90`, `likely ≥0.75`, `uncertain ≥0.55`,
`risky ≥0.35`, ниже — `unreliable`.

Признаки, которые считаются всегда и идут в обученные веса, если они подключены:

| Признак | Формула | Смысл |
| :--- | :--- | --- |
| φ | 1 − <i>H</i><sub>K</sub> / ln <i>K</i> | уверенность по первому токену, 0…1 |
| <i>H</i><sub>K</sub> | −Σ<sub>i=1</sub><sup>K</sup> <i>q</i><sub>i</sub> · ln <i>q</i><sub>i</sub> | энтропия распределения top-K |
| <i>q</i><sub>i</sub> | <i>e</i><sup>ℓᵢ</sup> / Σ<sub>j=1</sub><sup>K</sup> <i>e</i><sup>ℓⱼ</sup> | нормированная вероятность альтернативы i |
| <i>K</i> | 20 | сколько альтернатив просим у провайдера |
| <i>f</i><sub>low</sub> | #{<i>k</i> : ℓ<sub>k</sub> < ln 0.5} / <i>n</i> | доля токенов с вероятностью ниже 0.5 |
| ℓ<sub>min</sub> | min<sub>k</sub> ℓ<sub>k</sub> | худший `logprob` |
| <i>d</i> | #{цифры} / #{символы} | доля цифр в видимом ответе (`digitDensity`) |

Здесь <i>d</i> — единственный текстовый признак с измеримым вкладом (+0.014 AUROC поверх полного
набора признаков, `docs/VALIDATION.md` §17). Хеджирование («probably», «I think») меряли — на текущем наборе
разброс нулевой, вклад не измерен.

Сегментация — по `. ! ? …` с учётом десятичных дробей, сокращений и CJK-терминаторов; блоки кода
выбрасываются целиком. Состояния: `ok` — токены совпали с текстом; `partial` — дрейф смещений;
`unavailable` — токенов нет.

## Проверки

| Что | Как | Результат |
| --- | --- | --- |
| Скоринг и сегментация | `bun test test/score.test.ts` | **44 pass / 0 fail**, 99 expect |
| Логика автопроверки (TTL, классификация ответов, кэш) | `bun test test/capability.test.ts` | **35 pass / 0 fail**, 73 expect |
| Список спорных предложений в desktop | `bun test src/message/doubtful.test.ts` из `packages/session-ui` | **9 pass / 0 fail**, 23 expect |
| Протокол OpenAI (гейт, тело запроса, разбор `choices[i].logprobs`) | `test/opencode-tree/protocol.test.ts`: в этом репозитории **8 skip** — файл реально прогоняется только внутри пропатченного дерева (`packages/ai/test/`, CI ставит `TRUTHPROBE_REQUIRE_PROTOCOL_TESTS=1`) | **8 pass / 0 fail** в дереве; в этом репозитории все 8 пропущены |
| Автовключение без переменных окружения | мок + два прогона подряд | RUN1: проба → `{"status":"ok"}`; RUN2: **2 из 2** запросов с `logprobs: true, top_logprobs: 20` |
| Регрессия вокруг событий текста | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Полный прогон core | `bun test` в `packages/core` (7 713 тестов, 331 файл) | 7 300 pass / 351 skip / 62 fail — ни одного в truthprobe: `tool-search` качает ripgrep с github.com, `provider-gitlab-oauth` ходит на gitlab.com, `cross-spawn`/MCP зависят от spawn; в окружении зарезана исходящая сеть |
| Тесты TruthProbe, этот репозиторий | `bun test test` | **92 pass / 8 skip / 0 fail**, 210 expect, 5 файлов, 100 тестов |
| Тесты TruthProbe, пропатченное дерево | `bun test truthprobe` в `packages/core/test` | **129 pass / 0 fail**, 6 файлов |
| Патч на чистом дереве | `git am` в worktree `007afb1` | применяется без конфликтов (identity задана локально), все truthprobe-тесты зелёные |
| Типизация | schema / ai / core / client / tui | зелёная (132 / 357+322 / 2 036 / 181 / 1 947 файлов) |
| Типизация UI-пакетов | session-ui / app / desktop | зелёная (384 / 2 447 / 3 571 файл, desktop — 2 проекта) |
| Сквозной прогон | мок-провайдер с настоящими `logprobs` | `logprobs: true, top_logprobs: 20` в запросе, `truthprobe` в базе |
| Живой TUI | pty-проба | бейдж и блок спорных предложений отрендерились |
| Desktop UI | чип `confidence` в общем компоненте `@opencode/session-ui` | типизация desktop (3 571 файл) зелёная; чип `confidence NN%` и список спорных предложений в футере |
| Отдельное desktop-приложение | сборка с `OPENCODE_DESKTOP_APP`/`OPENCODE_DESKTOP_APP_ID` | `TruthProbe.exe`, заголовок окна `TruthProbe`, userData `ai.truthprobe.desktop`, сайдкар CLI рядом, `app-update.yml` нет |
| Windows-бинарь | `.exe` на моке | `status: "ok", score: 0.417, first 0.708, flagged: 1` |

Воспроизвести без ключей:

Блок ниже запускается **внутри пропатченного дерева opencode** (`.worktree/opencode` после
`make setup` или дерево, которое поставил `install.sh`), а не в этом репозитории: здесь нет
`packages/`, поэтому `bun run --cwd packages/cli` из корня репозитория не найдёт пакет.

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
| Тесты truthprobe | `bun test` шести файлов в `packages/core/test` | **129 pass, 0 fail** (пропатченное дерево; в этом репозитории — **92 pass / 8 skip**) |
| Тесты всего монорепо | `bun test` в `packages/core` — 7713 тестов, 331 файл | **7300 pass, 351 skip, 62 fail** |
| Ответ `freepi/particle` | живой запрос через боевой бинарь | `score 0.7595 · likely`, предложение `#0 0.603 · uncertain` |
| Ответ `freepi/deepseek-v4.1-flash` | живой запрос | `score 0.6893`, первый флаг `0.4849` |
| Сменный скорер | `TRUTHPROBE_SCORER=linear:weights.json` | score сместился с `0.7595` до `0.9992` — подмена реально работает |
| Установщик Windows | `install.ps1 -Dir <пусто> -DryRun` | клон, `git apply --check`, все коммиты патча применились, ошибок нет; CI повторяет это на каждом пуше |
| Сборка desktop | electron-builder | приложение 246 МБ, вложенный CLI 279 МБ |
| CI на чужих машинах | GitHub Actions, прогоны [`44593481931`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44593481931), [`44678633546`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44678633546) , [`44736706708`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44736706708) , [`44761971781`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44761971781) и [`44784920180`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44784920180), [`44787911144`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44787911144) и [`44918215420`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44918215420) и [`45161855972`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45161855972) (0.13.12), [`45163760974`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45163760974) (0.13.13), [`45165859105`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45165859105) (0.13.14), [`45169068249`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45169068249) (0.13.15) | **все 7 job'ов success** в каждом, на hosted-раннерах ubuntu-latest и windows-latest |
| Веса на модель в рантайме | два прогона на моке с разными бандлами, один и тот же ответ | `0.9997 · safe`, когда веса есть для `mock/mock-1`, и `0.0003 · unreliable`, когда они только у `other/model` — выбор по `providerID/modelID` реально работает |
| `collect.py` на живом шлюзе | 2 промпта, `freepi/particle` | строки с `meanLp -0.063 / -0.125`, `minLp -0.409 / -0.945`, `fracLow 0.00 / 0.06` — признаки считаются той же формулой, что в рантайме |
| Аудит банка вопросов | `python3 scripts/audit-bank.py data/qa-hard-bank.jsonl data/rows-hard.jsonl` | нашёл **4** пункта, где ошибается не модель, а эталон; после чистки набора — `AUROC n/a (one class)`, 739 верных / **0 неверных** |
| Сбор негативов | 47 вопросов × 4 модели × 4 сэмпла при `T=0.8` и `T=1.0`, затем ещё три банка (34 вопроса, классические провалы LLM, счёт по списку) | 1504 строки (47 × 4 × 4 × 2 температуры) + 688 строк на трёх дополнительных банках; настоящих негативов **0** — модели либо отвечают верно, либо молчат |
| Заказанная ложь: видит ли скорер | `scripts/measure-lies.py` на 626 строках (544 правды / 82 лжи) | прежняя формула — AUROC **0.388** (хуже случайного), ECE 0.368; обученные веса — 0.800 out-of-fold (групповая CV) |
| Встроенная формула переписана | те же 626 строк + 739 верных строк как контроль | `exp(meanLp)` вместо `0.4·geo + 0.3·worst + 0.3·φ`: AUROC **0.388 → 0.597**, ECE **0.368 → 0.098**, а на верных ответах ECE **0.493 → 0.160** |

**Про 62 падения в монорепо:** ни одно не относится к truthprobe. Причины видны в логе и не связаны
с патчем: `tool-search` тянет ripgrep с github.com, `provider-gitlab-oauth` ходит на gitlab.com,
`cross-spawn` и MCP-тесты зависят от spawn — в этом окружении исходящая сеть для тестов зарезана
(`test attempted network request: GET https://github.com/...`).

Чего мы **не** проверяли, и врать об этом не будем:

- **Чистые виртуальные машины — теперь проверено в CI.** GitHub Actions поднимает раннеры
  `ubuntu-latest` и `windows-latest` с нуля: прогоны
  [`44593481931`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44593481931) и
  [`44678633546`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44678633546)
  (уже с per-model весами) подтвердили, что установщики проходят `--dry-run` на обеих ОС, патч
  применяется к чистому дереву и ведёт себя одинаково. Это не ручная установка на десктоп, но это чистая ОС.
- **Linux и macOS.** `install.sh` теперь проверяется в CI на ubuntu-latest (dry-run, без установки
  в систему). macOS-раннер в матрице установщика не участвует — там проверялись только юнит-тесты.
- **Облачные провайдеры с ключами.** OpenAI, Anthropic, Gemini не проверялись — только локальный
  шлюз free-pi и мок-провайдер в e2e. Вывод об их поддержке основан на формате протокола, а не на замерах.
- **Калибровка — пока не измерена, и это выяснилось честным путём.** `calibrate.py --demo --fit`
  даёт `AUROC 1.000 / ECE 0.039` на синтетике — свойство синтетики, а не качество скорера.
  Первый замер на реальных данных (`data/rows-hard.jsonl`) дал `per-model 0.866`, но потом
  выяснилось, что все 40 «негативов» — брак: 23 ответа на двусмысленный вопрос («Saturn or Neptune»
  при эталоне `jupiter`) и 17 обрывов по `max_tokens`. После чистки в наборе **739 верных и 0
  неверных**, `evaluate.py` печатает `AUROC n/a (one class)`. Поэтому числа 0.538/0.683/0.866
  отозваны, а вместо них появился `scripts/audit-bank.py`, который ловит такой брак банка до
  обучения. Подробности — `docs/VALIDATION.md` §12.

## Устройство патча

53 файла, +3626/−55, тридцать коммитов поверх `007afb1`. Шов тонкий и аддитивный:

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
test/score.test.ts        44 теста без сети и без зависимостей
test/capability.test.ts   35 тестов статусов, TTL и кэша автопроверки
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
  данным: на живых длинных ответах их стоит перепроверить. Переопределяется
  `TRUTHPROBE_RISKY_THRESHOLD`. Переменная `TRUTHPROBE_SHAKY_THRESHOLD` удалена в 0.13.8: она
  ничего не настраивала (`docs/VALIDATION.md` §23, пункт 8).
- Известная слабость подхода: уверенная ложь. Лечится не порогом, а вторым независимым сигналом.

## Лицензия

MIT — см. [LICENSE](LICENSE). `opencode` остаётся под своей лицензией; здесь только патч.

## Что ещё не сделано (честный список)

План работ на 0.5 — [`docs/ROADMAP.md`](docs/ROADMAP.md): шкала уровней, заметная подсветка,
матрица поддерживаемых моделей, установка одним скриптом, сменный ML-скоринг.

Эти пункты из ревью закрыты **не** были (кроме отмеченных), и мы не делаем вид, что они закрыты:

- **Калибровка на настоящих галлюцинациях.** AUROC и ECE измерены, но на наборе «заказанной лжи»:
  626 строк, из них 82 негатива получены просьбой «соври». Самопроизвольных ошибок модели в наборе
  нет — 1504 запроса на четырёх моделях шлюза (47 вопросов × 4 модели × 4 сэмпла × 2 температуры)
  дали ноль негативов. Второго независимого набора
  тоже нет, поэтому CI-гейта по AUROC не будет, пока он не появится. Протокол и скрипт —
  [`docs/CALIBRATION.md`](docs/CALIBRATION.md) и `scripts/calibrate.py`.
- **Исправлено 22.11.2026. Поддержка logprobs проверяется по модели, а не по провайдеру.** Кэш
  автопроверки адресуется парой `provider/model`: подтверждённая `particle` больше не включает
  `logprobs` для `deepseek-*`, и провайдер, у которого часть моделей поле не знает, не получает 400
  на весь запрос. Плата — один пробный запрос на каждую новую модель, дальше вердикт кэшируется.
- **`temperature > 0`.** `top_logprobs` при ненулевой температуре — сглаженное распределение, а не
  уверенность модели. Мы это не блокируем и не помечаем `partial`; числа остаются числами, но
  трактовать их как «уверенность» при `temperature > 0` нельзя.
- **`top_logprobs` не настраивается.** `PROBE_TOP_K = 20` в `plugin-truthprobe.ts` — константа,
  уменьшить трафик нельзя; тот же размер в скорере задаёт `DEFAULT_SCORE_OPTIONS.topK`.
- **Два экземпляра TTL.** `core/src/truthprobe/capability.ts` и `ai/src/protocols/truthprobe-capability.ts`
  дублируют логику свежести; теста на рассинхрон нет.
