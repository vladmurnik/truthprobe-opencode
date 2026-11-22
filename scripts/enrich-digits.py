#!/usr/bin/env python3
"""Досчитывает `digitDensity` в уже собранных строках.

Признак появился позже, чем часть наборов: `collect.py` теперь пишет его сам, но
старые JSONL его не содержат. Пересчёт из поля `answer` — не выдумывание данных, а
та же самая функция, что в рантайме (`packages/core/src/truthprobe/score.ts`):

    digitDensity = число символов 0..9 в видимом ответе / длина ответа

Поэтому скрипт идемпотентен: повторный запуск даёт те же числа. Строки, где
`digitDensity` уже есть и совпадает, остаются нетронутыми.

    python3 scripts/enrich-digits.py data/rows-*.jsonl
    python3 scripts/enrich-digits.py --check data/rows-lie-vs-truth.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def digit_density(answer: str) -> float:
    """Ровно как `digitDensity` в score.ts: ASCII-цифры на UTF-16 code unit."""
    if not answer:
        return 0.0
    units = len(answer.encode("utf-16-le")) // 2
    return round(sum(1 for ch in answer if "0" <= ch <= "9") / units, 6)


def process(path: str, check: bool) -> tuple[int, int]:
    """Возвращает (сколько строк всего, сколько изменено или разошлось)."""
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
    parser.add_argument("--check", action="store_true", help="только показать расхождения, не писать")
    args = parser.parse_args()

    exit_code = 0
    for path in args.paths:
        if not os.path.exists(path):
            print(f"{path}: нет файла", file=sys.stderr)
            exit_code = 2
            continue
        total, changed = process(path, args.check)
        verb = "разошлось" if args.check else "обновлено"
        print(f"{path}: {total} строк, {verb} {changed}")
        if args.check and changed:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
