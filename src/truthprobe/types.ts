/**
 * TruthProbe — типы данных.
 *
 * Всё, что здесь описано, — контракт между слоем провайдера (который собирает
 * logprobs из стрима), слоем скоринга (чистые функции) и UI/плагинами.
 */

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
}

/** Итог по всему ответу. */
export interface AnswerScore {
  status: "ok" | "partial" | "unavailable";
  /** 0..1 или null, если сигнала нет. */
  score: number | null;
  risk: number | null;
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
}

export const DEFAULT_SCORE_OPTIONS: Required<ScoreOptions> = {
  topK: 20,
  riskyThreshold: 0.45,
  shakyThreshold: 0.3,
  minTokenChars: 2,
  globalWeight: 0.6,
};
