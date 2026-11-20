/**
 * TruthProbe: проверка провайдеров и автоматическое включение сбора logprobs.
 *
 * Плагин слушает `http.request` — единственное место, где видны и модель, и
 * готовый URL с авторизацией. Запрос уходит своим чередом: хук только кладёт
 * событие в очередь, а проверка выполняется в отдельной fiber, поэтому ответ
 * модели никогда не ждёт проверки.
 *
 * Проверка — одна посылка на один токен с фиксированным текстом "ping".
 * Данные пользователя в ней не участвуют. Вердикт кладётся в
 * `<data>/truthprobe/capabilities.json` и, если провайдер отдаёт logprobs,
 * включает `capabilities.logprobs` у модели: со следующего запроса протокол
 * сам просит logprobs, и бейдж уверенности появляется без переменных окружения.
 *
 * Отключить проверку: OPENCODE_TRUTHPROBE_PROBE=off.
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
/** Столько же альтернатив, сколько просит боевой запрос (TRUTHPROBE_TOP_K). */
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

    // Протокол в пакете ai читает тот же файл: путь передаём один раз на процесс.
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
        // кэш — оптимизация: без него просто проверим ещё раз
      }
    }

    /** Включает logprobs у модели, если пользователь не выставил флаг явно. */
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
        // 429/5xx: не кэшируем, попробуем на следующем запросе
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

    // Выключено пользователем: не трогаем ни каталог моделей, ни сеть.
    if (disabled()) return

    // Известные «да» включаем сразу: бейдж работает с первого же ответа.
    const now = Date.now()
    for (const [key, entry] of Object.entries(state.entries)) {
      if (!Capability.enabled(entry, now)) continue
      const [providerID, ...rest] = key.split("/")
      if (!providerID || rest.length === 0) continue
      yield* enable(providerID, rest.join("/"))
    }


    // Очередь + одна fiber: хук не ждёт сети, проверки идут строго по одной.
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
