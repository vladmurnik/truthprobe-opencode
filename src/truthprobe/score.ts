/**
 * TruthProbe — confidence scoring from token logprobs.
 *
 * All functions are pure except for the optional loading of a swappable scorer
 * from `TRUTHPROBE_SCORER` (see scorer.ts): the math is the same and no state
 * accumulates. This lets unit tests cover the whole math on recorded fixtures
 * and lets the module serve both the OpenCode core and offline calibration (T8).
 */

import { levelOf } from "./levels";
import { featuresOf, scorerFromEnv } from "./scorer";
import { splitSentences, type Sentence } from "./sentences";
import {
  DEFAULT_SCORE_OPTIONS,
  type AnswerScore,
  type ScoreOptions,
  type SentenceScore,
  type TokenLogprob,
} from "./types";

const PUNCT_ONLY = /^[\s\p{P}\p{S}]+$/u;

/** A token carries meaning: not whitespace, not pure punctuation/symbols. */
export function isContentToken(token: string, minChars = 2): boolean {
  if (!token) return false;
  if (!/\S/.test(token)) return false;
  if (PUNCT_ONLY.test(token)) return false;
  const visible = token.replace(/\s/g, "")
  if (visible.length >= minChars) return true
  // A hieroglyph/kana/hangul is a whole word in one character and must not be dropped.
  return /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]/.test(visible);
}

/**
 * Normalised entropy of the distribution over the first token.
 *
 * q_i = exp(lp_i) / Σ exp(lp_j) over the available top-K; H = -Σ q_i ln q_i / ln K.
 * If there is no top-K (the provider did not return one) we degrade to 1 - p(token),
 * that is φ = p(token).
 */
export function normalizedEntropy(t: TokenLogprob, topK = 20): number {
  const top = (t.top ?? []).filter((x) => Number.isFinite(x.logprob));
  if (top.length < 2) return clamp01(1 - Math.exp(t.logprob));

  // Entropy and normalisation use one and the same set: taking every alternative
  // while dividing by ln(topK) pushes H above 1 and saturates φ to zero on long top-K lists.
  const k = Math.max(2, Math.min(topK, top.length));
  const probs = top.slice(0, k).map((x) => Math.exp(x.logprob));
  const sum = probs.reduce((a, b) => a + b, 0);
  if (!(sum > 0)) return 1;

  let h = 0;
  for (const p of probs) {
    const q = p / sum;
    if (q > 0) h -= q * Math.log(q);
  }
  return clamp01(h / Math.log(k));
}

/** φ = confidence in the first token, 0..1. */
export function phi(t: TokenLogprob, topK = 20): number {
  return clamp01(1 - normalizedEntropy(t, topK));
}

function clamp01(x: number): number {
  if (!Number.isFinite(x)) return 0;
  return Math.min(1, Math.max(0, x));
}

interface TokenWithOffset extends TokenLogprob {
  start: number;
  end: number;
}

/** Binds tokens to character offsets of the source text. */
export function tokensWithOffsets(tokens: TokenLogprob[]): TokenWithOffset[] {
  const out: TokenWithOffset[] = [];
  let pos = 0;
  for (const t of tokens) {
    const len = t.token.length;
    out.push({ ...t, start: pos, end: pos + len });
    pos += len;
  }
  return out;
}

/**
 * Binds tokens to the text, tolerating "internal" tokens.
 *
 * Providers (reasoning models especially) return tokens with no visible text:
 * `</think>`, service markers, trimmed whitespace. Blind concatenation breaks
 * offsets, so every token is either found in the text near the current position
 * or skipped.
 */
export function alignTokens(text: string, tokens: TokenLogprob[]): TokenWithOffset[] {
  const out: TokenWithOffset[] = [];
  let pos = 0;
  for (const t of tokens) {
    const tok = t.token;
    if (!tok) continue;
    if (text.startsWith(tok, pos)) {
      out.push({ ...t, start: pos, end: pos + tok.length });
      pos += tok.length;
      continue;
    }
    // A token may have lost its leading space/newline: look for it within a small window.
    const at = text.indexOf(tok, pos);
    if (at >= 0 && at - pos <= 8) {
      out.push({ ...t, start: at, end: at + tok.length });
      pos = at + tok.length;
      continue;
    }
    const trimmed = tok.trimStart();
    if (trimmed && trimmed !== tok) {
      const at2 = text.indexOf(trimmed, pos);
      if (at2 >= 0 && at2 - pos <= 8) {
        out.push({ ...t, start: at2, end: at2 + trimmed.length });
        pos = at2 + trimmed.length;
        continue;
      }
    }
    // An internal token with no visible text — skip it without breaking offsets.
  }
  return out;
}

