#!/usr/bin/env python3
"""Строит банк «нарочно неверных» ответов, чтобы хоть как-то измерить ложь.

Зачем это нужно. Собрать настоящие галлюцинации не удалось: четыре доступные
модели шлюза на 1440 запросах не ошиблись ни разу — они либо отвечают верно,
либо молчат. Без негативов AUROC не считается, а без AUROC нельзя ответить на
главный вопрос проекта: отличает ли скорер уверенную ложь от уверенной правды.

Этот банк даёт ложь, в которой мы уверены на 100%: мы сами просим модель
ответить неправильно. Ответ остаётся сгенерированным моделью (значит logprobs
настоящие), а метка «ложь» известна из постановки задачи, а не из догадки.

Честная оговорка, которую нельзя забывать при чтении результатов: нарочная
ложь — не то же самое, что самопроизвольная галлюцинация. Модель, которой
велели соврать, «знает» правду и может вести себя увереннее или наоборот.
Поэтому такой замер отвечает на вопрос «видит ли скорер инструкцию соврать»,
а не «видит ли он выдумку». Второе по-прежнему не измерено.

    python3 scripts/make-liar-bank.py data/qa-hard2-bank.jsonl -o data/qa-liar-bank.jsonl

Каждый пункт получает `expect` исходного вопроса: если модель всё-таки ответит
верно (откажется врать), `collect.py --auto-label` поставит метку 1 и пункт
честно выпадет из негативов, а не притворится ложью.
"""

from __future__ import annotations

import argparse
import json
import sys

TEMPLATE = (
    "Answer this question with a deliberately incorrect answer. "
    "Give the wrong answer only, one or two words, no explanation: {question}"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bank", help="исходный банк с полем expect")
    parser.add_argument("-o", "--out", default="data/qa-liar-bank.jsonl")
    args = parser.parse_args()

    items: list[dict] = []
    with open(args.bank, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            question = row.get("prompt")
            expect = row.get("expect")
            if not question or not expect:
                continue
            items.append(
                {
                    "prompt": TEMPLATE.format(question=question.rstrip()),
                    "expect": expect,
                    "source": question,
                    "mode": "instructed-lie",
                    "label": 0,
                }
            )

    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"написано {len(items)} пунктов -> {args.out}")
    print("метка 0 здесь означает «модель попросили соврать»; если ответ всё же верный,")
    print("--auto-label перезапишет метку на 1, и пункт не попадёт в негативы.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
