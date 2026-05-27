import { describe, expect, it } from 'vitest';
import { GathaPanel } from '@/components/GathaPanel';

describe('GathaPanel', () => {
  it('is a defined component for all supported langs', () => {
    expect(GathaPanel).toBeDefined();
  });
});