/**
 * The sentence that owns a token's range.
 *
 * A token can start with a space the segmenter already consumed as the tail of
 * the previous sentence (for example " Bad" right after a period), so we check
 * range overlap rather than just the token start.
 */
function sentenceAt(sentences: Sentence[], start: number, end: number): Sentence | null {
  for (const s of sentences) {
    if (start < s.end && end > s.start) return s;
    if (s.start >= end) break;
  }
  return null;
}

/**
 * Fraction of characters that are digits. The same feature is computed in
 * `scripts/collect.py` from the answer text; in the "text vs logprobs" fork it is
 * the only text signal that produced a measurable gain (§15 VALIDATION).
 */
export function digitDensity(text: string): number {
  if (!text) return 0;
  // Count numerator and denominator in code points: `text.length` measures UTF-16
  // units, and on emoji or astral CJK the digit share was understated.
  let digits = 0;
  let chars = 0;
  for (const ch of text) {
    chars++;
    if (ch >= "0" && ch <= "9") digits++;
  }
  return clamp01(digits / chars);
}

function geometricMean(lps: number[]): number {
  if (lps.length === 0) return 0;
  return clamp01(Math.exp(lps.reduce((a, b) => a + b, 0) / lps.length));
}

/**
 * Minimum without `Math.min(...values)`: spreading a long array into arguments
 * fails with `RangeError` on very long answers, and this runs synchronously on publish.
 */
function minOf(values: number[]): number {
  if (values.length === 0) return 0;
  let min = values[0];
  for (const value of values) if (value < min) min = value;
  return min;
}

/** Key of the pseudo-sentence that collects tokens when offsets drift. */
const DRIFT_BUCKET = -1;

/**
 * Computes confidence over the whole answer.
 *
 * @param text  final answer text (the same one whose tokens arrived in `tokens`)
 * @param tokens logprobs per token in generation order
 */
