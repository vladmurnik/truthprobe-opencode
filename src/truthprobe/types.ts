/**
 * TruthProbe — типы данных.
 *
 * Всё, что здесь описано, — контракт между слоем провайдера (который собирает
 * logprobs из стрима), слоем скоринга (чистые функции) и UI/плагинами.
 */

import type { ConfidenceLevel } from "./levels.js"

/** Один альтернативный токен из `top_logprobs`. */
export interface TopLogprob {
  token: string;
  logprob: number;
}

/** Один сгенерированный токен с вероятностью (и, опционально, top-K). */
export interface TokenLogprob {
  token: string;
  logprob: number;
  top?: TopLogprob[];
}

/** Оценка одного предложения. */
export interface SentenceScore {
  /** Порядковый номер предложения в ответе, с нуля. */
  i: number;
  /** Смещение начала в исходном тексте (включительно). */
  start: number;
  /** Смещение конца (исключительно). */
  end: number;
  /** Исходный текст предложения. */
  text: string;
  /** 0..1, выше — увереннее. */
  score: number;
  /** 1 - score. */
  risk: number;
  /** Геометрическое среднее вероятностей содержательных токенов. */
  meanLp: number;
  /** Минимальный logprob среди содержательных токенов (худший токен). */
  minLp: number;
  /** Уверенность по первому содержательному токену предложения. */
  phi: number;
  /** Сколько содержательных токенов попало в предложение. */
  tokens: number;
  /** score < 1 - riskyThreshold. */
  flag: boolean;
  /** Уровень уверенности по score: safe | likely | uncertain | risky | unreliable. */
  level: ConfidenceLevel;
}

/** Итог по всему ответу. */
export interface AnswerScore {
  status: "ok" | "partial" | "unavailable";
  /** 0..1 или null, если сигнала нет. */
  score: number | null;
  risk: number | null;
  /** Уровень уверенности по score; null, если сигнала нет. */
  level: ConfidenceLevel | null;
  /** Уверенность по первому содержательному токену всего ответа. */
  first: { score: number; entropy: number; token: string } | null;
  sentences: SentenceScore[];
  /** Количество предложений с flag = true. */
  flagged: number;
  /** Причина недоступности (для UI). */
  reason?: string;
}

export interface ScoreOptions {
  /** Размер top-K, по которому считалась энтропия. */
  topK?: number;
  /** Порог риска для подсветки. */
  riskyThreshold?: number;
  /** Порог «шатко» (жёлтый), если понадобится третий уровень. */
  shakyThreshold?: number;
  /** Минимальная длина содержательного токена, чтобы считать его значимым. */
  minTokenChars?: number;
  /** Доля веса whole-answer, отданная глобальному геом. среднему. */
  globalWeight?: number;
  /** Скорер: null/undefined — встроенная формула (см. scorer.ts). */
  scorer?: Scorer | null;
}

/** Признаки, которые скорер получает по набору токенов. */
export interface ScorerFeatures {
  /** ln геометрического среднего вероятностей. */
  meanLp: number;
  /** ln вероятности худшего токена. */
  minLp: number;
  /** Средняя уверенность первого токена по top-K. */
  meanPhi: number;
  /** Доля токенов с вероятностью ниже 0.5. */
  fracLow: number;
  /**
   * Доля символов текста, которые являются цифрами (0..1).
   * Единственный текстовый признак, который измерен на реальных данных: в наборе
   * заказанной лжи ответы короче и почти без цифр, поэтому признак добавляет AUROC
   * (0.774 → 0.808 в обученной модели), но в оценку по умолчанию он не входит.
   */
  digitDensity: number;
  /** Сколько токенов участвовало. */
  tokens: number;
}

export interface ScorerInput {
  features: ScorerFeatures;
  /** Текст, к которому относятся токены (для моделей, смотрящих на текст). */
  text: string;
  /** Модель, сгенерировавшая ответ (`providerID/modelID`); для весов «на модель». */
  model?: string;
}

export interface Scorer {
  /** Имя для логов и диагностики. */
  name: string;
  /** 0..1, выше — увереннее. */
  score(input: ScorerInput): number;
}

/** Веса линейной модели; готовит `scripts/calibrate.py --fit`. */
export interface LinearWeights {
  bias: number;
  meanLp: number;
  minLp: number;
  meanPhi: number;
  fracLow: number;
  /** Необязательный текстовый вес: старые файлы весов читаются как 0. */
  digitDensity?: number;
}

export const DEFAULT_SCORE_OPTIONS: Required<Omit<ScoreOptions, "scorer">> = {
  topK: 20,
  riskyThreshold: 0.45,
  shakyThreshold: 0.3,
  minTokenChars: 2,
  globalWeight: 0.6,
};
