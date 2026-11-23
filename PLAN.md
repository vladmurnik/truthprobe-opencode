> Русская версия: [docs/ru/PLAN.md](docs/ru/PLAN.md)

# TruthProbe for OpenCode — development plan

Status: **0.4.0** — eight commits on top of `007afb1`; the current numbers and measurements live in
`docs/VALIDATION.md`; this file is kept as a history of decisions and in places is outdated.
Open: T8 — probing the real opencode gateway (a key is needed) and calibrating `riskyThreshold` on live answers; conscious debt — an explicit `unavailable` status in the UI when the provider ignored the logprobs request.
Project: `C:\Users\adik\Desktop\progects\opencode-truthprobe`
Sandbox: WSL2 `Ubuntu 26.04`, 12 vCPU, 7.6 GB RAM, `~/src/opencode` (upstream `sst/opencode`, `dev`).

---

## 1. Goal

Show the OpenCode user **how confident the model is in what it says**, relying on the
probabilities of the first tokens, and not on the model's self-report.

Three levels of output, in ascending order of complexity:

| # | What the user sees | Signal source |
|---|---|---|
| L1 | A line **before** the answer: confidence about the first sentence | `φ_first` of the first content-bearing token |
| L2 | A block **at the end** of the answer: aggregated confidence over the whole answer + the number of doubtful sentences | geom. mean of token probabilities, mean over sentences |
| L3 | **Highlighting** of specific doubtful sentences right in the text | min/mean logprob + entropy at the start of a sentence |

### Non-goals

- Not to prove "truth" as a fact. The output is a **calibrated risk**, not a verdict.
- Not to replace or redefine verification with tools/tests: code is verified by a compiler, not by logprobs.
- Not to block model answers (v1 — indication only; blocking is possible later as a policy).
- Not to support providers without token logprobs (Anthropic, Gemini) — for them the honest status is `unavailable`.
- Not to implement semantic entropy / SelfCheckGPT sampling in v1 (expensive, a separate stage).

## 2. The key constraint that determines the whole architecture

OpenCode **does not request and does not store** logprobs. Verified against the `sst/opencode@dev` tree
(12 659 files): zero matches for `logprob`, including `@opencode-ai/plugin` d.ts.
So the task cannot be solved by a plugin (hook-only) → **we patch the core**, as chosen (option B).

What this entails:

1. `logprobs: true` + `top_logprobs: K` must be added to the request at the provider level.
2. We need to learn to parse `choices[].logprobs.content[]` from the stream (OpenAI-compatible format).
3. We need a storage location: message part metadata (survives a session reload, available to plugins).
4. We need to render: TUI text rendering + a status line.

## 3. Provider matrix (capability gate)

| Provider | logprobs | top_logprobs | Note |
|---|---|---|---|
| OpenAI (chat completions) | yes | yes | reference format |
| DeepSeek (OpenAI-compatible) | yes | yes | main test provider |
| Groq / vLLM / llama.cpp | yes | yes | convenient for offline tests |
| Anthropic, Gemini | **no** | — | the feature must degrade, not break the request |

Rule: the parameter is added only if `model.capabilities.logprobs === true` **and** the config is
enabled. Otherwise — we send nothing (otherwise the provider will return 400).

## 4. Architecture and data flow

```
user turn
  └─ session/prompt
      ├─ provider.request  ──[+ logprobs, top_logprobs: K]──> API
      │        stream chunks ──> ParseLogprobs ──> TokenBuffer (per messageID)
      │                                              │
      │                        SentenceSegmenter <────┘
      │                                │
      │                          Score (φ_first, per-sentence, whole-answer)
      │                                │
      ├─ part.text.metadata.truthprobe ─┤   (persisted, schema-extended)
      ├─ event "truthprobe.scored"  ────┤   (for plugins/scripts)
      └─ TUI render: badge before / block after / inline highlight
```

### 4.1 Data schema (part metadata)

```jsonc
{
  "truthprobe": {
    "version": 1,
    "status": "ok" | "unavailable" | "partial",
    "model": { "providerID": "deepseek", "modelID": "deepseek-chat", "topK": 20 },
    "answer": { "score": 0.87, "risk": 0.13, "sentences": 14, "flagged": 2 },
    "first":  { "score": 0.94, "entropy": 0.11, "token": "T", "text": "The statement is true." },
    "sentences": [
      { "i": 0, "start": 0, "end": 18, "score": 0.94, "risk": 0.06, "minLp": -0.02, "flag": false },
      { "i": 7, "start": 412, "end": 470, "score": 0.41, "risk": 0.59, "minLp": -1.83, "flag": true }
    ]
  }
}
```

We do not store tokens in full (size): we store per-sentence aggregates + the first token.
Raw tokens — only with `truthprobe.debug = true`.

### 4.2 Metrics (exact formulas)

Let a token `t` have `lp_t = log p(t)` and a top-K distribution `{q_1..q_K}`.

