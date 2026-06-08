// Parse bhaavarth prose into a sequence of segments so runs of short
// `[word] meaning` blocks can be replaced inline with a compact शब्दार्थ
// chip-row (reusing TaggedTermPopover). Long-form prose between those runs is
// preserved and rendered through the normal markdown path.
//
// Real source content is typically line-oriented:
// `**[word]**`
// `meaning...`
// with no blank line between entries. We therefore parse by header-led blocks
// instead of blank-line paragraphs.

const MIN_COMPACT_TOTAL = 3;
const MAX_MEANING_LEN = 260;

export interface CompactBracketEntry {
  word: string;
  meaning: string;
}

export type BhaavarthSegment =
  | { kind: 'chips'; items: CompactBracketEntry[]; start: number; end: number }
  | { kind: 'html'; text: string; start: number; end: number };

interface LineInfo {
  raw: string;
  start: number;
  end: number;
}

interface BlockInfo {
  raw: string;
  start: number;
  end: number;
  compact: CompactBracketEntry | null;
}

const BRACKET_ONLY_LINE = /^\s*(?:\*\*)?\[(.+?)\](?:\*\*)?\s*$/;
const BRACKET_INLINE_LINE = /^\s*(?:\*\*)?\[(.+?)\](?:\*\*)?\s+(.+?)\s*$/;
const BOLD_NON_BRACKET_LINE = /^\s*\*\*(?!\s*\[).+\*\*\s*$/;
const VERSE_MARKER_LINE = /^\s*॥[^॥]*॥\s*$/;

function stripHtml(text: string): string {
  return text.replace(/<[^>]+>/g, '');
}

function normalizeMeaning(lines: string[]): string {
  return lines
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function toLines(text: string): LineInfo[] {
  const lines: LineInfo[] = [];
  let start = 0;
  for (let i = 0; i <= text.length; i += 1) {
    if (i === text.length || text[i] === '\n') {
      lines.push({ raw: text.slice(start, i), start, end: i });
      start = i + 1;
    }
  }
  return lines;
}

function buildBlocks(text: string): BlockInfo[] {
  const lines = toLines(text);
  const blocks: BlockInfo[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const inline = line.raw.match(BRACKET_INLINE_LINE);
    const header = line.raw.match(BRACKET_ONLY_LINE);
    const isCompactLead = (input: string) => BRACKET_ONLY_LINE.test(input) || BRACKET_INLINE_LINE.test(input);

    if (inline) {
      const word = stripHtml(inline[1]).trim();
      const meaning = normalizeMeaning([inline[2]]);
      const compact =
        word
        && meaning
        && meaning.length <= MAX_MEANING_LEN
        && !/(^|\n)\s*-\s+/.test(meaning)
        && !/\[/.test(meaning)
          ? { word, meaning }
          : null;
      blocks.push({
        raw: line.raw,
        start: line.start,
        end: line.end,
        compact,
      });
      i += 1;
      continue;
    }

    if (!header) {
      const startIndex = i;
      i += 1;
      while (i < lines.length && !isCompactLead(lines[i].raw)) {
        i += 1;
      }
      const slice = lines.slice(startIndex, i);
      blocks.push({
        raw: slice.map((entry) => entry.raw).join('\n'),
        start: slice[0].start,
        end: slice[slice.length - 1].end,
        compact: null,
      });
      continue;
    }

    const meaningLines: string[] = [];
    let j = i + 1;
    while (
      j < lines.length
      && !lines[j].raw.match(BRACKET_ONLY_LINE)
      && !BOLD_NON_BRACKET_LINE.test(lines[j].raw)
      && !VERSE_MARKER_LINE.test(lines[j].raw)
    ) {
      meaningLines.push(lines[j].raw);
      j += 1;
    }

    const word = stripHtml(header[1]).trim();
    const meaning = normalizeMeaning(meaningLines);
    const compact =
      word
      && meaning
      && meaning.length <= MAX_MEANING_LEN
      && !/(^|\n)\s*-\s+/.test(meaning)
      && !/\[/.test(meaning)
        ? { word, meaning }
        : null;

    blocks.push({
      raw: lines.slice(i, j).map((entry) => entry.raw).join('\n'),
      start: line.start,
      end: (lines[j - 1] ?? line).end,
      compact,
    });
    i = j;
  }

  return blocks;
}

export function parseBhaavarthSegments(text: string): BhaavarthSegment[] {
  const blocks = buildBlocks(text);
  const totalCompact = blocks.reduce((n, block) => n + (block.compact ? 1 : 0), 0);
  if (totalCompact < MIN_COMPACT_TOTAL) {
    return [{ kind: 'html', text, start: 0, end: text.length }];
  }

  const segments: BhaavarthSegment[] = [];
  let chipBuf: CompactBracketEntry[] = [];
  let htmlBuf: string[] = [];
  let chipStart = -1;
  let chipEnd = -1;
  let htmlStart = -1;
  let htmlEnd = -1;

  const flushChips = () => {
    if (!chipBuf.length) return;
    segments.push({ kind: 'chips', items: chipBuf, start: chipStart, end: chipEnd });
    chipBuf = [];
    chipStart = -1;
    chipEnd = -1;
  };

  const flushHtml = () => {
    if (!htmlBuf.length) return;
    segments.push({ kind: 'html', text: htmlBuf.join('\n'), start: htmlStart, end: htmlEnd });
    htmlBuf = [];
    htmlStart = -1;
    htmlEnd = -1;
  };

  for (const block of blocks) {
    if (block.compact) {
      flushHtml();
      if (chipStart < 0) chipStart = block.start;
      chipEnd = block.end;
      chipBuf.push(block.compact);
    } else {
      flushChips();
      if (htmlStart < 0) htmlStart = block.start;
      htmlEnd = block.end;
      htmlBuf.push(block.raw);
    }
  }

  flushChips();
  flushHtml();
  return segments;
}
