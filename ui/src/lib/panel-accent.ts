export type PanelAccent =
  | 'keyword'
  | 'teeka'
  | 'bhaavarth'
  | 'kalash'
  | 'shastra'
  | 'gatha'
  | 'topic';

const TOKEN: Record<PanelAccent, string> = {
  keyword: '--cat-keyword',
  teeka: '--cat-teeka',
  bhaavarth: '--cat-bhaavarth',
  kalash: '--cat-kalash',
  shastra: '--cat-shastra',
  gatha: '--cat-gatha',
  topic: '--cat-topic',
};

export function panelAccentVar(accent?: PanelAccent): string | undefined {
  if (!accent) return undefined;
  return `var(${TOKEN[accent]})`;
}

export function panelAccentRootStyle(accent?: PanelAccent): React.CSSProperties | undefined {
  if (!accent) return undefined;
  return {
    ['--panel-accent' as string]: `var(${TOKEN[accent]})`,
    borderColor: `color-mix(in srgb, var(${TOKEN[accent]}) 35%, var(--border))`,
  };
}

export function panelAccentHeaderStyle(accent?: PanelAccent): React.CSSProperties | undefined {
  if (!accent) return undefined;
  return {
    backgroundColor: `color-mix(in srgb, var(${TOKEN[accent]}) 12%, transparent)`,
    borderBottomColor: `color-mix(in srgb, var(${TOKEN[accent]}) 25%, var(--border))`,
  };
}

export function panelAccentTitleStyle(accent?: PanelAccent): React.CSSProperties | undefined {
  if (!accent) return undefined;
  return { color: `color-mix(in srgb, var(${TOKEN[accent]}) 85%, var(--foreground))` };
}
