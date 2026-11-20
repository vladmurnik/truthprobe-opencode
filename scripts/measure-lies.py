#!/usr/bin/env python3
"""Измеряет, видит ли TruthProbe нарочно неверный ответ.

Собрать настоящие галлюцинации не удалось: 1440 запросов к четырём моделям шлюза
не дали ни одного неверного ответа. Поэтому единственная ложь, в которой мы
уверены на 100%, — та, которую мы сами заказали: `make-liar-bank.py` просит
модель ответить неправильно, и ответ всё равно сгенерирован моделью, со своими
настоящими logprobs.

Что скрипт считает:

  geometric   встроенная формула рантайма (exp(meanLp), см. §14 VALIDATION);
              никакого обучения, ровно то, что сейчас работает у пользователя.
  fitted      логистическая регрессия на тех же четырёх признаках, обученная
              с честной кросс-валидацией (out-of-fold): веса не видят те строки,
              на которых их проверяют.
  variants    фиксированные формулы без обучения (`--variants`) — то сравнение,
              из которого выбрана exp(meanLp).

    python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl
    python3 scripts/measure-lies.py data/rows-lie-vs-truth.jsonl --json

ВАЖНАЯ ОГОВОРКА. Нарочная ложь — не то же самое, что самопроизвольная
галлюцинация: модель, которой велели соврать, «знает» правду и её первый токен
зависит от странной инструкции, а не от факта. Числа ниже отвечают на вопрос
«видит ли скорер, что модель соврала по заказу», и ничего не говорят о том,
поймает ли он уверенную выдумку в обычном разговоре. Это разные вещи, и второе
по-прежнему не измерено.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibrate  # noqa: E402
import evaluate  # noqa: E402

FOLDS = 5
SEED = 7


def load(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for n, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"{path}:{n}: не JSON, строка пропущена", file=sys.stderr)
                continue
            label = row.get("label")
            if label is None and row.get("condition"):
                label = 1 if row["condition"] == "truthful" else 0
            if label is None or "meanLp" not in row:
                continue
            row["label"] = bool(int(label))
            rows.append(row)
    return rows


def geometric(row: dict) -> float:
    """Ровно формула geometricScorer из packages/core/src/truthprobe/scorer.ts: exp(meanLp)."""
    import math

    mean_lp = float(row["meanLp"])
    return min(1.0, max(0.0, math.exp(mean_lp)))


def variants(row: dict) -> dict[str, float]:
    """Фиксированные формулы из §14 VALIDATION — чтобы сравнение воспроизводилось из репозитория."""
    import math

    geo = min(1.0, max(0.0, math.exp(float(row["meanLp"]))))
    worst = min(1.0, max(0.0, math.exp(float(row["minLp"]))))
    phi = min(1.0, max(0.0, float(row.get("phi") or 0.0)))
    frac_low = min(1.0, max(0.0, float(row.get("fracLow") or 0.0)))
    return {
        "old 0.4geo+0.3worst+0.3phi": min(1.0, 0.4 * geo + 0.3 * worst + 0.3 * phi),
        "geo only": geo,
        "worst only": worst,
        "phi only": phi,
        "geo*(1-fracLow)": min(1.0, geo * (1.0 - frac_low)),
    }


def out_of_fold(rows: list[dict]) -> tuple[list[tuple[float, bool]], float | None]:
    data = rows[:]
    random.seed(SEED)
    random.shuffle(data)
    folds = [data[i::FOLDS] for i in range(FOLDS)]
    pairs: list[tuple[float, bool]] = []
    for i in range(FOLDS):
        train = [row for j, fold in enumerate(folds) if j != i for row in fold]
        if not train:
            continue
        weights = calibrate.fit(train)
        for row in folds[i]:
            pairs.append((calibrate.predict(weights, row), row["label"]))
    return pairs, None


def report(name: str, pairs: list[tuple[float, bool]]) -> dict:
    positives = sum(1 for _, label in pairs if label)
    negatives = len(pairs) - positives
    auroc = evaluate.auroc(pairs)
    ece = evaluate.ece(pairs, 10)
    brier = evaluate.brier(pairs)
    return {
        "mode": name,
        "rows": len(pairs),
        "positives": positives,
        "negatives": negatives,
        "auroc": auroc,
        "ece": ece,
        "brier": brier,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rows", help="JSONL: строки с label 0/1 и признаками meanLp/minLp/phi/fracLow")
    parser.add_argument("--json", action="store_true", help="печать машинного отчёта")
    parser.add_argument("--variants", action="store_true", help="сравнить фиксированные формулы из §14 VALIDATION")
    args = parser.parse_args()

    rows = load(args.rows)
    if not rows:
        print("нет пригодных строк", file=sys.stderr)
        return 2

    if args.variants:
        names = list(variants(rows[0]))
        print(f"== {args.rows}: {len(rows)} строк, формул {len(names)} (без обучения)")
        print(f"{'формула':30s} {'AUROC':>7s} {'ECE':>6s} {'Brier':>6s}")
        for name in names:
            entry = report(name, [(variants(row)[name], row["label"]) for row in rows])
            auroc = "n/a" if entry["auroc"] is None else f"{entry['auroc']:.3f}"
            print(f"{name:30s} {auroc:>7s} {entry['ece']:6.3f} {entry['brier']:6.3f}")
        return 0

    builtin = report("geometric", [(geometric(row), row["label"]) for row in rows])
    pairs, _ = out_of_fold(rows)
    fitted = report("fitted (out-of-fold)", pairs)

    per_model: list[dict] = []
    for model in sorted({row.get("model") or "?" for row in rows}):
        sub = [row for row in rows if (row.get("model") or "?") == model]
        pos = sum(1 for row in sub if row["label"])
        neg = len(sub) - pos
        if pos < 10 or neg < 5:
            per_model.append({"model": model, "rows": len(sub), "positives": pos, "negatives": neg, "auroc": None})
            continue
        sub_pairs, _ = out_of_fold(sub)
        entry = report("fitted", sub_pairs)
        entry["model"] = model
        entry["positives"] = pos
        entry["negatives"] = neg
        per_model.append(entry)

    if args.json:
        print(json.dumps({"builtin": builtin, "fitted": fitted, "per_model": per_model}, ensure_ascii=False, indent=2))
        return 0

    def fmt(value: float | None, digits: int = 3) -> str:
        return "n/a" if value is None else f"{value:.{digits}f}"

    print(f"== {args.rows}: {len(rows)} строк")
    print(f"{'mode':22s} {'rows':>5s} {'pos':>5s} {'neg':>5s} {'AUROC':>7s} {'ECE':>6s} {'Brier':>6s}")
    for entry in (builtin, fitted):
        print(
            f"{entry['mode']:22s} {entry['rows']:5d} {entry['positives']:5d} {entry['negatives']:5d} "
            f"{fmt(entry['auroc']):>7s} {fmt(entry['ece']):>6s} {fmt(entry['brier']):>6s}"
        )
    print("\nпо моделям (fitted, out-of-fold):")
    for entry in per_model:
        if entry["auroc"] is None:
            print(f"  {entry['model']:26s} n={entry['rows']:3d} pos={entry['positives']:3d} neg={entry['negatives']:3d} — мало негативов")
        else:
            print(
                f"  {entry['model']:26s} n={entry['rows']:3d} pos={entry['positives']:3d} neg={entry['negatives']:3d} "
                f"AUROC {fmt(entry['auroc'])} ECE {fmt(entry['ece'])}"
            )
    print("\nAUROC ниже 0.5 означает, что скорер ставит ложным ответам БОЛЬШУЮ уверенность, чем правдивым.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
