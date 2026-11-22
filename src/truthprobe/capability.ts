/**
 * TruthProbe: определение того, отдаёт ли провайдер logprobs.
 *
 * Модуль чистый: ни сети, ни файлов. Всё, что можно проверить тестом без
 * поднятия opencode, живёт здесь. Плагин (plugin/truthprobe.ts) только
 * склеивает это с сетью и с каталогом моделей.
 */

/** Результат проверки одного провайдера/модели. */
export type Status = "ok" | "ignored" | "rejected" | "auth" | "unsupported" | "error"

export interface Entry {
  readonly status: Status
  /** Когда проверяли, миллисекунды эпохи. */
  readonly checkedAt: number
  /** Происхождение эндпоинта: схема + хост, без пути и query. */
  readonly endpoint?: string
  /** Идентификатор модели, на которой проверяли. */
  readonly model?: string
  /** Короткая причина (код ответа или текст ошибки, обрезанный). */
  readonly detail?: string
}

export interface File {
  readonly version: 1
  readonly entries: Readonly<Record<string, Entry>>
}

export const FILE_VERSION = 1 as const

const DAY = 24 * 60 * 60 * 1000

/** Сколько живёт результат. `auth` перепроверяем быстро: ключ могли добавить. */
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
 * Разбор файла кэша. Битый файл или чужие поля не должны ломать запуск:
 * всё непонятное молча отбрасывается.
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

/** Стабильная сериализация: одинаковый вход даёт одинаковый файл. */
export const serialize = (file: File): string => {
  const entries = Object.keys(file.entries)
    .sort()
    .map((key) => [key, file.entries[key]] as const)
  return `${JSON.stringify({ version: FILE_VERSION, entries: Object.fromEntries(entries) }, null, 2)}\n`
}

/** Запись результата без мутации входа. */
export const setEntry = (file: File, key: string, entry: Entry): File => ({
  version: FILE_VERSION,
  entries: { ...file.entries, [key]: entry },
})

export const getEntry = (file: File, key: string): Entry | undefined => file.entries[key]

/** Результат ещё актуален? `now` передаётся явно, чтобы тест не зависел от часов. */
export const fresh = (entry: Entry | undefined, now: number): entry is Entry => {
  if (!entry) return false
  const limit = ttl(entry.status)
  if (limit === 0) return false
  const age = now - entry.checkedAt
  return age >= 0 && age < limit
}

/** Можно ли включать сбор logprobs по этому результату. */
export const enabled = (entry: Entry | undefined, now: number) => fresh(entry, now) && entry.status === "ok"

/**
 * Тело минимальной проверочной посылки. Фиксированный текст, один токен:
 * ни вопроса пользователя, ни его данных здесь нет и быть не может.
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

/** Хост эндпоинта без пути: в кэше не должно быть ни query, ни ключей. */
export const originOf = (url: string): string | undefined => {
  try {
    const parsed = new URL(url)
    return `${parsed.protocol}//${parsed.host}`
  } catch {
    return undefined
  }
}

/** Идентификатор модели из уже собранного тела запроса; нужен, когда modelID — алиас. */
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
 * Классификация ответа проверки.
 *
 * `ok` — в ответе реально есть токены logprobs в любом канале (`content` или
 *        `reasoning_content`/`reasoning_logprobs`): у reasoning-моделей при
 *        `max_tokens: 1` видимого текста ещё нет, а рассуждения уже посчитаны;
 * `ignored` — 200, но поля нет (шлюз молча вырезал);
 * `rejected` — провайдер ругается именно на logprobs;
 * `auth` — ключ не принят;
 * `unsupported` — эндпоинт не про chat-completions или поля не знает;
 * `error` — временная беда (429/5xx/сеть), результат не кэшируем.
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

/** Человеческая строка для лога и статуса в TUI. */
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

/** Строка бейджа: то, что печатает `opencode truthprobe status` и TUI. */
export const summary = (entries: Readonly<Record<string, Entry>>, now: number): string[] =>
  Object.entries(entries)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, entry]) => {
      const stale = fresh(entry, now) ? "" : " (stale)"
      return `${key}: ${entry.status} — ${describe(entry.status)}${stale}`
    })
