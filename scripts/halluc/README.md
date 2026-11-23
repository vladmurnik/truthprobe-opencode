# Hallucination detector: how to reproduce the measurement

The data is not part of the repository: it is 20 MB of answers with tokens. Below is the order of steps —
exactly in this order, otherwise the features are computed over a corrupted dataset.

1. `collect3.py` — 31 trap questions × 4 models through an OpenAI-compatible gateway
   (`OPENCODE_BASE` defaults to `http://127.0.0.1:8790/v1`); the transport comes from
   `/home/adik/halluc/collect.py`, so put it next to this folder or set `HALLUC_DIR`.
   Writes `rows_raw3.jsonl`, labels are three-valued, resumes by the `(model, qid)` pair.
2. **`repair.py`** — restores the text of answers the collector saved with an empty
   `answer` while the tokens were live, and relabels them with the same rules. Writes `rows_raw2f.jsonl`
   and `rows_raw3f.jsonl`, leaves the sources untouched. Without this step half of the negative class
   is save truncation rather than fabrication; that is exactly how the inflated numbers in §21 appeared.
3. `score_all.ts` — runs the answers through the runtime scorer
   (`packages/core/src/truthprobe/score.ts`), writes `rows_scored2.jsonl` / `rows_scored3.jsonl`.
   By default it reads the already repaired `*f.jsonl` files.
4. `dataset.py` — 30 features from the tokens and the text → `dataset.jsonl` (`y = 1` for a lie).
5. `eval.py` — what is worth publishing: baselines, trained models, length control
   (orthogonalization by `n_tokens` inside the fold), AUROC by category and length quartile,
   cluster bootstrap by `qid` for confidence intervals.
6. `train.py` — logistic, CART, forest, mini-MLP on the stdlib, `GroupKFold` by `qid`,
   with and without length features; writes `model.json`. This is exploration, not a published result.
7. `ablate.py` — ablations and `leave-one-model-out`.
8. `thresholds.py` — shares of lies/truths below the product thresholds.

Numbers and caveats — `docs/VALIDATION.md` §22 (§21 published withdrawn values:
there the negative class was half empty answers). Short summary — `docs/LEARNED-WEIGHTS.md`:
the trained weights do not beat the built-in formula, so they are not shipped.
