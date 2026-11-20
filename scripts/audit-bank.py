#!/usr/bin/env python3
"""Ищет в банке вопросов такие, где ошибается не модель, а сам эталон.

Идея простая. Если несколько РАЗНЫХ моделей независимо дают один и тот же ответ,
которого нет в `expect`, то вероятнее всего неправ эталон (или вопрос
сформулирован двусмысленно), а не все модели сразу. Именно так и появились
«уверенно неверные» ответы: на вопрос «Which is the largest planet in the Solar
System: Saturn or Neptune?» три модели из четырёх ответили «Saturn» — потому что
вопрос предлагает выбор между Сатурном и Нептуном, а ожидался «jupiter», которого
среди вариантов нет. Лейбл `0` в этом случае — брак данных, а не сигнал.

Скрипт ничего не меняет: он только показывает, какие пункты банка надо
перечитать руками, и выходит с кодом 1, если такие есть (годится для CI).

    python3 scripts/audit-bank.py data/qa-hard-bank.jsonl data/rows-hard.jsonl
    python3 scripts/audit-bank.py bank.jsonl rows.jsonl --json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict

WORD = re.compile(r"[a-z0-9]+")


def norm(text: str) -> str:
    return " ".join(WORD.findall((text or "").lower()))


def matches(answer: str, expect: list[str]) -> bool:
    """То же правило, что в collect.py: короткое — по границе слова, длинное — подстрокой."""
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
    """Вопрос предлагает выбор «X or Y», а ожидаемого ответа нет среди вариантов."""
    options = re.findall(r"([A-Za-z][A-Za-z .'-]{2,30}?)\s+or\s+([A-Za-z][A-Za-z .'-]{2,30})", prompt)
    if not options:
        return False
    offered = norm(" ".join(options[0]))
    return not any(norm(item) in offered for item in expect)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bank")
    parser.add_argument("rows")
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    parser.add_argument("--min-models", type=int, default=2, help="сколько моделей должны согласиться (default 2)")
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
        if not per_model:
            continue
        modals = {model: counter.most_common(1)[0][0] for model, counter in per_model.items()}
        agree = [model for model, answer in modals.items() if not matches(answer, expect)]
        total = len(modals)
        conflict = premise_conflict(prompt, expect)
        if conflict or (len(agree) >= max(args.min_models, math.ceil(total / 2)) and total >= 2):
            findings.append(
                {
                    "prompt": prompt,
                    "expect": expect,
                    "models": total,
                    "disagreeing": len(agree),
                    "modals": modals,
                    "premise_conflict": conflict,
                }
            )

    findings.sort(key=lambda item: (-item["disagreeing"], item["prompt"]))

    if args.json:
        print(json.dumps({"findings": findings, "checked": len(bank)}, ensure_ascii=False, indent=2))
    else:
        print(f"проверено пунктов банка: {len(bank)}, подозрительных: {len(findings)}")
        for item in findings:
            why = "выбор в вопросе противоречит эталону" if item["premise_conflict"] else "модели согласны против эталона"
            print(f"\n- {item['prompt']}")
            print(f"  эталон: {item['expect']} | причина: {why}")
            for model, answer in item["modals"].items():
                mark = " " if matches(answer, item["expect"]) else "!"
                print(f"  {mark} {model}: {answer!r}")
        if findings:
            print("\nЭто брак банка, а не ошибки моделей: такие лейблы нельзя использовать в обучении.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
