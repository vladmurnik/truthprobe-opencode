#!/usr/bin/env python3
"""Собирает калибровочные строки через любой OpenAI-совместимый эндпоинт.

Один и тот же скрипт работает и с FreeLLMAPI (много моделей за одним baseURL),
и с локальным шлюзом, и с обычным OpenAI-совместимым сервером. На выходе —
JSONL ровно в том виде, который ест `scripts/calibrate.py --fit --by-model`:

    {"model": "freepi/particle", "prompt": "...", "answer": "...",
     "meanLp": -0.0573, "minLp": -0.493, "phi": 0.88, "fracLow": 0.05,
     "label": 1, "tokens": 22}

Признаки считаются **точно так же, как в рантайме** (`packages/core/src/truthprobe/score.ts`):

  meanLp  = среднее logprob по содержательным токенам ответа
  minLp   = худший logprob
  phi     = 1 - нормированная энтропия по top_logprobs ПЕРВОГО токена
  fracLow = доля токенов с exp(logprob) < 0.5, то есть logprob < ln 0.5

Важная деталь про «содержательные токены»: у reasoning-моделей поток logprobs
начинается с рассуждения (`<​/think>` и текст до него), а рантайм считает только
токены, попавшие в видимый ответ. Поэтому `collect.py` отбрасывает префикс до
начала текста ответа — иначе признаки и веса жили бы в разных мирах.

Разметка. Есть три способа:
  1. `--auto-label data/qa-bank.jsonl` — банк вопросов с эталонными ответами
     (`{"prompt": ..., "expect": ["canberra"]}`). Совпало — 1, ответила другим — 0,
     пусто/отказ — строка без метки (в обучение не идёт).
  2. `--prompts rows.jsonl`, где у строки уже есть `label`.
  3. Вручную: собрать без метки и проставить 0/1 позже.

Примеры:

    # много моделей, авторазметка по банку вопросов, 8 потоков
    python3 scripts/collect.py --url http://127.0.0.1:3001/v1 --key $FREELLMAPI_KEY \\
        --models auto,auto:fast,groq/llama-3.3-70b --prompts data/qa-bank.jsonl \\
        --auto-label data/qa-bank.jsonl --out data/rows.jsonl --resume --workers 8

    # один промпт для проверки контракта
    python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --key x \\
        --model freepi/particle --prompt "Назови столицу Франции" --out data/rows.jsonl

    # только план, без сети
    python3 scripts/collect.py --prompts data/qa-bank.jsonl --models auto --dry-run

    # несколько сэмплов на пару (модель, промпт): при temperature > 0 разные ответы
    python3 scripts/collect.py --url http://127.0.0.1:8790/v1 --key x \\
        --models particle,deepseek-v4.1-flash --prompts data/qa-hard-bank.jsonl \\
        --auto-label data/qa-hard-bank.jsonl --temperature 0.8 --samples 4 \\
        --workers 4 --out data/rows-hard.jsonl --resume

`--resume` пропускает пары (модель, промпт) — а при `--samples N` тройки
(модель, промпт, сэмпл) — которые уже лежат в `--out`. Строки без поля
`sample` считаются сэмплом 0, поэтому старые файлы остаются совместимыми.
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

FRAC_LOW_CUTOFF = math.log(0.5)  # ровно тот порог, что в score.ts


def clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    return min(1.0, max(0.0, x))


def phi(token: dict, top_k: int = 20) -> float:
    """Уверенность по top_logprobs: 1 − нормированная энтропия, как `phi` в рантайме."""
    top = [
        item
        for item in (token.get("top_logprobs") or [])
        if isinstance(item.get("logprob"), (int, float)) and math.isfinite(item["logprob"])
    ]
    if len(top) < 2:
        # Вырожденная ветка рантайма — это exp(logprob), а не 1 − exp(logprob):
        # иначе тот же токен получает обратный знак, и вес `meanPhi` работает против ответа.
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
    # φ — уверенность, как в рантайме (`packages/core/src/truthprobe/score.ts`): 1 − H/ln K.
    # Энтропия здесь давала бы обратный знак относительно живого скорера, и обученный
    # вес `meanPhi` работал бы против ответа.
    return clamp01(1.0 - h / math.log(k) if k > 1 else 1.0)


def answer_tokens(tokens: list[dict], answer: str) -> list[dict]:
    """Оставляет только токены, из которых состоит видимый ответ.

    Стрим начинается с рассуждения; рантайм скорит лишь то, что попало в текст
    ответа. Если ответ пуст или не найден в конкатенации токенов, возвращаем
    весь поток — лучше честно посчитать по нему, чем потерять строку.
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
        # Маркер полярности: `phi` здесь — уверенность (1 − энтропия), как в рантайме.
        # В наборах до 22.11.2026 поля не было и `phi` была энтропией; `calibrate.py`
        # инвертирует такие строки при загрузке. Без маркера он инвертировал бы и новые.
        "phiDef": "confidence",
        "fracLow": round(sum(1 for lp in lps if lp < FRAC_LOW_CUTOFF) / len(lps), 6),
        # Тот же признак, что считает рантайм (`digitDensity` в score.ts): только ASCII-цифры
        # и длина в UTF-16 code units (как `String.prototype.length`), иначе train и serve
        # расходятся на арабских цифрах и эмодзи.
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
                    print(f"{path}:{n}: не JSON, строка пропущена", file=sys.stderr)
                    continue
                prompt = item.get("prompt")
                if not prompt:
                    continue
                rows.append({"prompt": prompt, "label": item.get("label")})
            else:
                rows.append({"prompt": line, "label": None})
    return rows


