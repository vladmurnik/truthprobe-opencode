#!/usr/bin/env python3
"""Restores the answer text the collector lost and relabels it.

An empty `answer` with non-empty `tokens` is not a model refusal: the text simply was not saved.
We reassemble the text from the tokens and run the same labeling rules as in collect3.py.
The source files are not overwritten: the result goes to `rows_raw2f.jsonl` / `rows_raw3f.jsonl`.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(os.environ.get("HALLUC_DIR", Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))

import collect3  # noqa: E402  — QUESTIONS and label()

QUESTIONS = {q[0]: q for q in collect3.QUESTIONS}

for src, dst in [("rows_raw2.jsonl", "rows_raw2f.jsonl"), ("rows_raw3.jsonl", "rows_raw3f.jsonl")]:
    rows = [json.loads(line) for line in (HERE / src).read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    stats = {"kept": 0, "restored": 0, "dropped": 0}
    relabel = {"correct": 0, "correct_qualified": 0, "refusal": 0, "wrong": 0}
    for row in rows:
        if row.get("error") and not row.get("tokens"):
            stats["dropped"] += 1
            continue
        answer = (row.get("answer") or "").strip()
        if answer:
            stats["kept"] += 1
            out.append(row)
            continue
        tokens = row.get("tokens") or []
        text = "".join(t.get("token", "") if isinstance(t, dict) else str(t) for t in tokens).strip()
        if not text:
            stats["dropped"] += 1
            continue
        fixed = dict(row)
        fixed["answer"] = text
        question = QUESTIONS.get(row.get("qid"))
        if question:
            verdict, matched = collect3.label(text, question[3], question[4])
            fixed["verdict"] = verdict
            fixed["matched"] = matched
            fixed["correct"] = verdict in ("correct", "correct_qualified")
        fixed["repaired"] = True
        out.append(fixed)
        stats["restored"] += 1
        relabel[fixed.get("verdict", "wrong")] = relabel.get(fixed.get("verdict", "wrong"), 0) + 1

    (HERE / dst).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n", encoding="utf-8")
    print(f"{src}: had {len(rows)}, {stats}, in {dst} {len(out)} rows; relabeled {relabel}")

for dst in ["rows_raw2f.jsonl", "rows_raw3f.jsonl"]:
    rows = [json.loads(line) for line in (HERE / dst).read_text(encoding="utf-8").splitlines() if line.strip()]
    empty = [r for r in rows if not (r.get("answer") or "").strip()]
    print(f"{dst}: empty {len(empty)}, repaired {sum(1 for r in rows if r.get('repaired'))}, "
          f"correct {sum(1 for r in rows if r.get('correct'))}, wrong {sum(1 for r in rows if not r.get('correct'))}")
