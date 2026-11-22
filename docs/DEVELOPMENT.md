# Development: карта «что где менять»

TruthProbe живёт в пропатченном дереве `.worktree/opencode` (создаётся `make setup`).
Пути ниже — относительно корня **этого дерева**, т.е. `packages/…`. Ссылки на оригинальные
файлы sst/opencode из `docs/DEVELOPMENT.md` даны, чтобы их было видно и без дерева.

## Поток данных (куда смотреть первым делом)

```
provider stream ─► packages/ai/… (request logprobs, parse tokens)
       │                logprobs из ответа
       ▼
session/runner/publish-llm-event.ts   ─ накапливает токены, в конце зовёт scoreAnswer
       │    modelKey = providerID/modelID
       ▼
packages/core/src/truthprobe/score.ts ─ scoreAnswer(): выравнивание токенов, разбивка
       │                                  на предложения, признаки → Scorer
       ▼
packages/core/src/truthprobe/scorer.ts ─ geometric (по умолчанию) или linear-веса
       │                                  из TRUTHPROBE_SCORER, выбор по модели
       ▼
schema/src/truthprobe.ts ─ сериализация итога (AnswerScore) в базу/клиент
       ▼
packages/session-ui/src/message/… ─ desktop-чип «confidence NN%» и спорные предложения
packages/tui/src/routes/session/message-parts.tsx ─ то же в терминальном UI
```

signature вердикта (`AnswerScore`): `status`, `score`, `risk`, `level`, `first`,
`sentences[] {i,start,end,text,score,risk,meanLp,minLp,phi,tokens,flag,level}`, `flagged`.

## Математика (пакеты core)

| Файл | Что внутри | Когда трогать |
|---|---|---|
| `src/truthprobe/types.ts` | `TokenLogprob`, `ScorerInput{features,text,model}`, `LinearWeights`, `ScoreOptions`, `SentenceScore`, `AnswerScore`, `DEFAULT_SCORE_OPTIONS` | меняется контракт скорера/схемы |
| `src/truthprobe/score.ts` | `phi()` (1 − норм. энтропия top_logprobs), `alignTokens`, `splitSentences`, `scoreAnswer(text, tokens, options, model)` | формула уверенности, разбиение, признаки |
| `src/truthprobe/scorer.ts` | `geometricScorer`, `linearScorer`, `parseLinearWeights`, `WeightsBundle`, `parseWeightsBundle`, `bundleScorer`, `weightsFor`, `scorerFromEnv()` | сменные веса, выбор `models[providerID/modelID]`, откаты |
| `src/truthprobe/levels.ts` | `LEVEL_BOUNDS` (safe 0.90, likely 0.75, uncertain 0.55, risky 0.35), `levelOf` | пороги уровней |
| `src/truthprobe/sentences.ts` | `splitSentences` (честное разбиение на предложения) | токенизация текста |
| `src/truthprobe/capability.ts` | возможность модели отдавать `logprobs` | авто-включение probe'а |

**Важно:** `src/truthprobe/*` в этом репозитории — reference-копии для тестов без клона.
После правки в dev-дереве их надо синхронизировать (см. ниже). Тесты репозитория в `test/`.

## Признаки скорера (должны совпадать везде!)

| Признак | Определение | Где считается |
|---|---|---|
| `meanLp` | среднее logprob по содержательным токенам ответа | `score.ts` |
| `minLp` | худший logprob | `score.ts` |
| `phi` | 1 − норм. энтропия по `top_logprobs` **первого** токена | `score.ts` `phi()` |
| `fracLow` | доля токенов с `logprob < ln 0.5` | `score.ts` |
| `digitDensity` | доля цифр среди символов видимого ответа | `score.ts` `digitDensity()` |

Эти же формулы обязаны быть в `scripts/collect.py` и `scripts/calibrate.py`, иначе обученные
веса применяются к другим числам и калибровка разваливается. Признаки повторены там
комментарием-ссылкой на `score.ts`.

## Скрипты калибровки (репозиторий, вне патча)

| Файл | Роль |
|---|---|
| `scripts/collect.py` | сбор строк по моделям и промптам, `--auto-label` по банку `{prompt, expect}`, вырезает reasoning-токены |
| `scripts/calibrate.py` | `--fit` (linear-веса), `--fit --by-model` (бандл `{global, models}`), AUROC/ECE, отказ при одноклассовых данных |
| `scripts/probe-freellmapi.py` | проверка, что эндпоинт отдаёт `logprobs` |
| `scripts/mock-openai-logprobs.py` | мок-провайдер с настоящими logprobs (для e2e и `make preview`) |
| `scripts/preview.sh` / `dev-setup.sh` / `dev-setup.ps1` / `make-patch.sh` / `build-desktop.sh` | DX-обвязка |
| `data/qa-bank.jsonl` | канонические ответы для авто-разметки (`expect`) |

## Как поменять конкретную вещь

