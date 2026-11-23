> Русская версия: [docs/ru/CALIBRATION.md](ru/CALIBRATION.md)

# Calibration

**Status: measured on the "ordered lies" set, not on spontaneous hallucinations.**

There are 626 rows: 544 truths and 82 negatives, and the negatives were obtained by asking "lie". On them AUROC
and ECE are computed and live in `docs/VALIDATION.md` §14–§15. There are no real hallucinations in the set: 1504
requests (47 questions × 4 models × 4 samples × two temperatures, `T=0.8` and `T=1.0`) on four gateway models
gave zero negatives — the models either answer
correctly or stay silent. So the numbers below are about this set, not a universal property of the scorer.

What was measured (626 rows, grouped cross-validation by `model + prompt` — why exactly this way,
see `docs/VALIDATION.md` §17):

| Formula | AUROC | ECE |
| --- | --- | --- |
| the previous `0.4·geo + 0.3·worst + 0.3·φ` | 0.388 | 0.368 |
| the current default `exp(meanLp)` | 0.597 | 0.098 |
| learned weights, out-of-fold | 0.800 | 0.275 |

There are 626 rows, but only **205** unique `(model, prompt, answer, label)` pairs: the same answer
occurs up to four times (`sample 0..3`), and 34 questions are reused by all models. Folds
cut by rows left 88.5% of test rows with the byte-identically same answer in training —
therefore folds are cut by groups `(model, prompt)`. On the deduplicated 205 rows the learned
weights give **0.801**, the built-in formula — **0.640**.

ECE of the learned weights (0.275) is worse than that of the built-in formula (0.098): they help
to sort answers, but they give out biased probabilities. Therefore `exp(meanLp)` is enabled by default.

On 739 known-correct answers ECE drops from 0.493 to 0.160. The `digitDensity` feature gives **+0.014**
AUROC on top of the full feature set (ablation: 0.7858 without it versus 0.7998 with it, §17).
The ablation is sensitive to the fold split: on other seeds the same trick gives +0.041 and +0.047,
so +0.014 is a lower estimate of the contribution, not an exact value.
Per-model: `glm-5.3-flash` **0.840** on 198 rows (62 negatives); `deepseek-v4.1-flash` has 6
negatives, `particle` 10, `deepseek-v4-flash` 4 — fewer than the threshold 30, weights are not issued for them.

Percentages in the UI are still read as: **how smoothly the model walked through this text**. This is not
the probability of truth and not the probability of hallucination — confident lying exists
(`docs/PRIOR-ART.md`, ECLIPSE 2512.03107), and a threshold does not cure it.

## What is missing for this to become a full-fledged calibration

1. **Real negatives.** 200–500 sentences from real answers where the model errs on its own, not
   on request. The labels `true` / `false` / `unverifiable` are set by a human from sources; `unverifiable`
   is not to be thrown away but counted separately — otherwise the metric is biased toward verifiable facts.
2. **A second independent set.** Without it one can neither validate the weights nor set up a CI gate on AUROC:
   0.800 and 0.597 were obtained on one set, and overfitting on it is not ruled out.
3. **Precision/recall at thresholds.** How many false flags per 100 correct sentences we are willing to
   show — this is a policy, and so far nobody has chosen it.
4. **A threshold from data.** `riskyThreshold = 0.45` and the level boundaries `0.90 / 0.75 / 0.55 / 0.35`
   are still chosen by common sense, not from labelled data.

## The tool

`scripts/calibrate.py` computes AUROC and ECE over JSONL with the fields `score`, `phi`, `meanLp`, `minLp`,
`digitDensity`, `label`. Folds are built by groups `(model, prompt)`; byte-identical answers
are collapsed by `scripts/measure-lies.py --dedupe` (`calibrate.py` has no such flag). Without a labelled
file it runs only with `--demo`, which generates
synthetics: `AUROC 1.000` there is a property of the synthetics, not the quality of the scorer.

The full set of arguments: `python3 scripts/calibrate.py <file.jsonl> [--fit] [--by-model] [--out FILE]`
or `python3 scripts/calibrate.py --demo`.

## Honesty rules in the UI

- `unavailable` is shown with the reason rather than hidden.
- `first-token confidence` is named the first token, not the "first sentence".
- `answer confidence` is always visible, including good answers.
- README and this file directly state on which set the numbers were obtained and what is missing in them.

## Training the scorer weights

```bash
python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json
```

It prints AUROC and ECE over out-of-fold predictions (5 folds), then the weights of the linear model:

```
score = sigmoid(bias + w1·meanLp + w2·minLp + w3·meanPhi + w4·fracLow + w5·digitDensity)
```

With `--by-model` the weights are computed separately for each model from the `model` field and written as a bundle
`{"models": {"provider/model": {...}}}`; the runtime picks the set by `providerID/modelID`. Weights are
issued only if the model has at least 30 examples of each class; otherwise the bundle has
`"weights": null` and the global set is used. Fewer than that is no longer calibration: on four negatives
the `meanPhi` weight came out negative and made the score worse than random.

The `phi` field in sets collected before 22.11.2026 is **entropy** (0 = confident), while the runtime computes
confidence (`1 − entropy`). `calibrate.py` brings old rows to confidence on load,
so the learned weights and the runtime speak the same language.
Weights go into JSON and are enabled by the variable `TRUTHPROBE_SCORER=linear:<path>`.
Classes are balanced during training, L2 = 1e-3.

Any load error (no file, broken JSON, non-numeric coefficient) does not break scoring: one warning is printed
and the built-in formula `exp(meanLp)` is enabled.
