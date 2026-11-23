import { describe, expect, test } from "bun:test"
import {
  isContentToken,
  normalizedEntropy,
  phi,
  scoreAnswer,
  tokensWithOffsets,
} from "../src/truthprobe/score.js"
import { codeRanges, splitSentences } from "../src/truthprobe/sentences.js"
import type { TokenLogprob } from "../src/truthprobe/types.js"

/** A token with two alternatives: the token itself and "noise" one delta below. */
const token = (text: string, logprob: number, delta = 1): TokenLogprob => ({
  token: text,
  logprob,
  top: [
    { token: text, logprob },
    { token: " other", logprob: logprob - delta },
  ],
})

/** Builds tokens from pairs, the way a provider would return them. */
const tokens = (values: Array<[string, number]>, delta = 1): TokenLogprob[] =>
  values.map(([text, logprob]) => token(text, logprob, delta))

/** Cuts the text into tokens on word boundaries so the offsets line up. */
const slice = (text: string, size = 4): string[] => {
  const out: string[] = []
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size))
  return out
}

/** Even tokens with the given logprob across the whole text. */
const flat = (text: string, logprob: number): TokenLogprob[] =>
  slice(text).map((part) => token(part, logprob))

describe("truthprobe.isContentToken", () => {
  test("keeps ordinary words", () => {
    expect(isContentToken("Paris")).toBe(true)
    expect(isContentToken("Berlin")).toBe(true)
    expect(isContentToken(" 13")).toBe(true)
  })

  test("drops whitespace, punctuation and symbols", () => {
    expect(isContentToken("")).toBe(false)
    expect(isContentToken("   ")).toBe(false)
    expect(isContentToken("\n")).toBe(false)
    expect(isContentToken(".")).toBe(false)
    expect(isContentToken(" ... ")).toBe(false)
    expect(isContentToken("—")).toBe(false)
    expect(isContentToken("()[]{}")).toBe(false)
    expect(isContentToken("«»")).toBe(false)
  })

  test("drops tokens below minChars", () => {
    expect(isContentToken("a")).toBe(false)
    expect(isContentToken(" a ")).toBe(false)
    expect(isContentToken("a", 1)).toBe(true)
  })
})

describe("truthprobe.normalizedEntropy / phi", () => {
  test("certain token has zero entropy and full phi", () => {
    const certain = { token: "yes", logprob: 0, top: [{ token: "yes", logprob: 0 }] }
    expect(normalizedEntropy(certain)).toBe(0)
    expect(phi(certain)).toBe(1)
  })

  test("no top-k degrades to the token probability", () => {
    expect(phi({ token: "x", logprob: -0.5 })).toBeCloseTo(Math.exp(-0.5), 6)
    expect(phi({ token: "x", logprob: 0 })).toBe(1)
  })

  test("two equal alternatives give zero phi", () => {
    const split = { token: "yes", logprob: -0.7, top: [{ token: "yes", logprob: -0.7 }, { token: "no", logprob: -0.7 }] }
    expect(normalizedEntropy(split)).toBeCloseTo(1, 6)
    expect(phi(split)).toBeCloseTo(0, 6)
  })

  test("phi is monotone in the winner probability", () => {
    const build = (lp: number) => ({
      token: "a",
      logprob: lp,
      top: [
        { token: "a", logprob: lp },
        { token: "b", logprob: -3 },
        { token: "c", logprob: -4 },
      ],
    })
    const values = [0, -0.5, -1, -2, -4].map((lp) => phi(build(lp)))
    for (let i = 1; i < values.length; i++) expect(values[i]).toBeLessThanOrEqual(values[i - 1])
    expect(values[0]).toBeGreaterThan(0.7)
  })

  test("entropy is normalised by ln(K) of the available alternatives", () => {
    const four = {
      token: "a",
      logprob: 0,
      top: [
        { token: "a", logprob: 0 },
        { token: "b", logprob: 0 },
        { token: "c", logprob: 0 },
        { token: "d", logprob: 0 },
      ],
    }
    expect(normalizedEntropy(four)).toBeCloseTo(1, 6)
    expect(normalizedEntropy(four, 4)).toBeCloseTo(1, 6)
  })

  test("lower topK produces higher entropy, hence lower phi", () => {
    const skewed = {
      token: "a",
      logprob: 0,
      top: [
        { token: "a", logprob: 0 },
        { token: "b", logprob: -1 },
        { token: "c", logprob: -2 },
        { token: "d", logprob: -3 },
      ],
    }
    expect(phi(skewed, 2)).toBeLessThan(phi(skewed, 20))
  })

  test("non-finite alternatives are ignored", () => {
    const noisy = {
      token: "a",
      logprob: -0.1,
      top: [
        { token: "a", logprob: -0.1 },
        { token: "b", logprob: Number.NaN },
        { token: "c", logprob: Number.NEGATIVE_INFINITY },
      ],
    }
    // After filtering one candidate remains → degrade to p(token).
    expect(phi(noisy)).toBeCloseTo(Math.exp(-0.1), 6)
  })

  test("phi always stays inside 0..1", () => {
    const weird = [
      { token: "a", logprob: 5, top: [{ token: "a", logprob: 5 }, { token: "b", logprob: 4 }] },
      { token: "a", logprob: -50, top: [{ token: "a", logprob: -50 }, { token: "b", logprob: -60 }] },
    ]
    for (const value of weird) {
      const score = phi(value)
      expect(score).toBeGreaterThanOrEqual(0)
      expect(score).toBeLessThanOrEqual(1)
    }
  })
})