### Порог уровня (например `safe: 0.90 → 0.93`)
1. `src/truthprobe/levels.ts` → `LEVEL_BOUNDS.safe`.
2. `packages/core/test/truthprobe-levels.test.ts` (в дереве) — тесты границ.
3. `make patch`, `make verify`, обновить цифры в README/docs.

### Добавить признак в скорер
1. `src/truthprobe/scorer.ts`: `FEATURE_NAMES` + `LinearWeights` в `types.ts`.
2. `src/truthprobe/score.ts`: посчитать и положить в `ScorerFeatures`.
3. `scripts/calibrate.py`: `COLUMNS`, `fit()` (вектор), `--by-model`.
4. `scripts/collect.py`: `features()`.
5. Тесты на парсинг бандла и откаты: `truthprobe-scorer-bundle.test.ts`.
6. Патч, verify, документация.

### Веса только для `freepi/particle`
```bash
python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --model freepi/particle \
    --prompts data/prompts-labeled.jsonl --out data/rows.jsonl
# проставить label 0/1, затем:
python3 scripts/calibrate.py data/rows.jsonl --fit --by-model --out data/weights.json
TRUTHPROBE_SCORER=linear:data/weights.json bun run --cwd .worktree/opencode/packages/cli src/index.ts run "…"
```
Рантайм берёт `models[providerID/modelID]` и откатывается на `global`. Битая запись модели
пропускается молча.

### UI (desktop-чип и спорные предложения)
- `packages/session-ui/src/message/confidence.tsx` — новый общий компонент: `ConfidenceMeter`
  (шкала), `ConfidenceLine` (строка «confidence NN% · level»), `DoubtfulList` (список
  предложений с плашкой «#N NN% level»).
- `packages/session-ui/src/message/message-content.tsx` — место вставки `<ConfidenceLine/>` +
  `<DoubtfulList/>` (блок `data-slot="text-part-doubtful"`), плюс мемо `confidence()` для
  мета-строки (first-token NN% / answer NN% / N doubtful).
- `packages/session-ui/src/message/doubtful.ts` — хелперы: `levelOfInfo(probe)`,
  `levelOfSentence(item)`, `doubtfulSentences(probe)`, `percentOf`.
- `packages/tui/src/routes/session/message-parts.tsx` — тот же вердикт в TUI.

Проверка типизации пакета — из корня дерева opencode: `bun run --cwd packages/session-ui typecheck`
(тот же вызов, что в CI; для TUI — `bun run --cwd packages/tui typecheck`).

### Prompt / промпты сбора
Файл промптов: txt (по строке) или JSONL `{"prompt": "...", "label": 0/1}`. Пары
`(model, prompt)` в `--out` пропускаются при `--resume`. Банк для `--auto-label`:
`{"prompt": "...", "expect": ["canberra", "two", "2"]}` — короткие эталоны сравниваются
регуляркой по границам слова, длинные — подстрокой.

## Окружение и переменные

| Переменная | Где читается | Назначение |
|---|---|---|
| `OPENCODE_TRUTHPROBE=1` | ai-provider, авто-включение | вкл. сбор logprobs (обычно не нужна, capability решает) |
| `TRUTHPROBE_SCORER=linear:<path>` | `scorer.ts`, `score.ts` | путь к весам; пусто/`geometric` = встроенный |
| `TRUTHPROBE_BASE` | `Makefile`, `dev-setup.*`, `make-patch.sh` | коммит sst/opencode под патч (default `007afb1b`) |
| `TP_DIR` / `OPENCODE_REPO` | `Makefile`, `preview.sh`, `build-desktop.sh` | где развёрнуто dev-дерево |
| `MOCK_PORT` / `COLLECT_URL` | `preview.sh`, `collect.py` | адрес мок-/target-эндпоинта |

Пример `.env.example` в корне репозитория.

## Как узнать, что ничего не сломалось

```bash
make verify                        # тесты репо + патч на чистой базе
cd .worktree/opencode
bun test truthprobe                # юнит-тесты патча (127 на сейчас)
```
(реальный прогон — `make preview`; вердикт смотрите в `scripts/inspect-db.py` или
`make preview` выведет сам.)

## Перед сборкой патча

1. Коммит в dev-дереве (никаких незакоммиченных изменений — `make-patch.sh` откажется).
2. `make patch` → `patches/truthprobe-0001.patch`.
3. Синхронизировать reference-копии `src/truthprobe/*` (иначе `make test` проверит старьё).
4. `make verify`.
5. Desktop: `bash scripts/build-desktop.sh --win` (результат в `packages/desktop/dist/win-unpacked`),
   установка поверх `AppData/Local/Programs/TruthProbe` при необходимости.
   Скрипт сам копирует собранный CLI в `packages/desktop/resources/opencode-cli[.exe]` — именно
   оттуда electron-builder берёт бинарь (`extraResources`). Если этот шаг пропустить, приложение
   соберётся со **старым** CLI и будет молча вести себя как предыдущая версия.