- **Normalized entropy**: `H = -Σ q_i log q_i / log K`, `H ∈ [0,1]` (if top-K did not arrive — `H = 1 - exp(lp_t)`).
- **Confidence of the first token**: `φ_first = 1 − H_1` over the first content-bearing token
  (we skip markdown/punctuation/spaces, code and quotes — per the ignore list).
- **Sentence** `s` of `n_s` content-bearing tokens:
  - `g_s = exp( (1/n_s) Σ lp_t )` — geometric mean of the probabilities;
  - `φ_s = 1 − H_{first(s)}`;
  - `score_s = 0.5·g_s + 0.5·φ_s`, `risk_s = 1 − score_s`.
- **Whole answer**: `score = 0.6·exp(mean lp over all tokens) + 0.4·mean(score_s)`.
- **Flag**: `flag_s = risk_s ≥ threshold_risky` (default `0.45`, calibrated in T8).
- **Weights**: content-bearing tokens = not spaces, not punctuation at the start of a sentence,
  not inside ``` code fence```, not URLs.

All formulas are pure functions in a separate module, without I/O, so that they can be covered by unit tests
on recorded fixtures.

## 5. UI contract

Invariant: **we insert nothing into the answer text** (otherwise we break copy-paste and parsing).
The lines live in a separate rendering layer.

- **L1 (before/at the start of the answer)** — a muted line above the first text block:
  `⚑ confidence 0.94 · first sentence: «The statement is true.»`
  `status: unavailable` → `⚑ confidence unavailable (the provider does not return logprobs)`.
- **L2 (after the answer)** — a block:
  ```
  ⚑ TruthProbe   answer 0.87 · risk 0.13 · doubtful sentences: 2
     ├ #8  0.41  «...»
     └ #12 0.38  «...»
  ```
- **L3 (inline)** — doubtful sentences get the prefix `▍` and a muted-red style
  (ANSI truecolor, fallback to `red`/dim). No emoji inside the text, only style.

Switches: `truthprobe.mode: "off" | "summary" | "full"` (default `summary` = L1+L2).

## 6. Tasks

> The priority was changed by the user's decision (19.11.2026): first the feature must work on
> **opencode's built-in models** without own keys; extensibility for third-party APIs is the second
> step. The detailed plan of that stage: **`docs/PLAN-BUILTIN.md`** (stages E1–E7).
> Tasks T1–T9 below remain valid as "how exactly to patch the core", but their order and acceptance
> are subordinated to the E-stages: T1/T2/T3/T4 = E2/E3, T5/T6 = E4, T7 = E5, T8 = calibration, T9 = packaging.

| ID | Task | DoD (verifiable) |
|---|---|---|
| **T0** | VM: WSL2 Ubuntu, `opencode` CLI, clone of `sst/opencode`, `bun install` | `opencode --version` prints the version; `git log -1` in `~/src/opencode`; `bun run --cwd packages/opencode test` does not fail on the original code |
| **T1** | Code reconnaissance: a map of extension points | `docs/CODE-MAP.md` with exact paths: where provider options are built, where the stream is parsed, where the zod schema of a part is, where the TUI text rendering is |
| **T2** | Capability + schema | the `logprobs` field in the model capability description; `part.text.metadata.truthprobe` is validated by zod; old sessions are read without errors |
| **T3** | Request plumbing | with `truthprobe.enabled` + model support, `logprobs: true`, `top_logprobs: K` go into the request body; for Anthropic/Gemini the body does not change (request-body snapshot test) |
| **T4** | Stream parsing | a `TokenBuffer` is assembled from SSE chunks; a missing field does not crash the stream; covered by OpenAI/DeepSeek fixtures |
| **T5** | Scoring | `truthprobe/score.ts` + unit tests: φ_first, per-sentence, whole-answer; a golden test on a recorded session |
| **T6** | Persist + event | metadata is written into the part; the `truthprobe.scored` event is visible to a plugin; after a session reload the data is in place |
| **T7** | UI | L1 line, L2 block, L3 highlighting; a manual run in a WSL terminal, a screenshot in `docs/` |
| **T8** | Calibration | a dataset of 100 facts (PopQA/TriviaQA-like + 30 "confident lies"), thresholds, a report with a **measured** AUROC in `docs/CALIBRATION.md` |
| **T9** | Build and packaging | `bun run build` passes; launch instructions in the VM; the diff is fit for a PR upstream (isolated behind a flag, off by default) |

Order: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9. T2/T5 can be parallelized after T1.
T7 (highlighting) is deliberately last: L1+L2 deliver value earlier.

## 7. File changes (refined in T1)

| Layer | Expected files | Nature of the change |
|---|---|---|
| Provider request | `packages/opencode/src/provider/*`, `packages/ai/src/*` | add request options behind the gate |
| Stream parse | the same place where message parts are assembled | assemble `logprobs.content[]` |
| Schema | `packages/opencode/src/session/message-v2.ts` (zod) | optional `metadata.truthprobe` |
| Scoring | **new** `packages/opencode/src/truthprobe/{score,sentences,types}.ts` | pure functions |
| Events | session event registry | `truthprobe.scored` |
| TUI | `packages/tui/src/*` text/status rendering | L1/L2/L3 |
| Config | config schema | the `truthprobe` block |
| Tests | `packages/opencode/test/truthprobe/*` | fixtures + unit |

