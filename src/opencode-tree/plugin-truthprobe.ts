/**
 * TruthProbe: probing providers and automatically enabling logprobs collection.
 *
 * The plugin listens on `http.request` — the only place where both the model and
 * a ready URL with authorization are visible. The request proceeds on its own: the
 * hook only puts an event into a queue, and the probe runs in a separate fiber, so
 * the model answer never waits for the probe.
 *
 * The probe is a single request for a single token with the fixed text "ping".
 * No user data takes part in it. The verdict goes into
 * `<data>/truthprobe/capabilities.json` and, if the provider returns logprobs,
 * enables `capabilities.logprobs` on the model: from the next request the protocol
 * asks for logprobs itself, and the confidence badge appears without environment variables.
 *
 * To disable the probe: OPENCODE_TRUTHPROBE_PROBE=off.
 */
import { define } from "@opencode/plugin/effect/plugin"
import { Effect, Queue, Stream } from "effect"
import fs from "node:fs"
import path from "node:path"
import { Global } from "@opencode/util/global"
import type { SessionHooks } from "@opencode/plugin/effect/session"
import * as Capability from "../truthprobe/capability.js"
import type { PluginInternal } from "./internal.js"

const PROBE_TIMEOUT_MS = 15_000
const CHAT_PATH = "/chat/completions"
/** As many alternatives as the production request asks for (TRUTHPROBE_TOP_K). */
const PROBE_TOP_K = 20

type HttpRequest = SessionHooks["http.request"]

const disabled = () => {
  const env = process.env
  const flag = (env.OPENCODE_TRUTHPROBE_PROBE ?? "").toLowerCase()
  if (flag === "0" || flag === "off" || flag === "false" || flag === "no") return true
  const master = (env.OPENCODE_TRUTHPROBE ?? "").toLowerCase()
  return master === "0" || master === "off" || master === "false"
}

export const TruthprobePlugin = define({
  id: "opencode.truthprobe",
  effect: Effect.fn(function* (ctx) {
    const global = yield* Global.Service
    const directory = path.join(global.data, "truthprobe")
    const file = path.join(directory, "capabilities.json")

    // The protocol inside the ai package reads the same file: pass the path once per process.
    process.env.OPENCODE_TRUTHPROBE_CACHE ??= file

    let state = Capability.parse(read())
    const running = new Set<string>()
    const enabled = new Set<string>()

    function read() {
      try {
        return fs.readFileSync(file, "utf8")
      } catch {
        return undefined
      }
    }

    function write(next: Capability.File) {
      try {
        fs.mkdirSync(directory, { recursive: true })
        const temporary = `${file}.${process.pid}.tmp`
        fs.writeFileSync(temporary, Capability.serialize(next))
        fs.renameSync(temporary, file)
      } catch {
        // the cache is an optimisation: without it we simply probe once more
      }
    }

    /** Enables logprobs on the model if the user has not set the flag explicitly. */
    const enable = Effect.fn("TruthprobePlugin.enable")(function* (providerID: string, modelID: string) {
      const key = Capability.keyOf(providerID, modelID)
      if (enabled.has(key)) return
      enabled.add(key)
      yield* ctx.model.transform((models) => {
        models.update(providerID, modelID, (draft) => {
          if (draft.capabilities?.logprobs !== undefined) return
          draft.capabilities = { ...draft.capabilities, logprobs: true }
        })
      })
      yield* ctx.model.reload()
    })

    const probe = Effect.fn("TruthprobePlugin.probe")(function* (event: HttpRequest) {
      const providerID = event.model.providerID
      const key = Capability.keyOf(providerID, event.model.id)
      const url = event.request.url
      const raw = yield* Effect.promise(() => event.request.clone().text()).pipe(
        Effect.orElseSucceed(() => undefined as string | undefined),
      )
      const modelID = Capability.modelFromBody(raw) ?? event.model.id
      const headers = new Headers(event.request.headers)
      headers.delete("content-length")
      headers.set("content-type", "application/json")
      const body = JSON.stringify(Capability.probeBody(modelID, PROBE_TOP_K))
      const response = yield* Effect.promise(async () => {
        const result = await fetch(url, {
          method: "POST",
          headers,
          body,
          signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
        })
        return { status: result.status, body: await result.text() }
      }).pipe(Effect.orElseSucceed(() => undefined))
      if (!response) {
        yield* Effect.logDebug("truthprobe: probe could not reach the provider", { providerID, modelID })
        return
      }
      const status = Capability.classify(response)
      if (status === "error") {
        // 429/5xx: do not cache, retry on the next request
        yield* Effect.logDebug("truthprobe: probe inconclusive", { providerID, modelID, code: response.status })
        return
      }
      state = Capability.setEntry(state, key, {
        status,
        checkedAt: Date.now(),
        endpoint: Capability.originOf(url),
        model: modelID,
        ...(status === "ok" ? {} : { detail: `${response.status} ${response.body.slice(0, 160)}` }),
      })
      write(state)
      yield* Effect.logInfo(`truthprobe: ${key} → ${status} (${Capability.describe(status)})`)
      if (status === "ok") yield* enable(providerID, event.model.id)
    })

    // Disabled by the user: touch neither the model catalog nor the network.
    if (disabled()) return

    // Known "yes" answers are enabled right away: the badge works from the very first answer.
    const now = Date.now()
    for (const [key, entry] of Object.entries(state.entries)) {
      if (!Capability.enabled(entry, now)) continue
      const [providerID, ...rest] = key.split("/")
      if (!providerID || rest.length === 0) continue
      yield* enable(providerID, rest.join("/"))
    }


    // Queue + a single fiber: the hook does not wait for the network, probes run strictly one at a time.
    const queue = yield* Queue.unbounded<HttpRequest>()
    yield* Stream.fromQueue(queue).pipe(
      Stream.runForEach((event) => {
        const key = Capability.keyOf(event.model.providerID, event.model.id)
        return Effect.gen(function* () {
          const entry = Capability.getEntry(state, key)
          if (Capability.fresh(entry, Date.now())) {
            if (Capability.enabled(entry, Date.now())) yield* enable(event.model.providerID, event.model.id)
            return
          }
          yield* probe(event)
        }).pipe(
          Effect.catchCause(() => Effect.void),
          Effect.ensuring(Effect.sync(() => running.delete(key))),
        )
      }),
      Effect.forkScoped,
    )

    yield* ctx.session.hook("http.request", (event) =>
      Effect.gen(function* () {
        if (!event.request.url.includes(CHAT_PATH)) return
        const key = Capability.keyOf(event.model.providerID, event.model.id)
        if (running.has(key)) return
        running.add(key)
        yield* Queue.offer(queue, event).pipe(Effect.asVoid)
      }),
    )
  }),
}) satisfies PluginInternal.InternalPlugin
