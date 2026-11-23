import { describe, expect, test } from "bun:test"

import { bundleScorer, parseWeightsBundle, scorerFromEnv, weightsFor } from "../src/truthprobe/scorer.js"
import type { LinearWeights } from "../src/truthprobe/types.js"

const strong: LinearWeights = { bias: 6, meanLp: 0, minLp: 0, meanPhi: 6, fracLow: 0, digitDensity: 0 }
const weak: LinearWeights = { bias: -6, meanLp: 0, minLp: 0, meanPhi: -6, fracLow: 0, digitDensity: 0 }
const features = { meanLp: -1, minLp: -2, meanPhi: 0.5, fracLow: 0.25, digitDensity: 0.1, tokens: 12 }

describe("parseWeightsBundle", () => {
  test("flat weights become global", () => {
    const bundle = parseWeightsBundle({ bias: 1, meanLp: 2, minLp: 3, meanPhi: 4, fracLow: 5 })
    expect(bundle.global).toEqual({ bias: 1, meanLp: 2, minLp: 3, meanPhi: 4, fracLow: 5, digitDensity: 0 })
    expect(Object.keys(bundle.models)).toEqual([])
  })

  test("the bundle is read together with the model weights", () => {
    const bundle = parseWeightsBundle({ version: 1, global: strong, models: { "freepi/particle": weak } })
    expect(bundle.global).toEqual(strong)
    expect(bundle.models["freepi/particle"]).toEqual(weak)
  })

  test("a broken model entry is skipped", () => {
    const bundle = parseWeightsBundle({ global: strong, models: { broken: { bias: "nope" }, "freepi/particle": weak } })
    expect(bundle.models["broken"]).toBeUndefined()
    expect(bundle.models["freepi/particle"]).toEqual(weak)
  })
})

describe("weightsFor / bundleScorer", () => {
  const bundle = parseWeightsBundle({ global: strong, models: { "freepi/particle": weak } })

  test("for a known model — its weights, for a foreign one — global", () => {
    expect(weightsFor(bundle, "freepi/particle")).toEqual(weak)
    expect(weightsFor(bundle, "opencode/gpt-5")).toEqual(strong)
  })

  test("different models give different scores on the same features", () => {
    const scorer = bundleScorer(bundle, "test")
    const a = scorer.score({ features, text: "answer", model: "freepi/particle" })
    const b = scorer.score({ features, text: "answer", model: "other/model" })
    expect(a).toBeLessThan(b)
    expect(b).toBeGreaterThan(0.9)
  })

  test("the score is always in [0,1]", () => {
    const scorer = bundleScorer(bundle, "test")
    for (const model of ["freepi/particle", "other/model", undefined]) {
      const value = scorer.score({ features, text: "answer", model })
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThanOrEqual(1)
    }
  })
})

describe("scorerFromEnv", () => {
  const read = (path: string) => {
    if (path !== "/wb.json") throw new Error("ENOENT")
    return JSON.stringify({ global: strong, models: { "freepi/particle": weak } })
  }

  test("a bundle from a file is picked up", () => {
    const scorer = scorerFromEnv({ TRUTHPROBE_SCORER: "linear:/wb.json" }, read)
    expect(scorer).not.toBeNull()
    expect(scorer!.name).toContain("1 models")
  })

  test("broken file — null, no crash", () => {
    expect(scorerFromEnv({ TRUTHPROBE_SCORER: "linear:/broken.json" }, () => "not json")).toBeNull()
  })
})
