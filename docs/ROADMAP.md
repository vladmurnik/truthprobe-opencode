> Русская версия: [docs/ru/ROADMAP.md](ru/ROADMAP.md)

# Development plan

The document records what has already been done, what we do next and by which number we will understand that things have got better.
The rule is the same as in `CONTRIBUTING.md`: **any change is verified by a measurement**, not by a feeling.

Status as of 20.11.2026.

## What is already done

| What | Evidence |
| --- | --- |
| Scoring an answer by logprobs (first token + the whole answer) | `packages/core/src/truthprobe/*`, 129 tests, `docs/VALIDATION.md` |
| Calibration weights per model (`WeightsBundle`, `bundleScorer`, `scoreAnswer(..., model)`) | mock run: `0.99966 · safe` with weights for `mock/mock-1`, `0.000335 · unreliable` with weights only for `other/model` |
| A readable verdict in the UI | `packages/session-ui/src/message/confidence.tsx`, the markers `confidence-meter`/`doubtful-list` in the built `app.asar` |
| Collection of calibration rows | `scripts/collect.py` (the features are computed exactly as in the runtime, the reasoning prefix is cut out) |
| CI on other people's machines | 7/7 jobs on ubuntu and windows: runs `45256323762` (patch from `007afb1`), `45257273878` and `45258540185` (docs); the ids quoted in earlier versions (`44593481931`–`44787911144`) predate the 21.11.2026 recreation of the repository and answer 404 |
| DX: one command for setup/preview/patch/desktop | `Makefile`, `scripts/dev-setup.sh`, `scripts/preview.sh`, `CONTRIBUTING.md` |
| Quality evaluation on a single file | `scripts/evaluate.py` + `make eval`: AUROC/ECE/Brier and the share of correct answers by level for `geometric`/`global`/`per-model` |
| The built-in formula = `exp(meanLp)` | 626 rows (544 truths / 82 ordered lies): AUROC **0.388 → 0.597**, ECE **0.368 → 0.098**; on 739 correct rows ECE 0.493 → 0.160 (§14 VALIDATION) |
| Level thresholds verified by measurement, not by eye | `safe ≥0.90` gives 35.6% of truths and 15.9% of lies; lowering to 0.85 would have added more lies than truths — left as is |
| Protection against defective labelling | `scripts/audit-bank.py` finds items where the models agreed but the reference did not (it found 4 such); `collect.py` does not set `label=0` for a truncated answer |
| First data for calibration | `data/rows-hard.jsonl` / `rows-hard-t1.jsonl` — 752 rows each, 739/741 correct, **0 incorrect** after cleaning; `data/rows-lie-vs-truth.jsonl` — 544 truths + 82 ordered lies |

## What is still missing — and why it matters

**There are no spontaneous negatives.** The 1504 collected rows after the audit gave **zero** real
errors: the 40 former "negatives" turned out to be defects in our own data — 23 answers to an ambiguous question
("Saturn or Neptune" with the reference `jupiter`) and 17 truncations by `max_tokens`. Therefore `per-model`
AUROC `0.866` is withdrawn: there was nothing to compute it on. The negatives that exist (82 rows) were obtained **on order** —
the model was asked to lie (`scripts/make-liar-bank.py`); this is a different class of errors: obedient
execution of an instruction, not confident fabrication.

**AUROC in CI.** The first number exists: `0.597` for the built-in formula on 626 rows. But that is 82 negatives
of one type (ordered lies) and 17 questions, so for now we do not enable the gate: any change of thresholds would give
a jump on one prompt, not an improvement of the scorer. We will enable the gate when a second independent
set of negatives appears.

**Sentence-level labelling.** The rows are labelled at the answer level, while the runtime highlights
sentences. As long as there is no set where within one answer some sentences are correct and some are not,
one cannot claim "the highlighting lands on the false statement".

## Phase 0. Measurement

- [x] `scripts/evaluate.py`: AUROC (with averaging over ties), ECE, Brier, the share of correct answers within
      each level; comparison of `geometric` / `global` / `per-model` (done 20.11.2026).
- [x] `make eval` on the fixture lying in the repository (`data/eval-fixture.jsonl`).
- [x] Reconciliation of the tool with the runtime: `evaluate.py` computes the same formula as `geometricScorer`
      (`exp(meanLp)`). A discrepancy was found — the tool kept computing the old formula and understated
      AUROC down to 0.388; fixed 20.11.2026.
- [x] Level thresholds verified by the distribution of scores on 1 283 truthful and 82 false answers:
      no need to change. `safe ≥0.90` is the top step, not "a 90% chance of being right":
      ECE 0.098 was measured on ordered lies, and score remains a signal of token confidence
      (`docs/CALIBRATION.md`).
- [ ] The CI job `eval` that fails when AUROC drops below a fixed threshold —
      **postponed**: the set of negatives is narrow (one question), the threshold will give noise, not protection.

The criterion is met: on a real file the table is printed; on synthetics of two classes
AUROC = 1.0 with ideal separation; on a single-class file — `AUROC n/a`, without a crash.

## Phase 1. Negatives

Four approaches, all machine-verifiable:

1. **Multi-sampling with temperature** (`--temperature 0.8 --samples 4`): the variety of answers
   gives natural errors, the label is set automatically by the bank of references.
2. **Tricky but verifiable questions**: units of measure, exact dates and editions, river lengths,
   atomic numbers, multi-step tasks.
3. **Truncated context / short `max_tokens`**: the model confidently finishes the wrong thing.
4. **Weak models**: `gpt-oss-20b`, `ling-3.1-flash`, `qwen3.7-flash` err more often.

