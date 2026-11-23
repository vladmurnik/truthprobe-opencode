> Русская версия: [docs/ru/FREELLMAPI.md](ru/FREELLMAPI.md)

# FreeLLMAPI as a data source for calibration

[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) — a single OpenAI-compatible
endpoint (`/v1`) on top of the free tiers of dozens of providers. For TruthProbe it is
interesting not as "yet another gateway", but as a **factory of labelled data**: many different
models through one `baseURL`, the same `logprobs` format, and there is a router that
switches to the next model on its own at 429.

## What has already been verified (20.11.2026)

| What | How | Result |
| --- | --- | --- |
| The image comes up | `docker run ghcr.io/tashfeenahmed/freellmapi:latest` | the server listens on `:3001`, status `healthy` |
| First launch | `ENCRYPTION_KEY` + `FREEAPI_CONFIG_JSON` with an admin account | the DB is created, **25 models** are seeded, `POST /api/auth/login` → 200 |
| Model catalog | `GET /api/models` with a token | returns `platform`, `modelId`, `rpmLimit`, `contextWindow`, `enabled` |
| Inference | `POST /v1/chat/completions` | **not verified**: without provider keys all models are `enabled: false` |
| `logprobs` pass-through | — | **not verified**, below it is explained why this is the main question |
| Bulk collection on another gateway (`127.0.0.1:8790/v1`) | `collect.py --all-models --auto-label`, 24 models × 24 questions | **120 rows with features** on 7 models (4 models — 24/24), 108 × `HTTP 403 premium credits`, 348 × "without logprobs", **0 negatives** (all answers correct) |

Without keys for at least one provider (Groq, Google, Cerebras, OpenRouter…) the router
cannot serve a single request. Keys are put on the **Keys** page of the local
dashboard `http://127.0.0.1:3001`; the same header also holds the **unified key** of the form
`freellmapi-…` — this is the only token that the client sees.

### Why the collection still does not give calibration

On the 24×24 run (576 requests) there were 120 rows with features and **zero negatives**:
all the models that answered at all answered correctly. Plus 108 requests ran into
`HTTP 403 premium credits` (on this gateway premium models require credits), and 348
came back without `logprobs`. Training the weights needs both labels, so `calibrate.py --fit`
honestly refuses to work on such a file and says: "the set has only one class".

What will give negatives: deliberately weak/small models, tricky questions with a verifiable
answer, or an artificially truncated context — then part of the answers will be wrong, and
the features (`meanLp`, `minLp`, `phi`, `fracLow`) will have something to compare against.

## Bringing it up locally

```bash
KEY=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
docker run -d --name freellmapi -p 3001:3001 \
  -e ENCRYPTION_KEY="$KEY" -e NODE_ENV=production \
  -e FREEAPI_CONFIG_JSON='{"admin":{"email":"you@example.com","password":"change-me"}}' \
  -v "$HOME/freellmapi-data:/app/server/data" \
  ghcr.io/tashfeenahmed/freellmapi:latest
```

`ENCRYPTION_KEY` is mandatory in `production`: without it the server crashes at startup with
`ENCRYPTION_KEY is required in production for API key encryption`.
`FREEAPI_CONFIG_JSON` creates the first account, so as not to catch the setup code from the logs.

## Checking whether logprobs get through

```bash
python3 scripts/probe-freellmapi.py --key freellmapi-xxxx
python3 scripts/probe-freellmapi.py --key freellmapi-xxxx --model auto:fast --jsonl labeled.jsonl
```

The script does `GET /v1/models`, then `POST /v1/chat/completions` with
`logprobs: true, top_logprobs: 3` and prints the verdict:

- `logprobs did not arrive` → for this model TruthProbe will show `unavailable`, collecting
  data is pointless;
- `logprobs arrive` → a row with `meanLp / minLp / phi / fracLow` is appended to the JSONL,
  all that remains is to set `label` (truth/lie) and accumulate 200–500 rows.
- To collect a set across several models at once, use `scripts/collect.py` (below) —
  it computes the features exactly the same way as the runtime, and can continue an interrupted collection.

