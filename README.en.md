# TruthProbe for opencode

[![unit tests](https://img.shields.io/badge/unit%20tests-91%20pass-brightgreen)](docs/VALIDATION.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![opencode base](https://img.shields.io/badge/opencode-007afb1-informational)](patches/truthprobe-0001.patch)

**English** · [Русский](README.md)

Shows **how confident the model is in its own answer**, from the log-probabilities of the first
tokens — no second pass, no self-check by the model, no second judge model.

A patch for the [opencode](https://github.com/sst/opencode) core: one place that collects tokens, one
schema field, one badge in the TUI and one chip in the desktop/Electron session UI.

```
   What is the capital of France and how many people live there?

   first-sentence confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 40% · 1 doubtful sentence
     ! #2 8%: It is home to about 2 million people.
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

## What it shows

| Level | Where | What you see |
| --- | --- | --- |
| **L1** | the line before the answer | confidence in the first sentence: does the model know this off the top of its head |
| **L2** | the block after the answer | confidence over the whole answer plus the number of doubtful sentences |
| **L3** | the list under the answer (TUI and desktop) | every doubtful sentence: number, percentage, start of the text |

Confidence is not a verdict: confident lies exist (`docs/PRIOR-ART.md`, ECLIPSE 2512.03107). That is
why the UI says `confidence`, not `truth`.

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

```
φ_first        = 1 − H_norm(top-K of the first tokens)   K = 20
H_norm         = −Σ q ln q / ln K,   q = softmax(logprob)
score_sentence = 0.4 · geo(exp(lp)) + 0.3 · exp(minLp) + 0.3 · φ_first
risk           = 1 − score            flagged at risk ≥ 0.45
score_answer   = 0.6 · globalGeo + 0.4 · mean(score_sentence)
```

Three signals per sentence: average confidence (geometric mean), the worst token (it is the one that
gives away an invented number or name) and the first-token entropy. Segmentation is by `. ! ? …`
with decimals, abbreviations and CJK terminators taken into account; code blocks are dropped
entirely.

States: `ok` — tokens matched the text; `partial` — offsets drifted; `unavailable` — no tokens.

## Verification

| What | How | Result |
| --- | --- | --- |
| Scoring and segmentation | `bun test test/score.test.ts` | **45 pass / 0 fail**, 104 expect |
| Probe logic (TTL, response classification, cache) | `bun test test/capability.test.ts` | **32 pass / 0 fail**, 70 expect |
| Doubtful sentences in desktop | `bun test src/message/doubtful.test.ts` from `packages/session-ui` | **6 pass / 0 fail**, 14 expect |
| OpenAI protocol (gate, request body, `choices[i].logprobs` parsing) | `packages/ai/test/truthprobe.test.ts` | **8 pass / 0 fail**, 23 expect |
| Auto-enable without environment variables | mock + two consecutive runs | RUN1: probe → `{"status":"ok"}`; RUN2: **2 of 2** requests with `logprobs: true, top_logprobs: 20` |
| Regression around text events | `test/session*.test.ts test/projector*.test.ts test/message*.test.ts` | **811 pass / 0 fail** |
| Full core run | `bun run script/test.ts` | 7 272 pass / 39 fail — the same 39 fail on a clean base (network: GitLab OAuth, ripgrep) |
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

## Anatomy of the patch

38 files, +2278/−40, eight commits on top of `007afb1`. The seam is thin and additive:

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
- The `0.45` threshold was calibrated on the mock; it needs checking on real long answers.
- A known weakness of the approach: confident lies. It is cured not by a threshold but by a second
  independent signal.

## License

MIT — see [LICENSE](LICENSE). `opencode` stays under its own license; this repository is only the
patch.
