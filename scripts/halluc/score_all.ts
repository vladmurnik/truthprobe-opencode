import { appendFileSync, readFileSync, writeFileSync } from "node:fs"
import { scoreAnswer } from "/home/adik/src/opencode/packages/core/src/truthprobe/score.ts"

const runs: Array<[string, string]> = [
  ["/home/adik/halluc/rows_raw2.jsonl", "/home/adik/halluc/rows_scored2.jsonl"],
  ["/home/adik/halluc/rows_raw3.jsonl", "/home/adik/halluc/rows_scored3.jsonl"],
]

for (const [input, output] of runs) {
  let raw: any[] = []
  try {
    raw = readFileSync(input, "utf8")
      .split("\n")
      .filter((line) => line.trim().length > 0)
      .map((line) => JSON.parse(line))
  } catch {
    console.log(`${input}: нет файла, пропускаю`)
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
  console.log(`${output}: ${out.length} строк`)
  appendFileSync("/home/adik/halluc/score.log", `${output}: ${out.length}\n`)
}