Invariant: **the feature is off by default** (`mode: "off"`), all the code is behind a flag, so that
the patch is a merge, not a fork.

## 8. Verification

1. `bun test` is green, including the new scoring tests and the request-body snapshots.
2. A live run in the VM on DeepSeek (`top_logprobs: 20`) — L1/L2/L3 rendered.
3. A run on Anthropic — status `unavailable`, the answer is not broken.
4. Session reload — metadata is in place.
5. T8: AUROC measured on our own dataset, a number in the report, not "approximately".

## 9. Risks and what we do about them

| Risk | Impact | Mitigation |
|---|---|---|
| RLHF models are poorly calibrated: logprobs do not equal truth (arXiv 2305.14975) | false calm on a "confident lie" | we show risk, not "truth"; in L2 explicitly "doubtful: N"; T8 measures exactly the false-confident cases |
| A single signal collapses to "all ok" on long answers (arXiv 2606.24420) | uselessness in coding chats | fusion of 3 signals (per-token lp, φ at the start of a sentence, spread across sentences); later — disagreement between two passes |
| `temperature > 0` → top_logprobs are noisy | jumpy scores | we fix `temperature` for the scoring request or mark `status: "partial"` |
| No top-K in the response (some providers) | fallback | `H = 1 − exp(lp)`, status `partial` |
| Cost: the extra field increases the response | traffic | `top_logprobs` ≤ 20, we store aggregates, not tokens |
| TUI highlighting breaks line wrapping/copy-paste | UX | style without inserting characters into the buffer; `▍` only in the display |

## 10. Rollback

The feature is behind a flag → turning it off = `truthprobe.mode = "off"`, no code rollback.
Full rollback — `git revert` of a single PR; the metadata schema is additive and optional, migrations are not needed.

## 11. Strategy for the patch's life across upstream updates

Short answer: **yes, when forking the patch will have to be updated**, but the amount of work is manageable — if
you keep it additive, behind a flag and isolated in a separate module. The full set of approaches:

| Approach | Survives updates | Cost | Verdict |
|---|---|---|---|
| A. Oracle plugin (own request with `max_tokens:1`) | **without changes** — public plugin API | does not see the logprobs of the real answer, only a "re-ask" | keep as a fallback |
| B. Fork + core patch | no, a rebase is needed | 7 files, 1 of them "hot" | **current choice** |
| C. Upstream PR to `sst/opencode` | after the merge — 0 work | review, timelines, no guarantee it will be accepted | the goal after stabilization |
| D. Local proxy sidecar (MITM between opencode and the API) | almost no changes | fragile w.r.t. request formats, some data is lost | reserve |

How we minimize the pain from B:

1. **Everything is additive.** Not a single changed default behavior: new fields are `optional`,
   the feature is off (`truthprobe.mode = "off"`). Such edits almost never conflict.
2. **Code isolation.** Scoring is entirely in the new directory `packages/core/src/truthprobe/` —
   conflicts there are impossible by definition, the module survives a rebase as a whole.
3. **Thin seams.** We touch exactly 6 places pointwise (1–5 lines each): `bodyFields` + `fromRequest`
   in `openai-chat.ts`, an optional field in `AssistantText`, an optional field in `Text.Ended`,
   one `case` in `publish-llm-event.ts`, one handler in `message-updater.ts`, one block in
   `message-parts.tsx`. The "hottest" file is `openai-chat.ts` (upstream edits most often land there).
4. **The patch as a series of commits**, not one giant diff: `01-schema`, `02-protocol-request`,
   `03-protocol-parse`, `04-core-score`, `05-tui`. On a conflict exactly one layer falls off.
5. **CI rebase watchdog**: once a day `git fetch upstream && git rebase upstream/dev` in the
   `feat/truthprobe` branch; if it fails — a notification arrives. That way you learn about breakage on the day
   the release comes out, and not a month later.
6. **Version pinned**: until the patch is merged upstream, we work on a fixed commit
   (`007afb1`), not on `latest` — an update is a conscious action, not a surprise.
7. **Migration path to C**: if the PR was accepted — we delete our commits, and only the display plugin
   remains; if not — the patch lives as a series of 5 file-commits and is updated in
   ~15–30 minutes of conflict review per release.

What this means in practice: on every opencode update you run
`scripts/apply-patch.sh` (rebase + build + tests), and if it is green — nothing needs to be done.

## 12. Open questions (answered by facts in T1, not by guesses)

1. The exact place where the provider request body is built in the current architecture (v2 packages/ai?).
2. Whether there is already a capability flag for streaming options to hook onto.
3. Whether the TUI renderer in the current version supports custom ANSI styles inside a markdown block.
4. How a plugin gets access to part metadata (an existing hook or a new one).
