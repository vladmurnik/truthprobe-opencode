/**
 * TruthProbe — сменный скорер.
 *
 * По умолчанию оценка — геометрическое среднее вероятностей содержательных
 * токенов (`exp(meanLp)`). Раньше здесь была эвристика 0.4·гео + 0.3·худший токен
 * + 0.3·уверенность первого токена; замер на 626 строках (544 правды и 82
 * заказанной лжи, docs/VALIDATION.md §14) показал, что она даёт AUROC 0.388 —
 * хуже случайного, причём виноват именно φ (сама по себе AUROC 0.199, то есть
 * антикоррелирует с правильностью). Без φ та же величина даёт 0.597 при ECE
 * 0.098 против 0.368, а на 739 заведомо верных ответах ECE падает с 0.493 до 0.160.
 * φ и minLp остаются в признаках — их может использовать обученная модель.
 *
 * Скорер сменный, менять его можно, не пересобирая патч:
 *
 *   TRUTHPROBE_SCORER=geometric                 # встроенный (по умолчанию)
 *   TRUTHPROBE_SCORER=linear:/path/weights.json # линейная модель, веса из JSON
 *
 * Веса готовит `scripts/calibrate.py --fit` на размеченном наборе предложений.
 * Любая ошибка загрузки (нет файла, битый JSON, нечисловые веса) не ломает
 * оценку: печатается одно предупреждение в stderr и включается geometric.
 */

import { readFileSync } from "node:fs"

import type { LinearWeights, Scorer, ScorerFeatures } from "./types.js"

export const FEATURE_NAMES = ["bias", "meanLp", "minLp", "meanPhi", "fracLow", "digitDensity"] as const

function clamp01(x: number): number {
  if (!Number.isFinite(x)) return 0
  return Math.min(1, Math.max(0, x))
}

/** Встроенный скорер: геометрическое среднее вероятностей содержательных токенов. */
export function geometricScorer(): Scorer {
  return {
    name: "geometric",
    score(input) {
      // clamp01 сам отдаёт 0 на NaN/Infinity, поэтому битые признаки не ломают оценку.
      return clamp01(Math.exp(input.features.meanLp))
    },
  }
}

function sigmoid(x: number): number {  if (x >= 0) return 1 / (1 + Math.exp(-x))
  const e = Math.exp(x)
  return e / (1 + e)
}

/** Линейная модель: score = sigmoid(bias + Σ w·x), признаки из FEATURE_NAMES. */
export function linearScorer(weights: LinearWeights, name = "linear"): Scorer {
  return {
    name,
    score(input) {
      const { features } = input
      const x = [1, features.meanLp, features.minLp, features.meanPhi, features.fracLow, features.digitDensity]
      const w = [
        weights.bias,
        weights.meanLp,
        weights.minLp,
        weights.meanPhi,
        weights.fracLow,
        weights.digitDensity ?? 0,
      ]
      let z = 0
      for (let i = 0; i < x.length; i++) {
        const wi = w[i] ?? Number.NaN
        const xi = x[i] ?? 0
        if (!Number.isFinite(wi)) return geometricScorer().score(input)
        z += wi * xi
      }
      if (!Number.isFinite(z)) return geometricScorer().score(input)
      return clamp01(sigmoid(z))
    },
  }
}

/** Достаёт признаки из чисел токенов (энтропию первого токена считает вызывающий). */
export function featuresOf(args: {
  meanLp: number
  minLp: number
  meanPhi: number
  lowFraction: number
  digitDensity?: number
  tokens?: number
}): ScorerFeatures {
  return {
    meanLp: args.meanLp,
    minLp: args.minLp,
    meanPhi: args.meanPhi,
    fracLow: args.lowFraction,
    digitDensity: args.digitDensity ?? 0,
    tokens: args.tokens ?? 0,
  }
}

export function parseLinearWeights(raw: unknown): LinearWeights {
  const obj = raw as Record<string, unknown> | null
  const src = (obj?.weights ?? obj) as Record<string, unknown> | null
  if (!src) throw new Error("weights object is missing")
  // `Number(null) === 0`, поэтому JSON-`null` надо отсекать до преобразования:
  // иначе молчаливо обнулённый коэффициент даёт «валидные» веса с другим смыслом.
  const num = (key: string, value: unknown) => {
    if (value === null) throw new Error(`weight "${key}" is null`)
    if (value === undefined) throw new Error(`weight "${key}" is missing`)
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) throw new Error(`weight "${key}" is not a number`)
    return parsed
  }
  const out: LinearWeights = {
    bias: num("bias", src.bias),
    meanLp: num("meanLp", src.meanLp),
    minLp: num("minLp", src.minLp),
    meanPhi: num("meanPhi", src.meanPhi),
    fracLow: num("fracLow", src.fracLow),
    digitDensity: src.digitDensity === undefined ? 0 : num("digitDensity", src.digitDensity),
  }
  for (const [key, value] of Object.entries(out)) {
    if (!Number.isFinite(value)) throw new Error(`weight "${key}" is not a number`)
  }
  return out
}

