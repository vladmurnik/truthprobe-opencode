/**
 * TruthProbe — data types.
 *
 * Everything defined here is the contract between the provider layer (which
 * collects logprobs from the stream), the scoring layer (pure functions) and
 * the UI/plugins.
 */

import type { ConfidenceLevel } from "./levels.js"

/** One alternative token from `top_logprobs`. */
export interface TopLogprob {
  token: string;
  logprob: number;
}

/** One generated token with its probability (and, optionally, top-K). */
export interface TokenLogprob {
  token: string;
  logprob: number;
  top?: TopLogprob[];
}

/** Score of a single sentence. */
export interface SentenceScore {
  /** Ordinal number of the sentence in the answer, zero-based. */
  i: number;
  /** Start offset in the source text (inclusive). */
  start: number;
  /** End offset (exclusive). */
  end: number;
  /** Source text of the sentence. */
  text: string;
  /** 0..1, higher is more confident. */
  score: number;
  /** 1 - score. */
  risk: number;
  /** Geometric mean of the probabilities of the content tokens. */
  meanLp: number;
  /** Minimum logprob among content tokens (the worst token). */
  minLp: number;
  /** Confidence in the first content token of the sentence. */
  phi: number;
  /** How many content tokens landed in the sentence. */
  tokens: number;
  /** score < 1 - riskyThreshold. */
  flag: boolean;
  /** Confidence level by score: safe | likely | uncertain | risky | unreliable. */
  level: ConfidenceLevel;
}

/** Result over the whole answer. */
export interface AnswerScore {
  status: "ok" | "partial" | "unavailable";
  /** 0..1, or null when there is no signal. */
  score: number | null;
  risk: number | null;
  /** Confidence level by score; null when there is no signal. */
  level: ConfidenceLevel | null;
  /** Confidence in the first content token of the whole answer. */
  first: { score: number; entropy: number; token: string } | null;
  sentences: SentenceScore[];
  /** Number of sentences with flag = true. */
  flagged: number;
  /** Reason for unavailability (for the UI). */
  reason?: string;
}

export interface ScoreOptions {
  /** Size of the top-K over which entropy was computed. */
  topK?: number;
  /** Risk threshold for highlighting. */
  riskyThreshold?: number;
  /** Minimum length of a content token to count it as meaningful. */
  minTokenChars?: number;
  /** Share of the whole-answer weight given to the global geometric mean. */
  globalWeight?: number;
  /** Scorer: null/undefined — the built-in formula (see scorer.ts). */
  scorer?: Scorer | null;
}

/** Features the scorer receives for a set of tokens. */
export interface ScorerFeatures {
  /** ln of the geometric mean of probabilities. */
  meanLp: number;
  /** ln of the worst token probability. */
  minLp: number;
  /** Mean first-token confidence over top-K. */
  meanPhi: number;
  /** Share of tokens with probability below 0.5. */
  fracLow: number;
  /**
   * Share of text characters that are digits (0..1).
   * The only text feature measured on real data: in the commissioned-lie set the
   * answers are shorter and almost digit-free, so the feature adds AUROC
   * (0.774 → 0.808 in the trained model), but it is not part of the default score.
   */
  digitDensity: number;
  /** How many tokens took part. */
  tokens: number;
}

export interface ScorerInput {
  features: ScorerFeatures;
  /** Text the tokens belong to (for models that look at the text). */
  text: string;
  /** Model that generated the answer (`providerID/modelID`); for per-model weights. */
  model?: string;
}

export interface Scorer {
  /** Name for logs and diagnostics. */
  name: string;
  /** 0..1, higher is more confident. */
  score(input: ScorerInput): number;
}

/** Linear model weights; prepared by `scripts/calibrate.py --fit`. */
export interface LinearWeights {
  bias: number;
  meanLp: number;
  minLp: number;
  meanPhi: number;
  fracLow: number;
  /** Optional text weight: old weight files are read as 0. */
  digitDensity?: number;
}

export const DEFAULT_SCORE_OPTIONS: Required<Omit<ScoreOptions, "scorer">> = {
  topK: 20,
  riskyThreshold: 0.45,
  minTokenChars: 2,
  globalWeight: 0.6,
};
