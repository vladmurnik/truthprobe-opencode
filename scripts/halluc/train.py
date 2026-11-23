#!/usr/bin/env python3
"""Trains lie detectors on the stdlib (numpy/sklearn are not available in the environment).

Models: logistic regression, CART tree, random forest, mini-MLP.
Validation: GroupKFold by `qid` — one question cannot be in train and test at the same time.
Metrics: AUROC, ECE (15 bins), Brier, accuracy@0.5.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import random

HERE = pathlib.Path(os.environ.get("HALLUC_DIR") or pathlib.Path(__file__).resolve().parent)
DATA = HERE / "dataset.jsonl"
MODEL = HERE / "model.json"

FEATURES = [
    "n_tokens", "mean_lp", "min_lp", "max_lp", "p10_lp", "p25_lp", "std_lp",
    "frac_below_half", "geo", "mean_phi", "min_phi", "frac_phi_lt_05",
    "mean_margin", "min_margin", "first_lp", "first_phi", "first_margin",
    "n_chars", "digit_density", "upper_ratio", "newlines", "n_sentences",
    "sent_min", "sent_mean", "sent_frac_low", "sent_flagged",
    "hedge_count", "negation_count", "number_count", "ends_period",
]


def load() -> list[dict]:
    return [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]


def auroc(pairs: list[tuple[float, int]]) -> float | None:
    pos = [p for p, y in pairs if y == 1]
    neg = [p for p, y in pairs if y == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for a in pos:
        for b in neg:
            wins += 1.0 if a > b else (0.5 if a == b else 0.0)
    return wins / (len(pos) * len(neg))


def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def ece(pairs: list[tuple[float, int]], bins: int = 15) -> float:
    total = len(pairs)
    value = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [(p, y) for p, y in pairs if low <= p < high or (index == bins - 1 and p >= high)]
        if not bucket:
            continue
        mean_p = sum(p for p, _ in bucket) / len(bucket)
        mean_y = sum(y for _, y in bucket) / len(bucket)
        value += abs(mean_p - mean_y) * len(bucket) / total
    return value


def accuracy(pairs: list[tuple[float, int]], threshold: float = 0.5) -> float:
    return sum(1 for p, y in pairs if (p >= threshold) == (y == 1)) / len(pairs)


def folds(rows: list[dict], k: int = 5, seed: int = 13) -> list[list[int]]:
    """GroupKFold by qid: all answers to one question land in one fold."""
    groups = sorted({row["qid"] for row in rows})
    random.Random(seed).shuffle(groups)
    assignment = {qid: index % k for index, qid in enumerate(groups)}
    buckets: list[list[int]] = [[] for _ in range(k)]
    for index, row in enumerate(rows):
        buckets[assignment[row["qid"]]].append(index)
    return buckets


# ---------------------------------------------------------------- logistic
class Logistic:
    def __init__(self, l2: float = 0.05, epochs: int = 400, lr: float = 0.5):
        self.l2, self.epochs, self.lr = l2, epochs, lr
        self.w: list[float] = []
        self.b = 0.0

    def fit(self, X: list[list[float]], y: list[int], weights: list[float] | None = None) -> "Logistic":
        n, d = len(X), len(X[0])
        self.w = [0.0] * d
        self.b = 0.0
        weights = weights or [1.0] * n
        total = sum(weights)
        for _ in range(self.epochs):
            gw = [0.0] * d
            gb = 0.0
            for row, label, weight in zip(X, y, weights):
                z = self.b + sum(wi * xi for wi, xi in zip(self.w, row))
                error = (sigmoid(z) - label) * weight
                for j in range(d):
                    gw[j] += error * row[j]
                gb += error
            self.w = [wi - self.lr * (gi / total + self.l2 * wi) for wi, gi in zip(self.w, gw)]
            self.b -= self.lr * gb / total
        return self

    def predict(self, X: list[list[float]]) -> list[float]:
        return [sigmoid(self.b + sum(wi * xi for wi, xi in zip(self.w, row))) for row in X]


def sigmoid(z: float) -> float:
    if z > 35:
        return 1.0
    if z < -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


# ------------------------------------------------------------------- tree
class Tree:
    def __init__(self, max_depth: int = 4, min_leaf: int = 6, candidates: int = 12, seed: int = 1):
        self.max_depth, self.min_leaf, self.candidates = max_depth, min_leaf, candidates
        self.rng = random.Random(seed)
        self.root: dict | None = None

    def fit(self, X: list[list[float]], y: list[int], features: list[int]) -> "Tree":
        self.root = self.build(X, y, features, 0)
        return self

    def build(self, X: list[list[float]], y: list[int], features: list[int], depth: int) -> dict:
        positives = sum(y)
        node = {"p": (positives + 0.5) / (len(y) + 1.0)}
        if depth >= self.max_depth or len(y) < 2 * self.min_leaf or positives in (0, len(y)):
            return node
        best = None
        for feature in features:
            values = sorted({row[feature] for row in X})
            if len(values) < 2:
                continue
            step = max(1, len(values) // self.candidates)
            for value in values[::step][1:]:
                left = [label for row, label in zip(X, y) if row[feature] <= value]
                right = [label for row, label in zip(X, y) if row[feature] > value]
                if len(left) < self.min_leaf or len(right) < self.min_leaf:
                    continue
                score = gini(left) * len(left) + gini(right) * len(right)
                if best is None or score < best[0]:
                    best = (score, feature, value)
        if best is None:
            return node
        _, feature, value = best
        left_x = [row for row in X if row[feature] <= value]
        left_y = [label for row, label in zip(X, y) if row[feature] <= value]
        right_x = [row for row in X if row[feature] > value]
        right_y = [label for row, label in zip(X, y) if row[feature] > value]
        node.update({
            "feature": feature, "value": value, "count": len(y),
            "left": self.build(left_x, left_y, features, depth + 1),
            "right": self.build(right_x, right_y, features, depth + 1),
        })
        return node

    def predict(self, X: list[list[float]]) -> list[float]:
        out = []
        for row in X:
            node = self.root or {"p": 0.5}
            while "feature" in node:
                node = node["left"] if row[node["feature"]] <= node["value"] else node["right"]
            out.append(node["p"])
        return out


def gini(labels: list[int]) -> float:
    if not labels:
        return 0.0
    p = sum(labels) / len(labels)
    return 2 * p * (1 - p)


class Forest:
    def __init__(self, trees: int = 120, seed: int = 5):
        self.trees, self.seed = trees, seed

    def fit(self, X: list[list[float]], y: list[int]) -> "Forest":
        rng = random.Random(self.seed)
        d = len(X[0])
        subset = max(3, int(math.sqrt(d)))
        self.models = []
        for index in range(self.trees):
            sample = [rng.randrange(len(X)) for _ in range(len(X))]
            features = rng.sample(range(d), subset)
            tree = Tree(max_depth=5, min_leaf=5, seed=index)
            tree.fit([X[i] for i in sample], [y[i] for i in sample], features)
            self.models.append(tree)
        return self

    def predict(self, X: list[list[float]]) -> list[float]:
        columns = list(zip(*(model.predict(X) for model in self.models)))
        return [sum(column) / len(column) for column in columns]


# -------------------------------------------------------------------- MLP
class MLP:
    def __init__(self, hidden: int = 10, epochs: int = 300, lr: float = 0.08, seed: int = 3):
        self.hidden, self.epochs, self.lr, self.seed = hidden, epochs, lr, seed

    def fit(self, X: list[list[float]], y: list[int]) -> "MLP":
        rng = random.Random(self.seed)
        d = len(X[0])
        self.w1 = [[rng.uniform(-0.5, 0.5) for _ in range(d)] for _ in range(self.hidden)]
        self.b1 = [0.0] * self.hidden
        self.w2 = [rng.uniform(-0.5, 0.5) for _ in range(self.hidden)]
        self.b2 = 0.0
        for _ in range(self.epochs):
            gw1 = [[0.0] * d for _ in range(self.hidden)]
            gb1 = [0.0] * self.hidden
            gw2 = [0.0] * self.hidden
            gb2 = 0.0
            for row, label in zip(X, y):
                hidden = [math.tanh(self.b1[i] + sum(w * x for w, x in zip(self.w1[i], row)))
                          for i in range(self.hidden)]
                out = sigmoid(self.b2 + sum(w * h for w, h in zip(self.w2, hidden)))
                delta = out - label
                for i in range(self.hidden):
                    gw2[i] += delta * hidden[i]
                    back = delta * self.w2[i] * (1 - hidden[i] ** 2)
                    gb1[i] += back
                    for j in range(d):
                        gw1[i][j] += back * row[j]
                gb2 += delta
            n = len(X)
            for i in range(self.hidden):
                self.w2[i] -= self.lr * gw2[i] / n
                self.b1[i] -= self.lr * gb1[i] / n
                for j in range(d):
                    self.w1[i][j] -= self.lr * gw1[i][j] / n
            self.b2 -= self.lr * gb2 / n
        return self

    def predict(self, X: list[list[float]]) -> list[float]:
        out = []
        for row in X:
            hidden = [math.tanh(self.b1[i] + sum(w * x for w, x in zip(self.w1[i], row)))
                      for i in range(self.hidden)]
            out.append(sigmoid(self.b2 + sum(w * h for w, h in zip(self.w2, hidden))))
        return out


# ------------------------------------------------------------------- main
# The length features tell "the model lied at length" from "the model answered briefly".
# On this dataset they explain almost all of the high AUROC, so the models
# are computed twice: with and without them. The honest estimate of the signal is the second one.
LENGTH = {"n_tokens", "n_chars", "n_sentences", "newlines"}


def matrix(rows: list[dict], features: list[str]) -> list[list[float]]:
    return [[float(row[name]) for name in features] for row in rows]


def standardize(train: list[list[float]], test: list[list[float]]) -> tuple[list[list[float]], list[list[float]]]:
    d = len(train[0])
    mean = [sum(row[j] for row in train) / len(train) for j in range(d)]
    std = []
    for j in range(d):
        var = sum((row[j] - mean[j]) ** 2 for row in train) / len(train)
        std.append(math.sqrt(var) or 1.0)
    norm = lambda data: [[(row[j] - mean[j]) / std[j] for j in range(d)] for row in data]
    return norm(train), norm(test)


def evaluate(name: str, pairs: list[tuple[float, int]]) -> dict:
    return {
        "name": name,
        "auroc": auroc(pairs),
        "ece": ece(pairs),
        "brier": brier(pairs),
        "acc": accuracy(pairs),
        "n": len(pairs),
    }


def experiment(features: list[str], title: str) -> tuple[dict, list[dict]]:
    rows = load()
    X = matrix(rows, features)
    y = [row["y"] for row in rows]
    print(f"\n## {title}: features {len(features)}, rows {len(rows)}, lies {sum(y)}")

    buckets = folds(rows)
    results: dict[str, list[tuple[float, int]]] = {}

    def collect(name: str, scores: list[float], index: list[int]) -> None:
        results.setdefault(name, []).extend(zip(scores, [y[i] for i in index]))

    for fold, test_idx in enumerate(buckets):
        train_idx = [i for i in range(len(rows)) if i not in set(test_idx)]
        Xtr, Xte = standardize([X[i] for i in train_idx], [X[i] for i in test_idx])
        ytr = [y[i] for i in train_idx]
        positives = sum(ytr)
        weights = [(len(ytr) / (2 * positives)) if label else (len(ytr) / (2 * (len(ytr) - positives)))
                   for label in ytr]

        collect("baseline: exp(meanLp)", [min(1.0, max(0.0, rows[i]["geo"])) for i in test_idx], test_idx)
        collect("baseline: mean_phi", [min(1.0, max(0.0, rows[i]["mean_phi"])) for i in test_idx], test_idx)
        collect("baseline: sent_min", [min(1.0, max(0.0, rows[i]["sent_min"])) for i in test_idx], test_idx)
        collect("logistic", Logistic().fit(Xtr, ytr, weights).predict(Xte), test_idx)
        collect("tree (d=4)", Tree(max_depth=4).fit(Xtr, ytr, list(range(len(features)))).predict(Xte), test_idx)
        collect("random forest", Forest().fit(Xtr, ytr).predict(Xte), test_idx)
        collect("mlp (10)", MLP().fit(Xtr, ytr).predict(Xte), test_idx)

    print("| model | AUROC | ECE | Brier | acc@0.5 | n |")
    print("| --- | --- | --- | --- | --- | --- |")
    summary = []
    for name, pairs in results.items():
        value = evaluate(name, pairs)
        summary.append(value)
        a = value["auroc"]
        print(f"| {name} | {'n/a' if a is None else round(a, 3)} | {round(value['ece'], 3)} | "
              f"{round(value['brier'], 3)} | {round(value['acc'], 3)} | {value['n']} |")

    return results, rows


def single_feature(rows: list[dict], features: list[str]) -> None:
    print("\n### Single feature against the label (AUROC, no training)")
    single = []
    for name in features:
        pairs = [(float(rows[i][name]), rows[i]["y"]) for i in range(len(rows))]
        value = auroc(pairs)
        if value is not None:
            single.append((abs(value - 0.5), value, name))
    for _, value, name in sorted(single, reverse=True)[:12]:
        print(f"- {name}: {round(value, 3)}")


def per_run(rows: list[dict]) -> None:
    print("\n### Confidence signal within a run (AUROC over the answers of this run only)")
    for run in sorted({row["run"] for row in rows}):
        subset = [row for row in rows if row["run"] == run]
        positives = sum(row["y"] for row in subset)
        negatives = len(subset) - positives
        value = auroc([(row["geo"], row["y"]) for row in subset])
        print(f"- {run}: n={len(subset)} (truths {negatives}, lies {positives}), "
              f"AUROC(exp(meanLp)) = {'n/a' if value is None else round(value, 3)}")


def main() -> None:
    rows = load()
    print(f"rows {len(rows)}, lies {sum(row['y'] for row in rows)}, "
          f"questions {len({row['qid'] for row in rows})}")
    experiment(FEATURES, "All features")
    lean = [name for name in FEATURES if name not in LENGTH]
    experiment(lean, "Without length features")
    single_feature(rows, lean)
    per_run(rows)

    # The final model uses the features without length: those are the signal, not a dataset artifact.
    X = matrix(rows, lean)
    y = [row["y"] for row in rows]
    Xa, _ = standardize(X, X)
    positives = sum(y)
    weights = [len(y) / (2 * positives) if label else len(y) / (2 * (len(y) - positives)) for label in y]
    final = Logistic().fit(Xa, y, weights)
    named = {name: round(weight, 4) for name, weight in zip(lean, final.w)}
    MODEL.write_text(json.dumps({"features": lean, "weights": named, "bias": round(final.b, 4)}, indent=1),
                     encoding="utf-8")
    print("\n### Logistic weights without length (standardized features)")
    for name, weight in sorted(named.items(), key=lambda item: -abs(item[1]))[:10]:
        print(f"- {name}: {weight:+}")
    print("\nwritten:", MODEL)


if __name__ == "__main__":
    main()
