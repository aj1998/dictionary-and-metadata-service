# 02 — Layout & Navigation

## 1. Top navigation bar (global)

Visible on every public route. Matches the bar in
`overall_theme_and_panels.png` exactly.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [📖] जैन ज्ञान कोष        [🔎 गाथा, शास्त्र, कीवर्ड खोजें…]   होम  ग्राफ  शब्दकोष  परिचय │
└──────────────────────────────────────────────────────────────────────────┘
```

Specs:

- Height **64 px** on desktop, **56 px** on mobile.
- Background `--surface`, bottom `1 px --border`. No shadow.
- Full-bleed; inner content is centered in a 1440 px max-width container
  with 24 px horizontal padding.
- **Left** (logo/brand):
  - `BookOpen` icon 24 px in `--accent`.
  - Two-line stack: `जैन ज्ञान कोष` (`text-h3` 600, `font-serif-hindi`)
    over `Jain Knowledge Base` (`text-xs` `--foreground-muted`).
  - The whole brand block links to `/`.
- **Center** (global search):
  - 480 px wide (collapses to 360 / 240 at breakpoints), 40 px tall, pill
    radius. Left-anchored `Search` icon (`--foreground-subtle`).
  - Placeholder: `गाथा, शास्त्र, कीवर्ड खोजें…`.
  - Submitting routes to `/search?q=…`.
- **Right** (nav items): horizontal flex, 4 px gap. Each item is a
  text-only button, 36 px tall, 14 px horizontal padding, pill radius:
  - **Inactive**: `text-body` 500, `--foreground-muted`, hover bg
    `--surface-muted`.
  - **Active**: `--foreground` text, `--accent-soft` bg, pill outline
    in `--accent` at 30% alpha. (Match the red rounded pill behind "होम"
    in the reference.)

Nav items (Hindi label / route):

| Label | Route |
|---|---|
| होम | `/` |
| ग्राफ | `/graph` |
| शब्दकोष | `/dictionary` |
| शास्त्र | `/shastras` |
| विषय | `/topics` |
| परिचय | `/about` |
| प्रतिक्रिया | `/feedback` |

> The reference image only shows 4 items; the additional items
> (`शास्त्र`, `विषय`, `प्रतिक्रिया`) collapse into a "More ▾" menu when
> the viewport drops below 1200 px.

Mobile (< 768 px): center search collapses to an icon-only `Search`
button; the right nav collapses behind a `Menu` icon → off-canvas drawer
with the full list. The brand block stays.

## 2. Page shells

There are three shells. Choose by route:

### Shell A — **Graph shell** (full-bleed three-pane)

Used by `/graph` (the canonical graph traversal page).

```
┌─ TopBar ───────────────────────────────────────────────────────────────┐
├──────────┬───────────────────────────────────────────────┬─────────────┤
│ Filters  │              Graph canvas                     │  Details    │
│ (280 px) │              (flex-1, full-bleed)             │  (380 px)   │
│          │                                               │             │
└──────────┴───────────────────────────────────────────────┴─────────────┘
```

- Both side panes are `--surface`, with **only** the inner-facing edge
  bordered (`1 px --border`).
- Left filters pane collapses to a 56 px rail on `< 1100 px`; the rail
  exposes a `LayoutList` toggle that opens an overlay drawer.
- Right details pane is **hidden** until a node is selected; mounts via
  slide-in. On `< 1100 px` it becomes a bottom sheet (75 vh).
- The center pane is the dotted-grid canvas described in
  `03_graph_traversal_page.md`.

### Shell B — **Centered content shell**

Used by Home, About, Feedback, Dictionary index, Topics index, Search,
Shastras list, plus the keyword/topic/shastra/gatha detail pages.

- `max-w-[1200px]` centered in viewport, 24 px horizontal page padding,
  32 px top padding under the nav bar.
- Page begins with a **breadcrumb row** (12 px gap from top), then
  **hero / heading row**, then **content sections** separated by 32 px
  vertical gaps.
- Use white surface cards (`--surface`, `--radius-md`,
  `--node-shadow`) to group every content section; never put content
  directly on `--background`.

### Shell C — **Split-reading shell** (gatha & keyword detail)

For information-dense pages where panels stack vertically.

```
┌─ TopBar ─────────────────────────────────────────────────────────────┐
├──────────────────────────┬───────────────────────────────────────────┤
│ Reader column            │ Sidebar column                            │
│ (60–65 % width)          │ (35–40 % width, sticky)                   │
│ — Prakrit panel          │ — Related topics                          │
│ — Sanskrit panel         │ — Related keywords                        │
│ — Hindi panel            │ — "Open in graph" CTA                     │
│ — Word-by-word           │                                           │
│ — Teeka                  │                                           │
└──────────────────────────┴───────────────────────────────────────────┘
```

Stacks to single column < 1024 px (sidebar moves below reader).

## 3. Footer

A single 56 px bar at the bottom of every centered page (NOT on the graph
shell — the graph occupies full viewport height).

- `text-xs` `--foreground-muted` centered.
- Left: `© जैन ज्ञान कोष` + version tag.
- Right: links to `/about`, source attributions
  (jainkosh.org, nikkyjain.github.io), and locale switch (हिन्दी /
  English).

## 4. Breakpoints

Mobile-first. Tailwind defaults are sufficient:

| Name | Min width | Notable behavior |
|---|---|---|
| `sm` | 640 | (no major chrome change) |
| `md` | 768 | Mobile drawer → inline nav (limited items) |
| `lg` | 1024 | Split-reading shell goes side-by-side |
| `xl` | 1280 | Graph shell shows both side panes inline |
| `2xl` | 1536 | Increase outer page gutter to 48 px |

## 5. Loading & empty chrome

While the page-level fetch is in flight, the shell renders but the
content area shows skeleton blocks using `--surface-muted` rectangles
with a 1.4 s shimmer (`@keyframes shimmer` in `globals.css`). Never spin
a centered spinner — readers are landing on Devanagari content and
skeletons preserve layout.
