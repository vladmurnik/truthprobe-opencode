#!/usr/bin/env python3
"""AUROC и ECE для сигналов TruthProbe на размеченных предложениях.

Набор — JSONL, по одному предложению на строку:

    {"score": 0.71, "phi": 0.96, "meanLp": -0.87, "minLp": -1.43, "label": true}

`label` — правда ли утверждение (ставит человек по источникам). Строки с меткой
`null`/`"unverifiable"` пропускаются, но их количество печатается: молча их
выбрасывать нельзя, иначе метрика смещается в сторону проверяемых фактов.

    python3 scripts/calibrate.py labeled.jsonl
    python3 scripts/calibrate.py --demo

`--demo` считает синтетику. Это проверка самого скрипта, а не измерение модели.
"""

from __future__ import annotations

import argparse
import json
import random
import sys

COLUMNS = ("score", "phi", "meanLp", "minLp")


def load(path: str) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(row.get("label"), bool):
                skipped += 1
                continue
            rows.append(row)
    return rows, skipped


def demo(n: int = 400, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        truth = rng.random() < 0.6
        base = rng.gauss(0.78 if truth else 0.52, 0.14)
        base = min(max(base, 0.01), 0.99)
        rows.append(
            {
                "score": round(base, 4),
                "phi": round(min(max(rng.gauss(0.9 if truth else 0.7, 0.1), 0.01), 0.99), 4),
                "meanLp": round(rng.gauss(-0.7 if truth else -1.4, 0.3), 4),
                "minLp": round(rng.gauss(-1.2 if truth else -2.6, 0.5), 4),
                "label": truth,
            }
        )
    return rows


def auroc(pairs: list[tuple[float, bool]]) -> float:
    """Вероятность, что верное предложение получило больший сигнал, чем неверное."""
    positives = [value for value, label in pairs if label]
    negatives = [value for value, label in pairs if not label]
    if not positives or not negatives:
        return float("nan")
    total = 0.0
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                total += 1.0
            elif pos == neg:
                total += 0.5
    return total / (len(positives) * len(negatives))


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    if not pairs:
        return float("nan")
    total = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [(min(max(v, 0.0), 1.0), label) for v, label in pairs if low <= min(max(v, 0.0), 1.0) < high or (index == bins - 1 and v >= 1.0)]
        if not bucket:
            continue
        confidence = sum(v for v, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, label in bucket if label) / len(bucket)
        total += abs(confidence - accuracy) * len(bucket) / len(pairs)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="JSONL с размеченными предложениями")
    parser.add_argument("--demo", action="store_true", help="считать синтетику")
    args = parser.parse_args()

    if args.demo:
        rows, skipped = demo(), 0
        print("== demo: синтетика, это НЕ измерение модели ==")
    elif args.path:
        rows, skipped = load(args.path)
        print(f"== {args.path}: {len(rows)} размеченных строк, пропущено {skipped}")
    else:
        parser.error("нужен путь к JSONL или --demo")

    positives = sum(1 for row in rows if row["label"])
    print(f"правда: {positives}, ложь: {len(rows) - positives}")

    print(f"{'signal':10s} {'AUROC':>7s} {'ECE':>7s}")
    for column in COLUMNS:
        pairs = [(float(row[column]), row["label"]) for row in rows if row.get(column) is not None]
        if not pairs:
            continue
        # Все четыре сигнала растут вместе с уверенностью: score/phi — прямо,
        # meanLp/minLp — как logprob (ближе к нулю значит увереннее). Поэтому
        # никаких инверсий: иначе AUROC показывает 1-AUROC.
        print(f"{column:10s} {auroc(pairs):7.3f} {ece(pairs, bins=10):7.3f}")

    print("\nВеса смеси подбираются логистической регрессией на кросс-валидации, а порог — из")
    print("precision/recall под выбранную политику. Пока этого не сделано, проценты в UI —")
    print("не калиброванная вероятность (см. docs/CALIBRATION.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
