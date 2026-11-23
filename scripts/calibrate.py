#!/usr/bin/env python3
"""AUROC and ECE for the TruthProbe signals on labeled sentences.

The dataset is JSONL, one sentence per line:

    {"score": 0.71, "phi": 0.96, "phiDef": "confidence", "meanLp": -0.87, "minLp": -1.43, "label": true}

`label` says whether the claim is true (a human sets it from sources). Rows with the label
`null`/`"unverifiable"` are skipped, but their count is printed: throwing them away
silently is not allowed, otherwise the metric skews towards verifiable facts.

    python3 scripts/calibrate.py labeled.jsonl
    python3 scripts/calibrate.py --demo

`--demo` computes synthetic data. That checks the script itself, not the model.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys

COLUMNS = ("score", "phi", "meanLp", "minLp")


def truthy_label(value):
    """label from JSON: true/false, but also 1/0 — that is how `collect.py` writes them."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return None


def load(path: str) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    legacy = 0
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
            # phi (φ) at runtime (`score.ts.phi`) is confidence: 1 - H/ln K. The datasets collected
            # before the `collect.py` fix store entropy H/ln K; we bring them to the runtime
            # definition, otherwise the trained `meanPhi` weight gets the opposite sign and
            # works against confidence on live answers.
            if row.get("phiDef") != "confidence" and "phi" in row:
                row["phi"] = 1.0 - float(row["phi"] or 0.0)
                row["phiDef"] = "confidence"
                legacy += 1
            rows.append(row)
    # An unlabeled row is treated as entropy. That is only correct for the datasets
    # collected before the `collect.py` fix; the new format needs `phiDef`.
    if legacy:
        print(
            f"warning: {legacy} row(s) have no phiDef; treated phi as entropy and converted it to confidence",
            file=sys.stderr,
        )
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
                "phiDef": "confidence",
                "meanLp": round(rng.gauss(-0.7 if truth else -1.4, 0.3), 4),
                "minLp": round(rng.gauss(-1.2 if truth else -2.6, 0.5), 4),
                "label": truth,
            }
        )
    return rows


def auroc(pairs: list[tuple[float, bool]]) -> float:
    """Probability that the correct sentence got a larger signal than the incorrect one."""
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
    """Logistic regression over the scorer features (bias, meanLp, minLp, phi, fracLow, digitDensity)."""
    xs = [
        [1.0, float(row["meanLp"]), float(row["minLp"]), float(row["phi"]), float(row.get("fracLow") or 0.0),
         float(row.get("digitDensity") or 0.0)]
        for row in rows
    ]
    ys = [1.0 if row["label"] else 0.0 for row in rows]
    w = [0.0] * 6
    # Class balance: otherwise rare lies drown in the overall accuracy.
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
    """Transfer group: model + question. Answers inside a group are repeats of one fact."""
    return (str(row.get("model") or ""), str(row.get("prompt") or row.get("source") or ""))


