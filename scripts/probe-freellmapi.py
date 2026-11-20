#!/usr/bin/env python3
"""Проверяет, отдаёт ли FreeLLMAPI logprobs — то, без чего TruthProbe слепая.

FreeLLMAPI (https://github.com/tashfeenahmed/freellmapi) — один OpenAI-совместимый
эндпоинт поверх ~87 бесплатных провайдеров. Для TruthProbe он ценен тем, что даёт
много разных моделей через один baseURL: можно собрать размеченный набор
(«правда/ложь» + признаки скорера) по десяткам моделей и обучить отдельные веса
на каждую (`calibrate.py --fit --by-model`).

Скрипт ничего не знает про внутренности роутера: он просто проверяет контракт.

    python3 scripts/probe-freellmapi.py --key freellmapi-xxxx
    python3 scripts/probe-freellmapi.py --url http://127.0.0.1:3001/v1 --model auto:fast
    python3 scripts/probe-freellmapi.py --key ... --jsonl probe.jsonl

Ключ (unified key) берётся на странице Keys в локальном дашборде
http://127.0.0.1:3001 после добавления ключей провайдеров.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROMPT = "What is the capital of France? Answer in one sentence."


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
    parser.add_argument("--jsonl", help="куда дописать строку замера для калибровки")
    args = parser.parse_args()

    if not args.key:
        print("нужен unified key: --key freellmapi-... (или FREELLMAPI_KEY)", file=sys.stderr)
        return 2

    base = args.url.rstrip("/")

    status, _, body = request(f"{base}/models", args.key)
    models: list[str] = []
    if status == 200:
        try:
            models = [item.get("id", "") for item in json.loads(body).get("data", [])]
        except json.JSONDecodeError:
            pass
    print(f"GET /models -> {status}, моделей: {len(models)}")
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
        print("  ответ не разобрался: " + body[:300])
        return 1

    text = (choice.get("message") or {}).get("content") or ""
    tokens = ((choice.get("logprobs") or {}).get("content") or [])
    print(f"  ответ: {text[:160]!r}")
    print(f"  токенов с logprob: {len(tokens)}")

    if not tokens:
        print("  ВЕРДИКТ: logprobs НЕ пришли — TruthProbe покажет 'unavailable' для этой модели.")
        return 1

    lps = [float(token["logprob"]) for token in tokens if token.get("logprob") is not None]
    mean_lp = sum(lps) / len(lps)
    min_lp = min(lps)
    print(f"  meanLp {mean_lp:.4f}, minLp {min_lp:.4f}, пример: " + ", ".join(
        f"{token['token']!r}={token['logprob']:.3f}" for token in tokens[:5]
    ))
    print("  ВЕРДИКТ: logprobs доходят — модель годится для сбора калибровочных данных.")

    if args.jsonl:
        row = {
            "model": routed if routed != "—" else args.model,
            "prompt": args.prompt,
            "answer": text,
            "meanLp": round(mean_lp, 6),
            "minLp": round(min_lp, 6),
            "phi": round(min_lp / mean_lp if mean_lp else 0.0, 6),
            "fracLow": round(sum(1 for lp in lps if lp < -1.0) / len(lps), 6),
            "label": None,
        }
        with open(args.jsonl, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  строка без метки дописана в {args.jsonl} (label надо проставить вручную)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