Criterion: ≥ 200 rows, of which ≥ 30% `label=0`, and `calibrate.py --fit --by-model` actually trains
weights with out-of-fold AUROC/ECE.

**Result as of 20.11.2026: the criterion is not met.** All four approaches were checked plus one more
(counting by list): 2192 rows on four banks — 1504 on a bank of 47 questions (× 4 models ×
4 samples × 2 temperatures) and 688 on three additional ones — real negatives: **zero**. The available models
of the gateway either answer correctly or return empty content. Weak models (`gpt-oss-20b` and the like)
return `HTTP 403 premium credits` through the router, and those that do answer have degenerate logprobs.

The fifth approach that worked: **ordered lies** (`scripts/make-liar-bank.py`) — the model is asked
to answer incorrectly, the "lie" label is known from the task statement. This gives 82 negatives and the first
measurement on the "lie" class. The built-in formula after the rewrite (§14 VALIDATION) gives AUROC
**0.597**, ECE **0.098**; learned weights on the same features — **0.786**, with `digitDensity` — **0.800** (`scripts/measure-lies.py`).
Retraining the default weights on ordered lies is not allowed — that is not the right class of errors.

**Partially done (20.11.2026).** 1504 rows across 47 questions and 4 models at `T=0.8` and `T=1.0`
gave **40 "negatives", and all of them turned out to be defects**: 23 answers to an ambiguous question ("Saturn or
Neptune" with the reference `jupiter` — the models answered the question asked correctly) and 17 truncations by
`max_tokens`. After auditing the bank and re-collecting with `max_tokens 220` the set has **739 correct and 0 incorrect**.
The criterion "≥ 30% `label=0`" is not met: there are no incorrect ones at all.

The main conclusion therefore is not about models but about data: **before explaining a metric by the behaviour of
the model, one must check that the reference and the question are meaningful at all**. For this
`scripts/audit-bank.py` was added (cross-model agreement against the reference + the "X or Y" check), and
`collect.py` no longer sets `label=0` for a truncated answer. The next attempt to obtain negatives
must go through weak models and questions with an unambiguous reference.

What we do **not** do: we do not ask about invented entities — on this gateway such prompts give
an empty answer, that is, zero signal (verified).

## Phase 2. Signal quality

Right now the scorer looks only at logprobs and ignores the text.

**The first text feature has been introduced: `digitDensity`** (the share of digits in the visible answer) — **+0.014**
AUROC on top of the full feature set (0.786 → 0.800 out-of-fold with grouped CV,
`docs/VALIDATION.md` §17). It is computed identically in the runtime and in all python tools;
`scripts/enrich-digits.py` backfills it into old sets.

- Hedging in the text ("probably", "I think", "approximately") — measured, but on the current set
  the spread is zero: the feature remained unverified, rather than "rejected".
- Density of verifiable entities: numbers are already covered by `digitDensity`; dates and units are ahead.
- Entropy not only of the first token: the mean over content-bearing tokens and the "most uncertain" one.
- Self-consistency as an optional "deep mode" (k samples at `T>0`) — expensive, only on request.
- Explaining the score through `w_i · x_i` — free for the linear model.

Hard requirement: a new feature must be computed **identically** in `collect.py` and in the runtime, otherwise
the weights are applied to other numbers (we have already been burned by this with `fracLow` and `phi`).

The baseline to beat: AUROC **0.597** / ECE **0.098** on `data/rows-lie-vs-truth.jsonl`
(626 rows) for the `exp(meanLp)` formula without text; with fitted OOF features — **0.800**. Everything we
add is measured on the same file and on `data/rows-hard.jsonl` (739 correct rows) — the second is needed
so that an AUROC improvement is not bought at the price of false alarms.

## Phase 3. Interface

- TUI: the scale and the level label are already drawn (`answer confidence 44% ▰▰░░░ · risky`); in the plan —
  expanding "why" (top-3 feature contributions) by key.
- Desktop: expanding "why" — top-3 feature contributions, alternatives for the worst token.
- `unavailable` should be explained by an action ("the provider did not return logprobs — enable `OPENCODE_TRUTHPROBE=1`"),
  not by the phrase "no signal".
- Thresholds (`safe ≥0.90`, flag `risk >0.45`) should be moved into the config, so as to tune them per model.

## Phase 4. Reliability

- [x] Unicode/emoji/CJK: verified — alignment by code units does not break on Cyrillic,
  CJK, emoji, combining marks and Arabic; the behaviour is pinned by `truthprobe-unicode.test.ts`
  (`docs/VALIDATION.md` §16).
- Multi-turn: make sure the tokens of previous messages are not mixed in.
- Cost: measurement of the overhead on a 4 000-token answer (scoring runs on every delta event).
- A bundle with hundreds of models: lazy compilation of scorers instead of creating all of them at once.

## Phase 5. Distribution

- `truthprobe-weights.json` in the GitHub Release together with AUROC/ECE in the description.
- `install.sh --weights <url>`.
- `make data` / `make weights` — collection and training with one command.
- Scheduled-CI: a weekly evaluation run that fails on degradation.

## What we consider a regression

- Any truthprobe test turns red (currently 131 pass in the patched tree, 93 pass / 9 skip — in this repository).
- `scripts/evaluate.py` stops computing the same formula as the runtime (this has already happened: 0.388 versus 0.597).
- `git am` of the patch stops producing a byte-for-byte identical tree to the dev branch.
- An answer without logprobs starts showing a number instead of `unavailable`.
