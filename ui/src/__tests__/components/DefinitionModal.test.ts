import { describe, it, expect } from 'vitest';
import { getBlockBorderClass, formatRefSourceLabel, parseMarkdownSegments, pickRefsToShow, pickHiddenRefs, groupTopicExtractsByShastra } from '@/components/DefinitionModal';
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

describe('pickRefsToShow', () => {
  it('returns empty array when block has no references', () => {
    const block = makeBlock({ references: [] });
    expect(pickRefsToShow(block)).toEqual([]);
  });

  it('returns a single non-inline ref with resolved_fields', () => {
    const ref = makeRef({ inline_reference: false });
    const block = makeBlock({ references: [ref] });
    expect(pickRefsToShow(block)).toEqual([ref]);
  });

  it('returns ALL non-inline refs when multiple exist', () => {
    const ref1 = makeRef({ inline_reference: false, shastra_name: 'समयसार' });
    const ref2 = makeRef({ inline_reference: false, shastra_name: 'नियमसार' });
    const block = makeBlock({ references: [ref1, ref2] });
    const result = pickRefsToShow(block);
    expect(result).toHaveLength(2);
    expect(result).toContain(ref1);
    expect(result).toContain(ref2);
  });

  it('excludes non-inline refs with no resolved_fields', () => {
    const withFields = makeRef({ inline_reference: false });
    const noFields = makeRef({ inline_reference: false, resolved_fields: [] });
    const block = makeBlock({ references: [withFields, noFields] });
    expect(pickRefsToShow(block)).toEqual([withFields]);
  });

  it('falls back to first inline ref when all refs are inline', () => {
    const inline1 = makeRef({ inline_reference: true, shastra_name: 'समयसार' });
    const inline2 = makeRef({ inline_reference: true, shastra_name: 'नियमसार' });
    const block = makeBlock({ references: [inline1, inline2] });
    // Inline fallback: only the first qualifying ref
    expect(pickRefsToShow(block)).toEqual([inline1]);
  });

  it('prefers non-inline refs over inline refs when both present', () => {
    const nonInline = makeRef({ inline_reference: false, shastra_name: 'समयसार' });
    const inline = makeRef({ inline_reference: true, shastra_name: 'नियमसार' });
    const block = makeBlock({ references: [inline, nonInline] });
    expect(pickRefsToShow(block)).toEqual([nonInline]);
  });

  it('returns empty array when inline fallback refs have no resolved_fields', () => {
    const inline = makeRef({ inline_reference: true, resolved_fields: [] });
    const block = makeBlock({ references: [inline] });
    expect(pickRefsToShow(block)).toEqual([]);
  });

  it('returns all non-inline refs including teeka refs', () => {
    const shastraRef = makeRef({ inline_reference: false, is_teeka: false, shastra_name: 'समयसार' });
    const teekaRef = makeRef({ inline_reference: false, is_teeka: true, shastra_name: 'समयसार', teeka_name: 'टीका' });
    const block = makeBlock({ references: [shastraRef, teekaRef] });
    const result = pickRefsToShow(block);
    expect(result).toHaveLength(2);
    expect(result).toContain(shastraRef);
    expect(result).toContain(teekaRef);
  });
});

