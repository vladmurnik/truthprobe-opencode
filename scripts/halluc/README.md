# Детектор выдумок: как воспроизвести замер

Данные в репозиторий не входят: это 20 МБ ответов с токенами. Ниже порядок шагов.

1. `collect3.py` — 31 вопрос с ловушкой × 4 модели через OpenAI-совместимый шлюз
   (`OPENCODE_BASE` по умолчанию `http://127.0.0.1:8790/v1`); транспорт берётся из
   `/home/adik/halluc/collect.py`, поэтому положите рядом и его, либо задайте `HALLUC_DIR`.
   Пишет `rows_raw3.jsonl`, метки трёхзначные, возобновляется по паре `(model, qid)`.
2. `score_all.ts` — прогоняет ответы через рантайм-скорер (`packages/core/src/truthprobe/score.ts`),
   пишет `rows_scored2.jsonl` / `rows_scored3.jsonl`.
3. `dataset.py` — 30 признаков из токенов и текста → `dataset.jsonl` (`y = 1` для ложного).
4. `train.py` — логистика, CART, лес, мини-MLP на stdlib, `GroupKFold` по `qid`,
   с признаками длины и без; пишет `model.json`.
5. `ablate.py` — абляции и `leave-one-model-out`.
6. `thresholds.py` — доли ложных/верных ниже порогов продукта.

Числа и оговорки — `docs/VALIDATION.md` §21.
