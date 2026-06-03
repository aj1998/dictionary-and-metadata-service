export interface HighlightRange {
  start: number;
  end: number;
}

export interface HighlightSplit {
  before: string;
  matched: string;
  after: string;
}

/**
 * Splits `text` into three parts based on [start, end) offsets.
 * Returns null when the range is out of bounds or empty.
 */
export function splitHighlight(text: string, range: HighlightRange): HighlightSplit | null {
  const { start, end } = range;
  if (start < 0 || end > text.length || start >= end) {
    return null;
  }
  return {
    before: text.slice(0, start),
    matched: text.slice(start, end),
    after: text.slice(end),
  };
}
