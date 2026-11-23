#!/usr/bin/env python3
"""Checks whether FreeLLMAPI returns logprobs — without them TruthProbe is blind.

FreeLLMAPI (https://github.com/tashfeenahmed/freellmapi) is a single OpenAI-compatible
endpoint over ~87 free providers. For TruthProbe it is valuable because it provides
many different models behind one baseURL: you can collect a labeled dataset
("true/false" + scorer features) across dozens of models and train separate weights
for each one (`calibrate.py --fit --by-model`).

The script knows nothing about the internals of the router: it simply checks the contract.

    python3 scripts/probe-freellmapi.py --key freellmapi-xxxx
    python3 scripts/probe-freellmapi.py --url http://127.0.0.1:3001/v1 --model auto:fast
    python3 scripts/probe-freellmapi.py --key ... --jsonl probe.jsonl

The key (unified key) is taken from the Keys page of the local dashboard
http://127.0.0.1:3001 after the provider keys are added.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request

PROMPT = "What is the capital of France? Answer in one sentence."
FRAC_LOW_CUTOFF = math.log(0.5)  # threshold exactly as in packages/core/src/truthprobe/score.ts


def request(url: str, key: str, payload: dict | None = None, timeout: int = 90):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        return 0, {}, f"connection failed: {error.reason}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("FREELLMAPI_URL", "http://127.0.0.1:3001/v1"))
    parser.add_argument("--key", default=os.environ.get("FREELLMAPI_KEY"))
    parser.add_argument("--model", default="auto")
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--jsonl", help="where to append the measurement row for calibration")
    args = parser.parse_args()

    if not args.key:
        print("a unified key is required: --key freellmapi-... (or FREELLMAPI_KEY)", file=sys.stderr)
        return 2

    base = args.url.rstrip("/")

    status, _, body = request(f"{base}/models", args.key)
    models: list[str] = []
    if status == 200:
        try:
            models = [item.get("id", "") for item in json.loads(body).get("data", [])]
        except json.JSONDecodeError:
            pass
    print(f"GET /models -> {status}, models: {len(models)}")
    if models:
        print("  " + ", ".join(models[:10]) + (" ..." if len(models) > 10 else ""))
    elif status != 200:
        print("  " + body[:300])

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "logprobs": True,
        "top_logprobs": 3,
    }
    status, headers, body = request(f"{base}/chat/completions", args.key, payload)
    routed = headers.get("X-Routed-Via") or headers.get("x-routed-via") or "—"
    print(f"POST /chat/completions -> {status}, routed via {routed}")

    if status != 200:
        print("  " + body[:600])
        return 1

    try:
        payload_out = json.loads(body)
        choice = payload_out["choices"][0]
    except (json.JSONDecodeError, KeyError, IndexError):
        print("  could not parse the response: " + body[:300])
        return 1

    text = (choice.get("message") or {}).get("content") or ""
    tokens = ((choice.get("logprobs") or {}).get("content") or [])
    print(f"  answer: {text[:160]!r}")
    print(f"  tokens with logprob: {len(tokens)}")

    if not tokens:
        print("  VERDICT: logprobs did NOT arrive — TruthProbe will show 'unavailable' for this model.")
        return 1

    lps = [float(token["logprob"]) for token in tokens if token.get("logprob") is not None]
    mean_lp = sum(lps) / len(lps)
    min_lp = min(lps)
    top = [x for x in (tokens[0].get("top_logprobs") or []) if isinstance(x.get("logprob"), (int, float))]
    if len(top) < 2:
        start_phi = max(0.0, min(1.0, 1 - math.exp(float(tokens[0]["logprob"]))))
    else:
        probs = [math.exp(float(x["logprob"])) for x in top]
        total = sum(probs)
        h = -sum((p / total) * math.log(p / total) for p in probs if total > 0 and p > 0)
        start_phi = max(0.0, min(1.0, h / math.log(max(2, min(20, len(top))))))
    frac_low = sum(1 for lp in lps if lp < FRAC_LOW_CUTOFF) / len(lps)
    print(f"  meanLp {mean_lp:.4f}, minLp {min_lp:.4f}, phi(first token) {start_phi:.3f}, "
          f"fracLow {frac_low:.2f}, example: " + ", ".join(
        f"{token['token']!r}={token['logprob']:.3f}" for token in tokens[:5]
    ))
    print("  VERDICT: logprobs arrive — the model is suitable for collecting calibration data.")

    if args.jsonl:
        row = {
            "model": routed if routed != "—" else args.model,
            "prompt": args.prompt,
            "answer": text,
            "meanLp": round(mean_lp, 6),
            "minLp": round(min_lp, 6),
            "phi": round(start_phi, 6),
            "fracLow": round(frac_low, 6),
            "label": None,
        }
        with open(args.jsonl, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  unlabeled row appended to {args.jsonl} (the label has to be set by hand)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
