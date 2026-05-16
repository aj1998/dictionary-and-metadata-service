# 00 — Public UI: Overview & Reading Order

This folder contains the detailed UI specification for the public-facing
**Jain Knowledge Base** website. It is the implementation-level companion
to [`../14_public_ui.md`](../../14_public_ui.md), which lists routes and data
contracts. This folder fixes **design, theme, layout, components, and
interaction patterns** — pixel-level enough that two engineers building
independently produce visually identical results.

The two driver images live at:

- `ux_template_images/overall_theme_and_panels.png` — **canonical reference** for
  global chrome (nav bar, left filter panel, right details panel), the
  red-accent + light-grey palette, badge styling, typography hierarchy,
  card composition, and the bottom CTA. **Every page of the site must
  match this look.**
- `ux_template_images/navigation_and_graph_look.png` — **canonical reference**
  for the graph canvas: dotted-grid background, rounded white "card" nodes
  with icon + title + subtitle + body field, smooth curved connectors with
  small circular endpoints, soft drop shadow.

A working blueprint of the React/Tailwind structure (component names,
shadcn primitives, state plumbing) is already scaffolded in `ui_template/`.
The specs in this folder **override** the colors, node visuals, and panel
content of that scaffold — the scaffold's structure is correct, but its
node rendering (colored squares) and palette (indigo/purple/cyan/emerald)
must be replaced as described in `01_design_system.md`.

## Reading order

| # | File | What it covers |
|---|---|---|
| 00 | `00_overview.md` | This file. Reading order, source-of-truth images. |
| 01 | `01_design_system.md` | Color tokens, typography, spacing, radii, shadow, badges, icons. The design language. |
| 02 | `02_layout_and_navigation.md` | Top nav bar, page shells (full-bleed vs. centered), responsive breakpoints, footer. |
| 03 | `03_graph_traversal_page.md` | **Primary page.** Three-pane layout, node cards, connectors, left filters, right details panel, zoom/pan, interactions, state machine. |
| 04 | `04_content_pages.md` | Home, Shastras, Shastra detail, Gatha detail, Dictionary, Keyword detail, Topics, Topic detail, Search, About, Feedback. |
| 05 | `05_components.md` | Reusable building blocks: `NodeCard`, `RelationConnector`, `CategoryFilterList`, `StatTile`, `ConnectedItemRow`, `BadgeChip`, `PrimaryCTA`, `TopBar`, etc. |
| 06 | `06_interaction_and_state.md` | Click/hover/drag, keyboard, deep-linking, URL state, loading/empty/error states, animations. |
| 07 | `07_api_integration.md` | Which backend service powers which view; query → render mapping; caching/revalidation rules. |
| 08 | `08_accessibility_and_i18n.md` | Hindi-first defaults, Devanagari normalization, locale switch, aria/keyboard, font loading. |

## Non-goals

- **Admin UI** (`/admin/*`) is covered separately in `../13_admin_ui.md`.
- **Native mobile apps** are out of scope; the site is responsive web only.
- **Authentication** — the public site is fully anonymous and read-only.

## Brand identity at a glance

- Hindi-first, Devanagari-forward. English is the secondary label, smaller,
  in parentheses or a second line.
- **Calm scholarly aesthetic**: lots of whitespace, soft shadows, a single
  warm red accent (`#E63946`-class) used sparingly for selection, CTAs,
  category dots, and the active node. Body chrome is neutral white / very
  light grey.
- The graph is the centerpiece. Everything else (lists, detail pages) is
  styled to harmonize with the graph view, not the other way around.
