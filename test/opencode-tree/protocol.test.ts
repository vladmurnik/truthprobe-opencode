import { afterEach, describe, expect, test } from "bun:test"
import {
  TRUTHPROBE_TOP_K,
  truthprobeBody,
  truthprobeEnabled,
  truthprobeFromDelta,
} from "../src/protocols/openai-chat.js"

const original = process.env.OPENCODE_TRUTHPROBE

afterEach(() => {
  if (original === undefined) delete process.env.OPENCODE_TRUTHPROBE
  else process.env.OPENCODE_TRUTHPROBE = original
})

describe("openai-chat.truthprobeEnabled", () => {
  test("capabilities win over the environment", () => {
    process.env.OPENCODE_TRUTHPROBE = "1"
    expect(truthprobeEnabled({ capabilities: { logprobs: false } })).toBe(false)
    delete process.env.OPENCODE_TRUTHPROBE
    expect(truthprobeEnabled({ capabilities: { logprobs: true } })).toBe(true)
  })

  test("environment flag accepts 1/on/true only", () => {
    for (const value of ["1", "on", "true"]) {
      process.env.OPENCODE_TRUTHPROBE = value
      expect(truthprobeEnabled({})).toBe(true)
    }
    for (const value of ["0", "off", "false", "", "yes"]) {
      process.env.OPENCODE_TRUTHPROBE = value
      expect(truthprobeEnabled({})).toBe(false)
    }
    delete process.env.OPENCODE_TRUTHPROBE
    expect(truthprobeEnabled({})).toBe(false)
    expect(truthprobeEnabled({ capabilities: {} })).toBe(false)
  })
})

describe("openai-chat.truthprobeBody", () => {
  test("requests logprobs with the configured top-k", () => {
    expect(TRUTHPROBE_TOP_K).toBeGreaterThan(1)
    expect(truthprobeBody({ capabilities: { logprobs: true } })).toEqual({
      logprobs: true,
      top_logprobs: TRUTHPROBE_TOP_K,
    })
  })

  test("adds nothing when the model cannot return logprobs", () => {
    expect(truthprobeBody({ capabilities: { logprobs: false } })).toEqual({})
    delete process.env.OPENCODE_TRUTHPROBE
    expect(truthprobeBody({})).toEqual({})
  })
})

describe("openai-chat.truthprobeFromDelta", () => {
  test("missing or empty content yields undefined", () => {
    expect(truthprobeFromDelta(undefined)).toBeUndefined()
    expect(truthprobeFromDelta(null)).toBeUndefined()
    expect(truthprobeFromDelta({ content: [] } as never)).toBeUndefined()
  })

  test("keeps token, logprob and top alternatives", () => {
    const parsed = truthprobeFromDelta({
      content: [
        {
          token: "Paris",
          logprob: -0.02,
          bytes: [80, 97],
          top_logprobs: [
            { token: "Paris", logprob: -0.02 },
            { token: "Lyon", logprob: -3.9 },
          ],
        },
      ],
    } as never)
    expect(parsed).toEqual([
      {
        token: "Paris",
        logprob: -0.02,
        top: [
          { token: "Paris", logprob: -0.02 },
          { token: "Lyon", logprob: -3.9 },
        ],
      },
    ])
  })

  test("tokens without top_logprobs stay lean", () => {
    const parsed = truthprobeFromDelta({ content: [{ token: " ok", logprob: -0.4 }] } as never)
    expect(parsed).toEqual([{ token: " ok", logprob: -0.4 }])
    expect(parsed![0]).not.toHaveProperty("top")
  })

  test("logprob 0 survives (not treated as falsy)", () => {
    const parsed = truthprobeFromDelta({ content: [{ token: "a", logprob: 0, top_logprobs: [] }] } as never)
    expect(parsed![0].logprob).toBe(0)
  })
})
