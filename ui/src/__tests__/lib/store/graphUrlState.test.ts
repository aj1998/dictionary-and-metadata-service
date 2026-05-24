import { describe, expect, it } from 'vitest';
import { parseGraphQuery, buildGraphQuery } from '@/lib/store/graphUrlState';

describe('graphUrlState', () => {
  it('parses node/depth/cat from query params', () => {
    const parsed = parseGraphQuery(new URLSearchParams('node=n1&depth=3&cat=topic,keyword'));
    expect(parsed.node).toBe('n1');
    expect(parsed.depth).toBe(3);
    expect(parsed.hiddenCats).toEqual(['topic', 'keyword']);
  });

  it('bounds depth to 1..4 and ignores invalid categories', () => {
    const parsed = parseGraphQuery(new URLSearchParams('depth=99&cat=topic,foo'));
    expect(parsed.depth).toBe(4);
    expect(parsed.hiddenCats).toEqual(['topic']);
  });

  it('serializes query from state in stable order', () => {
    const query = buildGraphQuery({
      selectedNode: 'n1',
      selectedEdge: 'e1',
      depth: 2,
      hiddenCats: ['keyword', 'topic'],
    });
    expect(query.toString()).toBe('node=n1&edge=e1&depth=2&cat=keyword%2Ctopic');
  });
});
