# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-93%20pass-brightgreen)](docs/VALIDATION.md)
[![CI](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml/badge.svg)](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

**English** | [Русский](README.ru.md)

**TruthProbe exists to show you where exactly the model hallucinates or lies.** It does not rule
"true or false" for you — it shows the **place in the answer** where the model went unsure:
it highlights specific sentences and names their confidence, so you check two or three doubtful
claims instead of the whole answer.

Shows **how confident the model is in its own answer**, from the log-probabilities of the first
tokens — no second pass, no self-check by the model, no second judge model.

A patch for the [opencode](https://github.com/sst/opencode) core: one place that collects tokens, one
schema field, one badge in the TUI and one chip in the session UI of the desktop app (Electron).

```
   What is the capital of France and how many people live there?

   first-token confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 44% ▰▰░░░ · risky · 1 doubtful sentence
     ▌ #2 ▰░░░░ 16% · unreliable: It is home to about 2 million people.
     Build · Mock 1 · 59ms · 1333.3 tok/s
```

## Why

The idea is not ours: **"The First Token Knows: Single-Decode Confidence for Hallucination
Detection"** (M. Gabriel, P. Wang, [arXiv 2605.05166](https://arxiv.org/abs/2605.05166)) showed that
the normalised entropy of the **first** token's distribution works like self-consistency but costs
one greedy decode instead of 10+ samples and clustering. Nothing of this existed in the opencode
ecosystem: the `sst/opencode` tree has zero mentions of `logprob`, and plugin hooks give no access to
tokens — which is why this is a core patch and not a plugin.

A survey of papers and tools is in [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md).
What we improve next, and by which numbers we judge it, is in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What it shows

| Level | Where | What you see |
| --- | --- | --- |
| **L1** | the line before the answer | confidence in the **first token**: does the model know this off the top of its head |
| **L2** | the block after the answer | confidence over the whole answer, its level and the number of doubtful sentences |
| **L3** | the list under the answer (TUI and desktop) | every doubtful sentence: number, percentage, level, start of the text |

Confidence is not a verdict: confident lies exist (`docs/PRIOR-ART.md`, ECLIPSE 2512.03107). That is
why the UI says `confidence`, not `truth`.

### Confidence scale

The number next to the answer carries a level, not just a percentage:
`answer confidence 71% · uncertain`.

| level | score | how to read it |
| --- | --- | --- |
| `safe` | ≥ 90% | the model never hesitated |
| `likely` | 75–90% | confident answer |
| `uncertain` | 55–75% | visible hesitation |
| `risky` | 35–55% | shaky answer, worth double-checking |
| `unreliable` | < 35% | the model was mostly guessing |

`risky` and `unreliable` get a tinted card: amber left border and a faint background for `risky`,
red for `unreliable`. A sentence counts as doubtful at 45% risk by default; move that threshold with
`TRUTHPROBE_RISKY_THRESHOLD` (0..1, invalid values are ignored). `TRUTHPROBE_SHAKY_THRESHOLD`
was removed in 0.13.8: neither the variable nor the `shakyThreshold` field exists any more
(`docs/VALIDATION.md` §23, item 8).

**Important:** these percentages are the model's confidence in its own tokens, not the probability
that the answer is true. A deterministic gateway (logprob ≈ −0.001) yields `safe` on any text,
including fabricated text.

Which models emit logprobs and which will never show numbers —
[`docs/MODEL-SUPPORT.md`](docs/MODEL-SUPPORT.md).

## Install

Two commands, no clone of this repository needed:

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.sh | bash
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/vladmurnik/truthprobe-opencode/master/install.ps1 | iex
```

Both installers fetch `sst/opencode` pinned at `007afb1`, apply
`patches/truthprobe-0001.patch`, install the dependencies and print the build version. Requirements:
`git` and [`bun`](https://bun.sh); nothing outside the target directory is touched — the git identity,
if missing, is set locally in that directory. The directory can be named your own way:
`bash install.sh my-opencode` (`.\install.ps1 -Dir my-opencode`).

Installer flags:

| flag | what it does |
| --- | --- |
| `--dir DIR` | where to install (`-Dir` in PowerShell) |
| `--dry-run` | download and check that the patch applies; do not install dependencies |
| `--uninstall` | drop the patch commits and return the tree to the base commit |
| `--scorer FILE` | put your own scorer weights into `.truthprobe/weights.json` and print the line `TRUTHPROBE_SCORER=linear:$PWD/.truthprobe/weights.json` (the runtime does not read the file itself: weights are enabled only by the environment variable) |

### Swappable scorer

By default the score is the built-in `geometric` formula — `exp(meanLp)`, the geometric mean of the
content-token probabilities. The older heuristic `0.4·geo + 0.3·worst token + 0.3·first-token
confidence` scored AUROC 0.388 (worse than chance) on a 626-row set, so it was dropped from the
formula and survives only as a feature (`docs/VALIDATION.md` §14).

The formula can be replaced without rebuilding the patch:

```bash
# 1. fit a linear model on labelled sentences
python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json

# 2. turn it on
export TRUTHPROBE_SCORER=linear:/path/to/truthprobe-weights.json
```

Weights can be per model: fitting with `--by-model` writes a bundle (`make weights` does that on
`data/rows-lie-vs-truth.jsonl`), and the runtime picks the set by `providerID/modelID`, falling back
to the default formula when the model has no weights of its own.

Set format and metrics — [`docs/CALIBRATION.md`](docs/CALIBRATION.md). Weights are validated on load:
a missing file, broken JSON or a non-numeric coefficient prints one warning and switches to the
built-in formula; scoring never breaks. Features the model sees: `meanLp` (ln of the geometric mean),
`minLp` (ln of the worst token), `meanPhi` (first-token confidence over top-K), `fracLow` (share of
tokens below 0.5 probability), `digitDensity` (share of digits in the text).

A scorer in another language is either `scripts/calibrate.py --fit` for the weights, or your own
implementation of the `Scorer` interface in `packages/core/src/truthprobe/scorer.ts`.

### The fitted detector: a negative result

We collected 265 labelled answers (76 fabrications, 189 correct, 4 models, 68 questions) and tried to
fit a detector on the features the scorer already computes. The result is negative: the OOF AUROC of
the fitted logistic model is **0.783** (the five product features) and **0.815** (26 features without
length) against **0.799** for the built-in `1 − exp(meanLp)`; the confidence intervals on the
difference cover zero (`−0.057…+0.020` and `−0.036…+0.069`). Removing the linear contribution of
answer length drops the quality to chance — **0.541**. Within individual question categories AUROC is
0.33–0.47, i.e. at or below chance. The previously published `data/weights-detector.json` is
withdrawn: its 0.881 was measured on a corrupted set. All numbers and the post-mortem —
[`docs/LEARNED-WEIGHTS.md`](docs/LEARNED-WEIGHTS.md).

**Patch from the published release:**
[`truthprobe-0001.patch`](https://github.com/vladmurnik/truthprobe-opencode/releases/download/v0.13.18/truthprobe-0001.patch)
(514 039 B, sha256 `4436386b…6f34`).

## Manual patch

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout 007afb1
# identity for this command only: without it git am fails with "empty ident name"
git -c user.name=TruthProbe -c user.email=truthprobe@localhost am /path/to/patches/truthprobe-0001.patch
bun install
bun run --cwd packages/cli src/index.ts
```

Keys and providers are checked automatically: on the first chat-completions request the core sends a
single one-token probe with the text `ping`, and if the provider returns `logprobs` it turns them on
for that `provider/model` pair. No environment variables are needed.

### Prebuilt binaries

There are **no published builds**: no binary is hosted, so there is nothing to download. A checksum
exists only for the build the numbers in this repository were taken on: the full `sha256`
`396be271b40c96da602d208df35d27ec947b4716aa4b29de7a5afc9a15b1eb8d` is recorded in
[`docs/BUILD.md`](docs/BUILD.md). Build from the tree that `install.sh` produced:

```bash
cd opencode-truthprobe
bun run --cwd packages/cli script/build.ts        # dist/cli-<target>/bin/opencode
```

Windows cross-builds and target variants — [`docs/BUILD.md`](docs/BUILD.md).

### Desktop app

The same badge lives in the Electron app: the `confidence` chip in the answer footer is drawn by the
shared `@opencode/session-ui` component, so desktop and the web UI get it from one edit. Start it from
the same tree:

```bash
bun run dev:desktop
```

#### As a standalone app

The same tree builds a self-contained program with its own name, its own data directory and no
upstream auto-update. Two build-time variables are enough:

```bash
cd packages/desktop
export OPENCODE_TARGET=windows-x64 OPENCODE_CHANNEL=dev \
       OPENCODE_DESKTOP_APP=TruthProbe OPENCODE_DESKTOP_APP_ID=ai.truthprobe.desktop
bun x electron-vite build
bun x electron-builder --win --x64 --publish never --dir --config electron-builder.config.ts
```

`--config` is required: without it electron-builder falls back to its defaults and names the executable
after the npm package. The result is `dist/win-unpacked` (a portable folder, ≈877 MB: 246 MB app,
279 MB bundled CLI and the rest): it can live anywhere and run `TruthProbe.exe`. The window title, the
AppUserModelID, the `%APPDATA%\ai.truthprobe.desktop` directory and the installer name all come from
those two variables; unset, the build stays plain opencode.

**The build is unsigned.** `TruthProbe.exe` is packed without a certificate: the file properties
say `Signature: NotSigned`, and SmartScreen greets the first user with an "unknown publisher"
warning. The metadata is still the fork's own (`ProductName`, `CompanyName`, `LegalCopyright`
say `TruthProbe`, `FileVersion` is the product version). For a signed build see
`docs/DEVELOPMENT.md`, section "Signing".

### How it turns on

Automatically. The `opencode.truthprobe` plugin listens on `http.request` — the only place where the
model and the already-authorised URL are visible at the same time — and in parallel sends one probe:
`{"messages":[{"role":"user","content":"ping"}], "max_tokens":1, "logprobs":true}`. Conversation data
is never part of it. The model's answer does not wait for the probe: the hook only puts an event on a
queue and the network runs in a separate fiber.

The verdict is written to `<data>/truthprobe/capabilities.json` (Linux:
`~/.local/share/opencode/truthprobe/`, Windows: `%APPDATA%\opencode\truthprobe\`) and lives:
`ok`/`ignored`/`rejected`/`unsupported` — 7 days, `auth` — one hour (a key may have been added since),
network failures and 5xx are not cached at all.

| Status | Meaning | What the badge does |
| --- | --- | --- |
| `ok` | the response really carried `logprobs.content` | turns on, and stays on for later requests |
| `ignored` | 200 but the field is missing — the gateway silently dropped it | stays off, retried in 7 days |
| `rejected` | 400/422 mentioning `logprob` | stays off, retried in 7 days |
| `auth` | 401/403 | stays off, re-checked in an hour |
| `unsupported` | 404/405/501 or another 400 | stays off, retried in 7 days |

Manual switches remain and take precedence over the automation:

- `capabilities.logprobs: true` on a model in the config — the user decides, the probe does not argue;
- `OPENCODE_TRUTHPROBE=1` — ask every chat-completions model for `logprobs`;
- `OPENCODE_TRUTHPROBE_PROBE=off` — disable only the probe (no network calls at all).

Inspect the verdicts: `cat <data>/truthprobe/capabilities.json`.

## How it is computed

One formula, applied twice — to every sentence and to the whole answer. Entropy, the worst token and
the share of low probabilities stay **features** for fitted weights, but they are not part of the
default score: the measurement showed that first-token entropy flips the result
(`docs/VALIDATION.md` §14).

<p align="center">
<b><i>s</i><sub>i</sub> = exp(<i>ℓ̄</i><sub>i</sub>)</b>
&nbsp;&nbsp;&nbsp;where&nbsp;&nbsp;&nbsp;
<i>ℓ̄</i><sub>i</sub> = (ℓ<sub>i,1</sub> + ℓ<sub>i,2</sub> + … + ℓ<sub>i,n</sub>) / <i>n</i><sub>i</sub>
</p>

<p align="center">
<b><i>S</i> = 0.6 · <i>S</i><sub>all</sub> + 0.4 · (<i>s</i><sub>1</sub> + <i>s</i><sub>2</sub> + … + <i>s</i><sub>m</sub>) / <i>m</i></b>
&nbsp;&nbsp;&nbsp;&nbsp;
<i>r</i><sub>i</sub> = 1 − <i>s</i><sub>i</sub>
&nbsp;&nbsp;&nbsp;&nbsp;
<i>r</i> = 1 − <i>S</i>
</p>

| Symbol | Meaning |
| :--- | --- |
| <i>s</i><sub>i</sub> | confidence of sentence i, 0 to 1 |
| <i>r</i><sub>i</sub> | risk of sentence i, 1 − <i>s</i><sub>i</sub> |
| ℓ<sub>i,k</sub> | `logprob` of the k-th content token of sentence i |
| <i>ℓ̄</i><sub>i</sub> | mean of ℓ<sub>i,k</sub> over the content tokens of the sentence |
| <i>n</i><sub>i</sub> | number of content tokens in sentence i |
| <i>m</i> | number of sentences in the answer |
| <i>S</i><sub>all</sub> | the same formula over all content tokens of the answer |
| <i>S</i>, <i>r</i> | answer-level score and its risk; 0.6 / 0.4 is `globalWeight` |

In other words, **confidence is the average token probability**, not "the weakest token". The flag
fires at <i>r</i> > 0.45; levels are `safe ≥0.90`, `likely ≥0.75`, `uncertain ≥0.55`,
`risky ≥0.35`, below that `unreliable`.

Features that are always computed and feed the fitted weights when those are enabled:

| Feature | Formula | Meaning |
| :--- | :--- | --- |
| φ | 1 − <i>H</i><sub>K</sub> / ln <i>K</i> | confidence of the first token, 0…1 |
| <i>H</i><sub>K</sub> | −Σ<sub>i=1</sub><sup>K</sup> <i>q</i><sub>i</sub> · ln <i>q</i><sub>i</sub> | entropy of the top-K distribution |
| <i>q</i><sub>i</sub> | <i>e</i><sup>ℓᵢ</sup> / Σ<sub>j=1</sub><sup>K</sup> <i>e</i><sup>ℓⱼ</sup> | normalised probability of alternative i |
| <i>K</i> | 20 | how many alternatives we ask the provider for |
| <i>f</i><sub>low</sub> | #{<i>k</i> : ℓ<sub>k</sub> < ln 0.5} / <i>n</i> | share of tokens below 0.5 probability |
| ℓ<sub>min</sub> | min<sub>k</sub> ℓ<sub>k</sub> | the worst `logprob` |
| <i>d</i> | #{digits} / #{chars} | share of digits in the visible answer (`digitDensity`) |

Here <i>d</i> is the only textual feature with a measurable contribution (+0.014 AUROC on top of the
full feature set, `docs/VALIDATION.md` §17). Hedging ("probably", "I think") was measured too — zero
variance on the current set, so its contribution is not measured.

Segmentation is by `. ! ? …` with decimals, abbreviations and CJK terminators taken into account;
code blocks are dropped entirely. States: `ok` — tokens matched the text; `partial` — offsets
drifted; `unavailable` — no tokens.

## Verification

| What | How | Result |
| --- | --- | --- |
| Scoring and segmentation | `bun test test/score.test.ts` | **44 pass / 0 fail**, 99 expect |
| Probe logic (TTL, response classification, cache) | `bun test test/capability.test.ts` | **35 pass / 0 fail**, 73 expect |
| Doubtful sentences in desktop | `bun test src/message/doubtful.test.ts` from `packages/session-ui` | **9 pass / 0 fail**, 23 expect |
| OpenAI protocol (gate, request body, `choices[i].logprobs` parsing) | `test/opencode-tree/protocol.test.ts`: in this repository **8 skip** — the file only really runs inside a patched opencode tree (`packages/ai/test/`, CI sets `TRUTHPROBE_REQUIRE_PROTOCOL_TESTS=1`) | **8 pass / 0 fail** in the tree; all 8 skipped here |
| Auto-enable without environment variables | mock + two consecutive runs | RUN1: probe → `{"status":"ok"}`; RUN2: **2 of 2** requests with `logprobs: true, top_logprobs: 20` |
| Regression around text events | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Full core run | `bun test` in `packages/core` (7 713 tests, 331 files) | 7 300 pass / 351 skip / 62 fail — none in truthprobe: `tool-search` downloads ripgrep from github.com, `provider-gitlab-oauth` calls gitlab.com, `cross-spawn`/MCP depend on spawn; the harness blocks outbound network |
| TruthProbe tests, this repository | `bun test test` | **93 pass / 9 skip / 0 fail**, 211 expect, 5 files, 102 tests |
| TruthProbe tests, patched tree | `bun test truthprobe` in `packages/core/test` | **131 pass / 0 fail**, 6 files |
| Patch on a clean tree | `git am` in a `007afb1` worktree | applies without conflicts (identity configured locally), all truthprobe tests green |
| Typecheck | schema / ai / core / client / tui | green (132 / 357+322 / 2 036 / 181 / 1 947 files) |
| Typecheck of the UI packages | session-ui / app / desktop | green (384 / 2 447 / 3 571 files, desktop 2 projects) |
| End-to-end run | mock provider with real `logprobs` | `logprobs: true, top_logprobs: 20` in the request, `truthprobe` in the database |
| Live TUI | pty probe | badge and the doubtful-sentence block rendered |
| Desktop UI | `confidence` chip in the shared `@opencode/session-ui` component | green typecheck of desktop (3 571 files); `confidence NN%` chip and the doubtful-sentence list in the footer |
| Standalone desktop app | build with `OPENCODE_DESKTOP_APP`/`OPENCODE_DESKTOP_APP_ID` | `TruthProbe.exe`, window title `TruthProbe`, userData `ai.truthprobe.desktop`, CLI sidecar beside it, no `app-update.yml` |
| Windows binary | `.exe` against the mock | `status: "ok", score: 0.417, first 0.708, flagged: 1` |

Reproduce without keys:

The block below runs **inside the patched opencode tree** (`.worktree/opencode` after `make setup`, or
the tree `install.sh` produced), not in this repository: there is no `packages/` here, so
`bun run --cwd packages/cli` from the repo root finds no package.

```bash
python3 scripts/mock-openai-logprobs.py 8899 &
OPENCODE_CONFIG=scripts/mock-opencode.json \
  bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "capital of France?"
python3 scripts/check-db.py                  # what landed in the database
python3 scripts/tui-probe.py && python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Full numbers and the decision log — [`docs/VALIDATION.md`](docs/VALIDATION.md), step-by-step
reproduction — [`docs/SMOKE-E2E.md`](docs/SMOKE-E2E.md).

## What was actually verified (statistics as of 19.11.2026)

The snapshot was taken on build `0.0.0-dev-202611191814`, Windows 11, the local free-pi gateway.
Everything in the table is a measurement, not an expectation.

| What | How it was checked | Result |
| --- | --- | --- |
| TruthProbe tests | `bun test` of six files in `packages/core/test` | **131 pass, 0 fail** (patched tree; in this repository — **93 pass / 9 skip**) |
| Whole-monorepo tests | `bun test` in `packages/core` — 7713 tests, 331 files | **7300 pass, 351 skip, 62 fail** |
| Answer from `freepi/particle` | live request through the production binary | `score 0.7595 · likely`, sentence `#0 0.603 · uncertain` |
| Answer from `freepi/deepseek-v4.1-flash` | live request | `score 0.6893`, first flag `0.4849` |
| Swappable scorer | `TRUTHPROBE_SCORER=linear:weights.json` | score moved from `0.7595` to `0.9992` — the swap really works |
| Windows installer | `install.ps1 -Dir <empty> -DryRun` | clone, `git apply --check`, all 32 patch commits applied, no errors; CI repeats this on every push |
| Desktop build | electron-builder | app 246 MB, bundled CLI 279 MB |
| CI on foreign machines | GitHub Actions, runs [`44918215420`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44918215420), [`45161855972`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45161855972) (0.13.12), [`45163760974`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45163760974) (0.13.13), [`45165859105`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45165859105) (0.13.14), [`45169068249`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45169068249) (0.13.15), [`45207888021`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45207888021) (0.13.18), [`45256323762`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45256323762) (audit fixes) | **7 of 7 jobs success** in every run whose id still resolves; the earlier ids (`44593481931`–`44787911144`) predate the 21.11.2026 recreation of the repository and now answer 404 |
| Per-model weights at runtime | two mock runs with different bundles, same answer | `0.9997 · safe` when weights exist for `mock/mock-1`, `0.0003 · unreliable` when they only exist for `other/model` — selection by `providerID/modelID` really works |
| `collect.py` at scale | 7 models, 576 requests | 120 rows with logprobs; 108 requests refused with `HTTP 403 premium credits`; 348 answers came back without logprobs — the local gateway `127.0.0.1:8790` returns them only for the models it routes |
| `collect.py` against a live gateway | 2 prompts, `freepi/particle` | rows with `meanLp -0.063 / -0.125`, `minLp -0.409 / -0.945`, `fracLow 0.00 / 0.06` — features computed by the same formula as in the runtime |
| Question-bank audit | `python3 scripts/audit-bank.py data/qa-hard-bank.jsonl data/rows-hard.jsonl` | found **4** items where the reference answer, not the model, was wrong; after cleaning the set — `AUROC n/a (one class)`, 739 correct / **0 wrong** |
| Negative harvesting | 47 hard questions × 4 models × 4 samples at `T=0.8` and `T=1.0`, then three more banks (34 questions, classic LLM failures, list counting) | 1504 rows (47 × 4 × 4 × 2 temperatures) + 688 rows from the three extra banks; **0** genuine negatives — the models either answer correctly or stay silent |
| Instructed lies: can the scorer see them | `scripts/measure-lies.py` on 626 rows (544 truthful / 82 lies) | previous formula gave AUROC **0.388** (worse than chance), ECE 0.368; fitted weights give 0.800 out-of-fold (grouped CV) |
| Built-in formula rewritten | same 626 rows + 739 correct rows as a control | `exp(meanLp)` instead of `0.4·geo + 0.3·worst + 0.3·φ`: AUROC **0.388 → 0.597**, ECE **0.368 → 0.098**, and on correct answers ECE **0.493 → 0.160** |

**About the 62 failures in the monorepo:** none of them relates to truthprobe. The causes are visible
in the log and unrelated to the patch: `tool-search` pulls ripgrep from github.com,
`provider-gitlab-oauth` calls gitlab.com, `cross-spawn` and the MCP tests depend on spawn — in this
environment outbound network is blocked for tests
(`test attempted network request: GET https://github.com/...`).

What we did **not** check, and will not pretend otherwise:

- **Clean virtual machines — now verified in CI.** GitHub Actions brings up `ubuntu-latest` and
  `windows-latest` runners from scratch: runs
  [`44918215420`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44918215420) and
  [`45169068249`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/45169068249)
  (already with per-model weights) confirmed that the installers pass `--dry-run` on both OSes, the
  patch applies to a clean tree and behaves identically. This is not a manual install on a desktop,
  but it is a clean OS.
- **Linux and macOS.** `install.sh` is now exercised in CI on ubuntu-latest (dry-run, without
  installing into the system). The macOS runner does not take part in the installer matrix — only
  unit tests were checked there.
- **Cloud providers with keys.** OpenAI, Anthropic, Gemini were not checked — only the local free-pi
  gateway and the mock provider in e2e. The support claim rests on the protocol shape, not on
  measurements.
- **Calibration — not measured yet, and we found that out honestly.** `calibrate.py --demo --fit`
  reports `AUROC 1.000 / ECE 0.039` on synthetic data — a property of the synthetic set, not the
  quality of the scorer. The first real measurement (`data/rows-hard.jsonl`) gave `per-model 0.866`,
  but then it turned out that all 40 "negatives" were defects: 23 answers to an ambiguous question
  ("Saturn or Neptune" with `jupiter` as the reference) and 17 cut-offs by `max_tokens`. After
  cleaning, the set holds **739 correct and 0 wrong** rows, and `evaluate.py` prints
  `AUROC n/a (one class)`. So the numbers 0.538/0.683/0.866 are withdrawn, and instead
  `scripts/audit-bank.py` appeared, which catches that class of bank defect before training.
  Details — `docs/VALIDATION.md` §12.

## Anatomy of the patch

53 files, +3638/−55, 514 039 B, thirty-two commits on top of `007afb1`. The seam is thin and additive:

| Layer | File | What it does |
| --- | --- | --- |
| schema | `packages/schema/src/truthprobe.ts` | `Truthprobe.Info` — the only new type |
| schema | `session-message.ts`, `session-event.ts` | optional `truthprobe` on the text part and on `session.text.ended` |
| protocol | `packages/ai/src/protocols/openai-chat.ts` | asks for `logprobs`, parses `choices[i].logprobs` into `providerMetadata` |
| protocol | `packages/ai/src/protocols/truthprobe-capability.ts` | reads the verdict cache to enable collection without config |
| core | `plugin/truthprobe.ts` + `truthprobe/capability.ts` | probes the provider on `http.request`, caches verdicts |
| core | `model.ts` | `mergeCapabilities` no longer drops `logprobs` |
| core | `session/runner/publish-llm-event.ts` | accumulates tokens, computes the score, puts it on the durable event |
| core | `session/message-updater.ts` | moves the field onto the message part |
| client | `client/src/solid/data.ts` | **does not drop** the field on live store updates |
| desktop | `desktop/src/main/constants.ts`, `electron.vite.config.ts`, `electron-builder.config.ts` | build branding: name, AppUserModelID, userData, installer, no upstream updater |
| app | `app/src/brand.ts`, `app.tsx`, `session/route.tsx` | window and tab title from the same value |
| TUI | `tui/src/routes/session/message-parts.tsx` | badge and the doubtful-sentence block |
| desktop | `session-ui/src/message/message-content.tsx` | `confidence` chip in the answer footer, shared by the desktop app and the web UI |
| desktop | `session-ui/src/message/doubtful.ts` | doubtful-sentence list: numbering, percentage, 96-char truncation |
| scoring | `core/src/truthprobe/*` | pure functions, zero external dependencies |

Why it is shaped this way and what could break — [`PLAN.md`](PLAN.md) §11 "the life of the patch
across upgrades": 6 places that will need rebasing, 15–30 minutes per upstream release.

## Layout

```
src/truthprobe/           reference math (types, segmentation, scoring) and the probe logic
src/opencode-tree/        reference copies of the files that live in the opencode tree
test/score.test.ts        45 tests without network and without dependencies
test/capability.test.ts   35 tests for statuses, TTL and the probe cache
test/opencode-tree/       tests that live in the opencode tree
patches/                  the ready-to-apply git-am patch and python patchers for spot edits
scripts/                  mock provider, probe, TUI pty probe, screen emulator, builds
install.sh / install.ps1  two-command install: the patch on top of sst/opencode @ 007afb1
docs/                     prior art, built-in model plan, validation, build
```

## Limitations

- Only providers with `logprobs` (the chat-completions family). Responses API, Anthropic messages,
  Gemini generate-content — not yet; the plan is in [`docs/PLAN-BUILTIN.md`](docs/PLAN-BUILTIN.md).
- The first request to a new provider still goes without `logprobs`: the verdict appears after the
  probe, that is from the second request on. The first answer gets no badge.
- The real `opencode.ai/inference` gateway has not been verified: no key. The probe handles it on its
  own — `scripts/probe-logprobs.py` is only there to look at the verdict by hand.
- The `0.90 / 0.75 / 0.55 / 0.35` level bounds were chosen by common sense, not from labelled data:
  they need re-checking on real long answers. Override with `TRUTHPROBE_RISKY_THRESHOLD`.
  `TRUTHPROBE_SHAKY_THRESHOLD` was removed in 0.13.8 — it configured nothing
  (`docs/VALIDATION.md` §23, item 8).
- A known weakness of the approach: confident lies. It is cured not by a threshold but by a second
  independent signal.

## License

MIT — see [LICENSE](LICENSE). `opencode` stays under its own license; this repository is only the
patch.

## Still open (honest list)

The 0.5 work plan — [`docs/ROADMAP.md`](docs/ROADMAP.md): the level scale, prominent highlighting, a
supported-model matrix, one-script install, swappable ML scoring.

These review points were **not** closed (except the marked ones), and we do not pretend they were:

- **Calibration on spontaneous hallucinations.** AUROC and ECE are measured, but on a set of
  *commissioned* lies: 626 rows, 82 of them negatives obtained by asking the model to lie. There are no
  spontaneous model errors in it — 1504 requests across four gateway models (47 questions × 4 models ×
  4 samples × 2 temperatures) produced zero negatives. There is no second independent set either, so no
  AUROC gate can go into CI until there is one. The
  protocol and the script live in [`docs/CALIBRATION.md`](docs/CALIBRATION.md) and `scripts/calibrate.py`.
- **Fixed 22.11.2026. Logprobs support is checked per model, not per provider.** The capability cache
  is keyed by `provider/model`: confirming `particle` no longer turns logprobs on for `deepseek-*`, and
  a provider whose other models reject the field no longer gets a 400 for the whole request. The cost
  is one probe per new model, after which the verdict is cached.
- **`temperature > 0`.** `top_logprobs` at non-zero temperature is a smoothed distribution, not the
  model's confidence. We neither block it nor mark it `partial`; the numbers stay numbers, but they
  cannot be read as "confidence" at `temperature > 0`.
- **`top_logprobs` is not configurable.** `PROBE_TOP_K = 20` in `plugin-truthprobe.ts` is a constant;
  the traffic cannot be reduced; the same size in the scorer is `DEFAULT_SCORE_OPTIONS.topK`.
- **Two TTL implementations.** `core/src/truthprobe/capability.ts` and
  `ai/src/protocols/truthprobe-capability.ts` duplicate freshness logic without a drift test.
