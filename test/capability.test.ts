import { describe, expect, test } from "bun:test"
import * as Capability from "../src/truthprobe/capability.js"

const NOW = 1_800_000_000_000
const DAY = 24 * 60 * 60 * 1000

describe("ttl", () => {
  test("ok/ignored/rejected/unsupported live for a week", () => {
    expect(Capability.ttl("ok")).toBe(7 * DAY)
    expect(Capability.ttl("ignored")).toBe(7 * DAY)
    expect(Capability.ttl("rejected")).toBe(7 * DAY)
    expect(Capability.ttl("unsupported")).toBe(7 * DAY)
  })
  test("auth is re-checked after an hour", () => {
    expect(Capability.ttl("auth")).toBe(60 * 60 * 1000)
  })
  test("error is not cached at all", () => {
    expect(Capability.ttl("error")).toBe(0)
  })
})

describe("fresh", () => {
  test("a fresh entry lives", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - DAY }, NOW)).toBe(true)
  })
  test("a stale one does not", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - 8 * DAY }, NOW)).toBe(false)
  })
  test("exactly on the boundary — already not", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - 7 * DAY }, NOW)).toBe(false)
  })
  test("error is never fresh", () => {
    expect(Capability.fresh({ status: "error", checkedAt: NOW }, NOW)).toBe(false)
  })
  test("undefined is not fresh", () => {
    expect(Capability.fresh(undefined, NOW)).toBe(false)
  })
  test("an entry from the future is not fresh", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW + DAY }, NOW)).toBe(false)
  })
})

describe("enabled", () => {
  test("only ok enables collection", () => {
    expect(Capability.enabled({ status: "ok", checkedAt: NOW }, NOW)).toBe(true)
    for (const status of ["ignored", "rejected", "auth", "unsupported", "error"] as const) {
      expect(Capability.enabled({ status, checkedAt: NOW }, NOW)).toBe(false)
    }
  })
  test("an old ok does not enable", () => {
    expect(Capability.enabled({ status: "ok", checkedAt: NOW - 30 * DAY }, NOW)).toBe(false)
  })
})

describe("parse/serialize", () => {
  test("empty and broken input give an empty file", () => {
    expect(Capability.parse(undefined)).toEqual(Capability.empty())
    expect(Capability.parse("")).toEqual(Capability.empty())
    expect(Capability.parse("{not json")).toEqual(Capability.empty())
    expect(Capability.parse("null")).toEqual(Capability.empty())
    expect(Capability.parse('{"entries":null}')).toEqual(Capability.empty())
  })
  test("foreign and incomplete entries are dropped", () => {
    const file = Capability.parse(
      JSON.stringify({
        entries: {
          "p/m": { status: "ok", checkedAt: NOW },
          "p/bad": { status: "nonsense", checkedAt: NOW },
          "p/partial": { status: "ok" },
          "p/x": null,
        },
      }),
    )
    expect(Object.keys(file.entries)).toEqual(["p/m"])
  })
  test("roundtrip keeps the entry and the version", () => {
    const entry = { status: "ok" as const, checkedAt: NOW, endpoint: "https://x.test", model: "m" }
    const file = Capability.setEntry(Capability.empty(), "p/m", entry)
    expect(Capability.parse(Capability.serialize(file))).toEqual(file)
    expect(file.version).toBe(1)
  })
  test("serialization is stable and sorts keys", () => {
    let file = Capability.empty()
    file = Capability.setEntry(file, "z/z", { status: "ok", checkedAt: 1 })
    file = Capability.setEntry(file, "a/a", { status: "ignored", checkedAt: 2 })
    const text = Capability.serialize(file)
    expect(text.indexOf('"a/a"')).toBeLessThan(text.indexOf('"z/z"'))
    expect(Capability.serialize(file)).toBe(text)
  })
  test("setEntry does not mutate the input", () => {
    const file = Capability.empty()
    const next = Capability.setEntry(file, "p/m", { status: "ok", checkedAt: NOW })
    expect(file.entries).toEqual({})
    expect(next.entries["p/m"].status).toBe("ok")
  })
})

describe("probeBody", () => {
  test("one token, fixed text, logprobs enabled", () => {
    const body = Capability.probeBody("glm-5-free")
    expect(body.model).toBe("glm-5-free")
    expect(body.messages).toEqual([{ role: "user", content: "ping" }])
    expect(body.max_tokens).toBe(1)
    expect(body.stream).toBe(false)
    expect(body.logprobs).toBe(true)
    expect(body.top_logprobs).toBe(3)
  })
  test("topK is configurable", () => {
    expect(Capability.probeBody("m", 1).top_logprobs).toBe(1)
  })
})