FreeLLMAPI claims that `logprobs` is passed through to the provider, but the free tiers
of different providers treat the parameter differently: some simply ignore it,
some answer 400. Therefore it must be checked **for each model separately**, not "in general".

## Connecting as a provider in opencode

```json
{
  "provider": {
    "freellmapi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "FreeLLMAPI",
      "options": { "baseURL": "http://127.0.0.1:3001/v1", "apiKey": "freellmapi-xxxx" },
      "models": {
        "auto": { "name": "Auto (router)" },
        "auto:fast": { "name": "Auto fast" }
      }
    }
  }
}
```

The TruthProbe auto-check will hit the endpoint itself and write the verdict into
`~/.local/share/opencode/truthprobe/capabilities.json`; with `status: ok` the badge
will appear with no configuration at all.

## Separate weights for each model

The reason this is needed: the shape of the log-probability distribution differs between models.
One shared `sigmoid(bias + w·x)` is systematically biased for some models — deterministic
gateways have `logprob ≈ −0.001`, "live" models have a longer tail.

```bash
python3 scripts/calibrate.py labeled.jsonl --fit --by-model --out truthprobe-weights.json
```

The JSONL must contain a `model` field (the `probe-freellmapi.py --jsonl` script writes
`X-Routed-Via` there, that is, `platform/model`). The output is a bundle:

```json
{
  "version": 1,
  "features": ["bias", "meanLp", "minLp", "meanPhi", "fracLow"],
  "global": { "bias": 0.0, "meanLp": 0.0, "minLp": 0.0, "meanPhi": 0.0, "fracLow": 0.0 },
  "models": {
    "groq/llama-3.3-70b": { "rows": 120, "positives": 41, "auroc": 0.78, "ece": 0.06, "weights": {} }
  }
}
```

What **the runtime as of 0.7.0** does: `scoreAnswer` receives `providerID/modelID`
(`publish-llm-event.ts` → `modelKey`), the `bundleScorer` scorer takes `models[<id>]`,
and when it is absent — `global`. Broken or incomplete model entries (for example,
`weights: null` for a group with few rows) are silently skipped, so one
broken key does not break the calibration of the others. To check directly:

```bash
TRUTHPROBE_SCORER=linear:truthprobe-weights.json bun run --cwd packages/cli src/index.ts
# in stderr on load: linear:truthprobe-weights.json(3 models)
```

## Collecting a set: `scripts/collect.py`

`collect.py` is what was missing between "probing one model" and "training the weights":
it runs a list of prompts across a list of models and writes ready rows for
`calibrate.py`. The features are computed **with the same formula as in the runtime**:
`meanLp` = mean logprob, `minLp` = worst, `phi` = 1 − normalized entropy
over `top_logprobs` of the first token, `fracLow` = share of tokens with `logprob < ln 0.5`.

```bash
# prompts: txt (one per line) or JSONL {"prompt": "...", "label": 1}
python3 scripts/collect.py --url http://127.0.0.1:3001/v1 --key $FREELLMAPI_KEY \
    --models auto,auto:fast,groq/llama-3.3-70b --prompts prompts.txt \
    --out data/rows.jsonl --resume --sleep 0.5 --limit 200
```

- `--resume` skips (model, prompt) pairs already lying in `--out` — collection can be
  interrupted and resumed.
- `--dry-run` prints the plan without the network, `--limit` caps the number of requests
  (convenient for free quotas).
- an answer without `logprobs` is written as a row with `error`, but does not go into training.
- the `model` field is taken from `X-Routed-Via` if the router sent it: then the weights
  are bound to the model that actually answered, not to `auto`.

## What to expect from such a data source

- **Plus:** dozens of models for free, a single protocol, the router works around 429 by itself.
- **Minus:** free tiers are unstable in latency and limits; some models
  do not return logprobs; the "intelligence" of the endpoint degrades towards the end of the day, when the providers
  run out of daily quotas.
- **Conclusion:** as a source of a **labelled set** — it is suitable; as a production provider
  for the badge — only with an honest `unavailable` where logprobs did not arrive.
