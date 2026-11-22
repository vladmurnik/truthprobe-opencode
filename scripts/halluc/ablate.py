#!/usr/bin/env python3
"""Абляции: какие группы признаков реально несут сигнал, и переносится ли он
на модель, которой не было в обучении (leave-one-model-out)."""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train as T  # noqa: E402
LENGTH = {"n_tokens", "n_chars", "n_sentences", "newlines"}
TEXT = {"hedge_count", "negation_count", "number_count", "upper_ratio", "digit_density", "ends_period"}
DISPERSION = {"std_lp", "frac_below_half", "min_lp", "min_phi", "frac_phi_lt_05", "mean_margin", "min_margin"}


def run(name: str, rows: list[dict], features: list[str]) -> None:
    X = T.matrix(rows, features)
    y = [row["y"] for row in rows]
    pairs: list[tuple[float, int]] = []
    for test_idx in T.folds(rows):
        train_idx = [i for i in range(len(rows)) if i not in set(test_idx)]
        Xtr, Xte = T.standardize([X[i] for i in train_idx], [X[i] for i in test_idx])
        ytr = [y[i] for i in train_idx]
        pos = sum(ytr)
        weights = [(len(ytr) / (2 * pos)) if label else (len(ytr) / (2 * (len(ytr) - pos))) for label in ytr]
        model = T.Logistic().fit(Xtr, ytr, weights)
        pairs.extend(zip(model.predict(Xte), [y[i] for i in test_idx]))
    a = T.auroc(pairs)
    print(f"| {name} | {len(features)} | {'n/a' if a is None else round(a, 3)} | "
          f"{round(T.ece(pairs), 3)} | {round(T.brier(pairs), 3)} |")


def main() -> None:
    rows = T.load()
    lean = [f for f in T.FEATURES if f not in LENGTH]
    print(f"строк {len(rows)}, ложных {sum(r['y'] for r in rows)}\n")
    print("| набор признаков | кол-во | AUROC | ECE | Brier |")
    print("| --- | --- | --- | --- | --- |")
    run("все 30", rows, T.FEATURES)
    run("без длины", rows, lean)
    run("без длины и текста", rows, [f for f in lean if f not in TEXT])
    run("только дисперсия logprob", rows, [f for f in lean if f in DISPERSION])
    run("только текст", rows, [f for f in lean if f in TEXT])
    run("только средние (mean_lp, geo, mean_phi)", rows, ["mean_lp", "geo", "mean_phi", "first_lp", "first_phi"])

    print("\n### Leave-one-model-out (логистика на 'без длины')")
    print("| отложенная модель | train | test | верных/ложных в test | AUROC | ECE |")
    print("| --- | --- | --- | --- | --- | --- |")
    X = T.matrix(rows, lean)
    y = [row["y"] for row in rows]
    models = sorted({row["model"] for row in rows})
    for held in models:
        test_idx = [i for i, row in enumerate(rows) if row["model"] == held]
        train_idx = [i for i, row in enumerate(rows) if row["model"] != held]
        Xtr, Xte = T.standardize([X[i] for i in train_idx], [X[i] for i in test_idx])
        ytr = [y[i] for i in train_idx]
        pos = sum(ytr)
        weights = [(len(ytr) / (2 * pos)) if label else (len(ytr) / (2 * (len(ytr) - pos))) for label in ytr]
        model = T.Logistic().fit(Xtr, ytr, weights)
        pairs = list(zip(model.predict(Xte), [y[i] for i in test_idx]))
        good = sum(1 for _, label in pairs if label == 0)
        bad = len(pairs) - good
        a = T.auroc(pairs)
        print(f"| {held} | {len(train_idx)} | {len(test_idx)} | {good}/{bad} | "
              f"{'n/a' if a is None else round(a, 3)} | {round(T.ece(pairs), 3)} |")


if __name__ == "__main__":
    main()
