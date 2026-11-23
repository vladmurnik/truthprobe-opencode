#!/usr/bin/env python3
"""Checks the question bank: where the data is wrong and where the models really lie.

Three different diagnoses, and they must not be confused:

- `bank_error` — the question itself hints at a wrong answer ("Saturn or Neptune", while the
  reference is `jupiter`). Such a `0` label is broken data, not a signal. This is exit 1.
- `ambiguous` — the models disagree with each other (they have different modal answers).
  That means the question allows several readings, and it must not be used for training. This is exit 1.
- `suspect` — all models independently give ONE AND THE SAME answer that is not in the
  reference. Either the reference is wrong or the models are uniformly wrong. This is exactly the
  case negatives are collected for, so by default it is a
  warning, not a failure (`--strict` turns it into a failure).

The script changes nothing: it only shows the items that must be re-read by hand.

    python3 scripts/audit-bank.py data/qa-hard-bank.jsonl data/rows-hard.jsonl
    python3 scripts/audit-bank.py bank.jsonl rows.jsonl --json --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict

WORD = re.compile(r"[a-z0-9]+")


def norm(text: str) -> str:
    return " ".join(WORD.findall((text or "").lower()))


def matches(answer: str, expect: list[str]) -> bool:
    """Same rule as in collect.py: short values on word boundaries, long ones by substring."""
    got = norm(answer)
    if not got:
        return False
    for item in expect:
        want = norm(item)
        if not want:
            continue
        if len(want) <= 4 or " " in want:
            if re.search(rf"(?<![a-z0-9]){re.escape(want)}(?![a-z0-9])", got):
                return True
        elif want in got:
            return True
    return False


def load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def premise_conflict(prompt: str, expect: list[str]) -> bool:
    """The question offers an "X or Y" choice, and the expected answer is not among the options."""
    options = re.findall(r"([A-Za-z][A-Za-z .'-]{2,30}?)\s+or\s+([A-Za-z][A-Za-z .'-]{2,30})", prompt)
    if not options:
        return False
    offered = norm(" ".join(options[0]))
    return not any(norm(item) in offered for item in expect)


def classify(prompt: str, expect: list[str], modals: dict[str, str]) -> tuple[str | None, str]:
    """Returns (diagnosis, human-readable explanation) or (None, '')."""
    total = len(modals)
    if total < 2:
        return None, ""
    if premise_conflict(prompt, expect):
        return "bank_error", "the choice in the question contradicts the reference"
    wrong = {model: answer for model, answer in modals.items() if not matches(answer, expect)}
    if not wrong:
        return None, ""
    distinct = {answer for answer in wrong.values()}
    if len(wrong) == total and len(distinct) == 1:
        return "suspect", "all models give the same answer that misses the reference"
    if len(distinct) > 1:
        return "ambiguous", "the models disagree with each other — the question allows several readings"
    if len(wrong) >= max(2, (total + 1) // 2):
        return "suspect", "most models agree against the reference"
    return None, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bank")
    parser.add_argument("rows")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="treat suspect as a failure")
    parser.add_argument("--min-models", type=int, default=2, help="how many models are needed for a diagnosis (default 2)")
    args = parser.parse_args()

    bank = {row["prompt"]: row.get("expect") or [] for row in load_jsonl(args.bank) if row.get("prompt")}
    rows = load_jsonl(args.rows)

    by_prompt: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        prompt = row.get("prompt")
        answer = row.get("answer")
        if prompt in bank and answer:
            by_prompt[prompt][str(row.get("model") or "?")][norm(answer)] += 1

    findings = []
    for prompt, expect in bank.items():
        per_model = by_prompt.get(prompt, {})
        if len(per_model) < args.min_models:
            continue
        modals = {model: counter.most_common(1)[0][0] for model, counter in per_model.items()}
        diagnosis, why = classify(prompt, expect, modals)
        if not diagnosis:
            continue
        findings.append(
            {
                "prompt": prompt,
                "expect": expect,
                "diagnosis": diagnosis,
                "why": why,
                "models": len(modals),
                "modals": modals,
            }
        )

    order = {"bank_error": 0, "ambiguous": 1, "suspect": 2}
    findings.sort(key=lambda item: (order[item["diagnosis"]], item["prompt"]))

    failed = [item for item in findings if item["diagnosis"] != "suspect" or args.strict]

    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(bank),
                    "bank_error": sum(1 for item in findings if item["diagnosis"] == "bank_error"),
                    "ambiguous": sum(1 for item in findings if item["diagnosis"] == "ambiguous"),
                    "suspect": sum(1 for item in findings if item["diagnosis"] == "suspect"),
                    "findings": findings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        errors = sum(1 for item in findings if item["diagnosis"] == "bank_error")
        ambiguous = sum(1 for item in findings if item["diagnosis"] == "ambiguous")
        suspects = sum(1 for item in findings if item["diagnosis"] == "suspect")
        print(
            f"bank items checked: {len(bank)} | broken bank: {errors} | "
            f"ambiguous: {ambiguous} | models caught with a wrong answer: {suspects}"
        )
        for item in findings:
            print(f"\n- [{item['diagnosis']}] {item['prompt']}")
            print(f"  reference: {item['expect']} | {item['why']}")
            for model, answer in item["modals"].items():
                mark = " " if matches(answer, item["expect"]) else "!"
                print(f"  {mark} {model}: {answer!r}")
        if errors or ambiguous:
            print("\nThe first two diagnoses are broken data: such items must not be used for training.")
        if suspects:
            print("\nsuspect means either a broken reference or a real mistake of all models; decided by hand.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
