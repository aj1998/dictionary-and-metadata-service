import { describe, it, expect } from 'vitest';
import { getBlockBorderClass, formatRefSourceLabel, parseMarkdownSegments } from '@/components/DefinitionModal';
import type { DefinitionBlock, DefinitionReference } from '@/lib/types';

function makeRef(overrides: Partial<DefinitionReference> = {}): DefinitionReference {
  return {
    text: '',
    inline_reference: false,
    needs_manual_match: false,
    is_teeka: false,
    teeka_name: '',
    shastra_name: null,
    match_method: null,
    resolved_fields: [{ field: 'गाथा', value: '10' }],
    ...overrides,
  };
}

function makeBlock(overrides: Partial<DefinitionBlock> = {}): DefinitionBlock {
  return {
    kind: 'hindi_text',
    text_devanagari: 'परीक्षण पाठ',
    hindi_translation: null,
    references: [],
    is_orphan_translation: false,
    is_bullet_point: false,
    raw_html: null,
    table_rows: null,
    target_keyword: null,
    target_topic_path: null,
    target_url: null,
    is_self: false,
    target_exists: true,
    ...overrides,
  };
}

describe('getBlockBorderClass — null text_devanagari', () => {
  it('still computes border class when text_devanagari is null', () => {
    const block = makeBlock({ kind: 'hindi_text', text_devanagari: null });
    expect(getBlockBorderClass(block, [])).toBe('border-border-strong');
  });

  it('returns sky border for null-text block with a shastra ref', () => {
    const block = makeBlock({ kind: 'hindi_text', text_devanagari: null });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: false })])).toBe('border-sky-500');
  });
});

describe('getBlockBorderClass', () => {
  it('returns grey border for sanskrit_text with no refs', () => {
    const block = makeBlock({ kind: 'sanskrit_text' });
    expect(getBlockBorderClass(block, [])).toBe('border-border-strong');
  });

  it('returns grey border for prakrit_text with no refs', () => {
    const block = makeBlock({ kind: 'prakrit_text' });
    expect(getBlockBorderClass(block, [])).toBe('border-border-strong');
  });

  it('returns grey border for hindi_text with no refs', () => {
    const block = makeBlock({ kind: 'hindi_text' });
    expect(getBlockBorderClass(block, [])).toBe('border-border-strong');
  });

  it('returns teal border for sanskrit_text with shastra ref', () => {
    const block = makeBlock({ kind: 'sanskrit_text' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: false })])).toBe('border-cat-keyword');
  });

  it('returns green border for prakrit_text with shastra ref', () => {
    const block = makeBlock({ kind: 'prakrit_text' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: false })])).toBe('border-emerald-500');
  });

  it('returns green border for prakrit_gatha with shastra ref', () => {
    const block = makeBlock({ kind: 'prakrit_gatha' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: false })])).toBe('border-emerald-500');
  });

  it('returns amber border for sanskrit_text with teeka ref', () => {
    const block = makeBlock({ kind: 'sanskrit_text' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: true })])).toBe('border-amber-400');
  });

  it('returns amber border for hindi_text with teeka ref', () => {
    const block = makeBlock({ kind: 'hindi_text' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: true })])).toBe('border-amber-400');
  });

  it('returns sky border for hindi_text with shastra ref', () => {
    const block = makeBlock({ kind: 'hindi_text' });
    expect(getBlockBorderClass(block, [makeRef({ is_teeka: false })])).toBe('border-sky-500');
  });

  it('returns amber border when mixed refs contain at least one teeka', () => {
    const block = makeBlock({ kind: 'hindi_text' });
    const refs = [makeRef({ is_teeka: false }), makeRef({ is_teeka: true })];
    expect(getBlockBorderClass(block, refs)).toBe('border-amber-400');
  });
});

describe('parseMarkdownSegments', () => {
  it('returns a single text segment for plain text', () => {
    expect(parseMarkdownSegments('plain text')).toEqual([{ kind: 'text', text: 'plain text' }]);
  });

  it('parses **bold** correctly', () => {
    expect(parseMarkdownSegments('**प्रश्न** — उत्तर')).toEqual([
      { kind: 'bold', text: 'प्रश्न' },
      { kind: 'text', text: ' — उत्तर' },
    ]);
  });

  it('parses *italic* correctly', () => {
    expect(parseMarkdownSegments('see *this* here')).toEqual([
      { kind: 'text', text: 'see ' },
      { kind: 'italic', text: 'this' },
      { kind: 'text', text: ' here' },
    ]);
  });

  it('parses _italic_ correctly', () => {
    expect(parseMarkdownSegments('_hello_ world')).toEqual([
      { kind: 'italic', text: 'hello' },
      { kind: 'text', text: ' world' },
    ]);
  });

  it('handles multiple tokens in one string', () => {
    const result = parseMarkdownSegments('**bold** and *italic*');
    expect(result).toEqual([
      { kind: 'bold', text: 'bold' },
      { kind: 'text', text: ' and ' },
      { kind: 'italic', text: 'italic' },
    ]);
  });

  it('returns empty array for empty string', () => {
    expect(parseMarkdownSegments('')).toEqual([]);
  });

  it('returns empty array for null input', () => {
    expect(parseMarkdownSegments(null)).toEqual([]);
  });
});

describe('formatRefSourceLabel', () => {
  it('returns shastra_name for non-teeka refs', () => {
    const ref = makeRef({ is_teeka: false, shastra_name: 'समयसार', teeka_name: '' });
    expect(formatRefSourceLabel(ref)).toBe('समयसार');
  });

  it('returns empty string when shastra_name is null for non-teeka ref', () => {
    const ref = makeRef({ is_teeka: false, shastra_name: null, teeka_name: '' });
    expect(formatRefSourceLabel(ref)).toBe('');
  });

  it('combines shastra_name and teeka_name for teeka refs', () => {
    const ref = makeRef({ is_teeka: true, shastra_name: 'समयसार', teeka_name: 'तात्पर्यवृत्ति टीका' });
    expect(formatRefSourceLabel(ref)).toBe('समयसार, तात्पर्यवृत्ति टीका');
  });

  it('returns only teeka_name when shastra_name is null for teeka ref', () => {
    const ref = makeRef({ is_teeka: true, shastra_name: null, teeka_name: 'तात्पर्यवृत्ति टीका' });
    expect(formatRefSourceLabel(ref)).toBe('तात्पर्यवृत्ति टीका');
  });

  it('returns only shastra_name when teeka_name is empty for teeka ref', () => {
    const ref = makeRef({ is_teeka: true, shastra_name: 'समयसार', teeka_name: '' });
    expect(formatRefSourceLabel(ref)).toBe('समयसार');
  });
});
