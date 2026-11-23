> Русская версия: [docs/ru/PRIOR-ART.md](ru/PRIOR-ART.md)

# Prior art: model confidence from the first tokens

Collected 19.11.2026. Needed so as not to reinvent the metric and not to repeat others' mistakes.

## Directly on topic

**The First Token Knows: Single-Decode Confidence for Hallucination Detection** —
Mina Gabriel, Pei Wang. arXiv **2605.05166** (v1 06.05.2026, v2 14.11.2026),
TRUST-AI 2026, CEUR Vol. 4254, pp. 55–63.

- `φ_first = 1 − normalized entropy of the top-K distribution of the first content-bearing token`.
- PopQA + TriviaQA, three 7–8B instruct models: φ_first **catches up with or slightly exceeds**
  semantic self-consistency (1 greedy decode versus 1 decode + 10 samples + NLI clustering).
- φ_first correlates moderately strongly with semantic agreement; combining them gives only a small
  AUROC gain.
- Caveat from the authors: the method is weak on **high-confidence falsehoods** and **long-form generation**.

→ We take the formula as is (`φ_first`), but not as the only signal.

## Calibration: why logprob ≠ truth

**Just Ask for Calibration** — Tian et al., EMNLP 2023, arXiv **2305.14975**.

- For RLHF models (ChatGPT/GPT-4/Claude), **verbalized** confidence is usually
  better calibrated than conditional probabilities; ECE drops roughly by half.
- Implication for us: show "risk", not "the model is 94% confident".

**Beyond Logprobs: A Multi-Signal Confidence Engine for LLM-Based Document Field Extraction** —
Nitesh Kumar, arXiv **2606.24420** (IJCAI-ECAI 2026 workshop, oral).

- Token-level logprobs, verbalized confidence and multi-sample self-consistency
  "collapse toward all-positive behaviour at practical thresholds" — at working thresholds
  they do not separate the reliable from the unreliable.
- Fusion with an independent source (cross-call disagreement) → 0.928 ROC AUC,
  −70% selective risk against `logprob-mean`.
- Direct conclusion: **a single logprob signal in production is insufficient**, a second structurally different signal is needed.

**Detecting AI Hallucinations in Finance (ECLIPSE)** — arXiv **2512.03107**.

- Comparison of GPT-3.5-turbo vs Claude-3-Haiku: Claude "lacks token-level log probabilities",
  AUC drops from 0.89 to 0.59 — a direct confirmation of the provider barrier.

## Related methods (not in v1, but they influence the design)

- **Semantic Entropy Probes** — Kossen et al., arXiv **2406.15927**: an approximation of semantic entropy
  from the hidden states of a single pass. Requires whitebox → only for local models/a fork of inference.
- **lm-polygraph** (`IINemo/lm-polygraph`, ★530, MIT) — the most complete battery of UE methods
  (logprob-based, semantic entropy, SEP) + a benchmark. A reference for implementations.
- **SelfCheckGPT** (`potsawee/selfcheckgpt`, ★635) — sampling-based black-box.
- **llm-confidence-probe** (`prefersung`) — vLLM returns token logprobs, aggregation
  into sentence-level risk, highlighting of suspicious phrases. The closest UX analogue of L3.
- **LLM-Hallucination-Detection-Script** (`Mattbusel`, ★19, Rust CLI) — "which words of the
  answer to re-check", topics `logprobs`, `token-visualization`.
- **rydz** (`mobarski`) — logprobs for classification with a single token (the "1 request, 1 token" pattern).

## What already exists in the OpenCode ecosystem

- Nothing with token logprobs. The closest is **DCGP** (`addicted2crypto/DCGP`, ★6):
  "predicts entropy, blocks hallucinations", but the entropy there is over context health
  (domains, gates, anchors), the word `logprob` is absent from the README.
- `@tarquinen/opencode-dcp` — control over the amount of context, orthogonal.

## Verified facts about OpenCode (important for the architecture)

- In the `sst/opencode@dev` tree (12 659 files) there is **not a single match for `logprob`**.
- In the `@opencode-ai/plugin` d.ts there are **no** mentions of logprobs; the full list of hooks:
  `event`, `config`, `tool`, `auth`, `provider`, `chat.message`, `chat.params`, `chat.headers`,
  `permission.ask`, `command.execute.before`, `tool.execute.before`, `tool.execute.after`,
  `shell.env`, `experimental.chat.messages.transform`, `experimental.chat.system.transform`,
  `experimental.provider.small_model`, `experimental.session.compacting`,
  `experimental.compaction.autocontinue`, `experimental.text.complete`, `tool.definition`.
- `chat.params` can change `options: Record<string, any>` (one can try to add
  `logprobs`), but the response parser throws them away → a filter at the core level is unavoidable.
