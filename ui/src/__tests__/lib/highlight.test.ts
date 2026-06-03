import { describe, it, expect } from 'vitest';
import { splitHighlight } from '@/lib/highlight';

describe('splitHighlight', () => {
  const text = 'आत्मा परमात्मा है';

  it('splits text into before, matched, after for a mid-string range', () => {
    const result = splitHighlight(text, { start: 5, end: 13 });
    expect(result).not.toBeNull();
    expect(result!.before).toBe(text.slice(0, 5));
    expect(result!.matched).toBe(text.slice(5, 13));
    expect(result!.after).toBe(text.slice(13));
  });

  it('returns null when start >= end', () => {
    expect(splitHighlight(text, { start: 5, end: 5 })).toBeNull();
    expect(splitHighlight(text, { start: 8, end: 3 })).toBeNull();
  });

  it('returns null when start is negative', () => {
    expect(splitHighlight(text, { start: -1, end: 5 })).toBeNull();
  });

  it('returns null when end exceeds text length', () => {
    expect(splitHighlight(text, { start: 0, end: text.length + 1 })).toBeNull();
  });

  it('handles start = 0 (before is empty)', () => {
    const result = splitHighlight(text, { start: 0, end: 4 });
    expect(result).not.toBeNull();
    expect(result!.before).toBe('');
    expect(result!.matched).toBe(text.slice(0, 4));
  });

  it('handles end = text.length (after is empty)', () => {
    const result = splitHighlight(text, { start: 5, end: text.length });
    expect(result).not.toBeNull();
    expect(result!.after).toBe('');
  });

  it('handles entire text as range', () => {
    const result = splitHighlight(text, { start: 0, end: text.length });
    expect(result).not.toBeNull();
    expect(result!.before).toBe('');
    expect(result!.matched).toBe(text);
    expect(result!.after).toBe('');
  });
});
