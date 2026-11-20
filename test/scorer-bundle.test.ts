import { describe, expect, test } from "bun:test"

import { bundleScorer, parseWeightsBundle, scorerFromEnv, weightsFor } from "../src/truthprobe/scorer.js"
import type { LinearWeights } from "../src/truthprobe/types.js"

const strong: LinearWeights = { bias: 6, meanLp: 0, minLp: 0, meanPhi: 6, fracLow: 0 }
const weak: LinearWeights = { bias: -6, meanLp: 0, minLp: 0, meanPhi: -6, fracLow: 0 }
const features = { meanLp: -1, minLp: -2, meanPhi: 0.5, fracLow: 0.25, tokens: 12 }

describe("parseWeightsBundle", () => {
  test("плоские веса становятся global", () => {
    const bundle = parseWeightsBundle({ bias: 1, meanLp: 2, minLp: 3, meanPhi: 4, fracLow: 5 })
    expect(bundle.global).toEqual({ bias: 1, meanLp: 2, minLp: 3, meanPhi: 4, fracLow: 5 })
    expect(Object.keys(bundle.models)).toEqual([])
  })

  test("бандл читается вместе с весами моделей", () => {
    const bundle = parseWeightsBundle({ version: 1, global: strong, models: { "freepi/particle": weak } })
    expect(bundle.global).toEqual(strong)
    expect(bundle.models["freepi/particle"]).toEqual(weak)
  })

  test("битая запись модели пропускается", () => {
    const bundle = parseWeightsBundle({ global: strong, models: { broken: { bias: "nope" }, "freepi/particle": weak } })
    expect(bundle.models["broken"]).toBeUndefined()
    expect(bundle.models["freepi/particle"]).toEqual(weak)
  })
})

describe("weightsFor / bundleScorer", () => {
  const bundle = parseWeightsBundle({ global: strong, models: { "freepi/particle": weak } })

  test("для известной модели — её веса, для чужой — global", () => {
    expect(weightsFor(bundle, "freepi/particle")).toEqual(weak)
    expect(weightsFor(bundle, "opencode/gpt-5")).toEqual(strong)
  })

  test("разные модели дают разные оценки на одних признаках", () => {
    const scorer = bundleScorer(bundle, "test")
    const a = scorer.score({ features, text: "ответ", model: "freepi/particle" })
    const b = scorer.score({ features, text: "ответ", model: "other/model" })
    expect(a).toBeLessThan(b)
    expect(b).toBeGreaterThan(0.9)
  })

  test("оценка всегда в [0,1]", () => {
    const scorer = bundleScorer(bundle, "test")
    for (const model of ["freepi/particle", "other/model", undefined]) {
      const value = scorer.score({ features, text: "ответ", model })
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

  test("бандл из файла подхватывается", () => {
    const scorer = scorerFromEnv({ TRUTHPROBE_SCORER: "linear:/wb.json" }, read)
    expect(scorer).not.toBeNull()
    expect(scorer!.name).toContain("1 models")
  })

  test("битый файл — null, без падения", () => {
    expect(scorerFromEnv({ TRUTHPROBE_SCORER: "linear:/broken.json" }, () => "not json")).toBeNull()
  })
})