describe("originOf", () => {
  test("drops the path and the query", () => {
    expect(Capability.originOf("https://opencode.ai/inference/v1/chat/completions?x=1")).toBe(
      "https://opencode.ai",
    )
  })
  test("junk — undefined", () => {
    expect(Capability.originOf("not a url")).toBeUndefined()
  })
})

describe("modelFromBody", () => {
  test("extracts the model", () => {
    expect(Capability.modelFromBody('{"model":"gpt-5","messages":[]}')).toBe("gpt-5")
  })
  test("without a model — undefined", () => {
    expect(Capability.modelFromBody('{"messages":[]}')).toBeUndefined()
    expect(Capability.modelFromBody('{"model":42}')).toBeUndefined()
    expect(Capability.modelFromBody("")).toBeUndefined()
    expect(Capability.modelFromBody(undefined)).toBeUndefined()
  })
})

describe("classify", () => {
  const okBody = JSON.stringify({
    choices: [{ logprobs: { content: [{ token: "Pa", logprob: -0.1, top_logprobs: [] }] } }],
  })
  test("200 with logprobs — ok", () => {
    expect(Capability.classify({ status: 200, body: okBody })).toBe("ok")
  })
  test("200 without logprobs — ignored", () => {
    expect(Capability.classify({ status: 200, body: '{"choices":[{}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: '{"choices":[{"logprobs":null}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: '{"choices":[{"logprobs":{"content":[]}}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: "not json" })).toBe("ignored")
  })
  test("401/403 — auth", () => {
    expect(Capability.classify({ status: 401, body: "" })).toBe("auth")
    expect(Capability.classify({ status: 403, body: "" })).toBe("auth")
  })
  test("429 and 5xx — temporary failure, not cached", () => {
    expect(Capability.classify({ status: 429, body: "" })).toBe("error")
    expect(Capability.classify({ status: 500, body: "" })).toBe("error")
    expect(Capability.classify({ status: 503, body: "" })).toBe("error")
  })
  test("400 mentioning logprobs — rejected", () => {
    expect(
      Capability.classify({ status: 400, body: '{"error":{"message":"Unsupported parameter: logprobs"}}' }),
    ).toBe("rejected")
  })
  test("400 for another reason — unsupported, not rejected", () => {
    expect(Capability.classify({ status: 400, body: '{"error":{"message":"bad temperature"}}' })).toBe("unsupported")
  })
  test("404/405 — wrong endpoint", () => {
    expect(Capability.classify({ status: 404, body: "" })).toBe("unsupported")
    expect(Capability.classify({ status: 405, body: "" })).toBe("unsupported")
  })
})

describe("describe/summary", () => {
  test("every status has text", () => {
    for (const status of ["ok", "ignored", "rejected", "auth", "unsupported", "error"] as const) {
      expect(Capability.describe(status).length).toBeGreaterThan(0)
    }
  })
  test("summary sorts and marks stale entries", () => {
    let file = Capability.empty()
    file = Capability.setEntry(file, "z/z", { status: "ok", checkedAt: NOW })
    file = Capability.setEntry(file, "a/a", { status: "rejected", checkedAt: NOW - 30 * DAY })
    const lines = Capability.summary(file.entries, NOW)
    expect(lines[0]).toContain("a/a: rejected")
    expect(lines[0]).toContain("(stale)")
    expect(lines[1]).toContain("z/z: ok")
    expect(lines[1]).not.toContain("(stale)")
  })
  test("keyOf joins provider and model", () => {
    expect(Capability.keyOf("opencode", "glm-5-free")).toBe("opencode/glm-5-free")
  })
})

describe("classify — tokens in any channel", () => {
  const response = (payload: unknown) => ({ status: 200, body: JSON.stringify(payload) })

  test("reasoning tokens with empty content — that is ok", () => {
    const body = { choices: [{ logprobs: { content: [], reasoning_content: [{ token: "a", logprob: -0.1 }] } }] }
    expect(Capability.classify(response(body))).toBe("ok")
  })

  test("a separate reasoning_logprobs — also ok", () => {
    const body = { choices: [{ reasoning_logprobs: { content: [{ token: "a", logprob: -0.2 }] } }] }
    expect(Capability.classify(response(body))).toBe("ok")
  })

  test("empty channels stay ignored", () => {
    const body = { choices: [{ logprobs: { content: [] } }] }
    expect(Capability.classify(response(body))).toBe("ignored")
  })
})
