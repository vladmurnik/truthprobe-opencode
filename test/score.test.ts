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

/** Токен с двумя альтернативами: сам токен и «шум» на дельту ниже. */
const token = (text: string, logprob: number, delta = 1): TokenLogprob => ({
  token: text,
  logprob,
  top: [
    { token: text, logprob },
    { token: " other", logprob: logprob - delta },
  ],
})

/** Собирает токены из пар, как их вернул бы провайдер. */
const tokens = (values: Array<[string, number]>, delta = 1): TokenLogprob[] =>
  values.map(([text, logprob]) => token(text, logprob, delta))

/** Нарезает текст на токены по границам слов, чтобы смещения совпадали. */
const slice = (text: string, size = 4): string[] => {
  const out: string[] = []
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size))
  return out
}

/** Ровные токены с заданным logprob на весь текст. */
const flat = (text: string, logprob: number): TokenLogprob[] =>
  slice(text).map((part) => token(part, logprob))

describe("truthprobe.isContentToken", () => {
  test("keeps ordinary words", () => {
    expect(isContentToken("Paris")).toBe(true)
    expect(isContentToken("Париж")).toBe(true)
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
    const certain = { token: "да", logprob: 0, top: [{ token: "да", logprob: 0 }] }
    expect(normalizedEntropy(certain)).toBe(0)
    expect(phi(certain)).toBe(1)
  })

  test("no top-k degrades to the token probability", () => {
    expect(phi({ token: "x", logprob: -0.5 })).toBeCloseTo(Math.exp(-0.5), 6)
    expect(phi({ token: "x", logprob: 0 })).toBe(1)
  })

  test("two equal alternatives give zero phi", () => {
    const split = { token: "да", logprob: -0.7, top: [{ token: "да", logprob: -0.7 }, { token: "нет", logprob: -0.7 }] }
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
    // После фильтра остаётся один кандидат → деградация к p(token).
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
    const text = "Первое. Второе.\n\nТретье — с тире!"
    for (const sentence of splitSentences(text)) {
      expect(text.slice(sentence.start, sentence.end)).toBe(sentence.text)
    }
  })

  test("does not split decimals", () => {
    expect(texts("Pi is 3.14 exactly.")).toEqual(["Pi is 3.14 exactly."])
  })

  test("does not split abbreviations", () => {
    expect(texts("Это т.е. пример. Конец.")).toEqual(["Это т.е. пример.", "Конец."])
    expect(texts("Use e.g. this one. Fine.")).toEqual(["Use e.g. this one.", "Fine."])
    expect(texts("Apples, pears, etc. And more.")).toEqual(["Apples, pears, etc.", "And more."])
    expect(texts("См. выше. Да.")).toEqual(["См. выше.", "Да."])
  })

  test("supports the ellipsis and CJK terminators", () => {
    expect(texts("Ждём… И вот.")).toEqual(["Ждём…", "И вот."])
    expect(texts("これは文です。次です。")).toEqual(["これは文です。", "次です。"])
  })

  test("a blank line always breaks a sentence", () => {
    expect(texts("A\n\nB")).toEqual(["A", "B"])
  })

  test("code blocks are dropped entirely", () => {
    const text = "Перед.\n```js\nconst a = 1;\n```\nПосле."
    expect(texts(text)).toEqual(["Перед.", "После."])
  })

  test("unclosed code block swallows the rest", () => {
    expect(texts("Перед.\n```js\nconst a = 1;")).toEqual(["Перед."])
  })

  test("empty and whitespace-only input give nothing", () => {
    expect(splitSentences("")).toEqual([])
    expect(splitSentences("   \n\t ")).toEqual([])
  })

  test("single line without terminator is one sentence", () => {
    expect(texts("Просто строка без точки")).toEqual(["Просто строка без точки"])
  })

  test("list items without terminators stay together", () => {
    // Документируем поведение: одиночный перевод строки не является границей.
    expect(texts("- one\n- two")).toEqual(["- one\n- two"])
  })

  test("indices are sequential starting from zero", () => {
    const sentences = splitSentences("A. B. C.")
    expect(sentences.map((s) => s.i)).toEqual([0, 1, 2])
  })
})

describe("truthprobe.scoreAnswer — деградация", () => {
  test("без токенов возвращает unavailable", () => {
    const result = scoreAnswer("Любой текст.", [])
    expect(result.status).toBe("unavailable")
    expect(result.score).toBeNull()
    expect(result.risk).toBeNull()
    expect(result.first).toBeNull()
    expect(result.sentences).toEqual([])
    expect(result.flagged).toBe(0)
    expect(result.reason).toBe("no logprobs in response")
  })

  test("только пунктуация — нет содержательных токенов", () => {
    const result = scoreAnswer("...", tokens([["...", -0.1], [" .", -0.2]]))
    expect(result.status).toBe("unavailable")
    expect(result.reason).toBe("no content tokens")
  })

  test("minTokenChars можно ослабить", () => {
    const text = "a b"
    const raw = tokens([["a", -0.1], [" b", -0.1]])
    expect(scoreAnswer(text, raw).status).toBe("unavailable")
    expect(scoreAnswer(text, raw, { minTokenChars: 1 }).status).toBe("ok")
  })

  test("дрейф токенов относительно текста даёт unavailable, а не выдуманные числа", () => {
    const result = scoreAnswer("Совсем другой текст, который не совпадает.", tokens([["Что-то", -0.1], [" иное", -0.2]]))
    expect(result.status).toBe("unavailable")
    expect(result.reason).toBe("tokens do not match the answer text")
    expect(result.score).toBeNull()
    expect(result.sentences).toEqual([])
  })
})

