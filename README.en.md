# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-127%20pass-brightgreen)](docs/VALIDATION.md)
[![CI](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml/badge.svg)](https://github.com/vladmurnik/truthprobe-opencode/actions/workflows/verify.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

**English** · [Русский](README.md)

**TruthProbe exists to show you where exactly the model hallucinates or lies.** It does not rule
"true or false" for you — it points at the **place in the answer** where the model was unsure:
it highlights specific sentences and numbers their confidence, so you check two or three doubtful
claims instead of re-reading the whole answer.

Shows **how confident the model is in its own answer**, from the log-probabilities of the first
tokens — no second pass, no self-check by the model, no second judge model.

A patch for the [opencode](https://github.com/sst/opencode) core: one place that collects tokens, one
schema field, one badge in the TUI and one chip in the desktop/Electron session UI.

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

`risky` and `unreliable` get a tinted card: amber left border and background for `risky`, red for
`unreliable`. A sentence counts as doubtful at 45% risk by default; move the thresholds with
`TRUTHPROBE_RISKY_THRESHOLD` and `TRUTHPROBE_SHAKY_THRESHOLD` (0..1, invalid values are ignored).

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
`patches/truthprobe-0001.patch`, run `bun install` and print the resulting version. Requirements:
`git` and [`bun`](https://bun.sh). Nothing outside the target directory is touched; the git identity,
if missing, is set locally in that directory only. Pass a directory name to choose where it lands
(`bash install.sh my-opencode` / `.\install.ps1 -Dir my-opencode`).

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

Weights can be per model: `--by-model` writes a bundle (`make weights` does that on
`data/rows-lie-vs-truth.jsonl`), and the runtime picks the set by `providerID/modelID`, falling back
to the default formula when the model has no weights of its own.

Set format and metrics — [`docs/CALIBRATION.md`](docs/CALIBRATION.md). Weights are validated on load:
a missing file, broken JSON or a non-numeric coefficient prints one warning and switches to the
built-in formula; scoring never breaks. Features the model sees: `meanLp` (ln of the geometric mean),
`minLp` (ln of the worst token), `meanPhi` (first-token confidence over top-K), `fracLow` (share of
tokens below 0.5 probability), `digitDensity` (share of digits in the text).

A scorer in another language is either `scripts/calibrate.py --fit` for the weights, or your own
implementation of the `Scorer` interface in `packages/core/src/truthprobe/scorer.ts`.

### Weights that were fitted against fabrications

`data/weights-detector.json` is a linear model over the same five features, fitted to tell a fabricated
answer from a correct one on 265 labelled answers (102 false, 4 models). Out-of-fold AUROC **0.881**;
at a risk threshold of 0.55 it catches 75.5% of the fabrications and flags 12.9% of the correct
answers, at 0.35 — 95.1% and 33.7%. It is a hint about what to re-read, not a verdict: an unfamiliar
model may behave differently (on one of the four models the fitted weights collapse to chance). How to
turn it on, what is inside and what it does not prove — [`docs/LEARNED-WEIGHTS.md`](docs/LEARNED-WEIGHTS.md).

### Manual patch

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout 007afb1
git am /path/to/patches/truthprobe-0001.patch
bun install
bun run --cwd packages/cli src/index.ts
```

Keys and providers are checked automatically: on the first chat-completions request the core sends a
single one-token probe with the text `ping`, and if the provider returns `logprobs` it turns them on
for that provider. No environment variables are needed.

### Prebuilt binaries

There are **no published builds**: no binary is hosted and no checksum is published. Build from the
tree that `install.sh` produced:

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
upstream auto-update. Two variables are enough:

```bash
cd packages/desktop
export OPENCODE_TARGET=windows-x64 OPENCODE_CHANNEL=dev \
       OPENCODE_DESKTOP_APP=TruthProbe OPENCODE_DESKTOP_APP_ID=ai.truthprobe.desktop
bun x electron-vite build
bun x electron-builder --win --x64 --publish never --dir --config electron-builder.config.ts
```

`--config` is required: without it electron-builder falls back to its defaults and names the executable
after the npm package. The result is `dist/win-unpacked` (a portable folder, ~830 MB) that can live
anywhere and run `TruthProbe.exe`. The window title, the AppUserModelID, the
`%APPDATA%\ai.truthprobe.desktop` directory and the installer name all come from those two variables;
unset, the build stays plain opencode.

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

Support is a provider property, not a model property: a fresh `ok` for any model of a provider turns
the badge on for that provider, so aliases and variants do not switch it off.

Manual switches remain and take precedence over the automation:

- `capabilities.logprobs: true` on a model in the config — the user decides, the probe does not argue;
- `OPENCODE_TRUTHPROBE=1` — ask every chat-completions model for `logprobs`;
- `OPENCODE_TRUTHPROBE_PROBE=off` — disable only the probe (no network calls at all).

Inspect the verdicts: `cat <data>/truthprobe/capabilities.json`.

## How it is computed

One formula, applied twice — to every sentence and to the whole answer. Entropy, the worst token and
the share of low probabilities stay **features** for fitted weights, but they are not part of the
default score: measurement showed that first-token entropy flips the result
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
fires at <i>r</i> ≥ 0.45; levels are `safe ≥0.90`, `likely ≥0.75`, `uncertain ≥0.55`,
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
full feature set, `docs/VALIDATION.md` §17). Hedging ("probably", "I think") was measured too — zero variance
on the current set, so its contribution is unknown.

Segmentation is by `. ! ? …` with decimals, abbreviations and CJK terminators taken into account;
code blocks are dropped entirely. States: `ok` — tokens matched the text; `partial` — offsets
drifted; `unavailable` — no tokens.

## Verification

| What | How | Result |
| --- | --- | --- |
| Scoring and segmentation | `bun test test/score.test.ts` | **45 pass / 0 fail**, 104 expect |
| Probe logic (TTL, response classification, cache) | `bun test test/capability.test.ts` | **32 pass / 0 fail**, 70 expect |
| Doubtful sentences in desktop | `bun test src/message/doubtful.test.ts` from `packages/session-ui` | **9 pass / 0 fail**, 23 expect |
| OpenAI protocol (gate, request body, `choices[i].logprobs` parsing) | `packages/ai/test/truthprobe.test.ts` | **8 pass / 0 fail**, 26 expect |
| Auto-enable without environment variables | mock + two consecutive runs | RUN1: probe → `{"status":"ok"}`; RUN2: **2 of 2** requests with `logprobs: true, top_logprobs: 20` |
| Regression around text events | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Full core run | `bun test` in `packages/core` (7 713 tests, 331 files) | 7 300 pass / 351 skip / 62 fail — none in truthprobe: `tool-search` downloads ripgrep from github.com, `provider-gitlab-oauth` calls gitlab.com, `cross-spawn`/MCP depend on spawn; the harness blocks outbound network |
| TruthProbe tests, current build | `bun test` of the six truthprobe files | **127 pass / 0 fail** |
| Patch on a clean tree | `git am` in a `007afb1` worktree | applies without conflicts, tests 45 + 8 green |
| Typecheck | schema / ai / core / client / tui | green (132 / 357+322 / 2 030 / 181 / 1 942 files) |
| Typecheck of the UI packages | session-ui / app / desktop | green (382 / 2 445 / 3 569 files, desktop 2 projects) |
| End-to-end run | mock provider with real `logprobs` | `logprobs: true, top_logprobs: 20` in the request, `truthprobe` in the database |
| Live TUI | pty probe | badge and the doubtful-sentence block rendered |
| Desktop UI | session-ui chip in the shared Electron component | green typecheck of desktop (3 567 files); `confidence NN%` chip and the doubtful-sentence list in the footer |
| Standalone desktop app | build with `OPENCODE_DESKTOP_APP`/`OPENCODE_DESKTOP_APP_ID` | `TruthProbe.exe`, window title `TruthProbe`, userData `ai.truthprobe.desktop`, CLI sidecar beside it, no `app-update.yml` |
| Windows binary | `.exe` against the mock | `status: "ok", score: 0.417, first: 0.708, flagged: 1` |

Reproduce without keys:

```bash
python3 scripts/mock-openai-logprobs.py 8899 &
OPENCODE_CONFIG=scripts/mock-opencode.json \
  bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "capital of France?"
python3 scripts/check-db.py                  # what landed in the database
python3 scripts/tui-probe.py && python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Full numbers and the decision log — [`docs/VALIDATION.md`](docs/VALIDATION.md), step-by-step
reproduction — [`docs/SMOKE-E2E.md`](docs/SMOKE-E2E.md).

### Reproduced on 19.11.2026 (build `0.0.0-dev-202611191814`)

| What | Result |
| --- | --- |
| Live answer, `freepi/particle` | `score 0.7595 · likely`, sentence `#0 0.603 · uncertain` |
| Live answer, `freepi/deepseek-v4.1-flash` | `score 0.6893`, first doubtful sentence `0.4849` |
| Scorer swap `TRUTHPROBE_SCORER=linear:weights.json` | score moved `0.7595 → 0.9992`, so the custom scorer is really used |
| Windows installer, `install.ps1 -Dir <empty> -DryRun` | clean clone, `git apply --check` passed, 17 commits applied |
| Desktop build | app 246 MB, bundled CLI 279 MB |
| CI on foreign machines | GitHub Actions [run `44593481931`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44593481931), [run `44678633546`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44678633546) , [run `44736706708`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44736706708) , [run `44761971781`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44761971781) and [run `44784920180`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44784920180), [run `44787911144`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44787911144) and [run `44918215420`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44918215420) | **all 7 jobs success** in each, on hosted `ubuntu-latest` and `windows-latest` runners |
| Per-model weights at runtime | two mock runs with different bundles, same answer | `0.9997 · safe` when weights exist for `mock/mock-1`, `0.0003 · unreliable` when they only exist for `other/model` — selection by `providerID/modelID` really works |
| `collect.py` against a live gateway | 2 prompts, `freepi/particle` | rows with `meanLp -0.063 / -0.125`, `minLp -0.409 / -0.945`, `fracLow 0.00 / 0.06` — features computed by the same formula as in the runtime |
| `collect.py` at scale | 24 models × 24 questions = 576 requests on `127.0.0.1:8790` | **120 rows with features** on 7 models (4 models answered 24/24), 108 `HTTP 403 premium credits`, 348 without logprobs, **0 negatives** — every answer was correct, so calibration needs weaker models |
| Question-bank audit | `python3 scripts/audit-bank.py data/qa-hard-bank.jsonl data/rows-hard.jsonl` | found **4** items where the reference answer, not the model, was wrong; after cleaning the set — `AUROC n/a (one class)`, 739 correct / **0 wrong** |
| Negative harvesting | 47 hard questions × 4 models × 4 samples at `T=0.8` and `T=1.0`, then three more banks (34 questions, classic LLM failures, list counting) | 1504 + 688 rows; **0** genuine negatives — the models either answer correctly or stay silent |
| Instructed lies: can the scorer see them | `scripts/measure-lies.py` on 626 rows (544 truthful / 82 lies) | previous formula gave AUROC **0.388** (worse than chance), ECE 0.368; fitted weights give 0.800 out-of-fold (grouped CV) |
| Built-in formula rewritten | same 626 rows + 739 correct rows as a control | `exp(meanLp)` instead of `0.4·geo + 0.3·worst + 0.3·φ`: AUROC **0.388 → 0.597**, ECE **0.368 → 0.098**, and on correct answers ECE **0.493 → 0.160** |

**Not tested, and we will not pretend otherwise:**

- **Clean machines — verified through CI only.** GitHub-hosted `ubuntu-latest` and `windows-latest`
  runners are clean VMs, and all 7 jobs passed there twice — on 19.11.2026
  ([run `44593481931`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44593481931)) and
  on 20.11.2026 with the per-model weights
  ([run `44678633546`](https://github.com/vladmurnik/truthprobe-opencode/actions/runs/44678633546)):
  installer dry-runs, patch application, typecheck, truthprobe tests, e2e through the mock provider,
  CLI build. There is still no Hyper-V/VirtualBox/VMware/Windows Sandbox on the dev machine, so a human
  watching a one-click install on a fresh OS has not happened.
- **Linux and macOS.** `install.sh` is now exercised in CI (`installer-dry-run` on `ubuntu-latest`);
  macOS is not — the matrix only has ubuntu and windows.
- **Cloud providers with keys.** OpenAI, Anthropic, Gemini — never measured; the support claim rests on
  the protocol shape, not on numbers.
- **Calibration.** `calibrate.py --demo --fit` reports `AUROC 1.000 / ECE 0.039` on synthetic data.
  That is a property of the synthetic set, not of the scorer. The first real measurement
  (`per-model 0.866`) was withdrawn: every one of its negatives turned out to be a defect of our own
  question bank (an ambiguous "Saturn or Neptune" item) or a `max_tokens` cut-off. After cleaning,
  the set holds 739 correct and 0 wrong rows, so the honest result is "not measured yet" — and
  `scripts/audit-bank.py` now catches that class of defect before any weights are trained.

## Anatomy of the patch

46 files, +7023/−40, nineteen commits on top of `007afb1`. The seam is thin and additive:

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
test/capability.test.ts   32 tests for statuses, TTL and the probe cache
test/opencode-tree/       tests that live in the opencode tree
patches/                  the ready-to-apply git-am patch and python patchers for spot edits
scripts/                  mock provider, probe, TUI pty probe, screen emulator, builds
docs/                     prior art, built-in model plan, validation, build
```

## Limitations

- Only providers with `logprobs` (the chat-completions family). Responses API, Anthropic messages,
  Gemini generate-content — not yet; the plan is in [`docs/PLAN-BUILTIN.md`](docs/PLAN-BUILTIN.md).
- The first request to a new provider still goes without `logprobs`: the verdict appears after the
  probe, that is from the second request on. The first answer gets no badge.
- The real `opencode.ai/inference` gateway has not been verified: no key. The probe handles it on its
  own — `scripts/probe-logprobs.py` is only there to look at the verdict by hand.
- The `0.90 / 0.75 / 0.55 / 0.35` level bounds were chosen by common sense, not from labelled data;
  they need re-checking on real long answers. Override with `TRUTHPROBE_RISKY_THRESHOLD` and
  `TRUTHPROBE_SHAKY_THRESHOLD`.
- A known weakness of the approach: confident lies. It is cured not by a threshold but by a second
  independent signal.

## License

MIT — see [LICENSE](LICENSE). `opencode` stays under its own license; this repository is only the
patch.

## Still open (honest list)

These review points are **not** fixed, and the docs do not pretend otherwise:

- **Calibration on spontaneous hallucinations.** AUROC and ECE are measured, but on a set of
  *commissioned* lies: 626 rows, 82 of them negatives obtained by asking the model to lie. There are no
  spontaneous model errors in it — 1440 requests across four gateway models produced zero negatives.
  There is no second independent set either, so no AUROC gate can go into CI until there is one. The
  protocol and the script live in [`docs/CALIBRATION.md`](docs/CALIBRATION.md) and `scripts/calibrate.py`.
- **Fixed 22.11.2026. Logprobs support is checked per model, not per provider.** The capability cache
  is keyed by `provider/model`: confirming `particle` no longer turns logprobs on for `deepseek-*`, and
  a gateway whose other models reject the field can no longer 400 the whole request. The cost is one
  probe per new model, cached after the first answer.
- **`temperature > 0`.** `top_logprobs` at non-zero temperature is a smoothed distribution, not the
  model's confidence. We neither block nor mark it `partial`.
- **`top_logprobs` is not configurable.** `TRUTHPROBE_TOP_K = 20` is a constant.
- **Two TTL implementations.** `core/src/truthprobe/capability.ts` and
  `ai/src/protocols/truthprobe-capability.ts` duplicate freshness logic without a drift test.
