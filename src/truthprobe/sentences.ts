/**
 * TruthProbe — segmentation of an answer into sentences.
 *
 * The goal is not "perfect linguistics" but stable offsets: tokens are bound to
 * sentences by character positions, so the segmenter must return correct
 * `start`/`end` in the source string and must not include code blocks.
 */

export interface Sentence {
  i: number;
  start: number;
  end: number;
  text: string;
}

const FENCE = /^\s*(```|~~~)/;

/** Ranges [start, end) of the code blocks, including the fences themselves. */
export function codeRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let offset = 0;
  let open: number | null = null;

  for (const line of text.split("\n")) {
    const lineStart = offset;
    const lineEnd = offset + line.length;
    if (FENCE.test(line)) {
      if (open === null) open = lineStart;
      else {
        ranges.push([open, lineEnd]);
        open = null;
      }
    }
    offset = lineEnd + 1; // + "\n"
  }
  if (open !== null) ranges.push([open, text.length]); // unclosed fence (the stream is still running)
  return ranges;
}

const TERMINATORS = new Set([".", "!", "?", "…", "。", "！", "？"]);
// Russian abbreviations, written as escapes so the source stays ASCII-only.
const ABBREVIATIONS = new Set([
  "\u0442", "\u0435", "\u0434", "\u043F", "\u0434\u0440", "\u0441\u043C", "\u0433", "\u0433\u0433",
  "\u0432", "\u0432\u0432", "\u0440\u0438\u0441", "\u0442\u0430\u0431\u043B", "\u0441\u0442\u0440",
  "e.g", "i.e", "etc", "vs", "cf", "al", "no", "fig", "approx",
]);

function isExcluded(ranges: Array<[number, number]>, pos: number): boolean {
  for (const [a, b] of ranges) if (pos >= a && pos < b) return true;
  return false;
}

/** The previous "word" before position index (used to reject abbreviations). */
function wordBefore(text: string, index: number): string {
  let i = index - 1;
  while (i >= 0 && /[A-Za-z\u0410-\u044F\u0401\u0451.]/.test(text[i])) i--;
  return text.slice(i + 1, index).replace(/^\.+|\.+$/g, "").toLowerCase();
}

/** First word after position index (ignoring spaces and newlines). */
function wordAfter(text: string, index: number): string {
  let i = index + 1;
  while (i < text.length && /[\s"'«»()\[\]]/.test(text[i])) i++;
  let end = i;
  while (end < text.length && /[A-Za-z\u0410-\u044F\u0401\u04510-9]/.test(text[end])) end++;
  return text.slice(i, end);
}

/** Is this an abbreviation: check both the whole word and the last segment, "i.e." → "e". */
function isAbbreviation(text: string, index: number): boolean {
  const word = wordBefore(text, index);
  if (ABBREVIATIONS.has(word)) return true;
  const last = word.split(".").pop() ?? "";
  return last.length > 0 && ABBREVIATIONS.has(last);
}

/** Does a new sentence start after the position (a word starting with a capital letter)? */
function startsSentence(text: string, index: number): boolean {
  const word = wordAfter(text, index);
  return word.length > 0 && /^[A-Z\u0410-\u042F\u0401]/.test(word);
}

/**
 * Cuts the text into sentences. Boundaries:
 *  - a terminator `. ! ? …` followed by a space/end of line;
 *  - an empty line (a paragraph);
 *  - the start of a markdown list item;
 *  - code blocks are thrown away entirely.
 */
export function splitSentences(text: string): Sentence[] {
  const excluded = codeRanges(text);
  const out: Sentence[] = [];
  let start = 0;

  const push = (end: number, nextStart: number) => {
    let s = start;
    let e = end;
    while (s < e && /\s/.test(text[s])) s++;
    while (e > s && /\s/.test(text[e - 1])) e--;
    const body = text.slice(s, e);
    if (body.length > 0 && /\S/.test(body) && !isExcluded(excluded, s)) {
      out.push({ i: out.length, start: s, end: e, text: body });
    }
    start = nextStart;
  };

  for (let i = 0; i < text.length; i++) {
    if (isExcluded(excluded, i)) {
      // jump over the whole code block at once
      const range = excluded.find(([a, b]) => i >= a && i < b)!;
      push(i, range[1]);
      i = range[1] - 1;
      continue;
    }

    const ch = text[i];

    // empty line
    if (ch === "\n") {
      let j = i + 1;
      while (j < text.length && (text[j] === " " || text[j] === "\t")) j++;
      if (j < text.length && text[j] === "\n") {
        push(i, j);
        i = j - 1;
        continue;
      }
      continue;
    }

    if (!TERMINATORS.has(ch)) continue;

    const cjk = ch === "。" || ch === "！" || ch === "？";
    const next = text[i + 1];
    const prev = text[i - 1];
    const atEnd = i + 1 >= text.length;
    // In CJK there are no spaces between sentences, so the terminator is enough on its own.
    const boundaryAfter = cjk || atEnd || next === "\n" || /\s/.test(next);
    if (!boundaryAfter) continue;
    // "3.14", "v1.2"
    if (/\d/.test(prev ?? "") && /\d/.test(next ?? "")) continue;
    // "i.e.", "e.g." — unless a new sentence starts right after.
    if (isAbbreviation(text, i) && !startsSentence(text, i)) continue;

    let end = i + 1;
    while (end < text.length && (text[end] === " " || text[end] === "\t")) end++;
    push(end, end);
    i = end - 1;
  }

  push(text.length, text.length);
  return out;
}
