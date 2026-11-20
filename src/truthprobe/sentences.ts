/**
 * TruthProbe — сегментация ответа на предложения.
 *
 * Задача не «идеальная лингвистика», а стабильные смещения: токены привязываются
 * к предложениям по символьным позициям, поэтому сегментатор обязан возвращать
 * корректные `start`/`end` в исходной строке и не включать блоки кода.
 */

export interface Sentence {
  i: number;
  start: number;
  end: number;
  text: string;
}

const FENCE = /^\s*(```|~~~)/;

/** Диапазоны [start, end) блоков кода, включая сами fences. */
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
  if (open !== null) ranges.push([open, text.length]); // незакрытый fence (стрим ещё идёт)
  return ranges;
}

const TERMINATORS = new Set([".", "!", "?", "…", "。", "！", "？"]);
const ABBREVIATIONS = new Set([
  "т", "е", "д", "п", "др", "см", "г", "гг", "в", "вв", "рис", "табл", "стр",
  "e.g", "i.e", "etc", "vs", "cf", "al", "no", "fig", "approx",
]);

function isExcluded(ranges: Array<[number, number]>, pos: number): boolean {
  for (const [a, b] of ranges) if (pos >= a && pos < b) return true;
  return false;
}

/** Предыдущее «слово» перед позицией index (для отсечения сокращений). */
function wordBefore(text: string, index: number): string {
  let i = index - 1;
  while (i >= 0 && /[A-Za-zА-Яа-яЁё.]/.test(text[i])) i--;
  return text.slice(i + 1, index).replace(/^\.+|\.+$/g, "").toLowerCase();
}

/** Первое слово после позиции index (без учёта пробелов и переносов). */
function wordAfter(text: string, index: number): string {
  let i = index + 1;
  while (i < text.length && /[\s"'«»()\[\]]/.test(text[i])) i++;
  let end = i;
  while (end < text.length && /[A-Za-zА-Яа-яЁё0-9]/.test(text[end])) end++;
  return text.slice(i, end);
}

/** Сокращение ли это: проверяем и целое слово, и последний сегмент «т.е.» → «е». */
function isAbbreviation(text: string, index: number): boolean {
  const word = wordBefore(text, index);
  if (ABBREVIATIONS.has(word)) return true;
  const last = word.split(".").pop() ?? "";
  return last.length > 0 && ABBREVIATIONS.has(last);
}

/** Начинается ли после позиции новое предложение (слово с заглавной буквы). */
function startsSentence(text: string, index: number): boolean {
  const word = wordAfter(text, index);
  return word.length > 0 && /^[A-ZА-ЯЁ]/.test(word);
}

/**
 * Режет текст на предложения. Границы:
 *  - терминатор `. ! ? …` + пробел/конец строки;
 *  - пустая строка (абзац);
 *  - начало markdown-пункта списка;
 *  - блоки кода целиком выброшены.
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
      // перепрыгиваем весь блок кода целиком
      const range = excluded.find(([a, b]) => i >= a && i < b)!;
      push(i, range[1]);
      i = range[1] - 1;
      continue;
    }

    const ch = text[i];

    // пустая строка
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
    // В CJK пробелов между предложениями нет, терминатор достаточен сам по себе.
    const boundaryAfter = cjk || atEnd || next === "\n" || /\s/.test(next);
    if (!boundaryAfter) continue;
    // «3.14», «v1.2»
    if (/\d/.test(prev ?? "") && /\d/.test(next ?? "")) continue;
    // «т.е.», «e.g.» — если только дальше не начинается новое предложение.
    if (isAbbreviation(text, i) && !startsSentence(text, i)) continue;

    let end = i + 1;
    while (end < text.length && (text[end] === " " || text[end] === "\t")) end++;
    push(end, end);
    i = end - 1;
  }

  push(text.length, text.length);
  return out;
}
