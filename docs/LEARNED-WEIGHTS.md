> Русская версия: [docs/ru/LEARNED-WEIGHTS.md](ru/LEARNED-WEIGHTS.md)

# The learned hallucination detector: a negative result

22 November 2026. This document replaces the previous version, which published AUROC 0.881 and advised
connecting `data/weights-detector.json`. Those weights are **withdrawn**: the metric was computed on a corrupted
set where half of the "hallucinations" turned out to be text loss. Below — what exactly broke, what came out
after the fix and why the conclusion is now negative.

## What is in the set

265 labelled answers: 4 gateway models (`particle`, `deepseek-v4.1-flash`, `deepseek-v4-flash`,
`glm-5.3-flash`), 68 questions, `temperature 0`, `logprobs` with `top_logprobs 20`. Questions are of two kinds:
deliberately false premises and control correct ones.

| category | false / total |
| --- | --- |
| fact | 0 / 79 |
| numer | 0 / 59 |
| false-premise | 23 / 48 |
| fake-work | 37 / 48 |
| fake-person | 11 / 12 |
| myth | 5 / 19 |

## What was broken

The original set had 102 "false" answers, and in **52 of them the answer text was an empty string**
with `n_tokens = 160` — exactly at the `max_tokens` limit. The model answered, the tokens were saved, the text
did not land in the `answer` field: a collector error, not model behaviour. The label was still assigned
mechanically, and the empty string got `wrong` simply because neither the expected words
nor refusal features were found in it.

The fix: the text was reassembled by concatenating tokens from `rows_raw*.jsonl`, then the same labelling rules
were applied to the restored text. Result:

```
run B: 19 answers restored, 2 rows without tokens discarded
run C: 33 answers restored, 6 rows without tokens (provider errors) discarded
of the 52 restored, 26 turned out correct (17 correct + 9 correct_qualified)
total: was 102 "false" → became 76 fabrications and 189 correct
```

So half of the negative class was an artefact of data collection. Any metric computed on the
old set measured, among other things, "can the model tell an empty string from a non-empty one".

## What came out after the fix

Validation is the same as before: `GroupKFold` by `qid`, five folds, standardization only on the train fold.
The direction of the metric is risk (1 = lie).

| score | OOF AUROC | 95% CI (cluster bootstrap by `qid`, 400 replicates) |
| --- | --- | --- |
| the built-in formula `1 − exp(meanLp)` | **0.799** | [0.719, 0.872] |
| `1 − meanφ` | 0.811 | — |
| logistic regression on 5 product features | 0.783 | [0.696, 0.867] |
| logistic regression on 26 features without length | 0.815 | [0.737, 0.883] |
| 5 features, orthogonalized by `n_tokens` | **0.541** | — |
| 26 features, orthogonalized by `n_tokens` | 0.717 | — |

The difference from the built-in formula is statistically indistinguishable from zero:

```
ΔAUROC(5 features − formula)  = −0.016, CI [−0.057, +0.020]
ΔAUROC(26 features − formula) = +0.016, CI [−0.036, +0.069]
```

This is the main result: **training gives nothing beyond what the product already computes**. The only thing
the previous weights added was calibration and a convenient working range of thresholds, not better ranking.

## Why AUROC 0.8 means nothing

Two independent checks show that the signal comes almost entirely from answer length and from the type of
question, not from model confidence.

**Length.** If the linear contribution of `n_tokens` is removed from all features inside the train fold, quality
drops to random (0.541). Within length quartiles the sign of the signal even flips:

| `n_tokens` quartile | range | false / correct | `1 − exp(meanLp)` | 5 features |
| --- | --- | --- | --- | --- |
| Q1 | 0–36 | 0 / 64 | — | — |
| Q2 | 36–59 | 6 / 62 | 0.968 | 0.927 |
| Q3 | 59–148 | 33 / 33 | 0.674 | 0.624 |
| Q4 | 148–∞ | 37 / 30 | **0.285** | 0.303 |

In the longest quarter the token confidence of fabrications is *higher* than that of correct answers — that is,
on long answers the feature works in the opposite direction.

**Question type.** 218 of 265 rows (82%) have a label fully determined by the question: for a question with a
false premise either all models fabricate or all refuse. Therefore the overall AUROC measures
mainly "did the model tell a long fake-work question from a short control fact". Within the
categories where both classes occur, there is no signal:

| category | n | false | `1 − exp(meanLp)` | 5 features | 26 without length |
| --- | --- | --- | --- | --- | --- |
| false-premise | 48 | 23 | 0.435 | 0.391 | 0.470 |
| fake-work | 48 | 37 | 0.396 | 0.356 | 0.329 |
| fake-person | 12 | 11 | 0.636 | 0.727 | 0.455 |
| myth | 19 | 5 | 0.157 | 0.114 | 0.471 |

On `fake-work` all three scores are **worse than random**: token confidence of fabricated opera titles is
higher than that of correct answers to control questions.

## Conclusion

1. `data/weights-detector.json` has been removed from the repository. The promise "we catch 75% of fabrications" is withdrawn.
2. The built-in formula `exp(meanLp)` stays as is: as a rough indicator of "the model was not confident"
   it works (0.799 on this set), but not as a lie detector.
3. The level thresholds cannot be changed on any basis: the distinction between 0.55 and 0.75 still rests on data
   where the label is determined by the question, not by the answer.

## What could change the verdict

- **Real spontaneous hallucinations.** All 76 fabrications were obtained on order ("answer as if
  the premise were true, do not refuse"). On free questions the models refuse more often, and there
  token confidence may behave differently.
- **Questions with a numeric answer.** In `numer` 0 false out of 59: the category where spontaneous errors are
  most likely has been left empty.
- **Pairwise comparison within a single question.** Right now 82% of labels are determined by the question; we need
  questions where the same model is sometimes right and sometimes wrong, otherwise "lie detector" and "question-type
  detector" are indistinguishable.

## How to reproduce

```bash
export HALLUC_DIR=/path/to/rows        # directory with rows_raw2.jsonl, rows_raw3.jsonl
python3 scripts/halluc/repair.py       # restoring the text from tokens and re-labelling
bun run scripts/halluc/score_all.ts    # features from logprobs
python3 scripts/halluc/dataset.py      # assembling the dataset
python3 scripts/halluc/eval.py         # the AUROC table, CI, categories, length quartiles
```

`repair.py` and `eval.py` are new; `dataset.py` takes paths via `RAW2/RAW3/SCORED2/SCORED3` and
`DATASET_OUT`, so a run on the fixed files does not overwrite the originals.
