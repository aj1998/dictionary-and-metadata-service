# 03 — Shastra Reader UI Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md). The reading core — a per-shastra layout-driven page with stacked panels, keyword hover/click, JainKosh highlight overlay, audio strip, drushtaant images, and export menu.

Depends on:
- [`02_shastra_layout_configs_spec.md`](./02_shastra_layout_configs_spec.md) for the layout config served at `GET /v1/shastras/{nk}/layout`.
- [`04_keyword_hover_expansion_spec.md`](./04_keyword_hover_expansion_spec.md) for `<TaggedTermPopover>` and the annotated-spans contract.
- [`12_jainkosh_highlight_overlay_spec.md`](./12_jainkosh_highlight_overlay_spec.md) for the `<HighlightToggle>`.
- The existing data-service contract in [`docs/design/14_public_ui.md`](../14_public_ui.md). The new page lives at `ui/app/shastra-explorer/[nk]/[...unit_path]/page.tsx` — **does not modify** the existing `/shastras/[nk]/gathas/[number]/page.tsx`.

## URL contract

```
/shastra-explorer/[shastra_nk]/[...unit_path]
```

`unit_path` is the slash-joined leaf-unit address, resolved via the layout config's `native_structure`:

| Shastra | Example URL | Meaning |
|---|---|---|
| samaysaar | `/shastra-explorer/samaysaar/adhikaar/1/gatha/039` | adhikaar 1, gatha 39 |
| tatvarth-sutra | `/shastra-explorer/tatvarth-sutra/adhyaay/2/sutra/14` | adhyaay 2, sutra 14 |
| padma-puraan | `/shastra-explorer/padma-puraan/parva/1/sarga/3/shloka/12` | parva 1, sarga 3, shloka 12 |

Bare `/shastra-explorer/{nk}` redirects to first leaf unit. Query params: `?lang=hi|en`, `?highlights=on|off`, `?panel=bhaavarth` (auto-scroll target).

## Phase A — page shell driven by layout config

### Files

```
ui/app/shastra-explorer/
├── [nk]/
│   ├── page.tsx                       # bare → redirect to first unit
│   ├── [...unit_path]/
│   │   └── page.tsx                   # Server Component, fetches layout + unit, renders shell
│   └── error.tsx                      # boundary
├── _components/
│   ├── PanelStack.tsx                 # Server Component: ordered panel container
│   ├── Panel.tsx                      # Server wrapper; takes {kind, visible, collapsible, children}
│   ├── PanelPlaceholder.tsx           # Phase A only; "kind: prakrit (no data)"
│   ├── UnitPager.tsx                  # Client: prev/next within prev_next_scope
│   ├── BreadcrumbBar.tsx              # native_structure → breadcrumb labels
│   ├── LangToggle.tsx                 # Client: hi|en|+overlay
│   ├── HighlightToggle.tsx            # Client: see spec 12
│   ├── RightRail.tsx                  # Client: popover stack, mini graph, export, save mark
│   └── PanelHeader.tsx                # collapsible chevron + label

ui/lib/shastra_explorer/
├── url.ts                             # parseUnitPath(layout, segments) -> {level_values, leaf_natural_key}
├── resolve.ts                         # buildLeafNaturalKey(layout, level_values) using natural_key_template
├── prefetch.ts                        # prev/next URL builders
└── api.ts                             # getLayout(), getUnit(), getAnnotatedText()
```

### Server data flow

```ts
// ui/app/shastra-explorer/[nk]/[...unit_path]/page.tsx
export default async function Page({ params: { nk, unit_path } }) {
  const layout = await api.getLayout(nk);                       // GET /v1/shastras/{nk}/layout
  const { leaf_natural_key, level_values } = parseUnitPath(layout, unit_path);
  const unit = await api.getUnit(nk, leaf_natural_key);         // GET /v1/shastras/{nk}/units/{leaf_nk}
  return (
    <ReaderShell layout={layout} unit={unit} levelValues={level_values}>
      <BreadcrumbBar layout={layout} values={level_values} />
      <UnitPager layout={layout} values={level_values} unit={unit} />
      <PanelStack layout={layout} unit={unit} />
      <RightRail unit={unit} />
    </ReaderShell>
  );
}
```

Phase A `<PanelStack>` walks `layout.panels` in order and renders `<PanelPlaceholder kind={p.kind} />` for every panel — no panel-body data yet.

### Data-service endpoint (new in this spec)

