import { describe, expect, it } from 'vitest';
import { buildPreviewLayout } from '@/components/MiniGraphPreview';

describe('buildPreviewLayout', () => {
  it('projects nodes and edges into a bounded preview coordinate space', () => {
    const preview = buildPreviewLayout({
      nodes: [
        { nk: 'a', kind: 'topic', title_hi: 'अ', degree: 1 },
        { nk: 'b', kind: 'keyword', title_hi: 'ब', degree: 1 },
      ],
      edges: [{ id: 'e1', src: 'a', dst: 'b', kind: 'RELATED_TO', weight: 1 }],
      focus_nk: 'a',
      depth: 1,
    });

    expect(preview.nodes).toHaveLength(2);
    expect(preview.edges).toHaveLength(1);
    for (const node of preview.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.x).toBeLessThanOrEqual(280);
      expect(node.y).toBeLessThanOrEqual(180);
    }
  });
});
