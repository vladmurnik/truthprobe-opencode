#!/usr/bin/env python3
"""Оценка confidence-скоров TruthProbe: AUROC, ECE, Brier и разбивка по уровням.

Скрипт читает JSONL, который пишут `scripts/collect.py` и подобные сборщики
(`data/rows-*.jsonl`), считает score тремя способами и печатает одну таблицу:

    geometric   встроенная формула рантайма (TRUTHPROBE_SCORER=geometric)
    global      линейная модель по общим весам из `--weights`
    per-model   веса `models[<model>]` из бандла, иначе global

Признаки берутся ровно те же, что в рантайме (`src/truthprobe/scorer.ts`):

    meanLp  = средний logprob по содержательным токенам ответа
    minLp   = худший logprob
    phi     = meanPhi, уверенность первого токена (1 - нормированная энтропия)
    fracLow = доля токенов с logprob < ln 0.5

Формулы:

    geometric = clamp01(0.4*exp(meanLp) + 0.3*exp(minLp) + 0.3*phi)
    linear    = clamp01(sigmoid(bias + w1*meanLp + w2*minLp + w3*phi + w4*fracLow))

Границы уровней — те же, что в `src/truthprobe/levels.ts`:
safe >= 0.90, likely >= 0.75, uncertain >= 0.55, risky >= 0.35, иначе unreliable.

Метрики:

    AUROC  ранговая статистика Манна—Уитни (связанным score — средний ранг)
    ECE    sum(n_b/N * |acc_b - conf_b|) по равным интервалам [0,1]
    Brier  mean((p - y)^2)

Строки без числовых признаков (у них обычно есть `error`) и строки без метки
пропускаются, но их количество печатается по причинам: молча выбрасывать
нельзя, иначе метрика смещается в сторону удачных запросов.

Одноклассовые данные — не ошибка. Если все метки 1 или все 0, AUROC печатается
как `n/a (one class)`, а ECE и Brier считаются. Так выглядит честная реальность
`data/rows-all-models.jsonl`: там 96 строк с признаками и ни одного отрицания.

Примеры:

    python3 scripts/evaluate.py data/eval-fixture.jsonl
    python3 scripts/evaluate.py data/eval-fixture.jsonl --weights w.json --json
    python3 scripts/evaluate.py data/rows-all-models.jsonl --min-auroc 0.7

`--min-auroc` — гейт для CI: код возврата 1, если лучший AUROC ниже порога или
не измерим (в том числе на одноклассовых данных). `--json` печатает одну
машиночитаемую строку с теми же числами и ничего больше.
"""

from __future__ import annotations

import argparse
import json
import math
import sys

FEATURES = ("bias", "meanLp", "minLp", "meanPhi", "fracLow")

# Порядок и границы — как в src/truthprobe/levels.ts.
LEVELS = ("safe", "likely", "uncertain", "risky", "unreliable")
BOUNDS = {"safe": 0.90, "likely": 0.75, "uncertain": 0.55, "risky": 0.35}

SKIP_TEXT = {
    "bad_json": "битая строка JSON",
    "no_features": "нет числовых признаков (ошибка сбора)",
    "label_missing": "метка пустая (null / unverifiable)",
    "label_invalid": "метка не 0/1",
}

LABEL_TRUE = {"1", "true", "yes", "y", "correct", "ok"}
LABEL_FALSE = {"0", "false", "no", "n", "wrong", "incorrect"}
LABEL_EMPTY = {"", "null", "none", "nan", "unverifiable", "unknown", "?"}