```
GET /v1/shastras/{shastra_nk}/units/{leaf_natural_key}
```

Response shape (Pydantic on the server, TypeScript mirror in `ui/lib/shastra_explorer/api.ts`):

```python
class UnitPayload(BaseModel):
    shastra_natural_key: str
    leaf_natural_key: str
    breadcrumb: list[BreadcrumbItem]               # [{level, label_hi, label_en, value}]
    prakrit: TextBlock | None
    sanskrit_chhaaya: TextBlock | None
    hindi_chhand: list[TextBlock] = []
    word_meanings: list[WordMeaning] = []
    anvayartha: AnnotatedText | None               # see spec 04 for span shape
    bhaavarth: list[TeekaSection] = []             # one per teeka, ordered by layout.teeka_order
    drushtaant: DrushtaantImage | None             # see spec 05
    related_topics: list[RelatedTopic] = []
    audio: AudioChapterRef | None                  # see spec 06
    references: list[Reference] = []
    prev_leaf_natural_key: str | None
    next_leaf_natural_key: str | None
```

`AnnotatedText = {html_text: str, spans: list[Span]}` — span format defined in [`spec 04`](./04_keyword_hover_expansion_spec.md).

### Prefetch strategy

- `<UnitPager>` uses `<Link prefetch>` for both `prev_leaf_natural_key` and `next_leaf_natural_key`.
- Server Component sets `export const revalidate = 300` for unit pages (5 min). Cache key includes `?lang`.
- Layout payload cached at the route segment via `unstable_cache(getLayout, [nk], { revalidate: 600 })`.

### Tests (Phase A — TDD)

1. `ui/tests/shastra_explorer/url.test.ts::parses_samaysaar_adhikaar_gatha` — `parseUnitPath(samaysaar_layout, ["adhikaar","1","gatha","039"])` → `{leaf_natural_key:"samaysaar:039", level_values:{adhikaar_idx:"1", gatha_number:"039"}}`.
2. `url.test.ts::rejects_unknown_level` — extra segment → throws.
3. `url.test.ts::resolves_three_level_puraan` — padma-puraan parva/1/sarga/3/shloka/12 → leaf NK matches template.
4. `resolve.test.ts::builds_natural_key_from_template` — `buildLeafNaturalKey` round-trips.
5. `prefetch.test.ts::builds_prev_next_within_scope` — at first gatha of adhikaar with `prev_next_scope:"adhikaar"`, `prev = null`.
6. Playwright `tests/e2e/shastra_explorer_shell.spec.ts::renders_panel_placeholders_in_order` — visit `/shastra-explorer/samaysaar/adhikaar/1/gatha/039`, assert DOM order matches `layout.panels` kinds.
7. Playwright `lang_toggle_persists.spec.ts` — toggle `en`, refresh, still en.

## Phase B — wire panels to data sources

### Panel-by-panel component map

| Panel kind | Component (Client/Server) | Data source on `unit` |
|---|---|---|
| `prakrit` | `<PrakritPanel>` (Server) | `unit.prakrit` |
| `sanskrit_chhaaya` | `<SanskritChhaayaPanel>` (Server) | `unit.sanskrit_chhaaya` |
| `hindi_chhand` | `<HindiChhandPanel>` (Server) | `unit.hindi_chhand[]` (carousel if >1) |
| `word_meanings` | `<WordMeaningsPanel>` (Client) | `unit.word_meanings` — hover reveals Hindi gloss |
| `anvayartha` | `<AnvayarthaPanel>` (Client) | `unit.anvayartha` — passes spans to `<TaggedTermPopover>` per spec 04 |
| `bhaavarth` | `<BhaavarthPanel>` (Client) | `unit.bhaavarth[]` (per-teeka tabs honouring `layout.teeka_order`) |
| `drushtaant` | `<DrushtaantPanel>` (Client) | `unit.drushtaant` (spec 05); button to generate if missing & admin |
| `related_topics` | `<RelatedTopicsPanel>` (Client) | `unit.related_topics` — mini-graph via `navigation-service` |
| `audio` | `<AudioStrip>` (Client) | `unit.audio` (spec 06); pinned to bottom |
| `references` | `<ReferencesPanel>` (Server) | `unit.references` |
| `notes` | `<NotesPanel>` (Server) | `unit.notes` |

`<PanelStack>` in Phase B switches on `p.kind` to the right component.

### Hindi highlight overlay

