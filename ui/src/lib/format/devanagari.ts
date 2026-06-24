const ASCII_TO_DEVANAGARI: Record<string, string> = {
  "0": "०", "1": "१", "2": "२", "3": "३", "4": "४",
  "5": "५", "6": "६", "7": "७", "8": "८", "9": "९",
};

/** Maps ASCII digits 0–9 to Devanagari numerals ०–९. */
export function toDevanagariNumerals(n: number): string {
  return String(n).replace(/[0-9]/g, (d) => ASCII_TO_DEVANAGARI[d]);
}

/** Replaces every ASCII digit in an arbitrary string with its Devanagari equivalent. */
export function toDevanagariDigitsInString(s: string): string {
  return s.replace(/[0-9]/g, (d) => ASCII_TO_DEVANAGARI[d]);
}

/** NFC-normalizes a string (Devanagari-safe Unicode normalization). */
export function normalizeNFC(s: string): string {
  return s.normalize("NFC");
}

/** Returns the grapheme-cluster length of a string using Intl.Segmenter. */
export function minGraphemeLength(s: string): number {
  const segmenter = new Intl.Segmenter();
  return [...segmenter.segment(s)].length;
}
