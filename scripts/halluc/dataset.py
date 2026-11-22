#!/usr/bin/env python3
"""Собирает один датасет из прогонов B и C: признаки из logprobs и текста ответа.

Вход:  rows_raw2.jsonl + rows_scored2.jsonl, rows_raw3.jsonl + rows_scored3.jsonl
Выход: dataset.jsonl  — одна строка на ответ, поле `y` = 1 для ложного.

Строки без logprobs выбрасываются: без токенов признаков нет. Это надо помнить —
в прогоне B так выпало 20 из 32 ложных ответов, выборка смещена.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import re

HERE = pathlib.Path(os.environ.get("HALLUC_DIR") or pathlib.Path(__file__).resolve().parent)
OUT = HERE / "dataset.jsonl"
HEDGES = re.compile(r"\b(probably|perhaps|likely|may|might|usually|generally|i think|it seems|appears)\b", re.I)
NEGATIONS = re.compile(r"\b(no|not|never|none|cannot|can't|doesn't|does not|isn't|wasn't|won't|without)\b", re.I)


def load_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def phi_of(token: dict) -> float | None:
    """1 − H/ln K по top_logprobs; None, если альтернатив меньше двух."""
    top = [item for item in (token.get("top") or token.get("top_logprobs") or [])
           if isinstance(item.get("logprob"), (int, float)) and math.isfinite(item["logprob"])]
    if len(top) < 2:
        return None
    probs = [math.exp(float(item["logprob"])) for item in top]
    total = sum(probs)
    if total <= 0:
        return None
    h = 0.0
    for prob in probs:
        q = prob / total
        if q > 0:
            h -= q * math.log(q)
    return max(0.0, min(1.0, 1.0 - h / math.log(len(top))))


def margin_of(token: dict) -> float | None:
    top = sorted((float(item["logprob"]) for item in (token.get("top") or token.get("top_logprobs") or [])
                  if isinstance(item.get("logprob"), (int, float))), reverse=True)
    if len(top) < 2:
        return None
    return top[0] - top[1]


def feats(answer: str, tokens: list[dict], scored: dict | None) -> dict | None:
    usable = [t for t in tokens if isinstance(t.get("logprob"), (int, float)) and math.isfinite(t["logprob"])]
    if not usable:
        return None
    lp = [float(t["logprob"]) for t in usable]
    phis = [p for p in (phi_of(t) for t in usable) if p is not None]
    margins = [m for m in (margin_of(t) for t in usable) if m is not None]
    chars = [c for c in answer if not c.isspace()]
    digits = sum(1 for c in chars if c.isdigit())
    letters = [c for c in chars if c.isalpha()]
    upper = sum(1 for c in letters if c.isupper())
    sentences = (scored or {}).get("sentenceScores")
    if sentences is None:
        value = (scored or {}).get("sentences")
        sentences = value if isinstance(value, list) else []
    else:
        flags = (scored or {}).get("sentenceFlags") or []
        sentences = [{"score": s, "flag": bool(f)} for s, f in zip(sentences, flags)]
    sent_scores = [float(s["score"]) for s in sentences if isinstance(s.get("score"), (int, float))]
    mean_lp = sum(lp) / len(lp)
    return {
        "n_tokens": len(usable),
        "mean_lp": mean_lp,
        "min_lp": min(lp),
        "max_lp": max(lp),
        "p10_lp": percentile(lp, 0.10),
        "p25_lp": percentile(lp, 0.25),
        "std_lp": (sum((x - mean_lp) ** 2 for x in lp) / len(lp)) ** 0.5,
        "frac_below_half": sum(1 for x in lp if x < math.log(0.5)) / len(lp),
        "geo": math.exp(mean_lp),
        "mean_phi": sum(phis) / len(phis) if phis else 0.0,
        "min_phi": min(phis) if phis else 0.0,
        "frac_phi_lt_05": sum(1 for p in phis if p < 0.5) / len(phis) if phis else 0.5,
        "mean_margin": sum(margins) / len(margins) if margins else 0.0,
        "min_margin": min(margins) if margins else 0.0,
        "first_lp": lp[0],
        "first_phi": phis[0] if phis else 0.0,
        "first_margin": margins[0] if margins else 0.0,
        "n_chars": len(answer),
        "digit_density": digits / len(chars) if chars else 0.0,
        "upper_ratio": upper / len(letters) if letters else 0.0,
        "newlines": answer.count("\n"),
        "n_sentences": len(sentences),
        "sent_min": min(sent_scores) if sent_scores else 0.0,
        "sent_mean": sum(sent_scores) / len(sent_scores) if sent_scores else 0.0,
        "sent_frac_low": sum(1 for s in sent_scores if s < 0.55) / len(sent_scores) if sent_scores else 0.0,
        "sent_flagged": sum(1 for s in sentences if s.get("flag")),
        "hedge_count": len(HEDGES.findall(answer)),
        "negation_count": len(NEGATIONS.findall(answer)),
        "number_count": len(re.findall(r"\b\d[\d,. ]*\b", answer)),
        "ends_period": 1.0 if answer.strip().endswith((".", "!", "?")) else 0.0,
    }


def main() -> None:
    pairs = [(HERE / "rows_raw2.jsonl", HERE / "rows_scored2.jsonl", "B"),
             (HERE / "rows_raw3.jsonl", HERE / "rows_scored3.jsonl", "C")]
    out = []
    for raw_path, scored_path, run in pairs:
        raw = load_jsonl(raw_path)
        scored = {(r.get("model"), r.get("qid")): r for r in load_jsonl(scored_path)}
        kept = dropped = 0
        for row in raw:
            if row.get("error"):
                continue
            verdict = row.get("verdict") or row.get("label") or ("correct" if row.get("correct") else "wrong")
            if verdict in ("refusal",):
                continue
            key = (row.get("model"), row.get("qid"))
            scored_row = scored.get(key) or {}
            features = feats(row.get("answer", ""), row.get("tokens") or [], scored_row)
            if features is None:
                dropped += 1
                continue
            item = {
                "run": run,
                "model": row.get("model"),
                "qid": row.get("qid"),
                "category": row.get("category"),
                "verdict": verdict,
                "y": 0 if verdict in ("correct", "correct_qualified") else 1,
                "answer": (row.get("answer") or "")[:400],
                **features,
            }
            out.append(item)
            kept += 1
        false_dropped = sum(1 for r in raw
                            if not r.get("error") and (r.get("verdict") or "") == "wrong" and
                            feats(r.get("answer", ""), r.get("tokens") or [], scored.get((r.get("model"), r.get("qid"))) or {}) is None)
        print(f"{run}: оставлено {kept}, выброшено без logprobs {dropped} (из них ложных {false_dropped})")

    with OUT.open("w", encoding="utf-8") as handle:
        for item in out:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    positives = sum(1 for i in out if i["y"] == 1)
    print(f"\nвсего {len(out)} строк, ложных {positives}, верных {len(out) - positives}")
    print(f"уникальных вопросов: {len({i['qid'] for i in out})}, моделей: {len({i['model'] for i in out})}")
    by_cat: dict[str, list[int]] = {}
    for item in out:
        bucket = by_cat.setdefault(item["category"], [0, 0])
        bucket[1] += 1
        bucket[0] += item["y"]
    print("по категориям (ложных/всего):", {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_cat.items())})
    print("записано:", OUT)


if __name__ == "__main__":
    main()
