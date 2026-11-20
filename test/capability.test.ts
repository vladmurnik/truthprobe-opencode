import { describe, expect, test } from "bun:test"
import * as Capability from "../src/truthprobe/capability.js"

const NOW = 1_800_000_000_000
const DAY = 24 * 60 * 60 * 1000

describe("ttl", () => {
  test("ok/ignored/rejected/unsupported Р¶РёРІСѓС‚ РЅРµРґРµР»СЋ", () => {
    expect(Capability.ttl("ok")).toBe(7 * DAY)
    expect(Capability.ttl("ignored")).toBe(7 * DAY)
    expect(Capability.ttl("rejected")).toBe(7 * DAY)
    expect(Capability.ttl("unsupported")).toBe(7 * DAY)
  })
  test("auth РїРµСЂРµРїСЂРѕРІРµСЂСЏРµРј С‡РµСЂРµР· С‡Р°СЃ", () => {
    expect(Capability.ttl("auth")).toBe(60 * 60 * 1000)
  })
  test("error РЅРµ РєСЌС€РёСЂСѓРµС‚СЃСЏ РІРѕРІСЃРµ", () => {
    expect(Capability.ttl("error")).toBe(0)
  })
})

describe("fresh", () => {
  test("СЃРІРµР¶Р°СЏ Р·Р°РїРёСЃСЊ Р¶РёРІС‘С‚", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - DAY }, NOW)).toBe(true)
  })
  test("РїСЂРѕСЃСЂРѕС‡РµРЅРЅР°СЏ вЂ” РЅРµС‚", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - 8 * DAY }, NOW)).toBe(false)
  })
  test("СЂРѕРІРЅРѕ РЅР° РіСЂР°РЅРёС†Рµ вЂ” СѓР¶Рµ РЅРµС‚", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW - 7 * DAY }, NOW)).toBe(false)
  })
  test("error РЅРµ Р±С‹РІР°РµС‚ СЃРІРµР¶РёРј", () => {
    expect(Capability.fresh({ status: "error", checkedAt: NOW }, NOW)).toBe(false)
  })
  test("undefined вЂ” РЅРµ СЃРІРµР¶РёР№", () => {
    expect(Capability.fresh(undefined, NOW)).toBe(false)
  })
  test("Р·Р°РїРёСЃСЊ РёР· Р±СѓРґСѓС‰РµРіРѕ РЅРµ СЃС‡РёС‚Р°РµС‚СЃСЏ СЃРІРµР¶РµР№", () => {
    expect(Capability.fresh({ status: "ok", checkedAt: NOW + DAY }, NOW)).toBe(false)
  })
})

describe("enabled", () => {
  test("С‚РѕР»СЊРєРѕ ok РІРєР»СЋС‡Р°РµС‚ СЃР±РѕСЂ", () => {
    expect(Capability.enabled({ status: "ok", checkedAt: NOW }, NOW)).toBe(true)
    for (const status of ["ignored", "rejected", "auth", "unsupported", "error"] as const) {
      expect(Capability.enabled({ status, checkedAt: NOW }, NOW)).toBe(false)
    }
  })
  test("СЃС‚Р°СЂС‹Р№ ok РЅРµ РІРєР»СЋС‡Р°РµС‚", () => {
    expect(Capability.enabled({ status: "ok", checkedAt: NOW - 30 * DAY }, NOW)).toBe(false)
  })
})