describe("truthprobe.tokensWithOffsets", () => {
  test("offsets accumulate in generation order", () => {
    const mapped = tokensWithOffsets(tokens([[" ab", -1], ["cd", -1], [".", -1]]) as TokenLogprob[])
    expect(mapped.map((t) => [t.start, t.end])).toEqual([
      [0, 3],
      [3, 5],
      [5, 6],
    ])
  })

  test("empty input stays empty", () => {
    expect(tokensWithOffsets([])).toEqual([])
  })
})

describe("truthprobe.codeRanges", () => {
  test("closed fence is one range including the fences", () => {
    const text = "a\n```js\nconst x = 1\n```\nb"
    const ranges = codeRanges(text)
    expect(ranges.length).toBe(1)
    const [start, end] = ranges[0]
    expect(text.slice(start, end)).toBe("```js\nconst x = 1\n```")
  })

  test("tilde fence is detected too", () => {
    const text = "a\n~~~\ncode\n~~~"
    expect(codeRanges(text).length).toBe(1)
  })

  test("unclosed fence runs to the end of the text", () => {
    const text = "a\n```\ncode"
    expect(codeRanges(text)).toEqual([[2, text.length]])
  })

  test("plain text has no ranges", () => {
    expect(codeRanges("just text")).toEqual([])
  })
})