def fold_assignment(rows: list[dict], folds: int = 5, seed: int = 11) -> list[int]:
    """Fold number for every row, identical inside the `group_key` group.

    Splitting by row is not allowed: the same answer appears in the dataset several times,
    and the question is reused by every model. With a row-wise split 88% of the test set
    ends up in training byte for byte, and OOF measures memorization instead of transfer.
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
    """AUROC and ECE over out-of-fold predictions with group splitting.

    Folds are cut by `(model, prompt)`: a repeated answer to the same question does not
    get into training, otherwise the metric flatters itself.
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
    """Trains separate weights per model (the "model" field in JSONL).

    Rationale: the models have differently shaped logprob distributions, so one shared
    sigmoid is systematically biased for part of the models. Groups with few rows
    or fewer than `min_negatives` examples of any class get no weights: at such
    a volume the coefficients go to a random sign, and confidence gets inverted.
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
                "note": f"fewer than {min_rows} rows — global is used",
            }
            continue
        if positives == 0 or positives == len(group):
            bundle["models"][name] = {
                "rows": len(group),
                "positives": positives,
                "weights": None,
                "note": "single class in the group — weights are not trained, global is used",
            }
            continue
        negatives = len(group) - positives
        if negatives < min_negatives or positives < min_negatives:
            bundle["models"][name] = {
                "rows": len(group),
                "positives": positives,
                "negatives": negatives,
                "weights": None,
                "note": f"fewer than {min_negatives} examples of the class — global is used",
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
    parser.add_argument("path", nargs="?", help="JSONL with labeled sentences")
    parser.add_argument("--demo", action="store_true", help="compute synthetic data")
    parser.add_argument("--fit", action="store_true", help="train linear-scorer weights")
    parser.add_argument("--by-model", action="store_true", help="separate weights per model from the model field")
    parser.add_argument("--out", help="where to write the weights (stdout by default)")
    args = parser.parse_args()

    if args.demo:
        rows, skipped = demo(), 0
        print("== demo: synthetic data, this is NOT a model measurement ==")
    elif args.path:
        rows, skipped = load(args.path)
        print(f"== {args.path}: {len(rows)} labeled rows, {skipped} skipped")
    else:
        parser.error("a JSONL path or --demo is required")

    positives = sum(1 for row in rows if row["label"])
    print(f"true: {positives}, false: {len(rows) - positives}")

    print(f"{'signal':10s} {'AUROC':>7s} {'ECE':>7s}")
    for column in COLUMNS:
        pairs = [(float(row[column]), row["label"]) for row in rows if row.get(column) is not None]
        if not pairs:
            continue
        # All four signals grow together with confidence: score/phi directly,
        # meanLp/minLp like logprob (closer to zero means more confident). Hence
        # no inversions: otherwise AUROC shows 1-AUROC.
        print(f"{column:10s} {auroc(pairs):7.3f} {ece(pairs, bins=10):7.3f}")

    if args.fit:
        if len(rows) < 20:
            print("\ntoo few rows to train weights (need >= 20)")
            return 1
        if positives == 0 or positives == len(rows):
            # Single class: sigmoid will learn a constant, AUROC/ECE become meaningless,
            # and the weights harmful. Better to refuse honestly than to write such a file.
            print(
                f"\nrefusing: the dataset has only one class (true {positives}, false {len(rows) - positives}).\n"
                "Calibration needs BOTH labels: 0 — the model was wrong/hallucinated, 1 — it answered correctly.\n"
                "Take questions where part of the models fail, or add weaker models.",
                file=sys.stderr,
            )
            return 2
        cv_auroc, cv_ece = cross_validate(rows)
        print(f"\nlinear scorer, out-of-fold ({len(rows)} rows, 5 folds):")
        print(f"  AUROC {cv_auroc:.3f}   ECE {cv_ece:.3f}")

        if args.by_model:
            bundle = fit_by_model(rows)
            print("\nper model (out-of-fold where rows >= 20):")
            print(f"{'model':34s} {'rows':>5s} {'AUROC':>7s} {'ECE':>7s}")
            for name, entry in bundle["models"].items():
                auroc_text = f"{entry['auroc']:.3f}" if entry.get("auroc") is not None else "   —  "
                ece_text = f"{entry['ece']:.3f}" if entry.get("ece") is not None else "  —  "
                print(f"{name[:34]:34s} {entry['rows']:5d} {auroc_text:>7s} {ece_text:>7s}")
            text = json.dumps(bundle, ensure_ascii=False, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text + "\n")
                print(f"\nweights bundle written: {args.out}")
                print(f"enable with: TRUTHPROBE_SCORER=linear:{args.out}")
                print("at runtime it takes models[providerID/modelID], and global when that is missing")
            else:
                print("\nweights bundle:")
                print(text)
            return 0

        weights = fit(rows)
        text = json.dumps(weights, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
            print(f"\nweights written: {args.out}")
            print(f"enable with: TRUTHPROBE_SCORER=linear:{args.out}")
        else:
            print("\nweights (put them into a JSON file and set TRUTHPROBE_SCORER=linear:<path>):")
            print(text)
        return 0

    print("\nThe swappable scorer weights are trained on this same dataset:")
    print("  python3 scripts/calibrate.py labeled.jsonl --fit --out truthprobe-weights.json")
    print("Until they are trained, the percentages in the UI are not a calibrated probability (see docs/CALIBRATION.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
