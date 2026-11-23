import { afterEach, describe, expect, test } from "bun:test"

// This file lives both in the repository (`test/opencode-tree/`) and in the opencode tree
// (`packages/ai/test/`), so the path to the sources is tried in turn.
// A silent `describe.skip` hid these tests from CI, so with
// TRUTHPROBE_REQUIRE_PROTOCOL_TESTS=1 missing sources are an error.
const candidates = [
  "../src/protocols/openai-chat.js",
  "../../src/protocols/openai-chat.js",
  "../../packages/ai/src/protocols/openai-chat.js",
]
let protocol: Record<string, unknown> | undefined
for (const candidate of candidates) {
  protocol = await import(candidate).catch(() => undefined)
  if (protocol) break
}
if (!protocol && process.env.TRUTHPROBE_REQUIRE_PROTOCOL_TESTS === "1")
  throw new Error("protocol sources not found; run inside the opencode tree or unset TRUTHPROBE_REQUIRE_PROTOCOL_TESTS")
const TRUTHPROBE_TOP_K = protocol?.TRUTHPROBE_TOP_K as number
const truthprobeBody = protocol?.truthprobeBody as (...args: any[]) => Record<string, unknown>
const truthprobeEnabled = protocol?.truthprobeEnabled as (...args: any[]) => boolean
const truthprobeFromDelta = protocol?.truthprobeFromDelta as (...args: any[]) => unknown
const suite = protocol ? describe : describe.skip

const original = process.env.OPENCODE_TRUTHPROBE

afterEach(() => {
  if (original === undefined) delete process.env.OPENCODE_TRUTHPROBE
  else process.env.OPENCODE_TRUTHPROBE = original
})

suite("openai-chat.truthprobeEnabled", () => {
  // The README promises: `OPENCODE_TRUTHPROBE=1` asks for logprobs on every chat-completions
  // model, that is, the explicit variable is stronger than capabilities. The test used to
  // require the opposite and kept CI red.
  test("an explicit environment override wins over capabilities", () => {
    process.env.OPENCODE_TRUTHPROBE = "1"
    expect(truthprobeEnabled({ capabilities: { logprobs: false } })).toBe(true)
    process.env.OPENCODE_TRUTHPROBE = "0"
    expect(truthprobeEnabled({ capabilities: { logprobs: true } })).toBe(false)
  })

  test("without the environment, capabilities decide", () => {
    delete process.env.OPENCODE_TRUTHPROBE
    expect(truthprobeEnabled({ capabilities: { logprobs: true } })).toBe(true)
    expect(truthprobeEnabled({ capabilities: { logprobs: false } })).toBe(false)
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

suite("openai-chat.truthprobeBody", () => {
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

suite("openai-chat.truthprobeFromDelta", () => {
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
