#!/usr/bin/env python3
"""Builds a bank of counting questions: models count badly over a long list.

Each item is a list of 30 numbers plus the question "how many of them are greater than N". The answer
is verified arithmetically: it is easy to make a mistake, and just as easy to invent a "plausible" one.
"""
import json
import random

random.seed(7)
rows = []
for i in range(8):
    numbers = [random.randint(1, 99) for _ in range(30)]
    threshold = random.choice([40, 45, 50, 55, 60])
    expected = sum(1 for n in numbers if n > threshold)
    listing = ", ".join(str(n) for n in numbers)
    prompt = (
        "Count how many numbers in the following list are greater than "
        f"{threshold}. Answer with a number only.\n\n{listing}"
    )
    rows.append({"prompt": prompt, "expect": [str(expected), ]})

with open("data/qa-count-bank.jsonl", "w", encoding="utf-8", newline="\n") as handle:
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"wrote {len(rows)} items")
for row in rows:
    print(" expect", row["expect"][0], "|", row["prompt"][:60].replace("\n", " "))