The `<HighlightToggle>` (spec 12) toggles a CSS class on `<PanelStack>` root: `data-highlights="on"`. Each panel that consumes `AnnotatedText` (currently `anvayartha`, `bhaavarth`) styles spans differently when the class is on (see spec 12 for color rules).

### Right rail

`<RightRail>` is a sticky column with four stacked widgets:

1. **Keyword popover stack** — last 5 hovered/clicked keywords. Clicking → `<KeywordSidePanel>` (spec 04) docks in.
2. **Mini graph** — small Cytoscape view of the unit's `related_topics` + `keyword_ids` (lazy-loaded via `next/dynamic`, `ssr: false`).
3. **Export menu** — dropdown: "PDF: gatha", "PDF: adhikaar", "PDF: shastra", "PDF: selection" (spec 07).
4. **Save mark** — bookmark this unit (authenticated only; calls `/v1/me/saved-views` from [spec 01](./01_user_accounts_spec.md)).

### Performance budget

- LCP **< 2.5 s** on Slow-3G profile (Chrome DevTools throttling). Achieved by:
  - Server-side rendering Prakrit + Hindi chhand panels (text-only, no JS hydration cost).
  - Lazy-loading: `<DrushtaantPanel>`, `<RelatedTopicsPanel>` mini-graph, `<AudioStrip>` waveform.
  - Inlined critical font subset (Noto Serif Devanagari) for u+0900-097F.
- p95 panel render after data load **< 200 ms** measured by `performance.mark` in `<Panel>` mount/unmount.
- Lighthouse Performance ≥ 80 on a sample unit page; budgeted in `ui/lighthouserc.json`.

### Tests (Phase B — TDD)

1. `BhaavarthPanel.test.tsx::renders_teeka_tabs_in_layout_order` — given `layout.teeka_order = ["amritchandra","jaysenacharya"]`, first tab is amritchandra.
2. `AnvayarthaPanel.test.tsx::renders_spans_via_TaggedTermPopover` — counts `<TaggedTermPopover>` instances == span count of type `keyword|topic`.
3. `HindiChhandPanel.test.tsx::carousel_when_multiple` — given two chhand variants, renders pager dots.
4. `RightRail.test.tsx::save_mark_hidden_for_guest` — `useSession()` returns null → save button not rendered.
5. `RelatedTopicsPanel.test.tsx::lazy_loads_minigraph_on_open` — collapsed by default; expand triggers dynamic import.
6. Playwright `panel_visibility_follows_layout.spec.ts` — set layout panel `bhaavarth.visible_default=false`, reload, panel collapsed.
7. Playwright `lcp_under_2_5s.spec.ts` — uses `page.metrics()` + 3G throttle, assert LCP < 2500 ms on samaysaar gatha 001.
8. Playwright `p95_panel_render.spec.ts` — instrument `performance.mark`, navigate 20 units, assert p95 < 200 ms.

## Manual verification

```bash
# Backend
docker compose up -d postgres mongo data-service auth-service
python scripts/seed_shastra_layouts.py

# UI
cd ui && npm run dev

# Hit a few representative URLs
open http://localhost:3000/shastra-explorer/samaysaar/adhikaar/1/gatha/001
open http://localhost:3000/shastra-explorer/tatvarth-sutra/adhyaay/1/sutra/01
open http://localhost:3000/shastra-explorer/padma-puraan/parva/1/sarga/1/shloka/01

# Toggle language
# Click LangToggle → en, page rerenders, hindi_chhand panel falls back gracefully.

# Toggle JainKosh highlights
# Press 'j', spans gain colour (see spec 12).

# Pager
# Click next ► — URL updates to next leaf; prefetched, no full reload.
```

## Definition of done

- [ ] `GET /v1/shastras/{nk}/units/{leaf_nk}` returns the full `UnitPayload` for samaysaar gatha 1, tatvarth-sutra adhyaay 1 sutra 1, padma-puraan parva 1 sarga 1 shloka 1.
- [ ] Phase A shell renders panel placeholders in `layout.panels` order for every seeded shastra.
- [ ] Phase B panels render real data; all panel-level tests pass.
- [ ] LCP < 2.5 s on Slow-3G profile (Playwright assertion).
- [ ] p95 panel render < 200 ms after data loads.
- [ ] Prefetching on `<UnitPager>` works (Network tab shows next unit fetched before click).
- [ ] No modification to existing `/shastras/[nk]/gathas/[number]` route.

## Implementation notes

_(to be filled in after merge)_
