> Русская версия: [docs/ru/SMOKE-E2E.md](ru/SMOKE-E2E.md)

# End-to-end check of TruthProbe without external keys

The mock server serves an OpenAI-compatible stream with real `logprobs`, so the whole path
"request → parsing → scoring → durable event → message part" is checked locally.

## How to reproduce

```bash
# 1. mock in a separate terminal
python3 scripts/mock-openai-logprobs.py 8899

# 2. run opencode from source: TruthProbe turns itself on
cd ~/src/opencode
OPENCODE_CONFIG=/path/to/opencode-truthprobe/scripts/mock-opencode.json \
bun run --cwd packages/cli src/index.ts run --model mock/mock-1 \
  "What is the capital of France? Answer in two sentences."

# 3. (optional) what the auto-check decided
cat ~/.local/share/opencode/truthprobe/capabilities.json
```

The first run on a clean cache: the request itself goes out without `logprobs`, in parallel a probe
request `{"model":"mock-1","messages":[{"role":"user","content":"ping"}],"max_tokens":1,
"logprobs":true,"top_logprobs":20,"stream":false}` is sent, and the `ok` verdict lands in the cache. From the second
run on, all requests to this provider go out already with `logprobs: true, top_logprobs: 20` —
measured: 2 of 2 streaming requests, 0 new probes.

## Measured result (a run in a VM)

CLI output:

```
The capital of France is Paris. It is home to about 2 million people.
```

The request the mock server saw (`/tmp/mock/requests.jsonl`):

```json
{"path": "/v1/chat/completions", "model": "mock-1", "logprobs": true, "top_logprobs": 20, "stream": true}
```

The stored assistant part (the `session_part` table in `~/.local/share/opencode/opencode-local.db`):

```json
{"type":"text","text":"The capital of France is Paris. It is home to about 2 million people.",
 "truthprobe":{"status":"ok","score":0.4442,"risk":0.5558,"level":"risky",
   "first":{"score":0.7076,"entropy":0.2924,"token":"The"},
   "sentences":[
     {"i":0,"start":0,"end":31,"text":"The capital of France is Paris.","score":0.9672,"risk":0.0328,
      "meanLp":0.9672,"minLp":-0.08,"phi":0.7076,"tokens":6,"flag":false},
     {"i":1,"start":32,"end":69,"text":"It is home to about 2 million people.","score":0.1584,"risk":0.8416,
      "meanLp":0.1584,"minLp":-2.9,"phi":0.1068,"tokens":7,"flag":true}],
   "flagged":1}}
```

What this proves:

1. `logprobs: true, top_logprobs: 20` really go into the request body — with no environment variables,
   purely thanks to the auto-check verdict.
2. Stream chunks with `choices[].logprobs.content[]` are parsed, tokens are accumulated per text block.
3. Scoring counts the first sentence as confident (0.967, risk 0.033) and the second as doubtful (0.158, risk 0.842), φ of the first token is 0.708. The default score is the geometric-mean probability `exp(meanLp)`, without φ and without the worst-token weight (see `docs/VALIDATION.md` §14).
4. Scoring reaches storage via `session.text.ended`, without a separate `session.text.scored` event
   (the initial variant with a separate durable event was blocked on the bus and was replaced — see `docs/VALIDATION.md`).

## The same scenario in a live TUI

```bash
python3 scripts/tui-probe.py          # starts the TUI in a pty, prints the request, captures the screen
python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Result (see `docs/VALIDATION.md`, §6 "Live TUI render (pty)"):

```
   first-token confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 44% ▰▰░░░ · risky · 1 doubtful sentence
     ▌ #2 ▰░░░░ 16% · unreliable: It is home to about 2 million people.
```

## What this does NOT check

- The real `opencode.ai/inference` gateway (a key is needed): whether it returns logprobs and does not cut the field.
- Behaviour on long real answers (all the runs are on the mock with two sentences).
