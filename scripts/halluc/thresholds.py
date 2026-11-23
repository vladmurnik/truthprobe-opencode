#!/usr/bin/env python3
import json

import os
import pathlib

HERE = pathlib.Path(os.environ.get("HALLUC_DIR") or pathlib.Path(__file__).resolve().parent)
rows = [json.loads(line) for line in open(HERE / "dataset.jsonl", encoding="utf-8")]
bad = [r for r in rows if r["y"] == 1]
good = [r for r in rows if r["y"] == 0]


def share(items, limit, below=True):
    if not items:
        return 0.0
    n = sum(1 for r in items if (r["geo"] < limit) == below)
    return round(n / len(items), 3)


print(f"lies {len(bad)}, truths {len(good)}")
for limit in (0.55, 0.75, 0.90):
    print(f"score < {limit}: lies {share(bad, limit)}  truths {share(good, limit)}")
print(f"score >= 0.90 (safe): lies {share(bad, 0.90, below=False)}  truths {share(good, 0.90, below=False)}")

print("\nby category: total lies / of them score < 0.55")
for cat in sorted({r["category"] for r in rows}):
    items = [r for r in bad if r["category"] == cat]
    if not items:
        continue
    print(f"{cat:14s} {len(items):3d} / {share(items, 0.55)}")

print("\nby model: lies / score < 0.55 / median score of lies")
for model in sorted({r["model"] for r in rows}):
    items = [r for r in bad if r["model"] == model]
    if not items:
        continue
    geo = sorted(r["geo"] for r in items)
    print(f"{model:20s} {len(items):3d} / {share(items, 0.55)} / {geo[len(geo) // 2]:.3f}")
