import { describe, expect, it } from 'vitest';
import { GATHA_PANEL_ACCENTS } from './GathaPanel';

describe('GATHA_PANEL_ACCENTS', () => {
  it('maps all supported gatha panel languages', () => {
    expect(GATHA_PANEL_ACCENTS.prakrit).toContain('border-l-3');
    expect(GATHA_PANEL_ACCENTS.sanskrit).toContain('border-l-0');
    expect(GATHA_PANEL_ACCENTS['hindi-harigeet']).toContain('border-l-3');
  });
});