/**
 * Набор весов: общие плюс отдельные на модель. Так выглядит бандл, который пишет
 * `scripts/calibrate.py --fit --by-model`; плоский JSON (просто `bias/meanLp/...`)
 * тоже принимается — он становится `global`.
 */
export interface WeightsBundle {
  global: LinearWeights
  models: Record<string, LinearWeights>
}

/**
 * Читает и плоские веса, и бандл `{version, features, global, models}`.
 * Битые записи моделей пропускаются молча: одна испорченная модель не должна
 * отключать калибровку для всех остальных.
 */
export function parseWeightsBundle(raw: unknown): WeightsBundle {
  const obj = raw as Record<string, unknown> | null
  if (!obj || typeof obj !== "object") throw new Error("weights object is missing")
  const looksBundled = "global" in obj || "models" in obj || "features" in obj
  if (!looksBundled) return { global: parseLinearWeights(obj), models: {} }
  const global = parseLinearWeights(obj.global ?? obj.weights)
  const models: Record<string, LinearWeights> = {}
  const src = obj.models
  if (src && typeof src === "object") {
    for (const [key, value] of Object.entries(src as Record<string, unknown>)) {
      if (!value || typeof value !== "object") continue
      try {
        models[key] = parseLinearWeights(value)
      } catch {
        continue
      }
    }
  }
  return { global, models }
}

/**
 * Скорер с весами на модель: `models[providerID/modelID]`, иначе `global`.
 * Так калибровка, снятая на конкретной модели, не разбавляется чужими числами.
 */
export function bundleScorer(bundle: WeightsBundle, name = "linear"): Scorer {
  const fallback = linearScorer(bundle.global, name)
  const perModel = new Map<string, Scorer>()
  for (const [key, weights] of Object.entries(bundle.models)) perModel.set(key, linearScorer(weights, `${name}:${key}`))
  const warned = new Set<string>()
  return {
    name,
    score(input) {
      const scorer = input.model ? perModel.get(input.model) : undefined
      // Ключи калибровки — routed-имя модели; у алиасов и `auto` оно не совпадает с
      // запрошенным id. Молчаливая подмена на global — это неправда о точности, поэтому
      // про каждую такую модель говорим один раз.
      if (!scorer && input.model && perModel.size > 0 && !warned.has(input.model)) {
        warned.add(input.model)
        process.stderr.write(`truthprobe: no per-model weights for "${input.model}"; using global\n`)
      }
      return (scorer ?? fallback).score(input)
    },
  }
}

/** Веса, которые реально будут применены к модели (для диагностики и тестов). */
export function weightsFor(bundle: WeightsBundle, model?: string): LinearWeights {
  return (model ? bundle.models[model] : undefined) ?? bundle.global
}

let cached: { spec: string; scorer: Scorer } | null = null

/**
 * Скорер из переменной окружения. null — «использовать встроенную формулу»
 * (её применяет score.ts), чтобы поведение по умолчанию не менялось.
 */
export function scorerFromEnv(
  env: Record<string, string | undefined> = process.env,
  read: (path: string) => string = (path) => readFileSync(path, "utf8"),
): Scorer | null {
  const spec = (env.TRUTHPROBE_SCORER ?? "").trim()
  if (!spec || spec === "geometric" || spec === "default") return null
  if (cached && cached.spec === spec) return cached.scorer

  const warn = (why: string) => {
    process.stderr.write(`truthprobe: scorer "${spec}" ignored (${why}); using geometric\n`)
  }

  let scorer: Scorer | null = null
  if (spec.startsWith("linear:")) {
    const path = spec.slice("linear:".length).trim()
    try {
      const bundle = parseWeightsBundle(JSON.parse(read(path)))
      const count = Object.keys(bundle.models).length
      scorer = count ? bundleScorer(bundle, `linear:${path}(${count} models)`) : linearScorer(bundle.global, `linear:${path}`)
    } catch (error) {
      warn(error instanceof Error ? error.message : String(error))
    }
  } else {
    warn("unknown scorer, expected linear:<path> or geometric")
  }

  if (!scorer) return null
  cached = { spec, scorer }
  return scorer
}
