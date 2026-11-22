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
import math
import random
import sys

COLUMNS = ("score", "phi", "meanLp", "minLp")


def truthy_label(value):
    """label из JSON: true/false, но также 1/0 — так их пишет `collect.py`."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return None


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
            label = truthy_label(row.get("label"))
            if label is None:
                skipped += 1
                continue
            row["label"] = label
            # φ в рантайме (`score.ts.phi`) — уверенность: 1 − H/ln K. Наборы, собранные
            # до исправления `collect.py`, хранят энтропию H/ln K; приводим к определению
            # рантайма, иначе обученный вес `meanPhi` получает обратный знак и на живых
            # ответах работает против уверенности.
            if row.get("phiDef") != "confidence" and "phi" in row:
                row["phi"] = 1.0 - float(row["phi"] or 0.0)
                row["phiDef"] = "confidence"
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


def fit(rows: list[dict], epochs: int = 4000, lr: float = 0.6, l2: float = 1e-3) -> dict:
    """Логистическая регрессия на признаках скорера (bias, meanLp, minLp, phi, fracLow, digitDensity)."""
    xs = [
        [1.0, float(row["meanLp"]), float(row["minLp"]), float(row["phi"]), float(row.get("fracLow") or 0.0),
         float(row.get("digitDensity") or 0.0)]
        for row in rows
    ]
    ys = [1.0 if row["label"] else 0.0 for row in rows]
    w = [0.0] * 6
    # Баланс классов: иначе редкая ложь тонет в общей точности.
    pos = sum(ys) or 1.0
    neg = (len(ys) - sum(ys)) or 1.0
    weights_per_row = [0.5 * len(ys) / pos if y else 0.5 * len(ys) / neg for y in ys]
    for _ in range(epochs):
        grad = [0.0] * 6
        for x, y, wgt in zip(xs, ys, weights_per_row):
            z = sum(wi * xi for wi, xi in zip(w, x))
            p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            err = (p - y) * wgt
            for j in range(6):
                grad[j] += err * x[j]
        norm = len(xs)
        for j in range(6):
            penalty = l2 * w[j] if j else 0.0
            w[j] -= lr * (grad[j] / norm + penalty)
    return {
        "version": 1,
        "features": ["bias", "meanLp", "minLp", "meanPhi", "fracLow", "digitDensity"],
        "weights": {
            "bias": round(w[0], 4),
            "meanLp": round(w[1], 4),
            "minLp": round(w[2], 4),
            "meanPhi": round(w[3], 4),
            "fracLow": round(w[4], 4),
            "digitDensity": round(w[5], 4),
        },
    }


def predict(weights: dict, row: dict) -> float:
    w = weights["weights"]
    z = (
        w["bias"]
        + w["meanLp"] * float(row["meanLp"])
        + w["minLp"] * float(row["minLp"])
        + w["meanPhi"] * float(row["phi"])
        + w["fracLow"] * float(row.get("fracLow") or 0.0)
        + w.get("digitDensity", 0.0) * float(row.get("digitDensity") or 0.0)
    )
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def group_key(row: dict) -> tuple[str, str]:
    """Группа переноса: модель + вопрос. Ответы внутри группы — повторы одного факта."""
    return (str(row.get("model") or ""), str(row.get("prompt") or row.get("source") or ""))


def fold_assignment(rows: list[dict], folds: int = 5, seed: int = 11) -> list[int]:
    """Номер фолда на каждую строку, одинаковый внутри группы `group_key`.

    Резать по строкам нельзя: один и тот же ответ встречается в наборе несколько раз,
    а вопрос переиспользуется всеми моделями. При построчном делении 88% теста
    оказывается в обучении побайтово, и OOF измеряет запоминание, а не перенос.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(group_key(row), []).append(index)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    assignment = [0] * len(rows)
    for position, key in enumerate(keys):
        for index in groups[key]:
            assignment[index] = position % folds
    return assignment


def cross_validate(rows: list[dict], folds: int = 5) -> tuple[float, float]:
    """AUROC и ECE по out-of-fold предсказаниям с групповым делением.

    Фолды режутся по `(model, prompt)`: повторный ответ на тот же вопрос не попадает
    в обучение, иначе метрика льстит себе.
    """
    size = len(rows)
    if size < folds * 2:
        return float("nan"), float("nan")
    assignment = fold_assignment(rows, folds)
    oof: list[float] = [0.0] * size
    for fold in range(folds):
        test = [i for i in range(size) if assignment[i] == fold]
        train = [rows[i] for i in range(size) if assignment[i] != fold]
        if not test or not train:
            continue
        weights = fit(train)
        for i in test:
            oof[i] = predict(weights, rows[i])
    pairs = [(oof[i], rows[i]["label"]) for i in range(size)]
    return auroc(pairs), ece(pairs)


