#!/usr/bin/env python3
"""Проверяет банк вопросов: где ошибка в данных, а где модели действительно врут.

Три разных диагноза, и путать их нельзя:

- `bank_error` — вопрос сам подсказывает неверный ответ («Saturn or Neptune», а в
  эталоне `jupiter`). Такой лейбл `0` — брак данных, а не сигнал. Это exit 1.
- `ambiguous` — модели расходятся между собой (у них разные модальные ответы).
  Значит вопрос допускает разные прочтения, и на нём нельзя учить. Это exit 1.
- `suspect` — все модели независимо дают ОДИН И ТОТ ЖЕ ответ, которого нет в
  эталоне. Либо эталон врёт, либо модели одинаково ошибаются. Это именно тот
  случай, ради которого собирают негативы, поэтому по умолчанию это
  предупреждение, а не провал (`--strict` превращает его в провал).

Скрипт ничего не меняет: только показывает пункты, которые надо перечитать руками.

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


def classify(prompt: str, expect: list[str], modals: dict[str, str]) -> tuple[str | None, str]:
    """Возвращает (диагноз, человеческое объяснение) или (None, '')."""
    total = len(modals)
    if total < 2:
        return None, ""
    if premise_conflict(prompt, expect):
        return "bank_error", "выбор в вопросе противоречит эталону"
    wrong = {model: answer for model, answer in modals.items() if not matches(answer, expect)}
    if not wrong:
        return None, ""
    distinct = {answer for answer in wrong.values()}
    if len(wrong) == total and len(distinct) == 1:
        return "suspect", "все модели дают один и тот же ответ мимо эталона"
    if len(distinct) > 1:
        return "ambiguous", "модели расходятся между собой — вопрос допускает разные прочтения"
    if len(wrong) >= max(2, (total + 1) // 2):
        return "suspect", "большинство моделей согласно против эталона"
    return None, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bank")
    parser.add_argument("rows")
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    parser.add_argument("--strict", action="store_true", help="считать suspect провалом")
    parser.add_argument("--min-models", type=int, default=2, help="сколько моделей нужно для диагноза (default 2)")
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
            f"проверено пунктов банка: {len(bank)} | брак банка: {errors} | "
            f"двусмысленных: {ambiguous} | моделей поймали на неверном ответе: {suspects}"
        )
        for item in findings:
            print(f"\n- [{item['diagnosis']}] {item['prompt']}")
            print(f"  эталон: {item['expect']} | {item['why']}")
            for model, answer in item["modals"].items():
                mark = " " if matches(answer, item["expect"]) else "!"
                print(f"  {mark} {model}: {answer!r}")
        if errors or ambiguous:
            print("\nПервые два диагноза — брак данных: такие пункты нельзя использовать в обучении.")
        if suspects:
            print("\nsuspect — это либо брак эталона, либо настоящая ошибка всех моделей; решается руками.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