describe("parse/serialize", () => {
  test("РїСѓСЃС‚РѕР№ Рё Р±РёС‚С‹Р№ РІС…РѕРґ РґР°СЋС‚ РїСѓСЃС‚РѕР№ С„Р°Р№Р»", () => {
    expect(Capability.parse(undefined)).toEqual(Capability.empty())
    expect(Capability.parse("")).toEqual(Capability.empty())
    expect(Capability.parse("{РЅРµ json")).toEqual(Capability.empty())
    expect(Capability.parse("null")).toEqual(Capability.empty())
    expect(Capability.parse('{"entries":null}')).toEqual(Capability.empty())
  })
  test("С‡СѓР¶РёРµ Рё РЅРµРїРѕР»РЅС‹Рµ Р·Р°РїРёСЃРё РѕС‚Р±СЂР°СЃС‹РІР°СЋС‚СЃСЏ", () => {
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
  test("roundtrip СЃРѕС…СЂР°РЅСЏРµС‚ Р·Р°РїРёСЃСЊ Рё РІРµСЂСЃРёСЋ", () => {
    const entry = { status: "ok" as const, checkedAt: NOW, endpoint: "https://x.test", model: "m" }
    const file = Capability.setEntry(Capability.empty(), "p/m", entry)
    expect(Capability.parse(Capability.serialize(file))).toEqual(file)
    expect(file.version).toBe(1)
  })
  test("СЃРµСЂРёР°Р»РёР·Р°С†РёСЏ СЃС‚Р°Р±РёР»СЊРЅР° Рё СЃРѕСЂС‚РёСЂСѓРµС‚ РєР»СЋС‡Рё", () => {
    let file = Capability.empty()
    file = Capability.setEntry(file, "z/z", { status: "ok", checkedAt: 1 })
    file = Capability.setEntry(file, "a/a", { status: "ignored", checkedAt: 2 })
    const text = Capability.serialize(file)
    expect(text.indexOf('"a/a"')).toBeLessThan(text.indexOf('"z/z"'))
    expect(Capability.serialize(file)).toBe(text)
  })
  test("setEntry РЅРµ РјСѓС‚РёСЂСѓРµС‚ РІС…РѕРґ", () => {
    const file = Capability.empty()
    const next = Capability.setEntry(file, "p/m", { status: "ok", checkedAt: NOW })
    expect(file.entries).toEqual({})
    expect(next.entries["p/m"].status).toBe("ok")
  })
})

describe("probeBody", () => {
  test("РѕРґРёРЅ С‚РѕРєРµРЅ, С„РёРєСЃРёСЂРѕРІР°РЅРЅС‹Р№ С‚РµРєСЃС‚, logprobs РІРєР»СЋС‡РµРЅС‹", () => {
    const body = Capability.probeBody("glm-5-free")
    expect(body.model).toBe("glm-5-free")
    expect(body.messages).toEqual([{ role: "user", content: "ping" }])
    expect(body.max_tokens).toBe(1)
    expect(body.stream).toBe(false)
    expect(body.logprobs).toBe(true)
    expect(body.top_logprobs).toBe(3)
  })
  test("topK РЅР°СЃС‚СЂР°РёРІР°РµС‚СЃСЏ", () => {
    expect(Capability.probeBody("m", 1).top_logprobs).toBe(1)
  })
})

describe("originOf", () => {
  test("РѕС‚Р±СЂР°СЃС‹РІР°РµС‚ РїСѓС‚СЊ Рё query", () => {
    expect(Capability.originOf("https://opencode.ai/inference/v1/chat/completions?x=1")).toBe(
      "https://opencode.ai",
    )
  })
  test("РјСѓСЃРѕСЂ вЂ” undefined", () => {
    expect(Capability.originOf("not a url")).toBeUndefined()
  })
})

describe("modelFromBody", () => {
  test("РґРѕСЃС‚Р°С‘С‚ РјРѕРґРµР»СЊ", () => {
    expect(Capability.modelFromBody('{"model":"gpt-5","messages":[]}')).toBe("gpt-5")
  })
  test("Р±РµР· РјРѕРґРµР»Рё вЂ” undefined", () => {
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
  test("200 СЃ logprobs вЂ” ok", () => {
    expect(Capability.classify({ status: 200, body: okBody })).toBe("ok")
  })
  test("200 Р±РµР· logprobs вЂ” ignored", () => {
    expect(Capability.classify({ status: 200, body: '{"choices":[{}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: '{"choices":[{"logprobs":null}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: '{"choices":[{"logprobs":{"content":[]}}]}' })).toBe("ignored")
    expect(Capability.classify({ status: 200, body: "РЅРµ json" })).toBe("ignored")
  })
  test("401/403 вЂ” auth", () => {
    expect(Capability.classify({ status: 401, body: "" })).toBe("auth")
    expect(Capability.classify({ status: 403, body: "" })).toBe("auth")
  })
  test("429 Рё 5xx вЂ” РІСЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР°, РЅРµ РєСЌС€РёСЂСѓРµРј", () => {
    expect(Capability.classify({ status: 429, body: "" })).toBe("error")
    expect(Capability.classify({ status: 500, body: "" })).toBe("error")
    expect(Capability.classify({ status: 503, body: "" })).toBe("error")
  })
  test("400 СЃ СѓРїРѕРјРёРЅР°РЅРёРµРј logprobs вЂ” rejected", () => {
    expect(
      Capability.classify({ status: 400, body: '{"error":{"message":"Unsupported parameter: logprobs"}}' }),
    ).toBe("rejected")
  })
  test("400 РїРѕ РґСЂСѓРіРѕР№ РїСЂРёС‡РёРЅРµ вЂ” unsupported, Р° РЅРµ rejected", () => {
    expect(Capability.classify({ status: 400, body: '{"error":{"message":"bad temperature"}}' })).toBe("unsupported")
  })
  test("404/405 вЂ” СЌРЅРґРїРѕРёРЅС‚ РЅРµ С‚РѕС‚", () => {
    expect(Capability.classify({ status: 404, body: "" })).toBe("unsupported")
    expect(Capability.classify({ status: 405, body: "" })).toBe("unsupported")
  })
})

describe("describe/summary", () => {
  test("РєР°Р¶РґС‹Р№ СЃС‚Р°С‚СѓСЃ РёРјРµРµС‚ С‚РµРєСЃС‚", () => {
    for (const status of ["ok", "ignored", "rejected", "auth", "unsupported", "error"] as const) {
      expect(Capability.describe(status).length).toBeGreaterThan(0)
    }
  })
  test("summary СЃРѕСЂС‚РёСЂСѓРµС‚ Рё РїРѕРјРµС‡Р°РµС‚ РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ", () => {
    let file = Capability.empty()
    file = Capability.setEntry(file, "z/z", { status: "ok", checkedAt: NOW })
    file = Capability.setEntry(file, "a/a", { status: "rejected", checkedAt: NOW - 30 * DAY })
    const lines = Capability.summary(file.entries, NOW)
    expect(lines[0]).toContain("a/a: rejected")
    expect(lines[0]).toContain("(stale)")
    expect(lines[1]).toContain("z/z: ok")
    expect(lines[1]).not.toContain("(stale)")
  })
  test("keyOf СЃРєР»РµРёРІР°РµС‚ РїСЂРѕРІР°Р№РґРµСЂР° Рё РјРѕРґРµР»СЊ", () => {
    expect(Capability.keyOf("opencode", "glm-5-free")).toBe("opencode/glm-5-free")
  })
})