def fit_by_model(rows: list[dict], min_rows: int = 20, min_negatives: int = 30) -> dict:
    """Обучает отдельные веса на каждую модель (поле "model" в JSONL).

    Смысл: у моделей разная форма распределения логвероятностей, поэтому один
    общий sigmoid систематически смещён для части моделей. Группам, где мало строк
    или меньше `min_negatives` примеров любого класса, веса не выдаются — на таком
    объёме коэффициенты уходят в случайный знак, и уверенность инвертируется.
    """
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row.get("model") or "unknown")
        groups.setdefault(key, []).append(row)

    bundle: dict = {
        "version": 1,
        "features": ["bias", "meanLp", "minLp", "meanPhi", "fracLow", "digitDensity"],
        "global": fit(rows)["weights"],
        "models": {},
    }
    for name, group in sorted(groups.items()):
        positives = sum(1 for row in group if row["label"])
        if len(group) < min_rows:
            bundle["models"][name] = {
                "rows": len(group),
                "positives": positives,
                "weights": None,
                "note": f"меньше {min_rows} строк — используется global",
            }
            continue
        if positives == 0 or positives == len(group):
            bundle["models"][name] = {
                "rows": len(group),
                "positives": positives,
                "weights": None,
                "note": "в группе один класс — веса не обучаются, используется global",
            }
            continue
        negatives = len(group) - positives
        if negatives < min_negatives or positives < min_negatives:
            bundle["models"][name] = {
                "rows": len(group),
                "positives": positives,
                "negatives": negatives,
                "weights": None,
                "note": f"меньше {min_negatives} примеров класса — используется global",
            }
            continue
        cv_auroc, cv_ece = cross_validate(group)
        bundle["models"][name] = {
            "rows": len(group),
            "positives": positives,
            "auroc": round(cv_auroc, 4),
            "ece": round(cv_ece, 4),
            "weights": fit(group)["weights"],
        }
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="JSONL с размеченными предложениями")
    parser.add_argument("--demo", action="store_true", help="считать синтетику")
    parser.add_argument("--fit", action="store_true", help="обучить веса linear-скорера")
    parser.add_argument("--by-model", action="store_true", help="отдельные веса на каждую модель из поля model")
    parser.add_argument("--out", help="куда записать веса (по умолчанию stdout)")
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

    if args.fit:
        if len(rows) < 20:
            print("\nслишком мало строк для обучения весов (нужно >= 20)")
            return 1
        if positives == 0 or positives == len(rows):
            # Один класс: sigmoid выучит константу, AUROC/ECE станут бессмысленными,
            # а веса — вредными. Лучше честно отказаться, чем записать такой файл.
            print(
                f"\nотказ: в наборе только один класс (правда {positives}, ложь {len(rows) - positives}).\n"
                "Для калибровки нужны ОБЕ метки: 0 — модель ошиблась/выдумала, 1 — ответила верно.\n"
                "Возьмите вопросы, на которых часть моделей ошибается, или добавьте более слабые модели.",
                file=sys.stderr,
            )
            return 2
        cv_auroc, cv_ece = cross_validate(rows)
        print(f"\nlinear-скорер, out-of-fold ({len(rows)} строк, 5 фолдов):")
        print(f"  AUROC {cv_auroc:.3f}   ECE {cv_ece:.3f}")

        if args.by_model:
            bundle = fit_by_model(rows)
            print("\nпо моделям (out-of-fold там, где строк >= 20):")
            print(f"{'model':34s} {'rows':>5s} {'AUROC':>7s} {'ECE':>7s}")
            for name, entry in bundle["models"].items():
                auroc_text = f"{entry['auroc']:.3f}" if entry.get("auroc") is not None else "   —  "
                ece_text = f"{entry['ece']:.3f}" if entry.get("ece") is not None else "  —  "
                print(f"{name[:34]:34s} {entry['rows']:5d} {auroc_text:>7s} {ece_text:>7s}")
            text = json.dumps(bundle, ensure_ascii=False, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text + "\n")
                print(f"\nбандл весов записан: {args.out}")
                print(f"включить: TRUTHPROBE_SCORER=linear:{args.out}")
                print("рантайм берёт models[providerID/modelID], а при его отсутствии — global")
            else:
                print("\nбандл весов:")
                print(text)
            return 0

        weights = fit(rows)
        text = json.dumps(weights, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
            print(f"\nвеса записаны: {args.out}")
            print(f"включить: TRUTHPROBE_SCORER=linear:{args.out}")
        else:
            print("\nвеса (положить в JSON и указать TRUTHPROBE_SCORER=linear:<путь>):")
            print(text)
        return 0

    print("\nВеса сменного скорера обучаются на этом же наборе:")
    print("  python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json")
    print("Пока они не обучены, проценты в UI — не калиброванная вероятность (см. docs/CALIBRATION.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
