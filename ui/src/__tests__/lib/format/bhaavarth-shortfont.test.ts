import { describe, it, expect } from 'vitest';
import {
  getSegmentEntries,
  injectShortFontSentinels,
  postProcessShortFontHtml,
} from '@/lib/format/bhaavarth-shortfont';
import type { BhaavarthShortFontEntry } from '@/lib/types';

// "अब " is 3 JS chars; "मोक्ष-मार्ग-प्रपंच-सूचक" is 23 JS chars → end = 26
const ANCHOR_1 = 'मोक्ष-मार्ग-प्रपंच-सूचक';
const ENTRY_1: BhaavarthShortFontEntry = {
  marker_number: 4,
  marker_devanagari: '४',
  anchor_text: ANCHOR_1,
  meaning: 'मोक्ष का विस्तार बतलाने वाली।',
  is_definition: true,
  occurrences: [{ start_offset: 3, end_offset: 3 + ANCHOR_1.length }],
};

const ENTRY_2: BhaavarthShortFontEntry = {
  marker_number: 1,
  marker_devanagari: '१',
  anchor_text: 'उत्तर',
  meaning: 'बाद का।',
  is_definition: false,
  occurrences: [{ start_offset: 50, end_offset: 55 }],
};

describe('getSegmentEntries', () => {
  it('returns entry whose occurrence falls within segment bounds', () => {
    const result = getSegmentEntries([ENTRY_1], 0, 100);
    expect(result).toHaveLength(1);
    expect(result[0].entryIdx).toBe(0);
    expect(result[0].localStart).toBe(3);
    expect(result[0].localEnd).toBe(3 + ANCHOR_1.length);
  });

  it('adjusts local offsets relative to segment start', () => {
    // segment starts at offset 10, entry occurrence 3..27 in original text → outside [10,100)
    // entry occurrence start_offset must be >= segmentStart
    const entry: BhaavarthShortFontEntry = {
      ...ENTRY_1,
      occurrences: [{ start_offset: 15, end_offset: 30 }],
    };
    const result = getSegmentEntries([entry], 10, 100);
    expect(result[0].localStart).toBe(5);   // 15 - 10
    expect(result[0].localEnd).toBe(20);    // 30 - 10
  });

  it('excludes entry whose occurrence starts before segment', () => {
    const result = getSegmentEntries([ENTRY_1], 10, 100);
    // ENTRY_1 has start_offset=3, which is < segmentStart=10 → excluded
    expect(result).toHaveLength(0);
  });

  it('excludes entry whose occurrence ends after segment', () => {
    const entry: BhaavarthShortFontEntry = {
      ...ENTRY_1,
      occurrences: [{ start_offset: 3, end_offset: 200 }],
    };
    const result = getSegmentEntries([entry], 0, 50);
    expect(result).toHaveLength(0);
  });

  it('returns entries sorted by localStart', () => {
    const result = getSegmentEntries([ENTRY_2, ENTRY_1], 0, 100);
    // ENTRY_1: localStart=3, ENTRY_2: localStart=50 — should be in order 3, 50
    expect(result[0].entryIdx).toBe(1); // ENTRY_1 is index 1 in the input array
    expect(result[1].entryIdx).toBe(0); // ENTRY_2 is index 0 in the input array
    expect(result[0].localStart).toBeLessThan(result[1].localStart);
  });

  it('only uses the first matching occurrence per entry', () => {
    const entry: BhaavarthShortFontEntry = {
      ...ENTRY_1,
      occurrences: [
        { start_offset: 3, end_offset: 27 },
        { start_offset: 40, end_offset: 64 },
      ],
    };
    const result = getSegmentEntries([entry], 0, 100);
    expect(result).toHaveLength(1);
    expect(result[0].localStart).toBe(3);
  });
});

describe('injectShortFontSentinels', () => {
  it('wraps the anchor text in sentinels', () => {
    const text = 'अब मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।';
    const segEntries = getSegmentEntries([ENTRY_1], 0, text.length);
    const result = injectShortFontSentinels(text, segEntries);
    expect(result).toContain('\x02sf:0\x03');
    expect(result).toContain('\x02/sf\x03');
    expect(result).toContain('मोक्ष-मार्ग-प्रपंच-सूचक');
    // Text outside anchors is preserved
    expect(result.startsWith('अब ')).toBe(true);
    expect(result.endsWith(' चूलिका है।')).toBe(true);
  });

  it('preserves text before and after the anchor', () => {
    const text = 'prefix anchor suffix';
    const entry: BhaavarthShortFontEntry = {
      ...ENTRY_1,
      occurrences: [{ start_offset: 7, end_offset: 13 }], // "anchor"
    };
    const segEntries = getSegmentEntries([entry], 0, text.length);
    const result = injectShortFontSentinels(text, segEntries);
    expect(result.startsWith('prefix ')).toBe(true);
    expect(result.endsWith(' suffix')).toBe(true);
  });

  it('returns text unchanged when no segment entries provided', () => {
    const text = 'कोई भी टिप्पणी नहीं।';
    expect(injectShortFontSentinels(text, [])).toBe(text);
  });

  it('handles multiple anchors in correct order', () => {
    const text = '0000 AAAAA 00000 BBBBB 0000';
    const entryA: BhaavarthShortFontEntry = {
      ...ENTRY_1,
      occurrences: [{ start_offset: 5, end_offset: 10 }], // AAAAA
    };
    const entryB: BhaavarthShortFontEntry = {
      ...ENTRY_2,
      occurrences: [{ start_offset: 17, end_offset: 22 }], // BBBBB
    };
    const segEntries = getSegmentEntries([entryA, entryB], 0, text.length);
    const result = injectShortFontSentinels(text, segEntries);
    const posA = result.indexOf('AAAAA');
    const posB = result.indexOf('BBBBB');
    expect(posA).toBeGreaterThan(-1);
    expect(posB).toBeGreaterThan(-1);
    expect(posA).toBeLessThan(posB);
  });
});

describe('postProcessShortFontHtml', () => {
  it('replaces sentinel tokens with sf-anchor buttons', () => {
    const html = '<p>अब \x02sf:0\x03मोक्ष-मार्ग-प्रपंच-सूचक\x02/sf\x03 है।</p>';
    const result = postProcessShortFontHtml(html);
    expect(result).toContain('<button type="button" class="sf-anchor" data-sf-idx="0">');
    expect(result).toContain('मोक्ष-मार्ग-प्रपंच-सूचक');
    expect(result).toContain('</button>');
    expect(result).not.toContain('\x02');
    expect(result).not.toContain('\x03');
  });

  it('handles multiple anchors in one HTML string', () => {
    const html = '\x02sf:0\x03alpha\x02/sf\x03 text \x02sf:1\x03beta\x02/sf\x03';
    const result = postProcessShortFontHtml(html);
    expect(result).toContain('data-sf-idx="0"');
    expect(result).toContain('data-sf-idx="1"');
    expect(result).toContain('>alpha<');
    expect(result).toContain('>beta<');
  });

  it('passes through HTML without sentinels unchanged', () => {
    const html = '<p>सामान्य पाठ।</p>';
    expect(postProcessShortFontHtml(html)).toBe(html);
  });
});
