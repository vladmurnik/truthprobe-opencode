#!/usr/bin/env python3
"""Собирает калибровочные строки через любой OpenAI-совместимый эндпоинт.

Один и тот же скрипт работает и с FreeLLMAPI (много моделей за одним baseURL),
и с локальным шлюзом, и с обычным OpenAI-совместимым сервером. На выходе —
JSONL ровно в том виде, который ест `scripts/calibrate.py --fit --by-model`:

    {"model": "freepi/particle", "prompt": "...", "answer": "...",
     "meanLp": -0.0573, "minLp": -0.493, "phi": 0.88, "fracLow": 0.05,
     "label": 1, "tokens": 22}

Признаки считаются **точно так же, как в рантайме** (`packages/core/src/truthprobe/score.ts`):

  meanLp  = среднее logprob по всем содержательным токенам ответа
  minLp   = худший logprob
  phi     = 1 - нормированная энтропия по top_logprobs ПЕРВОГО токена
  fracLow = доля токенов с exp(logprob) < 0.5, то есть logprob < ln 0.5

Это важно: если считать признаки иначе (например, fracLow по порогу -1.0),
обученные веса будут применяться к другим числам и калибровка развалится.

Примеры:

    python3 scripts/collect.py --url http://127.0.0.1:3001/v1 --key $FREELLMAPI_KEY \\
        --models auto,auto:fast --prompts prompts.txt --out data/rows.jsonl

    python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --key x \\
        --model freepi/particle --prompt "Назови столицу Франции" --out data/rows.jsonl

    python3 scripts/collect.py --prompts prompts.txt --models auto --dry-run

Файл промптов: либо обычный текст (по промпту на строку), либо JSONL с полями
`prompt` и (необязательно) `label`; метка переносится в результат. Строки без
метки (`label: null`) тоже пишутся — их можно разметить позже, но в обучение
они попадут только после простановки 0/1.

`--resume` пропускает пары (модель, промпт), которые уже есть в `--out`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

FRAC_LOW_CUTOFF = math.log(0.5)  # ровно тот порог, что в score.ts


def clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    return min(1.0, max(0.0, x))


def phi(token: dict, top_k: int = 20) -> float:
    """1 - нормированная энтропия по top_logprobs; копия normalizedEntropy из score.ts."""
    top = [
        item
        for item in (token.get("top_logprobs") or [])
        if isinstance(item.get("logprob"), (int, float)) and math.isfinite(item["logprob"])
    ]
    if len(top) < 2:
        return clamp01(1 - math.exp(float(token["logprob"])))
    probs = [math.exp(float(item["logprob"])) for item in top]
    total = sum(probs)
    if not total > 0:
        return 1.0
    h = 0.0
    for p in probs:
        q = p / total
        if q > 0:
            h -= q * math.log(q)
    k = max(2, min(top_k, len(top)))
    return clamp01(h / math.log(k) if k > 1 else 0.0)


def features(tokens: list[dict], top_k: int = 20) -> dict | None:
    lps = [float(t["logprob"]) for t in tokens if isinstance(t.get("logprob"), (int, float))]
    if not lps:
        return None
    return {
        "meanLp": round(sum(lps) / len(lps), 6),
        "minLp": round(min(lps), 6),
        "phi": round(phi(tokens[0], top_k), 6),
        "fracLow": round(sum(1 for lp in lps if lp < FRAC_LOW_CUTOFF) / len(lps), 6),
        "tokens": len(lps),
    }


def request(url: str, key: str, payload: dict | None = None, timeout: int = 120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
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
                    print(f"{path}:{n}: не JSON, строка пропущена", file=sys.stderr)
                    continue
                prompt = item.get("prompt")
                if not prompt:
                    continue
                rows.append({"prompt": prompt, "label": item.get("label")})
            else:
                rows.append({"prompt": line, "label": None})
    return rows


def seen_pairs(path: str) -> set[tuple[str, str]]:
    if not path or not os.path.exists(path):
        return set()
    done: set[tuple[str, str]] = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("model") and row.get("prompt") and row.get("answer"):
                done.add((row["model"], row["prompt"]))
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("COLLECT_URL", "http://127.0.0.1:3001/v1"))
    parser.add_argument("--key", default=os.environ.get("FREELLMAPI_KEY") or os.environ.get("OPENAI_API_KEY") or "")
    parser.add_argument("--model", action="append", default=[], help="модель; можно повторять")
    parser.add_argument("--models", help="список моделей через запятую (альтернатива --model)")
    parser.add_argument("--prompt", action="append", default=[], help="промпт; можно повторять")
    parser.add_argument("--prompts", help="файл промптов: txt (по строке) или JSONL {prompt,label}")
    parser.add_argument("--out", default="truthprobe-rows.jsonl")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-logprobs", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.3, help="пауза между запросами, сек")
    parser.add_argument("--limit", type=int, help="не больше N запросов за запуск")
    parser.add_argument("--resume", action="store_true", help="пропускать уже собранные пары (модель, промпт)")
    parser.add_argument("--dry-run", action="store_true", help="только показать план, без сети")
    args = parser.parse_args()

    models = list(args.model)
    if args.models:
        models.extend(item.strip() for item in args.models.split(",") if item.strip())
    if not models:
        models = ["auto"]

    prompts: list[dict] = [{"prompt": p, "label": None} for p in args.prompt]
    if args.prompts:
        prompts.extend(read_prompts(args.prompts))
    if not prompts:
        print("нет промптов: задай --prompt или --prompts", file=sys.stderr)
        return 2
    if args.limit:
        prompts = prompts[: args.limit]

    plan = [(m, p["prompt"], p["label"]) for m in models for p in prompts]
    print(f"план: {len(models)} модел(ей) x {len(prompts)} промпт(ов) = {len(plan)} запросов -> {args.out}")

    if args.dry_run:
        for model, prompt, label in plan[:20]:
            print(f"  {model} | label={label} | {prompt[:70]}")
        if len(plan) > 20:
            print(f"  ... ещё {len(plan) - 20}")
        return 0

    done = seen_pairs(args.out) if args.resume else set()
    base = args.url.rstrip("/")
    written = skipped = failed = 0

    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        for index, (model, prompt, label) in enumerate(plan, start=1):
            if (model, prompt) in done:
                skipped += 1
                continue
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
            if status != 200:
                failed += 1
                row = {"model": routed, "prompt": prompt, "answer": "", "label": label, "error": f"HTTP {status}: {body[:200]}"}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"[{index}/{len(plan)}] {model} -> HTTP {status}")
                time.sleep(args.sleep)
                continue
            try:
                choice = json.loads(body)["choices"][0]
            except (json.JSONDecodeError, KeyError, IndexError):
                failed += 1
                print(f"[{index}/{len(plan)}] {model} -> не разобрал ответ")
                time.sleep(args.sleep)
                continue
            answer = (choice.get("message") or {}).get("content") or ""
            tokens = ((choice.get("logprobs") or {}).get("content") or [])
            feats = features(tokens)
            row = {
                "model": routed,
                "prompt": prompt,
                "answer": answer,
                "label": label,
                **({"error": "no logprobs in response"} if feats is None else feats),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            if feats is None:
                failed += 1
                print(f"[{index}/{len(plan)}] {routed} -> без logprobs")
            else:
                written += 1
                print(
                    f"[{index}/{len(plan)}] {routed} -> meanLp {feats['meanLp']:.3f} "
                    f"minLp {feats['minLp']:.3f} phi {feats['phi']:.3f} fracLow {feats['fracLow']:.2f}"
                )
            time.sleep(args.sleep)

    print(f"готово: {written} строк с признаками, {skipped} пропущено (--resume), {failed} без logprobs/ошибок")
    if written:
        print("дальше: проставь label 0/1 и запусти  python3 scripts/calibrate.py --fit --by-model --out weights.json "
              f"{args.out}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