describe('pickHiddenRefs', () => {
  it('returns empty array when block has no references', () => {
    expect(pickHiddenRefs(makeBlock({ references: [] }))).toEqual([]);
  });

  it('returns empty array when all non-inline refs are already shown', () => {
    const ref = makeRef({ inline_reference: false });
    expect(pickHiddenRefs(makeBlock({ references: [ref] }))).toEqual([]);
  });

  it('returns inline refs hidden when non-inline refs take precedence', () => {
    const nonInline = makeRef({ inline_reference: false, shastra_name: 'समयसार' });
    const inline = makeRef({ inline_reference: true, shastra_name: 'नियमसार' });
    const block = makeBlock({ references: [nonInline, inline] });
    const hidden = pickHiddenRefs(block);
    expect(hidden).toEqual([inline]);
  });

  it('returns extra inline refs beyond the first when only inline refs exist', () => {
    const first = makeRef({ inline_reference: true, shastra_name: 'समयसार' });
    const second = makeRef({ inline_reference: true, shastra_name: 'नियमसार' });
    const third = makeRef({ inline_reference: true, shastra_name: 'प्रवचनसार' });
    const block = makeBlock({ references: [first, second, third] });
    const hidden = pickHiddenRefs(block);
    expect(hidden).toHaveLength(2);
    expect(hidden).toContain(second);
    expect(hidden).toContain(third);
  });

  it('excludes refs with no resolved_fields from hidden list', () => {
    const nonInline = makeRef({ inline_reference: false });
    const inlineNoFields = makeRef({ inline_reference: true, resolved_fields: [] });
    const block = makeBlock({ references: [nonInline, inlineNoFields] });
    // inlineNoFields has no resolved_fields, so it should not appear in hidden
    expect(pickHiddenRefs(block)).toEqual([]);
  });

  it('returns multiple hidden refs when both inline and non-inline without fields coexist', () => {
    const nonInline = makeRef({ inline_reference: false, shastra_name: 'समयसार' });
    const inline1 = makeRef({ inline_reference: true, shastra_name: 'नियमसार' });
    const inline2 = makeRef({ inline_reference: true, shastra_name: 'प्रवचनसार' });
    const block = makeBlock({ references: [nonInline, inline1, inline2] });
    const hidden = pickHiddenRefs(block);
    expect(hidden).toHaveLength(2);
    expect(hidden).toContain(inline1);
    expect(hidden).toContain(inline2);
  });

  it('hidden + shown together equal all refs with resolved_fields', () => {
    const ref1 = makeRef({ inline_reference: false, shastra_name: 'अ' });
    const ref2 = makeRef({ inline_reference: true, shastra_name: 'ब' });
    const ref3 = makeRef({ inline_reference: true, shastra_name: 'क', resolved_fields: [] });
    const block = makeBlock({ references: [ref1, ref2, ref3] });
    const shown = pickRefsToShow(block);
    const hidden = pickHiddenRefs(block);
    const allWithFields = block.references.filter((r) => r.resolved_fields.length > 0);
    expect([...shown, ...hidden].sort()).toEqual(allWithFields.sort());
  });
});

// groupTopicExtractsByShastra is reused by KeywordDefinitionBlocks (keyword path)
// and TopicExtractsSection (topic path). These tests cover both call sites.
describe('groupTopicExtractsByShastra — keyword-path scenarios', () => {
  it('groups keyword blocks by shastra the same way as topic extracts', () => {
    const ref1 = makeRef({ shastra_name: 'सिद्धांतकोष', inline_reference: false });
    const ref2 = makeRef({ shastra_name: 'आत्मख्याति', inline_reference: false });
    const block1 = makeBlock({ references: [ref1] });
    const block2 = makeBlock({ references: [ref1] });
    const block3 = makeBlock({ references: [ref2] });

    const groups = groupTopicExtractsByShastra([block1, block2, block3]);
    expect(groups).toHaveLength(2);
    const g1 = groups.find((g) => g.groupKey === 'सिद्धांतकोष')!;
    const g2 = groups.find((g) => g.groupKey === 'आत्मख्याति')!;
    expect(g1.blocks).toHaveLength(2);
    expect(g2.blocks).toHaveLength(1);
  });

  it('filters see_also blocks so they never appear in keyword groups', () => {
    const ref = makeRef({ shastra_name: 'समयसार', inline_reference: false });
    const normalBlock = makeBlock({ references: [ref] });
    const seeAlsoBlock = makeBlock({ kind: 'see_also' });

    const groups = groupTopicExtractsByShastra([normalBlock, seeAlsoBlock]);
    expect(groups).toHaveLength(1);
    expect(groups[0].blocks).toHaveLength(1);
    expect(groups[0].blocks[0]).toBe(normalBlock);
  });

  it('returns empty array when all blocks are see_also (no visible keyword blocks)', () => {
    const block = makeBlock({ kind: 'see_also' });
    expect(groupTopicExtractsByShastra([block])).toEqual([]);
  });

  it('groups blocks with teeka refs under the shastra key (shastra_name from teeka ref)', () => {
    const teekaRef = makeRef({ is_teeka: true, shastra_name: 'समयसार', teeka_name: 'टीका', inline_reference: false });
    const block = makeBlock({ references: [teekaRef] });
    const groups = groupTopicExtractsByShastra([block]);
    expect(groups).toHaveLength(1);
    expect(groups[0].groupKey).toBe('समयसार');
  });
});

