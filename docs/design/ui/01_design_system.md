# 01 — Design System

Pixel-level tokens and primitives. Every value here is exported as a CSS
variable in `ui/src/styles/theme.css` and mirrored in `tailwind.config.ts`
via `@theme inline`. Components must consume tokens, never hard-code
hex values (except where explicitly noted, e.g. one-off node-category dots).

> **Canonical reference**: `ux_template_images/overall_theme_and_panels.png`.
> When in doubt, match the image. The image's red-on-white, generous
> whitespace, slim borders, and soft shadows define the entire look.

## 1. Color tokens

The existing `ui_template/src/styles/theme.css` indigo/purple palette is
**replaced** by this red-accent palette. Light theme is the default; dark
theme is a future enhancement (keep variables in place but ship light-only
in v1).

### Light theme (default)

| Token | Value | Use |
|---|---|---|
| `--background` | `#F7F7F8` | Body background behind cards |
| `--surface` | `#FFFFFF` | Cards, panels, nav bar |
| `--surface-muted` | `#FAFAFB` | Hover row, subtle wells |
| `--foreground` | `#1A1A1A` | Primary text |
| `--foreground-muted` | `#6B7280` | Secondary text, captions, English subtitles |
| `--foreground-subtle` | `#9CA3AF` | Hints, placeholders |
| `--border` | `#E5E7EB` | Hairline borders |
| `--border-strong` | `#D1D5DB` | Input borders, dividers |
| `--accent` | `#E63946` | **The red.** CTA, active node fill, selected badge, category dots |
| `--accent-hover` | `#D62839` | CTA hover |
| `--accent-foreground` | `#FFFFFF` | Text on accent |
| `--accent-soft` | `#FDECEE` | Accent-tinted backgrounds (selected row, badge bg) |
| `--ring` | `#E63946` | Focus ring (alpha 30%) |
| `--success` | `#16A34A` | Status only |
| `--warning` | `#D97706` | Status only |
| `--danger` | `#DC2626` | Destructive only (matches accent visually but reserved for errors) |
| `--graph-grid-dot` | `#D9DBE0` | Dotted-grid background dots in graph canvas |
| `--graph-edge` | `#1F3A8A` | Edge line color (deep indigo for contrast on white) |
| `--graph-edge-muted` | `#C7CCE0` | Faded/inactive edge |
| `--node-bg` | `#FFFFFF` | Default node card fill |
| `--node-bg-selected` | `#E63946` | Selected node fill (text becomes white) |
| `--node-border` | `#E5E7EB` | Node card border |
| `--node-shadow` | `0 1px 2px rgba(16,24,40,0.06), 0 1px 3px rgba(16,24,40,0.08)` | Node card shadow |
| `--node-shadow-hover` | `0 4px 12px rgba(16,24,40,0.10), 0 2px 4px rgba(16,24,40,0.06)` | Hover/active shadow |

### Category dot colors

The "विषय (CATEGORIES)" filter list and the small dot/marker on every
node card use **one accent red** for all categories in the canonical image
— but to keep things scannable we assign each entity type a distinct
hue. All four are saturated but muted enough to coexist with the red
accent. They are used **only** on the 6×6 dot/swatch in the category
filter and the 4-px stripe at the top of each node card. Selection state
still uses `--accent`.

| Token | Value | Entity |
|---|---|---|
| `--cat-shastra` | `#E63946` | शास्त्र / Shastra |
| `--cat-gatha` | `#F4A261` | गाथा / Gatha |
| `--cat-topic` | `#2A9D8F` | विषय / Topic |
| `--cat-keyword` | `#264653` | शब्द / Keyword |

> If `ux_template_images/overall_theme_and_panels.png` is later updated
> to use red for every dot, drop the per-category hues and use
> `--accent` everywhere — the rest of the system requires no change.

## 2. Typography

Two font families, both via `next/font` so they self-host and never FOUC.

| Family | Weights | Use |
|---|---|---|
| **Noto Serif Devanagari** | 400, 500, 600, 700 | All Hindi/Sanskrit/Prakrit body text, headings, gatha rendering. **Default `body` font.** Tailwind class `font-serif-hindi`. |
| **Inter** | 400, 500, 600, 700 | English chrome, numerals, badges, buttons, captions, code/IDs. Tailwind class `font-sans`. |

Numerals: prefer **Devanagari numerals** (०१२३४५६७८९) for counts shown to
the reader (`१०`, `३५७`, `२` exactly as in the reference image). Use
ASCII numerals only for technical IDs, pagination internals, and code.

### Scale (mobile-first; desktop tracked in parens)

