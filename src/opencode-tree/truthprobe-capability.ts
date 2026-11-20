/**
 * TruthProbe: чтение вердикта «провайдер отдаёт logprobs» из кэша.
 *
 * Путь к файлу кэша сообщает ядро (переменная OPENCODE_TRUTHPROBE_CACHE,
 * её ставит плагин opencode.truthprobe). Если переменной нет, пакет ai просто
 * не знает о кэше и работает по явному `capabilities.logprobs`.
 *
 * Модуль не делает сетевых запросов и не зависит от каталога моделей: только
 * чтение файла с коротким TTL в памяти, чтобы не трогать диск на каждый токен.
 */

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

export type Status = "ok" | "ignored" | "rejected" | "auth" | "unsupported" | "error"

interface Entry {
  readonly status?: unknown
  readonly checkedAt?: unknown
}

const DEFAULT_TTL = 7 * 24 * 60 * 60 * 1000
const AUTH_TTL = 60 * 60 * 1000
const READ_INTERVAL_MS = 2_000

let snapshot: { at: number; path: string; entries: Record<string, Entry> } | undefined

/** Путь к кэшу: ядро передаёт его переменной, иначе берём стандартный каталог данных. */
const cachePath = (): string | undefined => {
  const explicit = typeof process === "undefined" ? undefined : process.env?.OPENCODE_TRUTHPROBE_CACHE
  if (explicit) return explicit
  const data =
    process?.env?.XDG_DATA_HOME ?? (process?.platform === "win32"
      ? process?.env?.APPDATA
      : os.homedir() && path.join(os.homedir(), ".local", "share"))
  if (!data) return undefined
  return path.join(data, "opencode", "truthprobe", "capabilities.json")
}

const readEntries = (): Record<string, Entry> => {
  const file = cachePath()
  if (!file) return {}
  const now = Date.now()
  if (snapshot && snapshot.path === file && now - snapshot.at < READ_INTERVAL_MS) return snapshot.entries
  let entries: Record<string, Entry> = {}
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf8")) as { entries?: unknown }
    if (parsed && typeof parsed === "object" && typeof parsed.entries === "object" && parsed.entries !== null) {
      entries = parsed.entries as Record<string, Entry>
    }
  } catch {
    entries = {}
  }
  snapshot = { at: now, path: file, entries }
  return entries
}

/** Сколько живёт вердикт. Повторяет правило ядра: auth перепроверяем быстро. */
const ttl = (status: string) => (status === "auth" ? AUTH_TTL : DEFAULT_TTL)

const fresh = (entry: Entry | undefined, now: number): boolean => {
  if (!entry || entry.status !== "ok" || typeof entry.checkedAt !== "number") return false
  const age = now - entry.checkedAt
  return age >= 0 && age < ttl("ok")
}

/**
 * `true` — провайдер подтверждённо отдаёт logprobs.
 *
 * Проверяется запись именно этой модели, а если её нет — любая запись того же
 * провайдера: поддержка logprobs почти всегда свойство эндпоинта, а не модели,
 * и алиасы/варианты не должны гасить бейдж. Просроченные записи не считаются.
 */
export const supported = (providerID: string | undefined, modelID: string | undefined): boolean => {
  if (!providerID) return false
  const entries = readEntries()
  const now = Date.now()
  if (modelID && fresh(entries[`${providerID}/${modelID}`], now)) return true
  const prefix = `${providerID}/`
  return Object.keys(entries).some((key) => key.startsWith(prefix) && fresh(entries[key], now))
}

/** Сброс кэша в памяти — для тестов. */
export const reset = () => {
  snapshot = undefined
}

export const cacheFile = () => cachePath()
