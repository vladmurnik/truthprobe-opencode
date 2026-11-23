#!/usr/bin/env python3
"""Honest evaluation: baselines, trained models, length control, cluster bootstrap by qid.

Out-of-fold only: `GroupKFold` by `qid`, standardization on the train fold. Nothing is tuned
on the test folds, including the orthogonalization by length.
"""
import json
import math
import os
import random
import sys
from pathlib import Path

HERE = Path(os.environ.get("HALLUC_DIR", Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))

import train  # noqa: E402

train.DATA = Path(os.environ.get("DATASET_OUT", HERE / "dataset.jsonl"))
rows = train.load()
y = [r["y"] for r in rows]
pos, neg = sum(y), len(y) - sum(y)
print(f"rows {len(rows)}: lies {pos}, truths {neg}, questions {len({r['qid'] for r in rows})}")

LEAN = [f for f in train.FEATURES if f not in train.LENGTH]
PRODUCT = ["mean_lp", "min_lp", "mean_phi", "frac_below_half", "digit_density"]


def balanced(labels):
    p = sum(labels)
    return [len(labels) / (2 * p) if v else len(labels) / (2 * (len(labels) - p)) for v in labels]


def oof(names, orth=False):
    X = [[float(r[n]) for n in names] for r in rows]
    tokens = [float(r["n_tokens"]) for r in rows]
    out = [0.0] * len(rows)
    for test in train.folds(rows):
        tr = [i for i in range(len(rows)) if i not in set(test)]
        Xtr = [X[i][:] for i in tr]
        Xte = [X[i][:] for i in test]
        if orth:
            for j in range(len(names)):
                n = len(tr)
                sx = sum(tokens[i] for i in tr)
                sxx = sum(tokens[i] ** 2 for i in tr)
                sy = sum(X[i][j] for i in tr)
                sxy = sum(tokens[i] * X[i][j] for i in tr)
                den = n * sxx - sx * sx
                b = 0.0 if abs(den) < 1e-12 else (n * sxy - sx * sy) / den
                a = (sy - b * sx) / n
                for local, i in enumerate(tr):
                    Xtr[local][j] = X[i][j] - (a + b * tokens[i])
                for local, i in enumerate(test):
                    Xte[local][j] = X[i][j] - (a + b * tokens[i])
        Xtr_s, Xte_s = train.standardize(Xtr, Xte)
        model = train.Logistic().fit(Xtr_s, [y[i] for i in tr], balanced([y[i] for i in tr]))
        for local, i in enumerate(test):
            out[i] = model.predict([Xte_s[local]])[0]
    return out


def cat(scores, name):
    idx = [i for i, r in enumerate(rows) if r["category"] == name]
    return train.auroc([(scores[i], y[i]) for i in idx]), len(idx), sum(y[i] for i in idx)


risk_geo = [1 - math.exp(r["mean_lp"]) for r in rows]
risk_phi = [1 - r["mean_phi"] for r in rows]
five = oof(PRODUCT)
lean = oof(LEAN)
five_orth = oof(PRODUCT, orth=True)
lean_orth = oof(LEAN, orth=True)

fmt = lambda v: "—" if v is None else f"{v:.3f}"

print("\n| estimate (risk direction) | AUROC |")
print("| --- | --- |")
for name, s in [("1 − exp(meanLp)", risk_geo), ("1 − meanφ", risk_phi),
                ("logistic, 5 product features", five), ("logistic, 26 without length", lean),
                ("5 features, orthogonalized by n_tokens", five_orth),
                ("26 without length, orthogonalized by n_tokens", lean_orth)]:
    print(f"| {name} | {fmt(train.auroc(list(zip(s, y))))} |")

print("\n| category | n | lies | 1-exp(meanLp) | 5 features | 26 without length |")
print("| --- | --- | --- | --- | --- | --- |")
for name in ["false-premise", "fake-work", "fake-person", "myth", "fact", "numer"]:
    a, n, p = cat(risk_geo, name)
    b, _, _ = cat(five, name)
    c, _, _ = cat(lean, name)
    print(f"| {name} | {n} | {p} | {fmt(a)} | {fmt(b)} | {fmt(c)} |")

print("\n| n_tokens quartile | range | lies/truths | 1-exp(meanLp) | 5 features |")
print("| --- | --- | --- | --- | --- |")
counts = sorted(r["n_tokens"] for r in rows)
cuts = [counts[len(counts) // 4], counts[len(counts) // 2], counts[3 * len(counts) // 4]]
bounds = [0, cuts[0], cuts[1], cuts[2], 10 ** 9]
for q in range(4):
    idx = [i for i, r in enumerate(rows) if bounds[q] <= r["n_tokens"] < bounds[q + 1]]
    p = sum(y[i] for i in idx)
    a = train.auroc([(risk_geo[i], y[i]) for i in idx])
    b = train.auroc([(five[i], y[i]) for i in idx])
    hi = "∞" if q == 3 else bounds[q + 1]
    print(f"| Q{q + 1} | {bounds[q]}–{hi} | {p}/{len(idx) - p} | {fmt(a)} | {fmt(b)} |")

qids = sorted({r["qid"] for r in rows})
by_q = {q: [i for i, r in enumerate(rows) if r["qid"] == q] for q in qids}


def boot(stat, reps=400, seed=7):
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        idx = [i for q in (rng.choice(qids) for _ in qids) for i in by_q[q]]
        v = stat(idx)
        if v is not None:
            vals.append(v)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def au(idx, s):
    return train.auroc([(s[i], y[i]) for i in idx])


print()
for name, s in [("1 - exp(meanLp)", risk_geo), ("5 features", five), ("26 without length", lean)]:
    lo, hi = boot(lambda idx, s=s: au(idx, s))
    print(f"CI {name}: [{lo:.3f}, {hi:.3f}]  point {fmt(train.auroc(list(zip(s, y))))}")
for name, s in [("5 features - formula", five), ("26 without length - formula", lean)]:
    lo, hi = boot(lambda idx, s=s: (au(idx, s) or 0) - (au(idx, risk_geo) or 0))
    print(f"CI Δ({name}): [{lo:+.3f}, {hi:+.3f}]")

pure, by_qid = 0, {}
for r in rows:
    by_qid.setdefault(r["qid"], set()).add(r["y"])
for q, ys in by_qid.items():
    if len(ys) == 1:
        pure += len(by_q[q])
print(f"\nrows with a label fully determined by the question: {pure}/{len(rows)} ({100 * pure / len(rows):.0f}%)")
