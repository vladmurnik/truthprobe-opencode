/**
 * TruthProbe — swappable scorer.
 *
 * By default the score is the geometric mean of the content-token probabilities
 * (`exp(meanLp)`). It used to be a heuristic of 0.4·geo + 0.3·worst token
 * + 0.3·first-token confidence; measurement on 626 lines (544 true and 82
 * commissioned lies, docs/VALIDATION.md §14) showed it gives AUROC 0.388 —
 * worse than chance, and the culprit is φ (on its own AUROC 0.199, that is
 * anti-correlated with correctness). Without φ the same quantity gives 0.597 with
 * ECE 0.098 versus 0.368, and on 739 certainly-correct answers ECE drops from 0.493 to 0.160.
 * φ and minLp stay among the features — a trained model can use them.
 *
 * The scorer is swappable, so you can change it without rebuilding the patch:
 *
 *   TRUTHPROBE_SCORER=geometric                 # built-in (default)
 *   TRUTHPROBE_SCORER=linear:/path/weights.json # linear model, weights from JSON
 *
 * The weights are prepared by `scripts/calibrate.py --fit` on a labelled set of sentences.
 * Any loading error (no file, broken JSON, non-numeric weights) does not break the
 * score: a single warning is printed to stderr and geometric is used.
 */

import { readFileSync } from "node:fs"

import type { LinearWeights, Scorer, ScorerFeatures } from "./types.js"

export const FEATURE_NAMES = ["bias", "meanLp", "minLp", "meanPhi", "fracLow", "digitDensity"] as const

function clamp01(x: number): number {
  if (!Number.isFinite(x)) return 0
  return Math.min(1, Math.max(0, x))
}

/** Built-in scorer: geometric mean of the content-token probabilities. */
export function geometricScorer(): Scorer {
  return {
    name: "geometric",
    score(input) {
      // clamp01 itself returns 0 on NaN/Infinity, so broken features do not break the score.
      return clamp01(Math.exp(input.features.meanLp))
    },
  }
}

function sigmoid(x: number): number {  if (x >= 0) return 1 / (1 + Math.exp(-x))
  const e = Math.exp(x)
  return e / (1 + e)
}

/** Linear model: score = sigmoid(bias + Σ w·x), features from FEATURE_NAMES. */
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

/** Extracts features from token numbers (first-token entropy is computed by the caller). */
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
  // `Number(null) === 0`, so JSON `null` has to be rejected before conversion:
  // otherwise a silently zeroed coefficient yields "valid" weights with a different meaning.
  const num = (key: string, value: unknown) => {
    if (value === null) throw new Error(`weight "${key}" is null`)
    if (value === undefined) throw new Error(`weight "${key}" is missing`)
    // `Number("") === 0`, `Number([]) === 0`, `Number(true) === 1`: without a type check,
    // garbage in the weights file silently turns into a valid coefficient.
    if (typeof value !== "number") throw new Error(`weight "${key}" is not a number`)
    if (!Number.isFinite(value)) throw new Error(`weight "${key}" is not a number`)
    return value
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
 * A weight set: shared weights plus per-model ones. This is the shape of the bundle
 * written by `scripts/calibrate.py --fit --by-model`; a flat JSON (just `bias/meanLp/...`)
 * is accepted too — it becomes `global`.
 */
export interface WeightsBundle {
  global: LinearWeights
  models: Record<string, LinearWeights>
}

/**
 * Reads both flat weights and a `{version, features, global, models}` bundle.
 * Broken model entries are skipped silently: one corrupted model must not
 * disable calibration for all the others.
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
 * Scorer with per-model weights: `models[providerID/modelID]`, otherwise `global`.
 * So calibration taken on a specific model is not diluted by other numbers.
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
      // Calibration keys are the routed model name; for aliases and `auto` it does not
      // match the requested id. A silent fallback to global would be a lie about accuracy,
      // so we say it once per such model.
      if (!scorer && input.model && perModel.size > 0 && !warned.has(input.model)) {
        warned.add(input.model)
        process.stderr.write(`truthprobe: no per-model weights for "${input.model}"; using global\n`)
      }
      return (scorer ?? fallback).score(input)
    },
  }
}

/** Weights that will actually be applied to the model (for diagnostics and tests). */
export function weightsFor(bundle: WeightsBundle, model?: string): LinearWeights {
  return (model ? bundle.models[model] : undefined) ?? bundle.global
}

let cached: { spec: string; scorer: Scorer } | null = null

/**
 * Scorer from an environment variable. null — "use the built-in formula"
 * (applied by score.ts), so the default behaviour does not change.
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
