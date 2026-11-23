import { appendFileSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"

// Paths are set from the environment so that a run over the repaired files overwrites nothing.
// By default the repaired runs are read (`*f.jsonl`, see repair.py): in the originals
// some rows have an empty `answer` with live tokens — the text was lost on save.
const HALLUC = process.env.HALLUC_DIR ?? path.dirname(new URL(import.meta.url).pathname)
const OPENCODE = process.env.OPENCODE_DIR ?? "/home/adik/src/opencode"
const scorerModule = process.env.SCORE_MODULE ?? path.join(OPENCODE, "packages/core/src/truthprobe/score.ts")

const { scoreAnswer } = await import(scorerModule)

const runs: Array<[string, string]> = [
  [path.join(HALLUC, process.env.RAW2 ?? "rows_raw2f.jsonl"), path.join(HALLUC, process.env.SCORED2 ?? "rows_scored2.jsonl")],
  [path.join(HALLUC, process.env.RAW3 ?? "rows_raw3f.jsonl"), path.join(HALLUC, process.env.SCORED3 ?? "rows_scored3.jsonl")],
]

for (const [input, output] of runs) {
  let raw: any[] = []
  try {
    raw = readFileSync(input, "utf8")
      .split("\n")
      .filter((line) => line.trim().length > 0)
      .map((line) => JSON.parse(line))
  } catch {
    console.log(`${input}: no such file, skipping`)
    continue
  }
  const out: string[] = []
  for (const row of raw) {
    if (row.error && !row.tokens?.length) {
      out.push(JSON.stringify({ model: row.model, qid: row.qid, category: row.category, status: "unavailable", note: row.error }))
      continue
    }
    if (!row.tokens || row.tokens.length === 0) {
      out.push(JSON.stringify({ model: row.model, qid: row.qid, category: row.category, status: "unavailable", note: "no tokens" }))
      continue
    }
    const result: any = scoreAnswer(row.answer ?? "", row.tokens, {}, `free-pi/${row.model}`)
    const sentences = (result.sentences ?? []) as any[]
    out.push(
      JSON.stringify({
        model: row.model,
        qid: row.qid,
        category: row.category,
        verdict: row.verdict ?? null,
        answer: row.answer,
        status: result.status,
        score: result.score ?? null,
        level: result.level ?? null,
        firstScore: result.first?.score ?? null,
        sentenceScores: sentences.map((s) => s.score),
        sentenceFlags: sentences.map((s) => (s.flag ? 1 : 0)),
        sentenceRisks: sentences.map((s) => s.risk),
        flagged: result.flagged,
      }),
    )
  }
  writeFileSync(output, out.join("\n") + "\n", "utf8")
  console.log(`${output}: ${out.length} rows`)
  appendFileSync(path.join(HALLUC, "score.log"), `${output}: ${out.length}\n`)
}