describe('groupTopicExtractsByShastra', () => {
  it('returns empty array for empty input', () => {
    expect(groupTopicExtractsByShastra([])).toEqual([]);
  });

  it('skips see_also blocks', () => {
    const seeAlso = makeBlock({ kind: 'see_also' });
    expect(groupTopicExtractsByShastra([seeAlso])).toEqual([]);
  });

  it('puts blocks with no resolvable ref into अन्य group (key: empty string)', () => {
    const block = makeBlock({ references: [] });
    const groups = groupTopicExtractsByShastra([block]);
    expect(groups).toHaveLength(1);
    expect(groups[0].groupKey).toBe('');
    expect(groups[0].label).toBe('अन्य');
    expect(groups[0].blocks).toEqual([block]);
  });

  it('groups blocks by shastra_name from primary ref', () => {
    const refA = makeRef({ shastra_name: 'समयसार', inline_reference: false });
    const refB = makeRef({ shastra_name: 'नियमसार', inline_reference: false });
    const blockA1 = makeBlock({ references: [refA] });
    const blockA2 = makeBlock({ references: [refA] });
    const blockB = makeBlock({ references: [refB] });

    const groups = groupTopicExtractsByShastra([blockA1, blockA2, blockB]);
    expect(groups).toHaveLength(2);
    const samayaGroup = groups.find((g) => g.groupKey === 'समयसार')!;
    const niyamaGroup = groups.find((g) => g.groupKey === 'नियमसार')!;
    expect(samayaGroup.label).toBe('समयसार');
    expect(samayaGroup.blocks).toHaveLength(2);
    expect(niyamaGroup.blocks).toHaveLength(1);
  });

  it('sorts groups alphabetically by label (Hindi locale)', () => {
    const refB = makeRef({ shastra_name: 'समयसार', inline_reference: false });
    const refA = makeRef({ shastra_name: 'नियमसार', inline_reference: false });
    const blockB = makeBlock({ references: [refB] });
    const blockA = makeBlock({ references: [refA] });

    const groups = groupTopicExtractsByShastra([blockB, blockA]);
    // 'न' comes before 'स' in Hindi alphabet
    expect(groups[0].groupKey).toBe('नियमसार');
    expect(groups[1].groupKey).toBe('समयसार');
  });

  it('places अन्य group (empty key) last regardless of insertion order', () => {
    const refA = makeRef({ shastra_name: 'समयसार', inline_reference: false });
    const noRef = makeBlock({ references: [] });   // → अन्य
    const blockA = makeBlock({ references: [refA] });

    const groups = groupTopicExtractsByShastra([noRef, blockA]);
    expect(groups[0].groupKey).toBe('समयसार');
    expect(groups[1].groupKey).toBe('');
    expect(groups[1].label).toBe('अन्य');
  });

  it('uses shastra_name null as empty-string key → अन्य', () => {
    const ref = makeRef({ shastra_name: null, inline_reference: false });
    const block = makeBlock({ references: [ref] });
    const groups = groupTopicExtractsByShastra([block]);
    expect(groups[0].groupKey).toBe('');
    expect(groups[0].label).toBe('अन्य');
  });

  it('uses first shown ref to determine the group, not first raw ref', () => {
    // Two refs: first is inline (→ not preferred), second is non-inline (→ preferred).
    const inlineRef = makeRef({ inline_reference: true, shastra_name: 'ब' });
    const nonInlineRef = makeRef({ inline_reference: false, shastra_name: 'अ' });
    const block = makeBlock({ references: [inlineRef, nonInlineRef] });
    const groups = groupTopicExtractsByShastra([block]);
    // pickRefsToShow returns [nonInlineRef] → shastra_name 'अ'
    expect(groups[0].groupKey).toBe('अ');
  });

  it('all blocks (excluding see_also) are present across all groups', () => {
    const refA = makeRef({ shastra_name: 'समयसार', inline_reference: false });
    const refB = makeRef({ shastra_name: 'नियमसार', inline_reference: false });
    const blocks = [
      makeBlock({ references: [refA] }),
      makeBlock({ references: [refB] }),
      makeBlock({ kind: 'see_also' }),
      makeBlock({ references: [] }),
    ];
    const groups = groupTopicExtractsByShastra(blocks);
    const allGroupedBlocks = groups.flatMap((g) => g.blocks);
    expect(allGroupedBlocks).toHaveLength(3); // see_also excluded
  });
});
