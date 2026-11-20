#!/usr/bin/env python3
"""Дополняет openai-chat.ts экспортами, чтобы TruthProbe можно было тестировать.

Идемпотентен: повторный запуск ничего не ломает.
"""
import pathlib
import sys

ROOT = pathlib.Path("/home/adik/src/opencode")
TARGET = ROOT / "packages/ai/src/protocols/openai-chat.ts"

src = TARGET.read_text(encoding="utf-8")


def replace(old: str, new: str, label: str) -> None:
    global src
    if new in src:
        print(f"skip (already applied): {label}")
        return
    if old not in src:
        print(f"FAIL anchor not found: {label}")
        sys.exit(1)
    src = src.replace(old, new, 1)
    print(f"ok: {label}")


replace(
    """/** Сколько альтернатив просим в top_logprobs для TruthProbe. */
const TRUTHPROBE_TOP_K = 20

/**
 * TruthProbe включён, если модель объявила `capabilities.logprobs`,
 * иначе — по переменной окружения OPENCODE_TRUTHPROBE=1.
 */
const truthprobeEnabled = (model: { capabilities?: { logprobs?: boolean } }) => {
  if (model.capabilities?.logprobs !== undefined) return model.capabilities.logprobs
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
  const flag = env?.OPENCODE_TRUTHPROBE
  return flag === "1" || flag === "on" || flag === "true"
}
""",
    """/** Сколько альтернатив просим в top_logprobs для TruthProbe. */
export const TRUTHPROBE_TOP_K = 20

/**
 * TruthProbe включён, если модель объявила `capabilities.logprobs`,
 * иначе — по переменной окружения OPENCODE_TRUTHPROBE=1.
 */
export const truthprobeEnabled = (model: { capabilities?: { logprobs?: boolean } }) => {
  if (model.capabilities?.logprobs !== undefined) return model.capabilities.logprobs
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
  const flag = env?.OPENCODE_TRUTHPROBE
  return flag === "1" || flag === "on" || flag === "true"
}

/**
 * Поля запроса, которые включает TruthProbe. Отдельная функция, чтобы
 * поведение «просим logprobs» покрывалось тестом без сборки всего тела.
 */
export const truthprobeBody = (model: { capabilities?: { logprobs?: boolean } }) =>
  truthprobeEnabled(model) ? { logprobs: true, top_logprobs: TRUTHPROBE_TOP_K } : {}
""",
    "export helpers",
)

replace(
    """    // TruthProbe: только для моделей, у которых провайдер отдаёт logprobs.
    ...(truthprobeEnabled(request.model) ? { logprobs: true, top_logprobs: TRUTHPROBE_TOP_K } : {}),""",
    """    // TruthProbe: только для моделей, у которых провайдер отдаёт logprobs.
    ...truthprobeBody(request.model),""",
    "use truthprobeBody in fromRequest",
)

replace(
    """/** Приводит logprobs дельты к компактному виду для providerMetadata. */
const truthprobeFromDelta = (logprobs: OpenAIChatLogprobs | null | undefined) => {""",
    """export interface TruthprobeToken {
  token: string
  logprob: number
  top?: Array<{ token: string; logprob: number }>
}

/** Приводит logprobs дельты к компактному виду для providerMetadata. */
export const truthprobeFromDelta = (
  logprobs: { content?: OpenAIChatLogprobs["content"] } | null | undefined,
): TruthprobeToken[] | undefined => {""",
    "export truthprobeFromDelta",
)

TARGET.write_text(src, encoding="utf-8")
print("written", TARGET)
