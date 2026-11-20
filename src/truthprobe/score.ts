/**
 * TruthProbe — скоринг уверенности по token logprobs.
 *
 * Все функции чистые, кроме необязательной загрузки сменного скорера из
 * `TRUTHPROBE_SCORER` (см. scorer.ts): математика одна и та же, состояние не
 * копится. Это позволяет покрыть всю математику юнит-тестами на записанных
 * фикстурах и использовать модуль и в ядре OpenCode, и в офлайн-калибровке (T8).
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

/** Токен несёт смысл: не пробелы, не чистая пунктуация/символы. */
export function isContentToken(token: string, minChars = 2): boolean {
  if (!token) return false;
  if (!/\S/.test(token)) return false;
  if (PUNCT_ONLY.test(token)) return false;
  const visible = token.replace(/\s/g, "")
  if (visible.length >= minChars) return true
  // Иероглиф/канa/хангыль — самостоятельное слово в один символ, его нельзя терять.
  return /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]/.test(visible);
}

/**
 * Нормированная энтропия распределения на первом токене.
 *
 * q_i = exp(lp_i) / Σ exp(lp_j) по доступному top-K; H = -Σ q_i ln q_i / ln K.
 * Если top-K нет (провайдер не вернул) — деградируем к 1 - p(token),
 * то есть φ = p(token).
 */
export function normalizedEntropy(t: TokenLogprob, topK = 20): number {
  const top = (t.top ?? []).filter((x) => Number.isFinite(x.logprob));
  if (top.length < 2) return clamp01(1 - Math.exp(t.logprob));

  const probs = top.map((x) => Math.exp(x.logprob));
  const sum = probs.reduce((a, b) => a + b, 0);
  if (!(sum > 0)) return 1;

  let h = 0;
  for (const p of probs) {
    const q = p / sum;
    if (q > 0) h -= q * Math.log(q);
  }
  const k = Math.max(2, Math.min(topK, top.length));
  return clamp01(h / Math.log(k));
}

/** φ = уверенность по первому токену, 0..1. */
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

/** Привязывает токены к символьным смещениям исходного текста. */
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
 * Привязка токенов к тексту с терпимостью к «внутренним» токенам.
 *
 * Провайдеры (и reasoning-модели особенно) отдают токены, у которых нет
 * видимого текста: `</think>`, служебные маркеры, обрезанные пробелы. Слепая
 * конкатенация ломает смещения, поэтому каждый токен либо находится в тексте
 * рядом с текущей позицией, либо пропускается.
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
    // Токен мог потерять ведущий пробел/перенос: ищем его в пределах окна.
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
    // Внутренний токен без видимого текста — пропускаем, не ломая смещения.
  }
  return out;
}

/**
 * Предложение, которому принадлежит диапазон токена.
 *
 * Токен может начинаться с пробела, который сегментатор уже «съел» как
 * хвост предыдущего предложения (например « Плохо» сразу после точки),
 * поэтому проверяем пересечение диапазонов, а не только начало токена.
 */
function sentenceAt(sentences: Sentence[], start: number, end: number): Sentence | null {
  for (const s of sentences) {
    if (start < s.end && end > s.start) return s;
    if (s.start >= end) break;
  }
  return null;
}

/**
 * Доля символов, являющихся цифрами. Тот же признак считается в `scripts/collect.py`
 * по тексту ответа; в развилке «текст vs logprobs» это единственный текстовый сигнал,
 * который дал измеримый прирост (§15 VALIDATION).
 */
export function digitDensity(text: string): number {
  if (!text) return 0;
  let digits = 0;
  for (const ch of text) if (ch >= "0" && ch <= "9") digits++;
  return clamp01(digits / text.length);
}

function geometricMean(lps: number[]): number {
  if (lps.length === 0) return 0;
  return clamp01(Math.exp(lps.reduce((a, b) => a + b, 0) / lps.length));
}

/**
 * Считает уверенность по всему ответу.
 *
 * @param text  финальный текст ответа (тот же, чьи токены пришли в `tokens`)
 * @param tokens logprobs по токенам в порядке генерации
 */
export function scoreAnswer(
  text: string,
  tokens: TokenLogprob[],
  options: ScoreOptions = {},
  /** `providerID/modelID` — чтобы сменный скорер мог взять веса именно этой модели. */
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

  // Дрейф смещений: хвост ответа не покрыт токенами — привязка к предложениям
  // ненадёжна, сигнализируем partial.
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
      // Токены пришли, но ни один не нашёлся в тексте ответа: числа по такому
      // потоку были бы выдумкой, честнее сказать «не могу сопоставить».
      reason: withOffsets.length ? "no content tokens" : "tokens do not match the answer text",
    };
  }

  const firstToken = content[0];
  const first = {
    score: phi(firstToken, opt.topK),
    entropy: normalizedEntropy(firstToken, opt.topK),
    token: firstToken.token,
  };

  // Группировка по предложениям (если дрейф — всё в одно «предложение»).
  const buckets = new Map<number, TokenWithOffset[]>();
  for (const t of content) {
    const s = offsetDrift ? null : sentenceAt(sentences, t.start, t.end);
    if (!s) continue;
    const arr = buckets.get(s.i) ?? [];
    arr.push(t);
    buckets.set(s.i, arr);
  }

  const scored: SentenceScore[] = [];
  for (const [i, arr] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    const s = sentences[i];
    const lps = arr.map((t) => t.logprob);
    const geo = geometricMean(lps);
    const startPhi = phi(arr[0], opt.topK);
    // Встроенная оценка — только геометрическое среднее: замер (docs/VALIDATION.md §14)
    // показал, что вес худшего токена и φ делают её хуже случайного.
    const features = featuresOf({
      meanLp: Math.log(Math.max(geo, 1e-9)),
      minLp: Math.min(...lps),
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
      minLp: Math.min(...lps),
      phi: startPhi,
      tokens: arr.length,
      flag: risk >= opt.riskyThreshold,
      level: levelOf(score) ?? "unreliable",
    });
  }

  const allLps = content.map((t) => t.logprob);
  const globalGeo = geometricMean(allLps);
  const globalFeatures = featuresOf({
    meanLp: Math.log(Math.max(globalGeo, 1e-9)),
    minLp: Math.min(...allLps),
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
 * Пороги можно переопределить окружением, не дожидаясь конфига в opencode.jsonc.
 * Некорректное значение молча игнорируется: сломанная переменная не должна
 * менять числа.
 */
export function envScoreOptions(env: Record<string, string | undefined> = process.env): ScoreOptions {
  const num = (name: string) => {
    const raw = env[name];
    if (raw === undefined || raw === "") return undefined;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 && value <= 1 ? value : undefined;
  };
  const risky = num("TRUTHPROBE_RISKY_THRESHOLD");
  const shaky = num("TRUTHPROBE_SHAKY_THRESHOLD");
  return {
    ...(risky === undefined ? {} : { riskyThreshold: risky }),
    ...(shaky === undefined ? {} : { shakyThreshold: shaky }),
  };
}
