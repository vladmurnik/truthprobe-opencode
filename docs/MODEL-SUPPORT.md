> Русская версия: [docs/ru/MODEL-SUPPORT.md](ru/MODEL-SUPPORT.md)

# Which models work with TruthProbe

Confidence numbers appear only where the provider returns **token logprobs**.
This is a property of the API and the model, not our setting: if the provider cuts the field,
no patch will restore it — under the answer there will be `no confidence signal` with the reason.

Updated: 19.11.2026.

## Verified

| provider / model | numbers | what the probe showed |
| --- | --- | --- |
| `freepi/particle` | ✅ | `status: ok`, score 0.798, first-token 0.989 |
| `freepi/deepseek-v4.1-flash` | ✅ | `status: ok`, score 0.689, first flag 0.485 |
| `opencode/deepseek-v4.1-flash-free` | ❌ | 200 OK, no `logprobs` field in the response — `no logprobs in response` |

## How to read the statuses

| probe status | meaning | what the person will see |
| --- | --- | --- |
| `ok` | logprobs arrived, alternatives are there | percentages and levels under the answer |
| `ignored` | 200 OK, the provider silently cut the field | `no confidence signal` |
| `rejected` | 4xx mentioning logprobs | `no confidence signal` + the reason |
| `auth` / `rate` | key not accepted / 429 | the verdict is not cached, the probe will repeat |
| `error` | anything else | `no confidence signal` + the error text |

## What is known to work

- **OpenAI-compatible local gateways** with `logprobs` enabled: llama.cpp, vLLM, LM Studio,
  Ollama (the OpenAI endpoint, if the version returns `logprobs`).
- **Aggregator gateways** that pass the field through: free-pi (verified), most
  `openai-compatible` proxies.
- Any provider for which `scripts/probe-logprobs.py` prints `ok`.

## What is known not to work

- `opencode.ai`'s own inference — the field is not passed through.
- Anthropic Claude and Google Gemini through their native APIs: logprobs are not returned in a text
  completion (we have not tried to check — the record will appear only after a probe, not from memory).

## How to check your model

```bash
# free-pi gateway (local)
python3 scripts/probe-logprobs.py \
  --base http://127.0.0.1:8790/v1 --key local \
  --models particle,deepseek-v4.1-flash,deepseek-v4-pro

# any OpenAI-compatible endpoint
python3 scripts/probe-logprobs.py \
  --base https://api.openai.com/v1 --key "$OPENAI_API_KEY" \
  --models gpt-4.1-mini,gpt-4o-mini
```

The result is printed one line per model and cached in
`~/.local/share/opencode/truthprobe/capabilities.json` (TTL 7 days). For a ready-made table:

```bash
python3 scripts/probe-logprobs.py --base http://127.0.0.1:8790/v1 --key local \
  --models particle,deepseek-v4.1-flash --md
```

## One key per model, no inheritance

The cache is keyed by `provider/model` (`keyOf` in `packages/core/src/truthprobe/capability.ts`), and
nothing is copied from a sibling model. A gateway whose first model returns logprobs does not lift the
rest of its models: each one answers its own probe, and until it does, it simply has no numbers. The
runtime enables `capabilities.logprobs` on the model object only for the exact key that was verified.

The cost is one probe per model (a verdict lives 7 days, 1 hour after `auth`, 0 after `error`); the
benefit is that a gateway where some models reject the field does not spread the rejection to the
others, which is what a per-provider guess did before 0.13.20.

## If there are no numbers on the first attempt

With an empty cache, the very first request goes out without `logprobs`: the probe has not managed to answer yet.
The verdict is applied from the next message. If the line `no confidence signal` remains even
after the second request — the probe returned not `ok`, look at the reason in parentheses.