describe("truthprobe.splitSentences", () => {
  const texts = (text: string) => splitSentences(text).map((s) => s.text)

  test("splits on terminators", () => {
    expect(texts("First one. Second one! Third one?")).toEqual(["First one.", "Second one!", "Third one?"])
  })

  test("offsets match the source string", () => {
    const text = "First one. Second one!\n\nThird — with a dash!"
    for (const sentence of splitSentences(text)) {
      expect(text.slice(sentence.start, sentence.end)).toBe(sentence.text)
    }
  })

  test("does not split decimals", () => {
    expect(texts("Pi is 3.14 exactly.")).toEqual(["Pi is 3.14 exactly."])
  })

  test("does not split abbreviations", () => {
    expect(texts("This is i.e. an example. The end.")).toEqual(["This is i.e. an example.", "The end."])
    expect(texts("Use e.g. this one. Fine.")).toEqual(["Use e.g. this one.", "Fine."])
    expect(texts("Apples, pears, etc. And more.")).toEqual(["Apples, pears, etc.", "And more."])
    expect(texts("Fig. 2 shows this. Fine.")).toEqual(["Fig. 2 shows this.", "Fine."])
  })

  test("does not split Cyrillic abbreviations", () => {
    // Russian abbreviations ("see above", "yes") are still supported; the input is written as
    // escapes so this file stays ASCII-only.
    const text = "\u0421\u043c. \u0432\u044b\u0448\u0435. \u0414\u0430."
    expect(texts(text)).toEqual(["\u0421\u043c. \u0432\u044b\u0448\u0435.", "\u0414\u0430."])
  })

  test("supports the ellipsis and CJK terminators", () => {
    expect(texts("We wait… And here.")).toEqual(["We wait…", "And here."])
    expect(texts("これは文です。次です。")).toEqual(["これは文です。", "次です。"])
  })

  test("a blank line always breaks a sentence", () => {
    expect(texts("A\n\nB")).toEqual(["A", "B"])
  })

  test("code blocks are dropped entirely", () => {
    const text = "Before.\n```js\nconst a = 1;\n```\nAfter."
    expect(texts(text)).toEqual(["Before.", "After."])
  })

  test("unclosed code block swallows the rest", () => {
    expect(texts("Before.\n```js\nconst a = 1;")).toEqual(["Before."])
  })

  test("empty and whitespace-only input give nothing", () => {
    expect(splitSentences("")).toEqual([])
    expect(splitSentences("   \n\t ")).toEqual([])
  })

  test("single line without terminator is one sentence", () => {
    expect(texts("Just a line without a dot")).toEqual(["Just a line without a dot"])
  })

  test("list items without terminators stay together", () => {
    // Documenting the behaviour: a single newline is not a boundary.
    expect(texts("- one\n- two")).toEqual(["- one\n- two"])
  })

  test("indices are sequential starting from zero", () => {
    const sentences = splitSentences("A. B. C.")
    expect(sentences.map((s) => s.i)).toEqual([0, 1, 2])
  })
})

describe("truthprobe.scoreAnswer — degradation", () => {
  test("without tokens it returns unavailable", () => {
    const result = scoreAnswer("Any text.", [])
    expect(result.status).toBe("unavailable")
    expect(result.score).toBeNull()
    expect(result.risk).toBeNull()
    expect(result.first).toBeNull()
    expect(result.sentences).toEqual([])
    expect(result.flagged).toBe(0)
    expect(result.reason).toBe("no logprobs in response")
  })

  test("punctuation only — no content tokens", () => {
    const result = scoreAnswer("...", tokens([["...", -0.1], [" .", -0.2]]))
    expect(result.status).toBe("unavailable")
    expect(result.reason).toBe("no content tokens")
  })

  test("minTokenChars can be relaxed", () => {
    const text = "a b"
    const raw = tokens([["a", -0.1], [" b", -0.1]])
    expect(scoreAnswer(text, raw).status).toBe("unavailable")
    expect(scoreAnswer(text, raw, { minTokenChars: 1 }).status).toBe("ok")
  })

  test("token drift relative to the text gives unavailable, not made-up numbers", () => {
    const result = scoreAnswer("A completely different text that does not match.", tokens([["Something", -0.1], [" else", -0.2]]))
    expect(result.status).toBe("unavailable")
    expect(result.reason).toBe("tokens do not match the answer text")
    expect(result.score).toBeNull()
    expect(result.sentences).toEqual([])
  })
})