| Token | Size / line-height | Use |
|---|---|---|
| `text-display` | 32 / 40 (40 / 48) | Page heroes only |
| `text-h1` | 24 / 32 (28 / 36) | Detail-page titles ("तत्त्वार्थसूत्र" in panel) |
| `text-h2` | 20 / 28 | Section headings ("विवरण", "संबंधित विषय") |
| `text-h3` | 16 / 24 | Card titles, node card title |
| `text-body` | 15 / 24 | Body paragraphs |
| `text-sm` | 13 / 20 | Captions, subtitles, English under Hindi |
| `text-xs` | 11 / 16 | Uppercase eyebrow labels, badge text |

Weights: headings 600, body 400, eyebrows 500 uppercase + 0.04em
letter-spacing.

## 3. Spacing & layout primitives

8-point spacing scale, identical to Tailwind defaults. Standard insets:

| Use | Padding |
|---|---|
| Page outer gutter (≥1280px) | 24 / 32 px |
| Card inner padding (node card) | 12 / 14 px |
| Detail-panel padding | 24 px |
| Section vertical gap (panel) | 24 px |
| Filter-row gap | 10 px |

Page max-width: **1440px** for centered pages; the graph page is
**full-bleed** (no max-width).

## 4. Radii & borders

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 6 px | Buttons, input, badges |
| `--radius-md` | 10 px | Cards, panels, node cards |
| `--radius-lg` | 14 px | Hero blocks, gatha quote blocks |
| `--radius-pill` | 9999 px | Filter chips, category pills, status pills |

Borders are always **1 px** `--border`. Never use 2 px borders. Selected
state replaces the border with a 2 px **inset** `--accent` outline so card
size does not shift.

## 5. Shadow

Two elevations only:

- **Resting**: `--node-shadow` (used by node cards, side panels, dropdowns).
- **Hover / focus**: `--node-shadow-hover`.

Modal/overlay: `0 24px 48px rgba(16,24,40,0.18)`.

## 6. Iconography

`lucide-react` only. Stroke width `1.5`. Sizes `16`, `18`, `20`, `24`.
Icons inside node cards use `18`; nav-bar icons use `20`.

Reserved icons (do not substitute):

| Concept | Icon |
|---|---|
| Search | `Search` |
| Home | `Home` |
| Graph | `Network` |
| Dictionary | `BookOpen` |
| Topic | `Tag` |
| Shastra | `ScrollText` |
| Gatha | `BookMarked` |
| Keyword | `Sparkles` |
| Filter / Categories | `LayoutList` |
| Info / Help | `Info` |
| Bookmark (CTA) | `Bookmark` |
| Read more arrow | `ArrowRight` |
| Connection arrow (right-chevron in list rows) | `ChevronRight` |
| Zoom in / out / reset | `Plus`, `Minus`, `Maximize2` |
| Close | `X` |

## 7. Badges, chips, stat tiles

### Entity badge (top-right of side panel, top-left of node card)

A `--radius-pill` chip, 22 px tall, 10 px horizontal padding, `text-xs`
600, color = the entity's category color, foreground white. Examples:

- `विषय / Topic` on `--cat-topic`
- `शास्त्र / Shastra` on `--cat-shastra`

### Category filter row (left panel)

Plain row, no border. 6×6 px rounded square `--cat-*` swatch + Hindi
label (`text-body` 500) + parenthesized English (`text-sm` 400
`--foreground-muted`). A checkbox-style toggle on the right (use the
shadcn `Switch` in a compact size, 28×16).

### Stat tile (3-up in the detail panel)

White card, `--radius-md`, `--border`, 16 px padding, two stacked lines:
big number `text-h1` Devanagari numerals 600, small caption
`text-xs` uppercase `--foreground-muted`.

```
┌──────────┐
│   १०     │
│ संबंध      │
└──────────┘
```

## 8. Primary CTA

The bottom red button in the detail panel ("विस्तार से पढ़ें / Read
More"):

- Background `--accent`, foreground white.
- 44 px tall, full panel width minus 24 px inset on both sides.
- 12 px radius (`--radius-md`).
- Left: bold Hindi label + smaller English subtitle in parentheses.
- Right: `Bookmark` icon, 18 px, white, opacity 90%.
- Hover: bg `--accent-hover`, shadow `--node-shadow-hover`.

Secondary action ("View All Connections" link inside the panel): plain
text link in `--accent`, 500, with a trailing `ChevronRight` 14 px.

## 9. Focus & motion

- Focus ring: 2 px solid `--ring` at 30% alpha, 2 px offset.
- Hover transitions: 120 ms ease-out on `background`, `box-shadow`,
  `border-color`. Never transition `transform` on hover for node cards
  (they jitter under the force layout).
- Side panel mount: slide-in from right 200 ms ease-out, fade simultaneously.
- Page transitions: instant; Next.js default. No global page fades.
