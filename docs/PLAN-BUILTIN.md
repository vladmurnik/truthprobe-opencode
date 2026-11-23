> Русская версия: [docs/ru/PLAN-BUILTIN.md](ru/PLAN-BUILTIN.md)

# Plan: TruthProbe on OpenCode's built-in models (stage E)

The user's decision: first the feature must work on **opencode's built-in models** (without
own keys), and people will write third-party APIs themselves through the extensible layer.

Source of facts: `packages/core/src/models-dev/snapshot.txt` (provider `opencode`, 150 models)
and the code of `packages/ai/src/protocols/*` in the `sst/opencode@007afb1` clone.

---

## 1. What we have as input (measured, not assumptions)

Provider `opencode` (Zen/Console), 150 models, six API families:

| Family | Models | Base URL | logprobs technically possible |
|---|---:|---|---|
| `chat-completions` (OpenAI-compatible) | **69** | `opencode.ai/inference/openai/v1` | **yes** — the only suitable one |
| `responses` (OpenAI Responses) | 37 | `opencode.ai/inference/openai/v1` | no (the Responses API does not return token logprobs) |
| `messages` (Anthropic) | 25 | `opencode.ai/inference/anthropic/v1` | no |
| `generate-content` (Google) | 12 | `opencode.ai/inference/google/v1beta` | no |
| `systemone` (decisions) | 4 | `opencode.ai/inference/systemone/v1` | no |
| `images` | 4 | — | not applicable |

**The main technical conclusion:** `packages/ai/src/protocols/openai-compatible-chat.ts` is a thin
wrapper that *"reuses `OpenAIChat.protocol` end-to-end and overrides only the route id"*.
So **one patch in `openai-chat.ts` automatically covers all 69 chat-completions models
of the built-in provider** — including all `-free` ones. Separate code per model is not needed.

Free models on the suitable protocol (candidates for the "out of the box" demo):
`longcat-2.5-free`, `glm-5-free`, `glm-4.7-free`, `deepseek-v4.1-flash-free`,
`mimo-v2.6-flash-free`, `ling-2.6-flash-free`, `ll-alpha-free`, `beam-free`, `exo-free`,
`trinity-large-preview-free`, `nemotron-3.5-super-vl-free`.

## 2. The only real unknown

The built-in provider is a **gateway** (`opencode.ai/inference/...`), not a direct vendor API.
The gateway is entitled to: (a) pass `logprobs`/`top_logprobs` through as is; (b) return 400 on unknown
fields; (c) silently ignore them and not return `logprobs` in the response. The behaviour must be **measured**,
not guessed, and separately for each model (upstreams differ between models: vLLM/SGLang return it,
some provider implementations do not).

That is why stage E starts with a probe, not with UI code.

## 3. Capability probe (E1)

`scripts/probe-logprobs.py` — for each chat-completions model:

```
POST {base}/chat/completions
{ "model": <id>, "messages": [{"role":"user","content":"Say OK"}],
  "max_tokens": 1, "logprobs": true, "top_logprobs": 5, "stream": false }
```

Classification of the response:

| Observation | Status | What we do in the UI |
|---|---|---|
| 200 + non-empty `choices[0].logprobs.content[]` | `ok` | full L1+L2+L3 mode |
| 200, but `logprobs` = null/absent | `ignored` | badge "the gateway does not return probabilities" + `verbalized` mode |
| 400/422 mentioning logprobs | `rejected` | the feature is silently disabled for the model |
| 401/403/429 | `auth`/`rate` | we do not cache, repeat later |

The result is `~/.local/share/opencode/truthprobe/capabilities.json`:

```jsonc
{ "version": 1, "probedAt": "2026-11-19T12:00:00Z",
  "providers": { "opencode": {
    "deepseek-v4.1-flash-free": { "status": "ok", "topK": 5, "latencyMs": 240 },
    "gpt-5.2-codex":            { "status": "skipped", "reason": "responses api" } } } }
```