def number(value) -> float | None:
    """Число из JSON или None. Строки вида "0.88" принимаются, bool — нет."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError:
            return None
        return result if math.isfinite(result) else None
    return None


def label_of(value) -> tuple[bool | None, str | None]:
    """Метка -> (True/False, причина пропуска). Поддерживает bool, 0/1 и строки."""
    if isinstance(value, bool):
        return value, None
    if isinstance(value, (int, float)):
        if value == 0 or value == 1:
            return bool(value), None
        return None, "label_invalid"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in LABEL_TRUE:
            return True, None
        if text in LABEL_FALSE:
            return False, None
        if text in LABEL_EMPTY:
            return None, "label_missing"
        return None, "label_invalid"
    if value is None:
        return None, "label_missing"
    return None, "label_invalid"


def clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    grown = math.exp(z)
    return grown / (1.0 + grown)


def load_rows(path: str) -> tuple[list[dict], dict[str, int], int]:
    """Читает JSONL. Возвращает (строки для оценки, счётчик причин пропуска, строк всего)."""
    rows: list[dict] = []
    skipped: dict[str, int] = {}
    total = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad_json"] = skipped.get("bad_json", 0) + 1
                continue
            if not isinstance(raw, dict):
                skipped["bad_json"] = skipped.get("bad_json", 0) + 1
                continue
            mean_lp = number(raw.get("meanLp"))
            min_lp = number(raw.get("minLp"))
            phi = number(raw.get("phi"))
            if mean_lp is None or min_lp is None or phi is None:
                skipped["no_features"] = skipped.get("no_features", 0) + 1
                continue
            label, reason = label_of(raw.get("label"))
            if label is None:
                key = reason or "label_invalid"
                skipped[key] = skipped.get(key, 0) + 1
                continue
            frac_low = number(raw.get("fracLow"))
            rows.append(
                {
                    "model": raw.get("model") if isinstance(raw.get("model"), str) else None,
                    "meanLp": mean_lp,
                    "minLp": min_lp,
                    "meanPhi": phi,
                    "fracLow": 0.0 if frac_low is None else frac_low,
                    "label": label,
                }
            )
    return rows, skipped, total


def geometric_score(row: dict) -> float:
    """Ровно формула geometricScorer() из src/truthprobe/scorer.ts."""
    return clamp01(
        0.4 * math.exp(row["meanLp"]) + 0.3 * math.exp(row["minLp"]) + 0.3 * row["meanPhi"]
    )


def linear_score(weights: dict, row: dict) -> float:
    """Ровно linearScorer(): x = [1, meanLp, minLp, meanPhi, fracLow]."""
    z = (
        weights["bias"]
        + weights["meanLp"] * row["meanLp"]
        + weights["minLp"] * row["minLp"]
        + weights["meanPhi"] * row["meanPhi"]
        + weights["fracLow"] * row["fracLow"]
    )
    if not math.isfinite(z):
        return geometric_score(row)
    return clamp01(sigmoid(z))


def parse_weights(node) -> tuple[dict | None, str | None]:
    """Один набор весов. Понимает и голые веса, и обёртку {"weights": ...}."""
    if node is None:
        return None, "null или отсутствует"
    if not isinstance(node, dict):
        return None, "веса не объект"
    source = node.get("weights", node)
    if source is None:
        return None, "weights: null"
    if not isinstance(source, dict):
        return None, "weights не объект"
    out: dict[str, float] = {}
    for key in FEATURES:
        value = number(source.get(key))
        if value is None:
            return None, f"вес {key!r} отсутствует или не число"
        out[key] = value
    return out, None


def load_weights(path: str) -> dict:
    """Читает бандл `{global, models}` или плоский JSON — как parseWeightsBundle()."""
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("ожидался JSON-объект с весами")

    bundled = any(key in raw for key in ("global", "models", "features"))
    if bundled:
        global_node = raw.get("global")
        if global_node is None:
            global_node = raw.get("weights")
    else:
        global_node = raw
    global_weights, global_reason = parse_weights(global_node)

    models: dict[str, dict] = {}
    without_weights: list[dict] = []
    source = raw.get("models") if bundled else None
    if isinstance(source, dict):
        for name, node in source.items():
            weights, reason = parse_weights(node)
            if weights is None:
                without_weights.append({"model": name, "reason": reason})
            else:
                models[name] = weights

    return {
        "path": path,
        "global": global_weights,
        "global_reason": global_reason,
        "models": models,
        "without_weights": without_weights,
    }


def auroc(pairs: list[tuple[float, bool]]) -> float | None:
    """Манн—Уитни через ранги: связанным score достаётся средний ранг."""
    positives = sum(1 for _, label in pairs if label)
    negatives = len(pairs) - positives
    if not positives or not negatives:
        return None
    order = sorted(range(len(pairs)), key=lambda index: pairs[index][0])
    ranks = [0.0] * len(pairs)
    position = 0
    while position < len(order):
        value = pairs[order[position]][0]
        stop = position
        while stop + 1 < len(order) and pairs[order[stop + 1]][0] == value:
            stop += 1
        average = (position + 1 + stop + 1) / 2.0
        for index in range(position, stop + 1):
            ranks[order[index]] = average
        position = stop + 1
    rank_sum = sum(ranks[index] for index in range(len(pairs)) if pairs[index][1])
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def ece(pairs: list[tuple[float, bool]], bins: int) -> float | None:
    """sum(n_b/N * |acc_b - conf_b|) по равным интервалам [0,1]; score==1 идёт в последний."""
    if not pairs:
        return None
    totals = [0] * bins
    scores = [0.0] * bins
    positives = [0] * bins
    for score, label in pairs:
        index = min(int(clamp01(score) * bins), bins - 1)
        totals[index] += 1
        scores[index] += clamp01(score)
        positives[index] += 1 if label else 0
    result = 0.0
    size = len(pairs)
    for index in range(bins):
        if totals[index] == 0:
            continue
        confidence = scores[index] / totals[index]
        accuracy = positives[index] / totals[index]
        result += totals[index] / size * abs(accuracy - confidence)
    return result


def brier(pairs: list[tuple[float, bool]]) -> float | None:
    """mean((p - y)^2)."""
    if not pairs:
        return None
    return sum((clamp01(score) - (1.0 if label else 0.0)) ** 2 for score, label in pairs) / len(pairs)


def level_of(score: float) -> str:
    for name in ("safe", "likely", "uncertain", "risky"):
        if score >= BOUNDS[name]:
            return name
    return "unreliable"


def level_breakdown(pairs: list[tuple[float, bool]]) -> dict[str, dict]:
    counts = {name: {"rows": 0, "positives": 0} for name in LEVELS}
    for score, label in pairs:
        entry = counts[level_of(clamp01(score))]
        entry["rows"] += 1
        entry["positives"] += 1 if label else 0
    for entry in counts.values():
        entry["correct_rate"] = round(entry["positives"] / entry["rows"], 4) if entry["rows"] else None
    return counts


def metrics(pairs: list[tuple[float, bool]], bins: int) -> dict | None:
    if not pairs:
        return None
    positives = sum(1 for _, label in pairs if label)
    return {
        "rows": len(pairs),
        "positives": positives,
        "negatives": len(pairs) - positives,
        "auroc": auroc(pairs),
        "ece": ece(pairs, bins),
        "brier": brier(pairs),
        "levels": level_breakdown(pairs),
    }


def build_modes(rows: list[dict], bundle: dict | None, bins: int) -> tuple[dict, dict]:
    """Считает три режима. Возвращает (метрики по режимам, диагностика весов)."""
    modes: dict[str, dict | None] = {}
    modes["geometric"] = metrics(
        [(geometric_score(row), row["label"]) for row in rows], bins
    )
    details = {"matched": 0, "global_reason": None, "without_weights": [], "models": 0}
    if bundle is None:
        return modes, details

    global_weights = bundle["global"]
    details["global_reason"] = bundle["global_reason"]
    details["without_weights"] = bundle["without_weights"]
    details["models"] = len(bundle["models"])

    if global_weights is None:
        modes["global"] = None
    else:
        modes["global"] = metrics(
            [(linear_score(global_weights, row), row["label"]) for row in rows], bins
        )

    pairs: list[tuple[float, bool]] = []
    matched = 0
    for row in rows:
        own = bundle["models"].get(row["model"]) if row["model"] else None
        if own is not None:
            matched += 1
            pairs.append((linear_score(own, row), row["label"]))
        elif global_weights is not None:
            pairs.append((linear_score(global_weights, row), row["label"]))
    details["matched"] = matched
    modes["per-model"] = metrics(pairs, bins)
    return modes, details


def fmt_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def best_auroc(modes: dict[str, dict | None]) -> tuple[float | None, str | None]:
    candidates = [(entry["auroc"], name) for name, entry in modes.items() if entry and entry["auroc"] is not None]
    if not candidates:
        return None, None
    value, name = max(candidates, key=lambda item: item[0])
    return value, name


def print_table(modes: dict[str, dict | None], notes: dict[str, str]) -> None:
    print(f"{'mode':10s} {'rows':>4s} {'AUROC':>7s} {'ECE':>7s} {'Brier':>7s}")
    for name in ("geometric", "global", "per-model"):
        entry = modes.get(name)
        if entry is None:
            print(f"{name:10s} {'--':>4s} {'skipped':>7s}  {notes.get(name, 'нет данных')}")
            continue
        print(
            f"{name:10s} {entry['rows']:4d} {fmt_metric(entry['auroc']):>7s} "
            f"{entry['ece']:7.3f} {entry['brier']:7.3f}"
        )


def print_levels(modes: dict[str, dict | None]) -> None:
    for name in ("geometric", "global", "per-model"):
        entry = modes.get(name)
        if entry is None:
            continue
        print(f"\nуровни {name}:")
        for level in LEVELS:
            info = entry["levels"][level]
            if info["rows"] == 0:
                print(f"  {level}: 0 rows, n/a")
            else:
                share = 100.0 * (info["correct_rate"] or 0.0)
                print(f"  {level}: {info['rows']} rows, {share:.0f}% correct")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", help="JSONL со строками: model, meanLp, minLp, phi, fracLow, label")
    parser.add_argument("--weights", help="JSON с весами: бандл {global, models} или плоские веса")
    parser.add_argument("--json", action="store_true", help="напечатать один JSON-объект вместо таблицы")
    parser.add_argument("--min-auroc", type=float, help="порог для CI: код 1, если лучший AUROC ниже")
    parser.add_argument("--bins", type=int, default=10, help="число интервалов ECE (по умолчанию 10)")
    args = parser.parse_args()

    if args.bins < 1:
        parser.error("--bins должен быть >= 1")

    try:
        rows, skipped, total = load_rows(args.path)
    except OSError as error:
        print(f"ошибка: не читается {args.path}: {error}", file=sys.stderr)
        return 2
    if not rows:
        print(
            f"ошибка: в {args.path} нет строк с числовыми meanLp/minLp/phi и меткой 0/1",
            file=sys.stderr,
        )
        return 2

    bundle = None
    if args.weights:
        try:
            bundle = load_weights(args.weights)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"ошибка: не читаются веса {args.weights}: {error}", file=sys.stderr)
            return 2
        if bundle["global"] is None and not bundle["models"]:
            print(
                f"предупреждение: в {args.weights} нет пригодных весов ({bundle['global_reason']})",
                file=sys.stderr,
            )

    modes, details = build_modes(rows, bundle, args.bins)

    if bundle is None:
        skip_notes = {"global": "нет файла весов", "per-model": "нет файла весов"}
    else:
        skip_notes = {
            "global": f"в весах нет global ({details['global_reason']})",
            "per-model": "ни одна строка не получила весов",
        }

    positives = sum(1 for row in rows if row["label"])
    negatives = len(rows) - positives
    one_class = positives == 0 or negatives == 0
    best, best_mode = best_auroc(modes)
    skipped_total = sum(skipped.values())

    gate_ok: bool | None = None
    gate_reason = "порог не задан"
    if args.min_auroc is not None:
        if best is None:
            gate_ok = False
            gate_reason = (
                "AUROC не измерим (один класс)" if one_class else "AUROC не измерим (нет строк)"
            )
        elif best < args.min_auroc:
            gate_ok = False
            gate_reason = f"лучший AUROC {best:.3f} ({best_mode}) < {args.min_auroc:.3f}"
        else:
            gate_ok = True
            gate_reason = f"лучший AUROC {best:.3f} ({best_mode}) >= {args.min_auroc:.3f}"

    payload = {
        "file": args.path,
        "rows_total": total,
        "rows_scored": len(rows),
        "skipped": {"total": skipped_total, "reasons": dict(sorted(skipped.items()))},
        "positives": positives,
        "negatives": negatives,
        "one_class": one_class,
        "bins": args.bins,
        "levels": list(LEVELS),
        "modes": {
            name: (
                None
                if entry is None
                else {
                    "rows": entry["rows"],
                    "positives": entry["positives"],
                    "negatives": entry["negatives"],
                    "auroc": None if entry["auroc"] is None else round(entry["auroc"], 4),
                    "ece": None if entry["ece"] is None else round(entry["ece"], 4),
                    "brier": None if entry["brier"] is None else round(entry["brier"], 4),
                    "levels": entry["levels"],
                }
            )
            for name, entry in modes.items()
        },
        "weights": None
        if bundle is None
        else {
            "file": bundle["path"],
            "global": bundle["global"] is not None,
            "global_reason": bundle["global_reason"],
            "models": details["models"],
            "models_without_weights": details["without_weights"],
            "per_model_matched": details["matched"],
        },
        "best_auroc": None if best is None else round(best, 4),
        "best_mode": best_mode,
        "min_auroc": args.min_auroc,
        "gate": {"ok": gate_ok, "reason": gate_reason},
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"== {args.path}: {len(rows)} строк в оценке, пропущено {skipped_total} из {total}")
        for key in ("bad_json", "no_features", "label_missing", "label_invalid"):
            if skipped.get(key):
                print(f"   пропуск: {SKIP_TEXT[key]} — {skipped[key]}")
        print(f"классы: положительных {positives}, отрицательных {negatives}")
        if one_class:
            print("AUROC n/a (one class)")
        models_seen = len({row["model"] for row in rows if row["model"]})
        print(f"моделей среди оценённых строк: {models_seen}")

        if bundle is not None:
            weights_note = f"веса: {bundle['path']} — global "
            weights_note += "есть" if bundle["global"] is not None else f"нет ({bundle['global_reason']})"
            weights_note += f", моделей с весами {details['models']}"
            if details["without_weights"]:
                weights_note += f", без весов {len(details['without_weights'])}"
            print(weights_note)
            if details["models"]:
                print(
                    f"per-model: {details['matched']} из {len(rows)} строк получили свои веса "
                    "(ключи models — <provider>/<model>)"
                )

        print_table(modes, skip_notes)
        print_levels(modes)

        if args.min_auroc is not None:
            verdict = "ok" if gate_ok else "провал"
            print(f"\nгейт --min-auroc {args.min_auroc:.3f}: {verdict} — {gate_reason}")

    if gate_ok is False:
        if args.json:
            print(f"гейт --min-auroc {args.min_auroc:.3f}: провал — {gate_reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
