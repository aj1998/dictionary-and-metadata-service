import { shortFontOpenToken, SHORTFONT_CLOSE_TOKEN } from './bhaavarth-shortfont';

// Highlight sentinel for bhaavarth prose. When a match highlight overlaps a
// markdown prose segment, slicing the raw text and rendering the pieces as
// plain strings would expose markdown markers (e.g. `*((अस्तित्व))*`) and drop
// formatting. Instead we splice a sentinel pair into the RAW markdown at the
// highlight boundaries, run markdown→HTML conversion, then replace the
// sentinels with a `<mark>` element — so the highlighted span stays formatted.
//
// Uses STX/ETX control chars (same family as the shortfont sentinels) which
// never appear in Devanagari prose and pass through the markdown renderer
// untouched.
const HL_OPEN = '\x02hl\x03';
const HL_CLOSE = '\x02/hl\x03';
const HL_SENTINEL_RE = /\x02hl\x03([\s\S]*?)\x02\/hl\x03/g;

const HL_MARK_OPEN = '<mark class="rounded bg-[var(--accent-soft)] text-[var(--accent)]">';
const HL_MARK_CLOSE = '</mark>';

/**
 * Splice a highlight sentinel pair into `text` around [start, end).
 * Returns `text` unchanged when the range is empty or out of bounds.
 */
export function injectHighlightSentinel(text: string, start: number, end: number): string {
  if (start < 0 || end > text.length || start >= end) return text;
  return text.slice(0, start) + HL_OPEN + text.slice(start, end) + HL_CLOSE + text.slice(end);
}

interface ShortFontSpan {
  localStart: number;
  localEnd: number;
  entryIdx: number;
}

/**
 * Splice both the highlight sentinel and any shortfont sentinels into `text` in
 * a single left-to-right pass, so a highlighted prose segment keeps its
 * clickable shortfont anchors (the highlight branch otherwise dropped them).
 *
 * All offsets are in original `text` coordinates. At a shared offset the events
 * are ordered so nesting stays valid: inner (shortfont) closes first, then the
 * highlight close, then the highlight open, then inner opens — i.e. the
 * highlight `<mark>` wraps shortfont anchors that begin inside it. Shortfont
 * spans whose offsets are out of range or out of order are skipped.
 */
export function injectHighlightAndShortFont(
  text: string,
  shortFontSpans: ShortFontSpan[],
  hlStart: number,
  hlEnd: number,
): string {
  type Ev = { pos: number; kind: 'sfClose' | 'hlClose' | 'hlOpen' | 'sfOpen'; token: string };
  const evs: Ev[] = [];
  const hlValid = hlStart >= 0 && hlEnd <= text.length && hlStart < hlEnd;
  if (hlValid) {
    evs.push({ pos: hlStart, kind: 'hlOpen', token: HL_OPEN });
    evs.push({ pos: hlEnd, kind: 'hlClose', token: HL_CLOSE });
  }
  for (const s of shortFontSpans) {
    if (s.localStart < 0 || s.localEnd > text.length || s.localStart >= s.localEnd) continue;
    evs.push({ pos: s.localStart, kind: 'sfOpen', token: shortFontOpenToken(s.entryIdx) });
    evs.push({ pos: s.localEnd, kind: 'sfClose', token: SHORTFONT_CLOSE_TOKEN });
  }
  if (!evs.length) return text;
  const rank: Record<Ev['kind'], number> = { sfClose: 0, hlClose: 1, hlOpen: 2, sfOpen: 3 };
  evs.sort((a, b) => a.pos - b.pos || rank[a.kind] - rank[b.kind]);

  let out = '';
  let cursor = 0;
  for (const e of evs) {
    out += text.slice(cursor, e.pos);
    out += e.token;
    cursor = e.pos;
  }
  out += text.slice(cursor);
  return out;
}

/** Replace highlight sentinels in rendered HTML with `<mark>` elements. */
export function postProcessHighlightHtml(html: string): string {
  return html.replace(HL_SENTINEL_RE, (_, inner) => `${HL_MARK_OPEN}${inner}${HL_MARK_CLOSE}`);
}
