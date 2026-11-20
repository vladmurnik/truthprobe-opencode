/**
 * TruthProbe — шкала уверенности.
 *
 * Одно место, где score превращается в человекочитаемый уровень. Уровень едет
 * в парте рядом с числом, чтобы session-ui, TUI и REST говорили одно и то же.
 *
 * Важно: score — уверенность модели в собственных токенах, а не вероятность
 * того, что ответ правдив. Детерминированный шлюз (logprob ≈ -0.001) даёт
 * "safe" на любом тексте, включая выдуманный.
 */

/** Уровень уверенности ответа или предложения. */
export type ConfidenceLevel = "safe" | "likely" | "uncertain" | "risky" | "unreliable"

/** Нижние границы уровней по score. Всё, что ниже последней границы, — unreliable. */
export const LEVEL_BOUNDS = {
  safe: 0.9,
  likely: 0.75,
  uncertain: 0.55,
  risky: 0.35,
} as const

/** Уровни от надёжного к ненадёжному — порядок для UI и документации. */
export const LEVEL_ORDER = ["safe", "likely", "uncertain", "risky", "unreliable"] as const

/** Что уровень значит словами. */
export const LEVEL_TEXT: Record<ConfidenceLevel, string> = {
  safe: "no visible hesitation",
  likely: "confident",
  uncertain: "noticeable hesitation",
  risky: "shaky",
  unreliable: "mostly guessing",
}

/**
 * Переводит score в уровень. `null`/`NaN`/`undefined` — уровня нет (сигнала нет),
 * а не «самый плохой».
 */
export function levelOf(score: number | null | undefined): ConfidenceLevel | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null
  if (score >= LEVEL_BOUNDS.safe) return "safe"
  if (score >= LEVEL_BOUNDS.likely) return "likely"
  if (score >= LEVEL_BOUNDS.uncertain) return "uncertain"
  if (score >= LEVEL_BOUNDS.risky) return "risky"
  return "unreliable"
}

/** Уровень — повод подсветить строку: только `risky` и `unreliable`. */
export function isDoubtful(level: ConfidenceLevel | null | undefined): boolean {
  return level === "risky" || level === "unreliable"
}
