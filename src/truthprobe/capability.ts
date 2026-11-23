/**
 * TruthProbe: detecting whether a provider returns logprobs.
 *
 * The module is pure: no network, no files. Everything that a test can check
 * without bringing up opencode lives here. The plugin (plugin/truthprobe.ts) only
 * glues this to the network and to the model catalog.
 */

/** Result of checking one provider/model. */
export type Status = "ok" | "ignored" | "rejected" | "auth" | "unsupported" | "error"

export interface Entry {
  readonly status: Status
  /** When it was checked, epoch milliseconds. */
  readonly checkedAt: number
  /** Origin of the endpoint: scheme + host, without path and query. */
  readonly endpoint?: string
  /** ID of the model that was checked. */
  readonly model?: string
  /** Short reason (response code or truncated error text). */
  readonly detail?: string
}

export interface File {
  readonly version: 1
  readonly entries: Readonly<Record<string, Entry>>
}

export const FILE_VERSION = 1 as const

const DAY = 24 * 60 * 60 * 1000

/** How long a result lives. `auth` is re-checked quickly: a key may have been added. */
export const ttl = (status: Status): number => {
  switch (status) {
    case "ok":
    case "ignored":
    case "rejected":
    case "unsupported":
      return 7 * DAY
    case "auth":
      return 60 * 60 * 1000
    case "error":
      return 0
  }
}

export const empty = (): File => ({ version: FILE_VERSION, entries: {} })

export const keyOf = (providerID: string, modelID: string) => `${providerID}/${modelID}`

const STATUSES: ReadonlySet<string> = new Set<Status>([
  "ok",
  "ignored",
  "rejected",
  "auth",
  "unsupported",
  "error",
])

const isEntry = (value: unknown): value is Entry => {
  if (typeof value !== "object" || value === null) return false
  const entry = value as Record<string, unknown>
  return typeof entry.status === "string" && STATUSES.has(entry.status) && typeof entry.checkedAt === "number"
}

/**
 * Parsing the cache file. A broken file or foreign fields must not break startup:
 * everything unintelligible is silently dropped.
 */
export const parse = (raw: string | undefined | null): File => {
  if (!raw) return empty()
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return empty()
  }
  if (typeof data !== "object" || data === null) return empty()
  const entries = (data as { entries?: unknown }).entries
  if (typeof entries !== "object" || entries === null) return empty()
  const result: Record<string, Entry> = {}
  for (const [key, value] of Object.entries(entries as Record<string, unknown>)) {
    if (isEntry(value)) result[key] = value
  }
  return { version: FILE_VERSION, entries: result }
}

/** Stable serialisation: the same input gives the same file. */
export const serialize = (file: File): string => {
  const entries = Object.keys(file.entries)
    .sort()
    .map((key) => [key, file.entries[key]] as const)
  return `${JSON.stringify({ version: FILE_VERSION, entries: Object.fromEntries(entries) }, null, 2)}\n`
}

/** Recording a result without mutating the input. */
export const setEntry = (file: File, key: string, entry: Entry): File => ({
  version: FILE_VERSION,
  entries: { ...file.entries, [key]: entry },
})

export const getEntry = (file: File, key: string): Entry | undefined => file.entries[key]

/** Is the result still current? `now` is passed explicitly so a test does not depend on the clock. */
export const fresh = (entry: Entry | undefined, now: number): entry is Entry => {
  if (!entry) return false
  const limit = ttl(entry.status)
  if (limit === 0) return false
  const age = now - entry.checkedAt
  return age >= 0 && age < limit
}

/** Can logprobs collection be enabled based on this result. */
export const enabled = (entry: Entry | undefined, now: number) => fresh(entry, now) && entry.status === "ok"

/**
 * Body of the minimal probe request. Fixed text, a single token:
 * neither the user's question nor their data is here, and neither can be.
 */
export const probeBody = (modelID: string, topK = 3) => ({
  model: modelID,
  messages: [{ role: "user" as const, content: "ping" }],
  max_tokens: 1,
  temperature: 0,
  stream: false as const,
  logprobs: true,
  top_logprobs: topK,
})

/** Endpoint host without a path: the cache must contain neither query nor keys. */
export const originOf = (url: string): string | undefined => {
  try {
    const parsed = new URL(url)
    return `${parsed.protocol}//${parsed.host}`
  } catch {
    return undefined
  }
}

/** Model ID from an already assembled request body; needed when modelID is an alias. */
export const modelFromBody = (raw: string | undefined | null): string | undefined => {
  if (!raw) return undefined
  try {
    const data = JSON.parse(raw) as { model?: unknown }
    return typeof data.model === "string" && data.model.length > 0 ? data.model : undefined
  } catch {
    return undefined
  }
}

export interface ProbeResponse {
  readonly status: number
  readonly body: string
}

/**
 * Classification of the probe response.
 *
 * `ok` — the response really has logprob tokens in any channel (`content` or
 *        `reasoning_content`/`reasoning_logprobs`): with reasoning models at
 *        `max_tokens: 1` there is no visible text yet, but the reasoning is already computed;
 * `ignored` — 200, but the field is absent (the gateway silently stripped it);
 * `rejected` — the provider complains specifically about logprobs;
 * `auth` — the key was not accepted;
 * `unsupported` — the endpoint is not about chat-completions or does not know the field;
 * `error` — a temporary problem (429/5xx/network), the result is not cached.
 */
export const classify = (response: ProbeResponse): Status => {
  const { status, body } = response
  if (status >= 200 && status < 300) {
    try {
      const data = JSON.parse(body) as {
        choices?: Array<{
          logprobs?: Record<string, unknown> | null
          reasoning_logprobs?: Record<string, unknown> | null
        }>
      }
      const choice = data.choices?.[0]
      const hasTokens = (logprobs: Record<string, unknown> | null | undefined) =>
        !!logprobs && Object.values(logprobs).some((value) => Array.isArray(value) && value.length > 0)
      return hasTokens(choice?.logprobs) || hasTokens(choice?.reasoning_logprobs) ? "ok" : "ignored"
    } catch {
      return "ignored"
    }
  }
  if (status === 401 || status === 403) return "auth"
  if (status === 429 || status >= 500) return "error"
  if (status === 404 || status === 405 || status === 501) return "unsupported"
  if (status === 400 || status === 422) return /logprob/i.test(body) ? "rejected" : "unsupported"
  return "unsupported"
}

/** Human-readable line for the log and the status in the TUI. */
export const describe = (status: Status): string => {
  switch (status) {
    case "ok":
      return "provider returns logprobs"
    case "ignored":
      return "provider accepted the request but returned no logprobs"
    case "rejected":
      return "provider rejects logprobs"
    case "auth":
      return "provider rejected the credential"
    case "unsupported":
      return "endpoint does not support logprobs probing"
    case "error":
      return "probe failed temporarily"
  }
}

/** Badge lines: what `opencode truthprobe status` and the TUI print. */
export const summary = (entries: Readonly<Record<string, Entry>>, now: number): string[] =>
  Object.entries(entries)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, entry]) => {
      const stale = fresh(entry, now) ? "" : " (stale)"
      return `${key}: ${entry.status} — ${describe(entry.status)}${stale}`
    })
