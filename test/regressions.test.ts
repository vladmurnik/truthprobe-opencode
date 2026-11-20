import { describe, expect, test } from "bun:test"
import { alignTokens, isContentToken, scoreAnswer } from "../src/truthprobe/score.js"
import type { TokenLogprob } from "../src/truthprobe/types.js"

const token = (text: string, logprob = -0.1, delta = 1): TokenLogprob => ({
  token: text,
  logprob,
  top: [
    { token: text, logprob },
    { token: " other", logprob: logprob - delta },
  ],
})

describe("truthprobe regressions", () => {
  // A single ideograph is a whole word. Dropping it made every Chinese or
  // Japanese answer report "no content tokens" while real logprobs were there.
  test("single CJK characters count as content", () => {
    expect(isContentToken("東")).toBe(true)
    expect(isContentToken("の")).toBe(true)
    expect(isContentToken("한")).toBe(true)
    expect(isContentToken("東", 2)).toBe(true)
    // Latin single characters stay out: a lone letter is not a word.
    expect(isContentToken("A")).toBe(false)
  })

  test("a Chinese answer is scored, not reported as unavailable", () => {
    const text = "東京は日本の首都です。人口は約1400万人です。"
    const parts = ["東京", "は", "日本の", "首都", "です", "。", "人口", "は", "約", "1400", "万人", "です", "。"]
    const result = scoreAnswer(text, parts.map((part) => token(part, -0.2)))
    expect(result.status).toBe("ok")
    expect(result.sentences.length).toBeGreaterThan(1)
    expect(result.score).toBeGreaterThan(0)
  })

  // Gateways such as the free-pi one stream a text chunk and then a chunk that
  // carries logprobs for that token with an empty delta. Internal tokens
  // (`<​/think>`, stop markers) never appear in the answer text at all.
  test("alignment skips tokens that are not in the text", () => {
    const text = "Paris is the capital of France."
    const stream = [
      token("<​/think>", -0.01),
      token("Paris", -0.4),
      token(" is", -0.01),
      token("<​/end​-of​-sentence​>", -0.45),
      token(" the", -0.02),
      token(" capital", -0.05),
      token(" of", -0.01),
      token(" France", -0.03),
      token(".", -1.2),
    ]
    const aligned = alignTokens(text, stream)
    expect(aligned.map((t) => t.token)).not.toContain("<​/think>")
    expect(aligned[0]?.start).toBe(0)
    expect(aligned.at(-1)?.end).toBe(text.length)

    const result = scoreAnswer(text, stream)
    expect(result.status).toBe("ok")
    expect(result.sentences.length).toBe(1)
    expect(result.score).toBeGreaterThan(0)
  })

  test("no logprobs stays an explicit unavailable verdict", () => {
    const result = scoreAnswer("Paris is the capital of France.", [])
    expect(result.status).toBe("unavailable")
    expect(result.reason).toContain("no logprobs")
    expect(result.score).toBeNull()
    expect(result.sentences).toEqual([])
  })

  test("a partially covered answer is marked partial instead of silently wrong", () => {
    const text = "Paris is the capital of France. It has many museums."
    const result = scoreAnswer(text, [token("Paris", -0.2), token(" is", -0.1)])
    expect(result.status).toBe("partial")
  })
})
