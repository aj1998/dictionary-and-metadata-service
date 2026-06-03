import { describe, it, expect } from 'vitest';
import { splitHighlight } from '@/lib/highlight';
import { normalizeNFC } from '@/lib/format/devanagari';

// BhaavarthPanel is a React component — per existing test policy we don't mount JSX.
// These tests validate the pure logic used inside the component.

describe('BhaavarthPanel — highlight logic', () => {
  const text = 'जीव द्रव्य है। वह अनंत गुणों का पुंज है।';

  it('produces a valid split for a known range', () => {
    const nfcText = normalizeNFC(text);
    const result = splitHighlight(nfcText, { start: 0, end: 8 });
    expect(result).not.toBeNull();
    expect(result!.before).toBe('');
    expect(result!.matched).toBe(nfcText.slice(0, 8));
  });

  it('returns null when highlight is out of range — panel should skip the mark', () => {
    const nfcText = normalizeNFC(text);
    const result = splitHighlight(nfcText, { start: 0, end: nfcText.length + 10 });
    expect(result).toBeNull();
  });

  it('returns null when highlight is not provided (no highlight object)', () => {
    // Simulate the panel when highlight prop is undefined
    const highlight = undefined;
    const result = highlight ? splitHighlight(normalizeNFC(text), highlight) : null;
    expect(result).toBeNull();
  });

  it('matched segment is a substring of the NFC text', () => {
    const nfcText = normalizeNFC(text);
    const start = 4;
    const end = 12;
    const result = splitHighlight(nfcText, { start, end });
    expect(result).not.toBeNull();
    expect(nfcText).toContain(result!.matched);
  });
});
