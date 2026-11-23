#!/usr/bin/env python3
"""Backfills `digitDensity` in the rows that were already collected.

The feature appeared later than some datasets: `collect.py` now writes it itself, but
the old JSONL files do not contain it. Recomputing it from the `answer` field is not inventing data but
the very same function as at runtime (`packages/core/src/truthprobe/score.ts`):

    digitDensity = number of characters 0..9 in the visible answer / answer length

That is why the script is idempotent: a repeated run gives the same numbers. Rows where
`digitDensity` is already present and matches are left untouched.

    python3 scripts/enrich-digits.py data/rows-*.jsonl
    python3 scripts/enrich-digits.py --check data/rows-lie-vs-truth.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def digit_density(answer: str) -> float:
    """Exactly like `digitDensity` in score.ts: ASCII digits per UTF-16 code unit."""
    if not answer:
        return 0.0
    units = len(answer.encode("utf-16-le")) // 2
    return round(sum(1 for ch in answer if "0" <= ch <= "9") / units, 6)


def process(path: str, check: bool) -> tuple[int, int]:
    """Returns (total rows, rows changed or diverged)."""
    total = changed = 0
    rows: list[str] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                rows.append(line)
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                rows.append(line)
                continue
            if not isinstance(row, dict):
                rows.append(line)
                continue
            want = digit_density(row.get("answer") or "")
            have = row.get("digitDensity")
            if isinstance(have, (int, float)) and abs(float(have) - want) < 1e-9:
                rows.append(line if line.endswith("\n") else line + "\n")
                continue
            changed += 1
            row["digitDensity"] = want
            rows.append(json.dumps(row, ensure_ascii=False) + "\n")
    if not check and changed:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(rows)
        os.replace(tmp, path)
    return total, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--check", action="store_true", help="only show divergences, do not write")
    args = parser.parse_args()

    exit_code = 0
    for path in args.paths:
        if not os.path.exists(path):
            print(f"{path}: no such file", file=sys.stderr)
            exit_code = 2
            continue
        total, changed = process(path, args.check)
        verb = "diverged" if args.check else "updated"
        print(f"{path}: {total} rows, {verb} {changed}")
        if args.check and changed:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
