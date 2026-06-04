import { describe, it, expect } from 'vitest';
import { deriveStubTopicKeyword } from '@/components/DetailsPanel';
import type { GraphNode } from '@/lib/types';

function makeNode(nk: string, kind: GraphNode['kind'] = 'keyword', title_hi = nk): GraphNode {
  return { nk, kind, title_hi, degree: 1 };
}

describe('deriveStubTopicKeyword', () => {
  it('extracts keyword nk from the part before the first colon', () => {
    const nodes = { 'स्वभाव': makeNode('स्वभाव', 'keyword', 'स्वभाव') };
    const result = deriveStubTopicKeyword('स्वभाव:2', nodes);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ nk: 'स्वभाव', kind: 'keyword', edge_kind: 'HAS_TOPIC' });
  });

  it('uses the keyword node title_hi from nodes when present', () => {
    const nodes = { 'पारिणामिक': makeNode('पारिणामिक', 'keyword', 'पारिणामिक') };
    const result = deriveStubTopicKeyword('पारिणामिक:2', nodes);
    expect(result[0].title_hi).toBe('पारिणामिक');
  });

  it('falls back to keyword nk as title_hi when node is not in graph', () => {
    const result = deriveStubTopicKeyword('स्वभाव:उपचरित-स्वभाव', {});
    expect(result).toHaveLength(1);
    expect(result[0].nk).toBe('स्वभाव');
    expect(result[0].title_hi).toBe('स्वभाव');
  });

  it('passes through title_en from the keyword node when available', () => {
    const nodes = { 'atma': { nk: 'atma', kind: 'keyword' as const, title_hi: 'आत्मा', title_en: 'Soul', degree: 1 } };
    const result = deriveStubTopicKeyword('atma:paryay', nodes);
    expect(result[0].title_en).toBe('Soul');
  });

  it('returns empty array when nk has no colon (not a stub pattern)', () => {
    expect(deriveStubTopicKeyword('स्वभाव', {})).toEqual([]);
  });

  it('only splits on the first colon — multi-segment paths remain intact', () => {
    const result = deriveStubTopicKeyword('स्वभाव:भेद:उपभेद', {});
    expect(result[0].nk).toBe('स्वभाव');
  });
});
