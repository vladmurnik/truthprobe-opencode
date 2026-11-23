/**
 * TruthProbe — confidence scale.
 *
 * The single place where score turns into a human-readable level. The level travels
 * in the payload next to the number so that session-ui, TUI and REST all say the same thing.
 *
 * Important: score is the model's confidence in its own tokens, not the probability
 * that the answer is true. A deterministic gateway (logprob ≈ -0.001) gives
 * "safe" on any text, including a made-up one.
 */

/** Confidence level of an answer or a sentence. */
export type ConfidenceLevel = "safe" | "likely" | "uncertain" | "risky" | "unreliable"

/** Lower bounds of the levels by score. Anything below the last bound is unreliable. */
export const LEVEL_BOUNDS = {
  safe: 0.9,
  likely: 0.75,
  uncertain: 0.55,
  risky: 0.35,
} as const

/** Levels from reliable to unreliable — the order for the UI and the docs. */
export const LEVEL_ORDER = ["safe", "likely", "uncertain", "risky", "unreliable"] as const

/** What a level means in words. */
export const LEVEL_TEXT: Record<ConfidenceLevel, string> = {
  safe: "no visible hesitation",
  likely: "confident",
  uncertain: "noticeable hesitation",
  risky: "shaky",
  unreliable: "mostly guessing",
}

/**
 * Turns a score into a level. `null`/`NaN`/`undefined` — no level (no signal),
 * rather than "the worst one".
 */
export function levelOf(score: number | null | undefined): ConfidenceLevel | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null
  if (score >= LEVEL_BOUNDS.safe) return "safe"
  if (score >= LEVEL_BOUNDS.likely) return "likely"
  if (score >= LEVEL_BOUNDS.uncertain) return "uncertain"
  if (score >= LEVEL_BOUNDS.risky) return "risky"
  return "unreliable"
}

/** A level is a reason to highlight the line: only `risky` and `unreliable`. */
export function isDoubtful(level: ConfidenceLevel | null | undefined): boolean {
  return level === "risky" || level === "unreliable"
}
