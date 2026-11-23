/**
 * TruthProbe: reading the "provider returns logprobs" verdict from the cache.
 *
 * The core reports the path to the cache file (the OPENCODE_TRUTHPROBE_CACHE
 * variable, set by the opencode.truthprobe plugin). If the variable is absent, the ai
 * package simply does not know about the cache and relies on an explicit `capabilities.logprobs`.
 *
 * The module makes no network requests and does not depend on the model catalog: it only
 * reads the file with a short in-memory TTL, so the disk is not touched on every token.
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

/** Path to the cache: the core passes it via a variable, otherwise we use the default data directory. */
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

/** How long the verdict lives. Mirrors the core rule: auth is re-checked quickly. */
const ttl = (status: string) => (status === "auth" ? AUTH_TTL : DEFAULT_TTL)

const fresh = (entry: Entry | undefined, now: number): boolean => {
  if (!entry || entry.status !== "ok" || typeof entry.checkedAt !== "number") return false
  const age = now - entry.checkedAt
  return age >= 0 && age < ttl("ok")
}

/**
 * `true` — the provider is confirmed to return logprobs.
 *
 * The entry of this exact model is checked, and if it is absent, any entry of the same
 * provider: logprobs support is almost always a property of the endpoint, not of the model,
 * and aliases/variants must not turn the badge off. Stale entries do not count.
 */
export const supported = (providerID: string | undefined, modelID: string | undefined): boolean => {
  if (!providerID) return false
  const entries = readEntries()
  const now = Date.now()
  if (modelID && fresh(entries[`${providerID}/${modelID}`], now)) return true
  const prefix = `${providerID}/`
  return Object.keys(entries).some((key) => key.startsWith(prefix) && fresh(entries[key], now))
}

/** Reset the in-memory cache — for tests. */
export const reset = () => {
  snapshot = undefined
}

export const cacheFile = () => cachePath()