describe("truthprobe.scoreAnswer — arithmetic", () => {
  test("the total is a weighted mix of the global score and the sentence mean", () => {
    const text = "First. Second."
    const raw = tokens([
      ["First", -0.2],
      [".", -0.2],
      [" Second", -1.6],
      [".", -1.6],
    ])
    const result = scoreAnswer(text, raw, { globalWeight: 0.6 })
    const global = scoreAnswer(text, raw, { globalWeight: 1 }).score!
    const mean = result.sentences.reduce((sum, sentence) => sum + sentence.score, 0) / result.sentences.length
    expect(result.score!).toBeCloseTo(0.6 * global + 0.4 * mean, 10)
  })

  test("a confident answer scores higher than a doubtful one", () => {
    const text = "Moscow is the capital of Russia. Its population is about 13 million people."
    const confident = scoreAnswer(text, flat(text, -0.02))
    const hesitant = scoreAnswer(text, flat(text, -2.2))
    expect(confident.score!).toBeGreaterThan(hesitant.score!)
    expect(hesitant.flagged).toBeGreaterThan(0)
  })

  test("the first token is the first content token, punctuation is skipped", () => {
    const text = "«Paris» — the capital."
    const result = scoreAnswer(text, tokens([["«", -0.1], ["Paris", -0.5], ["»", -0.1], [" —", -0.1], [" the", -0.1], [" capital", -0.2], [".", -0.1]]))
    expect(result.first!.token).toBe("Paris")
    expect(result.first!.score).toBeCloseTo(phi(token("Paris", -0.5)), 10)
  })

  test("sentences do not mix tokens from their neighbours", () => {
    const text = "Good. Bad."
    const raw = tokens([["Good", -0.01], [".", -0.01], [" Bad", -3.5], [".", -3.5]])
    const result = scoreAnswer(text, raw)
    expect(result.sentences.length).toBe(2)
    const [good, bad] = result.sentences
    expect(good.flag).toBe(false)
    expect(bad.flag).toBe(true)
    expect(result.flagged).toBe(1)
    expect(good.tokens).toBe(1)
    expect(bad.tokens).toBe(1)
  })

  test("minLp and meanLp reflect the worst and the average token", () => {
    const text = "Alpha beta"
    const raw = tokens([["Alpha", -0.2], [" beta", -2.4]])
    const result = scoreAnswer(text, raw)
    const sentence = result.sentences[0]
    expect(sentence.minLp).toBe(-2.4)
    expect(sentence.meanLp).toBeCloseTo(Math.exp((-0.2 - 2.4) / 2), 10)
  })

  test("the risk threshold is configurable", () => {
    const text = "Moderately doubtful."
    const raw = flat(text, -1.4)
    const lenient = scoreAnswer(text, raw, { riskyThreshold: 1 })
    const strict = scoreAnswer(text, raw, { riskyThreshold: 0 })
    expect(lenient.flagged).toBe(0)
    expect(strict.flagged).toBe(strict.sentences.length)
    expect(strict.flagged).toBeGreaterThan(0)
  })

  test("globalWeight=1 gives the geometric mean over all tokens", () => {
    const text = "Absolutely certain."
    const raw = tokens([["Absol", -0.1], ["utely", -0.3], [" cert", -0.2], ["ain", -0.4], [".", -0.1]])
    const result = scoreAnswer(text, raw, { globalWeight: 1 })
    const expected = Math.exp((-0.1 - 0.3 - 0.2 - 0.4) / 4) // punctuation is not counted
    expect(result.score!).toBeCloseTo(expected, 10)
  })

  test("a repeated run on the same tokens gives the same numbers", () => {
    const text = "A repeatable answer. The very same."
    const first = scoreAnswer(text, flat(text, -0.7))
    const second = scoreAnswer(text, flat(text, -0.7))
    expect(second.score).toBeCloseTo(first.score!, 12)
    expect(second.sentences.map((sentence) => sentence.score)).toEqual(
      first.sentences.map((sentence) => sentence.score),
    )
  })

  test("a perfectly confident answer gives score 1 and risk 0", () => {
    const text = "ok"
    const result = scoreAnswer(text, [{ token: "ok", logprob: 0 }])
    expect(result.score).toBeCloseTo(1, 10)
    expect(result.risk).toBeCloseTo(0, 10)
    expect(result.flagged).toBe(0)
  })

  test("an extremely uncertain answer gives risk close to one", () => {
    const text = "Something very strange."
    const result = scoreAnswer(text, flat(text, -12))
    expect(result.risk!).toBeGreaterThan(0.95)
    expect(result.flagged).toBe(1)
  })

  test("sentence boundaries in the score match the segmenter", () => {
    const text = "First. Second."
    const result = scoreAnswer(text, flat(text, -0.3))
    const sentences = splitSentences(text)
    expect(result.sentences.map((s) => [s.start, s.end])).toEqual(sentences.map((s) => [s.start, s.end]))
  })
})
