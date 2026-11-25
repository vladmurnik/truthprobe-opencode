#!/usr/bin/env python3
"""Collects calibration rows through any OpenAI-compatible endpoint.

The same script works with FreeLLMAPI (many models behind one baseURL),
with a local gateway, and with a regular OpenAI-compatible server. The output is
JSONL in exactly the shape that `scripts/calibrate.py --fit --by-model` eats:

    {"model": "freepi/particle", "prompt": "...", "answer": "...",
     "meanLp": -0.0573, "minLp": -0.493, "phi": 0.88, "fracLow": 0.05,
     "label": 1, "tokens": 22}

The features are computed **exactly as at runtime** (`packages/core/src/truthprobe/score.ts`):

  meanLp  = mean logprob over the content tokens of the answer
  minLp   = worst logprob
  phi     = 1 - normalized entropy over the top_logprobs of the FIRST token
  fracLow = share of tokens with exp(logprob) < 0.5, i.e. logprob < ln 0.5

An important detail about "content tokens": with reasoning models the logprobs stream
starts with the reasoning (`</think>` and the text before it), while the runtime counts only
the tokens that made it into the visible answer. That is why `collect.py` drops the prefix up to
the start of the answer text — otherwise features and weights would live in different worlds.

Labeling. There are three ways:
  1. `--auto-label data/qa-bank.jsonl` — a question bank with reference answers
     (`{"prompt": ..., "expect": ["canberra"]}`). A match is 1, a different answer is 0,
     an empty answer/refusal is a row without a label (it does not go into training).
  2. `--prompts rows.jsonl`, where the row already has a `label`.
  3. By hand: collect without a label and fill in 0/1 later.

Examples:

    # many models, auto-labeling from the question bank, 8 workers
    python3 scripts/collect.py --url http://127.0.0.1:3001/v1 --key $FREELLMAPI_KEY \\
        --models auto,auto:fast,groq/llama-3.3-70b --prompts data/qa-bank.jsonl \\
        --auto-label data/qa-bank.jsonl --out data/rows.jsonl --resume --workers 8

    # a single prompt to check the contract
    python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --key x \\
        --model freepi/particle --prompt "Name the capital of France" --out data/rows.jsonl

    # plan only, no network
    python3 scripts/collect.py --prompts data/qa-bank.jsonl --models auto --dry-run

    # several samples per (model, prompt) pair: with temperature > 0 the answers differ
    python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --key x \\
        --models particle,deepseek-v4.1-flash --prompts data/qa-hard-bank.jsonl \\
        --auto-label data/qa-hard-bank.jsonl --temperature 0.8 --samples 4 \\
        --workers 4 --out data/rows-hard.jsonl --resume

`--resume` skips the (model, prompt) pairs, and with `--samples N` the triples
(model, prompt, sample), that are already present in `--out`. Rows without the
`sample` field count as sample 0, so the old files stay compatible.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

FRAC_LOW_CUTOFF = math.log(0.5)  # exactly the threshold used in score.ts


def clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    return min(1.0, max(0.0, x))


def phi(token: dict, top_k: int = 20) -> float:
    """Confidence from top_logprobs: 1 - normalized entropy, like `phi` at runtime."""
    top = [
        item
        for item in (token.get("top_logprobs") or [])
        if isinstance(item.get("logprob"), (int, float)) and math.isfinite(item["logprob"])
    ]
    if len(top) < 2:
        # The degenerate runtime branch is exp(logprob), not 1 - exp(logprob):
        # otherwise the same token gets the opposite sign and the `meanPhi` weight works against the answer.
        return clamp01(math.exp(float(token["logprob"])))
    k = max(2, min(top_k, len(top)))
    probs = [math.exp(float(item["logprob"])) for item in top[:k]]
    total = sum(probs)
    if not total > 0:
        return 1.0
    h = 0.0
    for p in probs:
        q = p / total
        if q > 0:
            h -= q * math.log(q)
    # phi is confidence, as at runtime (`packages/core/src/truthprobe/score.ts`): 1 - H/ln K.
    # Entropy here would give the opposite sign relative to the live scorer, and the trained
    # `meanPhi` weight would work against the answer.
    return clamp01(1.0 - h / math.log(k) if k > 1 else 1.0)


def answer_tokens(tokens: list[dict], answer: str) -> list[dict]:
    """Keeps only the tokens that make up the visible answer.

    The stream starts with the reasoning; the runtime scores only what made it into the
    answer text. If the answer is empty or is not found in the concatenated tokens, we return
    the whole stream: better to honestly score over it than to lose the row.
    """
    if not tokens or not (answer or "").strip():
        return tokens
    text = "".join(str(t.get("token") or "") for t in tokens)
    needle = answer.strip()
    start = text.find(needle)
    if start < 0 and len(needle) > 40:
        start = text.find(needle[:40])
    if start <= 0:
        return tokens
    out: list[dict] = []
    pos = 0
    for token in tokens:
        following = pos + len(str(token.get("token") or ""))
        if following > start:
            out.append(token)
        pos = following
    return out or tokens


def features(tokens: list[dict], answer: str = "", top_k: int = 20) -> dict | None:
    scored = answer_tokens(tokens, answer)
    lps = [float(t["logprob"]) for t in scored if isinstance(t.get("logprob"), (int, float))]
    if not lps:
        return None
    return {
        "meanLp": round(sum(lps) / len(lps), 6),
        "minLp": round(min(lps), 6),
        "phi": round(phi(scored[0], top_k), 6),
        # Polarity marker: `phi` here is confidence (1 - entropy), as at runtime.
        # In datasets from before 22.11.2026 there was no field and `phi` was entropy; `calibrate.py`
        # inverts such rows on load. Without the marker it would invert the new ones too.
        "phiDef": "confidence",
        "fracLow": round(sum(1 for lp in lps if lp < FRAC_LOW_CUTOFF) / len(lps), 6),
        # The same feature the runtime computes (`digitDensity` in score.ts): ASCII digits only
        # and the length in UTF-16 code units (like `String.prototype.length`), otherwise train and serve
        # diverge on Arabic-Indic digits and emoji.
        "digitDensity": round(
            sum(1 for ch in answer if "0" <= ch <= "9") / (len(answer.encode("utf-16-le")) // 2), 6
        ) if answer else 0.0,
        "tokens": len(lps),
    }


def request(url: str, key: str, payload: dict | None = None, timeout: int = 120):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        return 0, {}, f"connection failed: {error.reason}"


def read_prompts(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for n, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    print(f"{path}:{n}: not JSON, line skipped", file=sys.stderr)
                    continue
                prompt = item.get("prompt")
                if not prompt:
                    continue
                rows.append({"prompt": prompt, "label": item.get("label")})
            else:
                rows.append({"prompt": line, "label": None})
    return rows


def read_bank(path: str) -> dict[str, list[str]]:
    """Question bank: prompt -> list of accepted answers (lowercase)."""
    bank: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            prompt = item.get("prompt")
            expect = item.get("expect") or []
            if prompt and expect:
                bank[prompt] = [str(value).lower() for value in expect]
    return bank


# Any Cyrillic letter counts, including "ё" (U+0451) and the letters outside the a-я block,
# which is why the range is written as a code point range rather than a character run.
WORD = re.compile(r"[0-9a-z\u0400-\u04ff]+")


def matches(answer: str, expect: list[str]) -> bool:
    """Short references are compared on word boundaries, long ones by substring."""
    text = " ".join(WORD.findall(answer.lower()))
    words = text.split()
    for value in expect:
        if " " in value or len(value) > 4:
            if value in answer.lower():
                return True
        elif value in words:
            return True
    return False


def autolabel(answer: str, expect: list[str]) -> int | None:
    if not (answer or "").strip():
        return None  # refusal or empty answer: no label, not used for training
    if not WORD.search(answer.lower()):
        # Nothing to compare against: a CJK answer would be labelled 0 and silently
        # trained as a hallucination. Unlabelled is the honest answer.
        return None
    return 1 if matches(answer, expect) else 0


def seen_pairs(path: str) -> set[tuple[str, str, int]]:
    """Triples (model, prompt, sample) collected so far.

    Rows without the `sample` field are sample 0: the old datasets were written before
    `--samples` appeared, and after `--resume` they must not be requested again.
    """
    if not path or not os.path.exists(path):
        return set()
    done: set[tuple[str, str, int]] = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (row.get("model") and row.get("prompt") and row.get("answer")):
                continue
            try:
                sample = int(row.get("sample") or 0)
            except (TypeError, ValueError):
                sample = 0
            done.add((row["model"], row["prompt"], sample))
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("COLLECT_URL", "http://127.0.0.1:3001/v1"))
    parser.add_argument("--key", default=os.environ.get("FREELLMAPI_KEY") or os.environ.get("OPENAI_API_KEY") or "")
    parser.add_argument("--model", action="append", default=[], help="model; can be repeated")
    parser.add_argument("--models", help="comma-separated model list (alternative to --model)")
    parser.add_argument("--all-models", action="store_true", help="take the whole catalog from GET /v1/models")
    parser.add_argument("--prompt", action="append", default=[], help="prompt; can be repeated")
    parser.add_argument("--prompts", help="prompt file: txt (one per line) or JSONL {prompt,label}")
    parser.add_argument("--auto-label", metavar="BANK", help="JSONL with expect answers: set label 0/1 automatically")
    parser.add_argument("--out", default="truthprobe-rows.jsonl")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-logprobs", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.3, help="pause between requests, sec (per worker)")
    parser.add_argument("--samples", type=int, default=1, help="how many times to request each (model, prompt) pair")
    parser.add_argument(
        "--provider",
        default="",
        help="prefix for the model field in rows (e.g. freepi): at runtime the weights key is providerID/modelID",
    )
    parser.add_argument("--workers", type=int, default=1, help="how many requests to keep in flight")
    parser.add_argument("--limit", type=int, help="no more than N requests per run")
    parser.add_argument("--resume", action="store_true", help="skip already collected (model, prompt, sample)")
    parser.add_argument("--dry-run", action="store_true", help="only show the plan, without network")
    args = parser.parse_args()

    models = list(args.model)
    if args.models:
        models.extend(item.strip() for item in args.models.split(",") if item.strip())
    if args.all_models:
        status, _, body = request(f"{args.url.rstrip('/')}/models", args.key)
        if status != 200:
            print(f"model catalog unavailable: HTTP {status}", file=sys.stderr)
            return 2
        try:
            models.extend(row["id"] for row in json.loads(body).get("data", []) if row.get("id"))
        except (json.JSONDecodeError, KeyError, TypeError):
            print("could not parse the model catalog", file=sys.stderr)
            return 2
    if not models:
        models = ["auto"]

    prompts: list[dict] = [{"prompt": p, "label": None} for p in args.prompt]
    if args.prompts:
        prompts.extend(read_prompts(args.prompts))
    if not prompts:
        print("no prompts: pass --prompt or --prompts", file=sys.stderr)
        return 2
    if args.limit:
        prompts = prompts[: args.limit]

    bank = read_bank(args.auto_label) if args.auto_label else {}

    samples = max(1, args.samples)
    plan = [(m, p["prompt"], p["label"], s) for m in models for p in prompts for s in range(samples)]
    print(
        f"plan: {len(models)} model(s) x {len(prompts)} prompt(s) x {samples} sample(s) "
        f"= {len(plan)} requests -> {args.out}"
    )

    if args.dry_run:
        for model, prompt, label, sample in plan[:20]:
            print(f"  {model} sample={sample} | label={label} | {prompt[:70]}")
        if len(plan) > 20:
            print(f"  ... {len(plan) - 20} more")
        return 0

    done = seen_pairs(args.out) if args.resume else set()
    base = args.url.rstrip("/")
    lock = threading.Lock()
    counters = {"written": 0, "skipped": 0, "failed": 0}

    def run_one(item: tuple[int, str, str, int | None, int]) -> None:
        index, model, prompt, label, sample = item
        plan_model = f"{args.provider}/{model}" if args.provider else model
        if (plan_model, prompt, sample) in done:
            with lock:
                counters["skipped"] += 1
            return
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "logprobs": True,
            "top_logprobs": args.top_logprobs,
        }
        status, headers, body = request(f"{base}/chat/completions", args.key, payload)
        routed = headers.get("X-Routed-Via") or headers.get("x-routed-via") or model
        # The weights key at runtime is `providerID/modelID`, so the record in the row
        # must have the same shape, otherwise per-model calibration will not find the model.
        model_id = f"{args.provider}/{routed}" if args.provider else routed
        with lock:
            if status != 200:
                counters["failed"] += 1
                row = {
                    "model": model_id,
                    "prompt": prompt,
                    "answer": "",
                    "label": label,
                    "sample": sample,
                    "error": f"HTTP {status}: {body[:200]}",
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                print(f"[{index}/{len(plan)}] {model} sample={sample} -> HTTP {status}")
                time.sleep(args.sleep)
                return
            try:
                choice = json.loads(body)["choices"][0]
            except (json.JSONDecodeError, KeyError, IndexError):
                counters["failed"] += 1
                print(f"[{index}/{len(plan)}] {model} sample={sample} -> could not parse the response")
                time.sleep(args.sleep)
                return
            answer = (choice.get("message") or {}).get("content") or ""
            tokens = ((choice.get("logprobs") or {}).get("content") or [])
            feats = features(tokens, answer, args.top_logprobs)
            # An answer truncated by max_tokens is an artifact of our own limit, not a model
            # error. Such an answer must not become a negative, otherwise the weights learn
            # from our own greediness.
            truncated = choice.get("finish_reason") == "length"
            if bank and prompt in bank:
                label = autolabel(answer, bank[prompt])
                if truncated and label == 0:
                    label = None
            row = {
                "model": model_id,
                "prompt": prompt,
                "answer": answer,
                "label": label,
                "sample": sample,
                **({"truncated": True} if truncated else {}),
                **({"error": "no logprobs in response"} if feats is None else feats),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            if feats is None:
                counters["failed"] += 1
                print(f"[{index}/{len(plan)}] {routed} sample={sample} -> no logprobs")
            else:
                counters["written"] += 1
                print(
                    f"[{index}/{len(plan)}] {routed} sample={sample} label={label} -> "
                    f"meanLp {feats['meanLp']:.3f} minLp {feats['minLp']:.3f} "
                    f"phi {feats['phi']:.3f} fracLow {feats['fracLow']:.2f}"
                )
            time.sleep(args.sleep)

    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        items = [(i, m, p, l, s) for i, (m, p, l, s) in enumerate(plan, start=1)]
        if args.workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(run_one, items))
        else:
            for item in items:
                run_one(item)

    print(
        f"done: {counters['written']} rows with features, {counters['skipped']} skipped (--resume), "
        f"{counters['failed']} without logprobs/errors"
    )
    if counters["written"]:
        print(
            "next: python3 scripts/calibrate.py --fit --by-model --out weights.json "
            f"{args.out}   (rows without a label will not be used for training)"
        )
    return 0 if counters["written"] else 1


if __name__ == "__main__":
    sys.exit(main())