export function scoreAnswer(
  text: string,
  tokens: TokenLogprob[],
  options: ScoreOptions = {},
  /** `providerID/modelID` — so the swappable scorer can use this model's weights. */
  model?: string,
): AnswerScore {
  const opt = { ...DEFAULT_SCORE_OPTIONS, ...envScoreOptions(), ...options };
  const scorer = opt.scorer === undefined ? scorerFromEnv() : opt.scorer;

  if (!tokens.length) {
    return {
      status: "unavailable",
      score: null,
      risk: null,
      level: null,
      first: null,
      sentences: [],
      flagged: 0,
      reason: "no logprobs in response",
    };
  }

  const withOffsets = alignTokens(text, tokens);
  const sentences = splitSentences(text);

  // Offset drift: the tail of the answer is not covered by tokens, so binding to
  // sentences is unreliable and we signal partial.
  const totalLen = withOffsets.length ? withOffsets[withOffsets.length - 1].end : 0;
  const offsetDrift = totalLen < text.length - 2;

  const content = withOffsets.filter(
    (t) =>
      isContentToken(t.token, opt.minTokenChars) &&
      (offsetDrift || sentenceAt(sentences, t.start, t.end) !== null),
  );

  if (!content.length) {
    return {
      status: "unavailable",
      score: null,
      risk: null,
      level: null,
      first: null,
      sentences: [],
      flagged: 0,
      // Tokens arrived but none were found in the answer text: numbers over such a
      // stream would be made up, so it is honest to say "cannot align".
      reason: withOffsets.length ? "no content tokens" : "tokens do not match the answer text",
    };
  }

  const firstToken = content[0];
  const first = {
    score: phi(firstToken, opt.topK),
    entropy: normalizedEntropy(firstToken, opt.topK),
    token: firstToken.token,
  };

  // Group by sentence (with drift, everything goes into one "sentence").
  const buckets = new Map<number, TokenWithOffset[]>();
  if (offsetDrift) {
    // Offsets drifted: tokens cannot be bound to sentences, but an empty sentence
    // list reads as "nothing doubtful" from the outside. Keep everything in a single
    // pseudo-sentence with the real text range so the score stays visible.
    buckets.set(DRIFT_BUCKET, content);
  } else {
    for (const t of content) {
      const s = sentenceAt(sentences, t.start, t.end);
      if (!s) continue;
      const arr = buckets.get(s.i) ?? [];
      arr.push(t);
      buckets.set(s.i, arr);
    }
  }

  const scored: SentenceScore[] = [];
  for (const [i, arr] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    const s = i === DRIFT_BUCKET ? { i: 0, start: 0, end: text.length, text } : sentences[i];
    if (!s) continue;
    const lps = arr.map((t) => t.logprob);
    const geo = geometricMean(lps);
    const startPhi = phi(arr[0], opt.topK);
    // The built-in score is just the geometric mean: measurement (docs/VALIDATION.md §14)
    // showed that worst-token and φ weighting make it worse than chance.
    const features = featuresOf({
      // Raw mean logprob: `log(max(geo, 1e-9))` collapsed everything below 1e-9
      // into one value −20.7, and the linear model lost resolution on bad answers.
      meanLp: lps.reduce((a, b) => a + b, 0) / lps.length,
      minLp: minOf(lps),
      meanPhi: startPhi,
      lowFraction: lps.filter((lp) => Math.exp(lp) < 0.5).length / lps.length,
      digitDensity: digitDensity(s.text),
      tokens: arr.length,
    });
    const score = clamp01(
      (scorer ? scorer.score({ features, text: s.text, model }) : geo),
    );
    const risk = clamp01(1 - score);
    scored.push({
      i,
      start: s.start,
      end: s.end,
      text: s.text,
      score,
      risk,
      meanLp: Math.exp(lps.reduce((a, b) => a + b, 0) / lps.length),
      minLp: minOf(lps),
      phi: startPhi,
      tokens: arr.length,
      // Strict comparison: exactly on the boundary (score 0.55, risk 0.45) the level is
      // still `uncertain`, and the sentence must not be flagged.
      flag: risk > opt.riskyThreshold,
      level: levelOf(score) ?? "unreliable",
    });
  }

  const allLps = content.map((t) => t.logprob);
  const globalGeo = geometricMean(allLps);
  const globalFeatures = featuresOf({
    meanLp: allLps.reduce((a, b) => a + b, 0) / allLps.length,
    minLp: minOf(allLps),
    meanPhi: phi(content[0], opt.topK),
    lowFraction: allLps.filter((lp) => Math.exp(lp) < 0.5).length / allLps.length,
    digitDensity: digitDensity(text),
    tokens: content.length,
  });
  const globalScore = scorer
    ? clamp01(scorer.score({ features: globalFeatures, text, model }))
    : globalGeo;
  const meanSentence = scored.length
    ? scored.reduce((a, s) => a + s.score, 0) / scored.length
    : globalScore;
  const score = clamp01(opt.globalWeight * globalScore + (1 - opt.globalWeight) * meanSentence);

  return {
    status: offsetDrift ? "partial" : "ok",
    score,
    risk: clamp01(1 - score),
    level: levelOf(score),
    first,
    sentences: scored,
    flagged: scored.filter((s) => s.flag).length,
    ...(offsetDrift ? { reason: "token/text offset drift" } : {}),
  };
}

/**
 * Thresholds can be overridden by the environment, without waiting for a config
 * in opencode.jsonc. An invalid value is silently ignored: a broken variable must
 * not change the numbers.
 */
export function envScoreOptions(env: Record<string, string | undefined> = process.env): ScoreOptions {
  const num = (name: string) => {
    const raw = env[name];
    if (raw === undefined || raw === "") return undefined;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 && value <= 1 ? value : undefined;
  };
  const risky = num("TRUTHPROBE_RISKY_THRESHOLD");
  // `TRUTHPROBE_SHAKY_THRESHOLD` was removed: the variable was parsed but no scorer
  // and no UI ever read it, so it only promised a setting that did not exist.
  return risky === undefined ? {} : { riskyThreshold: risky };
}
