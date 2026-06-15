import { describe, it, expect } from 'vitest';
import { extractOriginalShastraInfo } from '@/lib/shastra-pdf-registry';
import { computePdfPage, buildOriginalShastraHref } from '@/components/OriginalShastraLink';
import type { DefinitionReference } from '@/lib/types';

function makeRef(fields: Array<{ field: string; value: string }>): DefinitionReference {
  return {
    text: '',
    inline_reference: false,
    needs_manual_match: false,
    is_teeka: false,
    teeka_name: '',
    shastra_name: 'समयसार',
    match_method: null,
    resolved_fields: fields,
  };
}

describe('extractOriginalShastraInfo', () => {
  it('returns null when ref has no पृष्ठ field', () => {
    const ref = makeRef([{ field: 'गाथा', value: '10' }]);
    expect(extractOriginalShastraInfo(ref)).toBeNull();
  });

  it('returns null when ref has no resolved_fields', () => {
    const ref = makeRef([]);
    expect(extractOriginalShastraInfo(ref)).toBeNull();
  });

  it('parses ASCII page number', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: '42' }]);
    expect(extractOriginalShastraInfo(ref)).toEqual({ publishedPage: 42, pustak: null });
  });

  it('parses Devanagari page number', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: '१२' }]);
    expect(extractOriginalShastraInfo(ref)).toEqual({ publishedPage: 12, pustak: null });
  });

  it('parses mixed Devanagari digits', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: '३४५' }]);
    expect(extractOriginalShastraInfo(ref)).toEqual({ publishedPage: 345, pustak: null });
  });

  it('trims whitespace from page value', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: ' 7 ' }]);
    expect(extractOriginalShastraInfo(ref)).toEqual({ publishedPage: 7, pustak: null });
  });

  it('extracts pustak when present', () => {
    const ref = makeRef([
      { field: 'पृष्ठ', value: '20' },
      { field: 'पुस्तक', value: '2' },
    ]);
    expect(extractOriginalShastraInfo(ref)).toEqual({ publishedPage: 20, pustak: '2' });
  });

  it('trims whitespace from pustak value', () => {
    const ref = makeRef([
      { field: 'पृष्ठ', value: '5' },
      { field: 'पुस्तक', value: ' 3 ' },
    ]);
    expect(extractOriginalShastraInfo(ref)?.pustak).toBe('3');
  });

  it('returns null when पृष्ठ value is not a valid number', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: 'abc' }]);
    expect(extractOriginalShastraInfo(ref)).toBeNull();
  });

  it('ignores पुस्तक when no पृष्ठ is present', () => {
    const ref = makeRef([{ field: 'पुस्तक', value: '1' }]);
    expect(extractOriginalShastraInfo(ref)).toBeNull();
  });
});

describe('computePdfPage', () => {
  it('adds pdfPageOffset to publishedPage when no pustakOffsets', () => {
    expect(computePdfPage(12, 5, null, null)).toBe(17);
  });

  it('uses zero offset when pdfPageOffset is 0', () => {
    expect(computePdfPage(12, 0, null, null)).toBe(12);
  });

  it('uses negative offset correctly', () => {
    expect(computePdfPage(12, -2, null, null)).toBe(10);
  });

  it('uses pustakOffsets when pustak key matches', () => {
    const pustakOffsets = { '1': 0, '2': -2, '3': 5 };
    expect(computePdfPage(12, 0, pustakOffsets, '2')).toBe(10);
  });

  it('falls back to pdfPageOffset when pustak key is not in pustakOffsets', () => {
    const pustakOffsets = { '1': 0, '2': -2 };
    expect(computePdfPage(12, 5, pustakOffsets, '3')).toBe(17);
  });

  it('falls back to pdfPageOffset when pustak is null and pustakOffsets present', () => {
    const pustakOffsets = { '1': 10 };
    expect(computePdfPage(12, 5, pustakOffsets, null)).toBe(17);
  });

  it('uses pustakOffset of 0 correctly (does not fall back)', () => {
    const pustakOffsets = { '1': 0 };
    expect(computePdfPage(12, 5, pustakOffsets, '1')).toBe(12);
  });

  it('resolves array-form pdfPageOffset by published page threshold', () => {
    const spec: Array<[number, number]> = [[204, 26], [215, 27]];
    expect(computePdfPage(178, spec, null, null)).toBe(178 + 26);
    expect(computePdfPage(204, spec, null, null)).toBe(204 + 26);
    expect(computePdfPage(205, spec, null, null)).toBe(205 + 27);
    expect(computePdfPage(215, spec, null, null)).toBe(215 + 27);
  });

  it('falls back to last bucket offset beyond all thresholds', () => {
    const spec: Array<[number, number]> = [[204, 26], [215, 27]];
    expect(computePdfPage(500, spec, null, null)).toBe(500 + 27);
  });

  it('resolves array-form pustakOffsets by published page', () => {
    const pustakOffsets: Record<string, number | Array<[number, number]>> = {
      '13': [[204, 26], [215, 27]],
      '14': 25,
    };
    expect(computePdfPage(178, 0, pustakOffsets, '13')).toBe(178 + 26);
    expect(computePdfPage(210, 0, pustakOffsets, '13')).toBe(210 + 27);
    expect(computePdfPage(50, 0, pustakOffsets, '14')).toBe(75);
  });

  it('sorts unordered array thresholds', () => {
    const spec: Array<[number, number]> = [[215, 27], [204, 26]];
    expect(computePdfPage(180, spec, null, null)).toBe(206);
    expect(computePdfPage(210, spec, null, null)).toBe(237);
  });
});

describe('buildOriginalShastraHref', () => {
  it('builds href with page fragment', () => {
    const href = buildOriginalShastraHref('समयसार', null, 42);
    expect(href).toBe('/api/metadata/v1/shastras/%E0%A4%B8%E0%A4%AE%E0%A4%AF%E0%A4%B8%E0%A4%BE%E0%A4%B0/pdf-file#page=42');
  });

  it('includes pustak query param when pustak is provided', () => {
    const href = buildOriginalShastraHref('समयसार', '2', 15);
    expect(href).toContain('?pustak=2');
    expect(href).toContain('#page=15');
  });

  it('omits pustak query param when pustak is null', () => {
    const href = buildOriginalShastraHref('समयसार', null, 10);
    expect(href).not.toContain('?pustak');
    expect(href).toContain('#page=10');
  });

  it('URL-encodes shastra name', () => {
    const href = buildOriginalShastraHref('धवला', null, 1);
    expect(href).toContain(encodeURIComponent('धवला'));
  });

  it('URL-encodes pustak value', () => {
    const href = buildOriginalShastraHref('धवला', 'पुस्तक 1', 1);
    expect(href).toContain(encodeURIComponent('पुस्तक 1'));
  });

  it('fragment is at the end of the URL', () => {
    const href = buildOriginalShastraHref('समयसार', '1', 5);
    expect(href.endsWith('#page=5')).toBe(true);
  });
});
