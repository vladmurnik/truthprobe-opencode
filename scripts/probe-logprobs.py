#!/usr/bin/env python3
"""TruthProbe E1 — проверка, отдаёт ли провайдер token logprobs.

Запуск (из любого места, нужен только python3, без зависимостей):

    python3 scripts/probe-logprobs.py \
        --base https://api.openai.com/v1 \
        --key  $OPENAI_API_KEY \
        --models gpt-4.1-mini,gpt-4o-mini

    # шлюз opencode (нужен токен из `opencode auth login`)
    python3 scripts/probe-logprobs.py \
        --base https://opencode.ai/inference/v1 \
        --key  "$OPENCODE_API_KEY" \
        --models deepseek-v4.1-flash-free,glm-4.7-free

Статусы:
  ok        — logprobs пришли и содержат альтернативы
  ignored   — ответ 200, но поля logprobs нет (провайдер молча вырезал)
  rejected  — 4xx с упоминанием logprobs (поле не поддерживается)
  auth      — 401/403: ключ не принят
  rate      — 429
  error     — прочее

Результат кэшируется в ~/.local/share/opencode/truthprobe/capabilities.json
(TTL 7 дней), чтобы ядро могло включать logprobs только для проверенных моделей.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

CACHE_PATH = os.path.expanduser("~/.local/share/opencode/truthprobe/capabilities.json")
TTL_SECONDS = 7 * 24 * 3600


def probe(base: str, key: str, model: str, timeout: float = 45.0) -> tuple[str, str, dict | None]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Answer with a single word: ping"}],
        "max_tokens": 1,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": 5,
        "stream": False,
    }
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:400]
        if error.code in (401, 403):
            return "auth", detail, None
        if error.code == 429:
            return "rate", detail, None
        if "logprob" in detail.lower() or "top_logprobs" in detail.lower():
            return "rejected", detail, None
        return "error", f"HTTP {error.code}: {detail}", None
    except Exception as error:  # noqa: BLE001 - сеть бывает любой
        return "error", str(error), None

    choices = body.get("choices") or []
    content = ((choices[0] if choices else {}).get("logprobs") or {}).get("content") or []
    if not content:
        return "ignored", "200 без поля logprobs", None
    first = content[0]
    alternatives = first.get("top_logprobs") or []
    detail = f"token={first.get('token')!r} logprob={first.get('logprob')} alternatives={len(alternatives)}"
    return "ok", detail, {
        "token": first.get("token"),
        "logprob": first.get("logprob"),
        "alternatives": [{"token": item.get("token"), "logprob": item.get("logprob")} for item in alternatives],
    }


def load_cache() -> dict:
    try:
        with open(CACHE_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2)


def markdown_table(base: str, rows: list[tuple[str, str, str]]) -> str:
    """Таблица для docs/MODEL-SUPPORT.md: одна строка на модель."""
    marks = {
        "ok": "✅ logprobs",
        "ignored": "❌ нет logprobs",
        "rejected": "❌ нет logprobs",
        "auth": "⚠️ ключ не принят",
        "rate": "⚠️ rate limit",
        "error": "⚠️ ошибка запроса",
    }
    lines = [
        f"<!-- сгенерировано scripts/probe-logprobs.py --md, endpoint {base} -->",
        "",
        "| модель | цифры уверенности | что показал зонд |",
        "| --- | --- | --- |",
    ]
    for model, status, detail in rows:
        mark = marks.get(status, f"⚠️ {status}")
        note = detail.replace("|", "\\|")
        lines.append(f"| `{model}` | {mark} | {note} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="TruthProbe: проверка поддержки logprobs")
    parser.add_argument("--base", required=True, help="base URL, например https://api.openai.com/v1")
    parser.add_argument("--key", default=os.environ.get("TRUTHPROBE_KEY", ""), help="API-ключ (или TRUTHPROBE_KEY)")
    parser.add_argument("--models", required=True, help="список моделей через запятую")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--md", action="store_true", help="напечатать таблицу Markdown для docs/MODEL-SUPPORT.md")
    args = parser.parse_args()

    if not args.key:
        print("Нет ключа: передайте --key или TRUTHPROBE_KEY", file=sys.stderr)
        return 2

    cache = {} if args.no_cache else load_cache()
    entry = cache.setdefault(args.base.rstrip("/"), {"probed": {}, "models": {}})
    failures = 0
    rows: list[tuple[str, str, str]] = []

    for model in [item.strip() for item in args.models.split(",") if item.strip()]:
        status, detail, sample = probe(args.base, args.key, model, args.timeout)
        if not args.md:
            print(f"{status:9} {model}: {detail}")
        rows.append((model, status, detail))
        if status in ("auth", "rate"):
            failures += 1
            break
        if status == "error":
            failures += 1
        if not args.no_cache:
            entry["models"][model] = {
                "status": status,
                "detail": detail,
                "sample": sample,
                "probed": int(time.time()),
                "ttl": TTL_SECONDS,
            }

    if args.md:
        print(markdown_table(args.base.rstrip("/"), rows))
        return 1 if failures else 0

    if not args.no_cache:
        save_cache(cache)
        print(f"\nкэш: {CACHE_PATH}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