Rules: TTL 7 days; the probe is lazy (on the model's first answer) and by button
`/truthprobe probe`; concurrency ≤ 4 so as not to hit 429; the result is reused by all sessions.

**DoD E1:** the file is filled for all 69 models, there is a table "how many `ok` / `ignored` / `rejected`"
in `docs/CAPABILITIES.md` (the file has not been created yet — an artefact of stage E1). This is the answer to the question "will it work on the built-in models at all?".

## 4. What we do on `ignored` — verbalized mode (E5)

Honest degradation: the same answer, but the signal is of a different nature — the model assesses confidence
for each sentence itself (we ask it to return the JSON `[{i, confidence}]`). We mark it with a "self-report" icon,
do not mix it with logprob scoring and **do not** pass it off as a measurement. The reason: according to arXiv 2305.14975,
for RLHF models verbalized confidence is often better calibrated than conditional probabilities, but it is
a different signal, and the two must not be confused in one number.

## 5. Extensibility layer for custom APIs (E6)

Goal: a person adds a provider **with a descriptor in the config, without editing code**.

```jsonc
// ~/.config/opencode/truthprobe.json
{
  "mode": "summary",
  "topK": 20,
  "adapters": {
    "vllm-local": {
      "protocol": "openai-chat",           // we reuse the existing parser
      "baseURL": "http://127.0.0.1:8000/v1",
      "request": { "logprobs": true, "top_logprobs": 20 },
      "response": { "path": "choices[0].logprobs.content[]",
                    "token": "token", "logprob": "logprob", "top": "top_logprobs" }
    },
    "custom-jsonl": {
      "protocol": "custom",
      "request": { "return_logits": true },
      "response": { "path": "tokens[]", "token": "t", "logprob": "lp", "top": "alternatives" }
    }
  }
}
```

The adapter contract is 4 things: (1) how to ask, (2) where the list of tokens lies in the response,
(3) the names of the token/logprob/alternatives fields, (4) how to compute entropy (top-K or only p).
Everything else (segmentation, formulas, thresholds, UI) is shared. This is exactly "people will write their own APIs".

Validation: an unknown `protocol` → a warning, the feature is off; a broken `path` → the status
`parse-error` in the badge, not a session crash.

## 6. Stages and order

| ID | Work | DoD |
|---|---|---|
| **E1** | Probing 69 `chat-completions` models on the Zen gateway | `docs/CAPABILITIES.md` (not created yet) with real statuses and numbers |
| **E2** | Protocol patch: `logprobs`/`top_logprobs` in `bodyFields` + a gate in `fromRequest` | snapshot test: the request body changes only with `status: ok`; Anthropic/Gemini untouched |
| **E3** | Parsing deltas + carrying them into `providerMetadata` → `session.text.scored` | OpenAI/DeepSeek/GLM fixtures; a missing field does not break the stream |
| **E4** | Scoring + storage in the message part (`AssistantText.truthprobe`) | unit tests green, a session reload keeps the score |
| **E5** | UI: a line before the answer (first sentence) + a block after + highlighting with flags | a manual run in a VM on 3 free models, a screenshot |
| **E6** | Degradation `ignored`/`rejected` + verbalized mode | on claude/gemini an honest "unavailable", nothing crashes |
| **E7** | Adapters of third-party providers by config | vLLM locally/through a tunnel — works without editing code |

The order is rigid: E1 → E2 → E3 → E4 → E5, then E6/E7 in parallel.

## 7. Stage acceptance criteria

1. On ≥3 free built-in models one can see: the confidence of the first sentence before the text,
   the aggregate after, marked doubtful sentences.
2. On `claude-*`, `gemini-*`, `gpt-5.x/6.x` (responses) — the state "unavailable", without breaking
   the answer and without 400s.
3. No model degrades in speed by more than ~5% (measurement on 5 requests).
4. Adding a new provider = editing one JSON, no restart needed.
5. `bun test` is green; the build of `packages/core` and `packages/tui` passes.

## 8. Stage risks and answers

| Risk | Verified by | If it happens |
|---|---|---|
| The Zen gateway cuts logprobs for all 69 | E1 | we stay on verbalized mode + own key/local model as the "exact" mode |
| Free models run with `temperature` > 0 | E1 (temp from the snapshot) | we mark the score as noisy (`status: partial`) and do not draw conclusions from it |
| `top_logprobs` is limited (say, 5) | E1 | we compute φ_first over the available K, take `topK` from the probe |
| Different upstreams inside one gateway behave differently | E1 | the status is **per model**, not per provider |
| "Confident" scoring on a fabrication | E6 calibration | we show "risk", not "truth"; the list of doubtful sentences is the main output |

## 9. Effort estimate

E1 — 0.5 day (script + run + report), E2–E4 — 1 day, E5 — 1 day, E6–E7 — 0.5 day.
Total ~3 days, of which the first day gives the answer "does this work on the built-in models at all".
