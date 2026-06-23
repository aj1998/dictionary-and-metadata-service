import type { BhaavarthShortFontEntry } from '@/lib/types';

// STX/ETX control characters used as sentinels — never appear in Devanagari prose.
// Format: \x02sf:entryIdx\x03anchor_text\x02/sf\x03
const SF_OPEN = '\x02sf:';
const SF_SEP = '\x03';
const SF_CLOSE = '\x02/sf\x03';
const SF_SENTINEL_RE = /\x02sf:(\d+)\x03([\s\S]*?)\x02\/sf\x03/g;

/** Opening shortfont sentinel for a given entry index (exposed so other
 * formatters can interleave shortfont + highlight sentinels in one pass). */
export const shortFontOpenToken = (entryIdx: number): string => `${SF_OPEN}${entryIdx}${SF_SEP}`;
/** Closing shortfont sentinel. */
export const SHORTFONT_CLOSE_TOKEN = SF_CLOSE;

export interface SegmentShortFontEntry {
  entry: BhaavarthShortFontEntry;
  entryIdx: number;
  localStart: number;
  localEnd: number;
}

/**
 * Returns shortfont entries whose occurrences fall within [segmentStart, segmentEnd).
 * Only the first matching occurrence per entry is used.
 */
export function getSegmentEntries(
  entries: BhaavarthShortFontEntry[],
  segmentStart: number,
  segmentEnd: number,
): SegmentShortFontEntry[] {
  const result: SegmentShortFontEntry[] = [];
  entries.forEach((entry, entryIdx) => {
    for (const occ of entry.occurrences) {
      if (occ.start_offset >= segmentStart && occ.end_offset <= segmentEnd) {
        result.push({
          entry,
          entryIdx,
          localStart: occ.start_offset - segmentStart,
          localEnd: occ.end_offset - segmentStart,
        });
        break;
      }
    }
  });
  return result.sort((a, b) => a.localStart - b.localStart);
}

/**
 * Splices sentinel tokens into `text` at occurrence positions.
 * Overlapping or out-of-order entries are skipped.
 */
export function injectShortFontSentinels(
  text: string,
  segmentEntries: SegmentShortFontEntry[],
): string {
  if (!segmentEntries.length) return text;

  let result = '';
  let pos = 0;

  for (const se of segmentEntries) {
    if (se.localStart < pos || se.localEnd > text.length) continue;
    result += text.slice(pos, se.localStart);
    result += `${SF_OPEN}${se.entryIdx}${SF_SEP}${text.slice(se.localStart, se.localEnd)}${SF_CLOSE}`;
    pos = se.localEnd;
  }
  result += text.slice(pos);
  return result;
}

/**
 * Replaces sentinel tokens in already-rendered HTML with styled `<button>` elements.
 * The button carries `data-sf-idx` for event-delegation click handling.
 */
export function postProcessShortFontHtml(html: string): string {
  return html.replace(
    SF_SENTINEL_RE,
    (_, idx, anchor) =>
      `<button type="button" class="sf-anchor" data-sf-idx="${idx}">${anchor}</button>`,
  );
}