def read_bank(path: str) -> dict[str, list[str]]:
    """Банк вопросов: prompt -> список принимаемых ответов (в нижнем регистре)."""
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


WORD = re.compile(r"[a-zа-я0-9]+")


def matches(answer: str, expect: list[str]) -> bool:
    """Короткие эталоны сравниваем по границам слова, длинные — по вхождению."""
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
        return None  # отказ или пустой ответ: метки нет, в обучение не идёт
    return 1 if matches(answer, expect) else 0


def seen_pairs(path: str) -> set[tuple[str, str, int]]:
    """Уже собранные тройки (модель, промпт, сэмпл).

    Строки без поля `sample` — это сэмпл 0: старые наборы писались до
    появления `--samples`, и после `--resume` их не нужно перезапрашивать.
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
    parser.add_argument("--model", action="append", default=[], help="модель; можно повторять")
    parser.add_argument("--models", help="список моделей через запятую (альтернатива --model)")
    parser.add_argument("--all-models", action="store_true", help="взять весь каталог из GET /v1/models")
    parser.add_argument("--prompt", action="append", default=[], help="промпт; можно повторять")
    parser.add_argument("--prompts", help="файл промптов: txt (по строке) или JSONL {prompt,label}")
    parser.add_argument("--auto-label", metavar="BANK", help="JSONL с expect-ответами: проставить label 0/1 автоматически")
    parser.add_argument("--out", default="truthprobe-rows.jsonl")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-logprobs", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.3, help="пауза между запросами, сек (на поток)")
    parser.add_argument("--samples", type=int, default=1, help="сколько раз запросить каждую пару (модель, промпт)")
    parser.add_argument(
        "--provider",
        default="",
        help="префикс для поля model в строках (например freepi): в рантайме ключ весов — providerID/modelID",
    )
    parser.add_argument("--workers", type=int, default=1, help="сколько запросов держать в полёте")
    parser.add_argument("--limit", type=int, help="не больше N запросов за запуск")
    parser.add_argument("--resume", action="store_true", help="пропускать уже собранные (модель, промпт, сэмпл)")
    parser.add_argument("--dry-run", action="store_true", help="только показать план, без сети")
    args = parser.parse_args()

    models = list(args.model)
    if args.models:
        models.extend(item.strip() for item in args.models.split(",") if item.strip())
    if args.all_models:
        status, _, body = request(f"{args.url.rstrip('/')}/models", args.key)
        if status != 200:
            print(f"каталог моделей недоступен: HTTP {status}", file=sys.stderr)
            return 2
        try:
            models.extend(row["id"] for row in json.loads(body).get("data", []) if row.get("id"))
        except (json.JSONDecodeError, KeyError, TypeError):
            print("не разобрал каталог моделей", file=sys.stderr)
            return 2
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

    bank = read_bank(args.auto_label) if args.auto_label else {}

    samples = max(1, args.samples)
    plan = [(m, p["prompt"], p["label"], s) for m in models for p in prompts for s in range(samples)]
    print(
        f"план: {len(models)} модел(ей) x {len(prompts)} промпт(ов) x {samples} сэмпл(ов) "
        f"= {len(plan)} запросов -> {args.out}"
    )

    if args.dry_run:
        for model, prompt, label, sample in plan[:20]:
            print(f"  {model} sample={sample} | label={label} | {prompt[:70]}")
        if len(plan) > 20:
            print(f"  ... ещё {len(plan) - 20}")
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
        # Ключ весов в рантайме — `providerID/modelID`, поэтому запись в строке
        # должна быть в том же виде, иначе per-model калибровка не найдёт модель.
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
                print(f"[{index}/{len(plan)}] {model} sample={sample} -> не разобрал ответ")
                time.sleep(args.sleep)
                return
            answer = (choice.get("message") or {}).get("content") or ""
            tokens = ((choice.get("logprobs") or {}).get("content") or [])
            feats = features(tokens, answer, args.top_logprobs)
            # Обрезанный по max_tokens ответ — это артефакт нашего лимита, а не ошибка
            # модели. Такой ответ не должен становиться негативом, иначе веса учатся
            # на собственной жадности.
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
                print(f"[{index}/{len(plan)}] {routed} sample={sample} -> без logprobs")
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
        f"готово: {counters['written']} строк с признаками, {counters['skipped']} пропущено (--resume), "
        f"{counters['failed']} без logprobs/ошибок"
    )
    if counters["written"]:
        print(
            "дальше: python3 scripts/calibrate.py --fit --by-model --out weights.json "
            f"{args.out}   (строки без label в обучение не попадут)"
        )
    return 0 if counters["written"] else 1


if __name__ == "__main__":
    sys.exit(main())