describe("truthprobe.scoreAnswer — арифметика", () => {
  test("итог — взвешенная смесь общего скора и среднего по предложениям", () => {
    const text = "Первое. Второе."
    const raw = tokens([
      ["Первое", -0.2],
      [".", -0.2],
      [" Второе", -1.6],
      [".", -1.6],
    ])
    const result = scoreAnswer(text, raw, { globalWeight: 0.6 })
    const global = scoreAnswer(text, raw, { globalWeight: 1 }).score!
    const mean = result.sentences.reduce((sum, sentence) => sum + sentence.score, 0) / result.sentences.length
    expect(result.score!).toBeCloseTo(0.6 * global + 0.4 * mean, 10)
    expect(result.risk!).toBeCloseTo(1 - result.score!, 10)
  })

  test("уверенный ответ выше сомнительного", () => {
    const text = "Москва — столица России. Население около 13 миллионов человек."
    const confident = scoreAnswer(text, flat(text, -0.02))
    const hesitant = scoreAnswer(text, flat(text, -2.2))
    expect(confident.score!).toBeGreaterThan(hesitant.score!)
    expect(hesitant.flagged).toBeGreaterThan(0)
  })

  test("первый токен — первый содержательный, пунктуация пропускается", () => {
    const text = "«Париж» — столица."
    const result = scoreAnswer(text, tokens([["«", -0.1], ["Париж", -0.5], ["»", -0.1], [" —", -0.1], [" столица", -0.2], [".", -0.1]]))
    expect(result.first!.token).toBe("Париж")
    expect(result.first!.score).toBeCloseTo(phi(token("Париж", -0.5)), 10)
  })

  test("предложения не смешивают токены соседей", () => {
    const text = "Хорошо. Плохо."
    const raw = tokens([["Хорошо", -0.01], [".", -0.01], [" Плохо", -3.5], [".", -3.5]])
    const result = scoreAnswer(text, raw)
    expect(result.sentences.length).toBe(2)
    const [good, bad] = result.sentences
    expect(good.flag).toBe(false)
    expect(bad.flag).toBe(true)
    expect(result.flagged).toBe(1)
    expect(good.tokens).toBe(1)
    expect(bad.tokens).toBe(1)
  })

  test("minLp и meanLp отражают худший и средний токен", () => {
    const text = "Аа бб"
    const raw = tokens([["Аа", -0.2], [" бб", -2.4]])
    const result = scoreAnswer(text, raw)
    const sentence = result.sentences[0]
    expect(sentence.minLp).toBe(-2.4)
    expect(sentence.meanLp).toBeCloseTo(Math.exp((-0.2 - 2.4) / 2), 10)
  })

  test("порог риска настраивается", () => {
    const text = "Средне сомнительно."
    const raw = flat(text, -1.4)
    const lenient = scoreAnswer(text, raw, { riskyThreshold: 1 })
    const strict = scoreAnswer(text, raw, { riskyThreshold: 0 })
    expect(lenient.flagged).toBe(0)
    expect(strict.flagged).toBe(strict.sentences.length)
    expect(strict.flagged).toBeGreaterThan(0)
  })

  test("globalWeight=1 даёт геометрическое среднее по всем токенам", () => {
    const text = "Совершенно уверенно."
    const raw = tokens([["Совер", -0.1], ["шенно", -0.3], [" уверен", -0.2], ["но", -0.4], [".", -0.1]])
    const result = scoreAnswer(text, raw, { globalWeight: 1 })
    const expected = Math.exp((-0.1 - 0.3 - 0.2 - 0.4) / 4) // пунктуация не в счёте
    expect(result.score!).toBeCloseTo(expected, 10)
  })

  test("повторный прогон на тех же токенах даёт те же числа", () => {
    const text = "Повторяемый ответ. Тот же самый."
    const first = scoreAnswer(text, flat(text, -0.7))
    const second = scoreAnswer(text, flat(text, -0.7))
    expect(second.score).toBeCloseTo(first.score!, 12)
    expect(second.sentences.map((sentence) => sentence.score)).toEqual(
      first.sentences.map((sentence) => sentence.score),
    )
  })

  test("идеально уверенный ответ даёт score 1 и risk 0", () => {
    const text = "ok"
    const result = scoreAnswer(text, [{ token: "ok", logprob: 0 }])
    expect(result.score).toBeCloseTo(1, 10)
    expect(result.risk).toBeCloseTo(0, 10)
    expect(result.flagged).toBe(0)
  })

  test("крайне неуверенный ответ даёт risk около единицы", () => {
    const text = "Что-то очень странное."
    const result = scoreAnswer(text, flat(text, -12))
    expect(result.risk!).toBeGreaterThan(0.95)
    expect(result.flagged).toBe(1)
  })

  test("границы предложений в оценке совпадают с сегментатором", () => {
    const text = "Первое. Второе."
    const result = scoreAnswer(text, flat(text, -0.3))
    const sentences = splitSentences(text)
    expect(result.sentences.map((s) => [s.start, s.end])).toEqual(sentences.map((s) => [s.start, s.end]))
  })

  test("каждое оценённое предложение имеет risk = 1 - score", () => {
    const text = "Раз. Два. Три."
    for (const sentence of scoreAnswer(text, flat(text, -0.9)).sentences) {
      expect(sentence.risk).toBeCloseTo(1 - sentence.score, 10)
    }
  })
})
