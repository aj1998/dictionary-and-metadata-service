# 12 — JainKosh Highlight Overlay Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md#jainkosh-highlight-overlay).

The visible payoff of the enrichment pipeline. Every span emitted by [`08_translation_pipeline_extraction_spec.md`](./08_translation_pipeline_extraction_spec.md) — topic, keyword, drushtaant, flowchart — is rendered as a colour-coded, hyperlinked overlay on top of the rendered Hindi panels in the Shastra Reader. The user toggles layers per type; hovering shows a tooltip with the reference label; clicking opens a side panel anchored to the underlying entity.

This spec covers both ends: the read endpoint that returns approved spans for a chapter, and the React overlay component that paints them.

Depends on:
- [`08_translation_pipeline_extraction_spec.md`](./08_translation_pipeline_extraction_spec.md) for the `extraction_spans` table (referenced here as `translation_spans` — the same physical table, exposed via this read API).
- [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md) for the `<HighlightToggle>` integration point and the `AnnotatedText` panel contract.
- [`04_keyword_hover_expansion_spec.md`](./04_keyword_hover_expansion_spec.md) for the `<KeywordSidePanel>` opened on click.
- [`05_drushtaant_image_gen_spec.md`](./05_drushtaant_image_gen_spec.md) for the drushtaant entity link target.
- [`20_flowchart_table_graph_scanner_spec.md`](./20_flowchart_table_graph_scanner_spec.md) for the flowchart entity link target.

## Goal

A single GET endpoint returns all approved spans for a chapter (one leaf unit or one adhikaar / parva / chapter). The Shastra Reader renders these as coloured underlines on the Hindi text. The user can:

- Toggle each layer (topic / keyword / drushtaant / flowchart) independently from the reader header.
- Hover any span to see a tooltip showing `ref_label` plus a short excerpt.
- Click a span to open the side panel anchored to the underlying entity.
- Keyboard-navigate (Tab / Shift+Tab) across spans within the current panel; Enter activates the side panel.
- Read the page accessibly: every colour pair meets WCAG 2.1 AA (4.5:1) against both light and dark themes, and patterns are layered on top of colour for colour-blind users.

Performance budget: with 200 spans on a single unit, overlay render must be ≤ 50 ms on a mid-range laptop (measured via `performance.mark` in `<HighlightOverlay>` mount).

## Module paths

```
services/data-service/app/routers/spans.py        # GET /v1/shastras/{nk}/chapters/{n}/spans
services/data-service/app/services/spans.py       # query + assembly
services/data-service/app/tests/test_spans_endpoint.py

ui/components/ShastraReader/
├── HighlightOverlay.tsx                          # core overlay renderer
├── HighlightLayerToggle.tsx                      # per-type checkboxes in reader header
├── SpanTooltip.tsx                               # hover popover
├── useSpanFetch.ts                               # SWR hook + layer-toggle state
├── useSpanKeyboardNav.ts                         # Tab / Enter handling
├── spanColors.ts                                 # palette + tokens
├── spanOverlap.ts                                # interval-tree → render-tree resolver
└── __tests__/
    ├── HighlightOverlay.test.tsx
    ├── spanOverlap.test.ts
    ├── useSpanKeyboardNav.test.ts
    ├── HighlightLayerToggle.test.tsx
    └── color_palette_accessibility.test.ts

ui/lib/spans/
├── types.ts                                      # Span, SpanType, LayerToggle
└── api.ts                                        # getSpans(shastraNk, chapter)
```

The endpoint reads from the existing `extraction_spans` table (defined in spec 08); no new migrations are required. A thin view `v_approved_spans` is added to keep query plans stable.

## Phase A — single-phase implementation

### Read-side view (migration `0029_v_approved_spans.py`)

```sql
CREATE OR REPLACE VIEW v_approved_spans AS
SELECT
  s.id              AS span_id,
  s.kind            AS span_kind,        -- 'topic' | 'keyword' | 'drushtaant' | 'flowchart'
  s.gatha_id,
  g.natural_key     AS gatha_natural_key,
  g.adhikaar_index  AS chapter_index,
  s.mongo_doc_id,
  s.mongo_collection,
  s.lang,
  s.entity_id,
  s.span_start,
  s.span_end,
  s.span_text,
  s.confidence,
  s.llm_model,
  s.reviewed_at
FROM extraction_spans s
LEFT JOIN gathas g ON g.id = s.gatha_id
WHERE s.status = 'approved';

CREATE INDEX IF NOT EXISTS idx_extraction_spans_chapter
  ON extraction_spans (gatha_id, kind, span_start)
  WHERE status = 'approved';
```

Note: span kinds `drushtaant` and `flowchart` are emitted by their respective workers (spec 05 and spec 20) and stored in the same `extraction_spans` table; the enum was widened in their own migrations. This spec only consumes them.

### Pydantic contract (`services/data-service/app/routers/spans.py`)

```python
class SpanOut(BaseModel):
    span_id: UUID
    type: Literal['topic', 'keyword', 'drushtaant', 'flowchart']
    gatha_natural_key: str
    panel: str                          # 'anvayartha' | 'bhaavarth' | 'hindi_chhand' | ...
    mongo_doc_id: str                   # disambiguates within-panel doc when multiple
    start_offset: int                   # NFC codepoint offset into the panel chunk
    end_offset: int
    ref_id: str                         # entity natural-key of topic / keyword / drushtaant / flowchart
    ref_label: str                      # display string for tooltip + side panel header
    ref_url: str                        # client-side route to the side-panel target
    excerpt: str | None                 # short definition / caption snippet, ≤ 240 chars
    confidence: Literal['high', 'medium', 'low']

class ChapterSpansOut(BaseModel):
    shastra_natural_key: str
    chapter_index: int
    span_count: int
    spans: list[SpanOut]
    types: list[Literal['topic','keyword','drushtaant','flowchart']]
    generated_at: datetime
```

### Endpoint

```
GET /v1/shastras/{shastra_natural_key}/chapters/{chapter_index}/spans
    ?types=topic,keyword,drushtaant,flowchart           (optional; default = all)
    &gatha_natural_key=samaysaar:001                    (optional; restrict to one unit)
    &min_confidence=medium                              (optional; default 'low' = all approved)
```

Response: `ChapterSpansOut` (above). Always `200` for valid shastra; empty list if no spans approved yet.

Caching:
- `Cache-Control: public, max-age=120, stale-while-revalidate=600`.
- ETag derived from `max(reviewed_at)` across the result set; clients send `If-None-Match` and the server returns `304` when unchanged.
- Server-side `unstable_cache` key includes `(shastra_nk, chapter_index, types_sorted, min_confidence, gatha_nk_or_null)`.

### Endpoint implementation skeleton

```python
@router.get("/shastras/{shastra_nk}/chapters/{chapter_index}/spans",
            response_model=ChapterSpansOut)
async def get_chapter_spans(
    shastra_nk: str,
    chapter_index: int,
    types: list[str] = Query(default_factory=lambda: ALL_SPAN_TYPES),
    gatha_natural_key: str | None = None,
    min_confidence: Literal['high','medium','low'] = 'low',
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_user_optional),
):
    await _verify_shastra_visible(session, shastra_nk, user)
    rows = await spans_svc.fetch_chapter_spans(
        session,
        shastra_nk=shastra_nk,
        chapter_index=chapter_index,
        types=types,
        gatha_natural_key=gatha_natural_key,
        min_confidence=min_confidence,
    )
    labels = await spans_svc.resolve_labels(session, rows)
    payload = ChapterSpansOut(
        shastra_natural_key=shastra_nk,
        chapter_index=chapter_index,
        span_count=len(rows),
        spans=[spans_svc.to_span_out(r, labels) for r in rows],
        types=types,
        generated_at=datetime.now(timezone.utc),
    )
    return payload
```

`resolve_labels` does one bulk lookup per kind:
- topic / keyword → `display_text` from the canonical table.
- drushtaant → caption from `drushtaant_images.caption`.
- flowchart → title from `flowcharts.title`.

`ref_url` builders:

```python
def build_ref_url(kind: str, natural_key: str) -> str:
    return {
        "topic":      f"/topics/{natural_key}",
        "keyword":    f"/dictionary/{natural_key}",
        "drushtaant": f"/drushtaant/{natural_key}",
        "flowchart":  f"/flowcharts/{natural_key}",
    }[kind]
```

### Frontend types (`ui/lib/spans/types.ts`)

```ts
export type SpanType = 'topic' | 'keyword' | 'drushtaant' | 'flowchart';

export interface Span {
  spanId: string;
  type: SpanType;
  panel: string;
  mongoDocId: string;
  startOffset: number;
  endOffset: number;
  refId: string;
  refLabel: string;
  refUrl: string;
  excerpt: string | null;
  confidence: 'high' | 'medium' | 'low';
}

export interface LayerToggle {
  topic: boolean;
  keyword: boolean;
  drushtaant: boolean;
  flowchart: boolean;
}
```

### Colour palette (`ui/components/ShastraReader/spanColors.ts`)

| Type | Light-mode underline | Light-mode hover bg | Dark-mode underline | Pattern | Min contrast on body text |
|---|---|---|---|---|---|
| topic | `#4F46E5` (indigo-600) | `#EEF2FF` | `#A5B4FC` | solid | 6.1:1 |
| keyword | `#7C3AED` (violet-600) | `#F5F3FF` | `#C4B5FD` | solid | 5.8:1 |
| drushtaant | `#D97706` (amber-600) | `#FFFBEB` | `#FCD34D` | dashed | 4.8:1 |
| flowchart | `#0F766E` (teal-700) | `#F0FDFA` | `#5EEAD4` | dotted | 5.3:1 |

Each underline is rendered as a CSS `text-decoration: underline; text-decoration-color: <colour>; text-decoration-thickness: 2px; text-underline-offset: 3px;` with `text-decoration-style` set per the pattern column above. This gives every type a second visual channel (line style) on top of colour, so a colour-blind user can still tell layers apart at a glance.

A `data-confidence="low"` attribute drops the underline to `1.5px` and lowers opacity to `0.6` so unreviewed-but-approved-low spans read as "tentative".

### Overlap resolution (`ui/components/ShastraReader/spanOverlap.ts`)

Spans of the *same kind* may overlap; spans of *different kinds* commonly overlap (a keyword inside a topic). The renderer cannot nest two `<span>` elements with overlapping but non-nested ranges, so we slice the text into atomic segments and tag each segment with the set of spans active over it.

```ts
export interface Segment {
  start: number;
  end: number;
  text: string;
  spans: Span[];               // spans active across [start, end)
}

export function resolveSegments(text: string, spans: Span[]): Segment[];
```

Algorithm:
1. Collect every `startOffset` and `endOffset` into a sorted, deduped offset list (plus 0 and `text.length`).
2. Between each consecutive offset pair `[a, b)`, emit a `Segment` whose `spans` field is every span whose `[start, end)` covers `[a, b)`.
3. Empty-span segments (no active spans) still emit (plain text).

`<HighlightOverlay>` then renders each segment as either plain `<span>` or `<mark>` with stacked underlines (one `<mark>` per active type, nested deepest-first by type priority `flowchart > drushtaant > keyword > topic`).

This guarantees correct visual output even for nested and partially-overlapping spans, and the click target is whichever `<mark>` the cursor is over (the innermost wins; outer types are still visible by their underlines).

### Component shape (`ui/components/ShastraReader/HighlightOverlay.tsx`)

```tsx
interface HighlightOverlayProps {
  panel: string;                        // 'anvayartha' | 'bhaavarth' | ...
  mongoDocId: string;
  text: string;                         // NFC-normalised panel chunk
  spans: Span[];
  layers: LayerToggle;
  onSpanActivate: (s: Span) => void;    // opens side panel
}

export function HighlightOverlay(props: HighlightOverlayProps): JSX.Element {
  const visibleSpans = useMemo(
    () => props.spans.filter(
      s => s.panel === props.panel
        && s.mongoDocId === props.mongoDocId
        && props.layers[s.type]
    ),
    [props.spans, props.panel, props.mongoDocId, props.layers],
  );
  const segments = useMemo(
    () => resolveSegments(props.text, visibleSpans),
    [props.text, visibleSpans],
  );
  const navRef = useSpanKeyboardNav(visibleSpans, props.onSpanActivate);
  return (
    <span ref={navRef} className="hl-overlay" data-panel={props.panel}>
      {segments.map((seg, i) => renderSegment(seg, i, props.onSpanActivate))}
    </span>
  );
}
```

`renderSegment` wraps each active span in nested `<mark>` tags ordered by type priority, attaches `tabIndex={0}` for keyboard nav on the outermost mark per span, and `aria-label={spanAriaLabel(seg.spans)}`.

### Layer toggle (`HighlightLayerToggle.tsx`)

Rendered in the reader header. Four checkboxes (topic / keyword / drushtaant / flowchart) each with the type's underline preview and a count chip showing the number of currently-visible spans of that type in the unit. State is persisted to user preferences (`user_preferences.ui.highlight_layers`, see spec 01); guests get `localStorage`.

Keyboard shortcut `j` toggles the master overlay on/off (mirrors the existing `<HighlightToggle>` from spec 03). `1`/`2`/`3`/`4` toggle the four layers respectively when the toggle group is focused.

### Tooltip (`SpanTooltip.tsx`)

Radix `<Popover>` opened on hover (300 ms delay) or focus. Content:

```
┌────────────────────────────────────────┐
│  [type chip]   ref_label               │
│  ─────                                 │
│  excerpt (up to 240 chars)             │
│  ─────                                 │
│  ↪ open in side panel  (Enter)         │
└────────────────────────────────────────┘
```

Tooltip is positioned with collision detection; on small screens it auto-flips to a bottom sheet via the existing `useMobileSheet()` hook.

### Side panel activation

`onSpanActivate(s: Span)` is supplied by the reader page and dispatches into the existing right-rail keyword popover stack (spec 03 §RightRail) extended to accept any of the four entity types. The dispatch maps span type → side panel component:

| type | side panel |
|---|---|
| topic | `<TopicSidePanel>` from spec 04 |
| keyword | `<KeywordSidePanel>` from spec 04 |
| drushtaant | `<DrushtaantSidePanel>` from spec 05 |
| flowchart | `<FlowchartSidePanel>` from spec 20 |

### Keyboard navigation (`useSpanKeyboardNav.ts`)

- `Tab` / `Shift+Tab` cycle focus across spans in DOM order within the current panel.
- `Enter` or `Space` on a focused span calls `onSpanActivate`.
- `Esc` closes any open tooltip and returns focus to the span.
- Focus ring is a 2px outline using the type's colour, plus a 1px white inner ring for contrast on coloured backgrounds.
- Visible focus must persist across `mousedown` (we set `:focus-visible` rules only — focus ring shows for keyboard users).

### Data hook (`useSpanFetch.ts`)

```ts
export function useSpanFetch(shastraNk: string, chapterIndex: number,
                             layers: LayerToggle): {
  spans: Span[];
  isLoading: boolean;
  error: Error | null;
} {
  const types = (Object.keys(layers) as SpanType[]).filter(k => layers[k]);
  const { data, error, isLoading } = useSWR(
    types.length > 0
      ? ['spans', shastraNk, chapterIndex, types.sort().join(',')]
      : null,
    () => api.getSpans(shastraNk, chapterIndex, types),
    { revalidateOnFocus: false, dedupingInterval: 120_000 },
  );
  return { spans: data?.spans ?? [], isLoading, error: error ?? null };
}
```

Toggling a layer off does NOT re-fetch — the hook uses the union of toggled-on types as the cache key, so once a user has seen all four layers the underlying fetch is one round-trip. Toggling subsets simply filters client-side.

### Tests (TDD — write these first)

1. `test_spans_endpoint.py::returns_approved_spans_for_chapter` — seed 3 approved + 2 pending spans on samaysaar adhikaar 1; GET returns exactly 3.
2. `test_spans_endpoint.py::types_filter_narrows_result` — `?types=topic` returns only topic kind.
3. `test_spans_endpoint.py::etag_revalidation` — second GET with `If-None-Match` of returned ETag → 304, no body.
4. `test_spans_endpoint.py::private_shastra_blocked_for_guest` — restricted shastra, guest → 403.
5. `test_spans_endpoint.py::min_confidence_filter` — `?min_confidence=high` drops medium/low spans.
6. `spanOverlap.test.ts::no_overlap_yields_one_segment_per_span` — three disjoint spans → 7 segments (4 plain + 3 covered).
7. `spanOverlap.test.ts::nested_spans_render_correctly` — `[topic 0..20]` containing `[keyword 5..10]` → segments `[0..5 topic]`, `[5..10 topic+keyword]`, `[10..20 topic]`.
8. `spanOverlap.test.ts::partial_overlap_same_kind` — `[topic 0..10]` + `[topic 5..15]` → segments `[0..5 t1]`, `[5..10 t1+t2]`, `[10..15 t2]`.
9. `spanOverlap.test.ts::adjacent_spans_do_not_merge` — `[k 0..5]` + `[k 5..10]` → two distinct segments with one span each.
10. `HighlightOverlay.test.tsx::renders_segments_in_order` — given fixture text + 2 spans, output preserves original text via `textContent`.
11. `HighlightOverlay.test.tsx::respects_layer_toggle` — `layers.keyword=false` → no keyword underline in DOM even if span data present.
12. `HighlightOverlay.test.tsx::click_fires_onSpanActivate` — click a `<mark>` → callback called with the inner-most span.
13. `useSpanKeyboardNav.test.ts::tab_cycles_spans` — render 3 spans, simulate Tab × 3 → focus lands on each in DOM order.
14. `useSpanKeyboardNav.test.ts::enter_activates_span` — focus a span, press Enter → `onSpanActivate` called once.
15. `HighlightLayerToggle.test.tsx::number_keys_toggle_layers` — focus toggle group, press `2` → keyword layer flips.
16. `HighlightLayerToggle.test.tsx::counts_reflect_visible_spans` — given 5 topic + 3 keyword spans, chips show "5" and "3".
17. `color_palette_accessibility.test.ts::all_pairs_meet_wcag_aa` — iterate the palette × {light bg, dark bg}; every text/underline pair contrast ≥ 4.5:1 via `wcag-contrast`.
18. `color_palette_accessibility.test.ts::each_type_has_distinct_line_style` — set of `text-decoration-style` values across types has size 4.

### Manual verification

```bash
# 0. Approve at least one span per kind on samaysaar adhikaar 1 (use spec 08 admin review)
psql -c "UPDATE extraction_spans SET status='approved', reviewed_by='dev', reviewed_at=now()
         WHERE gatha_id IN (SELECT id FROM gathas WHERE natural_key LIKE 'samaysaar:0%') LIMIT 20;"

# 1. Hit the endpoint
curl 'http://localhost:8001/v1/shastras/samaysaar/chapters/1/spans?types=topic,keyword' | jq

# 2. ETag revalidation
ETAG=$(curl -sI 'http://localhost:8001/v1/shastras/samaysaar/chapters/1/spans' | awk -F': ' '/^ETag/{print $2}' | tr -d '\r')
curl -i -H "If-None-Match: $ETAG" 'http://localhost:8001/v1/shastras/samaysaar/chapters/1/spans'
# → 304 Not Modified

# 3. UI walk-through
cd ui && npm run dev
open http://localhost:3000/shastra-explorer/samaysaar/adhikaar/1/gatha/001
# - Press 'j' → overlay activates; coloured underlines on bhaavarth + anvayartha.
# - Hover a topic span → tooltip shows ref_label + excerpt.
# - Click the span → topic side panel docks in right rail.
# - Tab → next span gets focus ring; Enter opens its side panel.
# - Toggle off "keyword" in the header — keyword underlines disappear, others remain.
# - Reload → layer toggles persist (logged-in) or via localStorage (guest).

# 4. Accessibility audit
npx playwright test ui/tests/a11y/highlight_overlay.spec.ts
# Uses axe-core; zero violations on the reader page with overlay on.
```

## Definition of done

- [ ] Migration `0029_v_approved_spans.py` applies; the view returns expected rows on the dev DB.
- [ ] `GET /v1/shastras/{nk}/chapters/{n}/spans` returns approved spans, filtered by `types` and `min_confidence`, with ETag-based caching.
- [ ] All 18 tests pass.
- [ ] Overlay renders 200 spans on one unit in ≤ 50 ms (perf mark assertion).
- [ ] All four types visually distinct via colour + line style; WCAG AA contrast in both light and dark themes; axe-core run clean.
- [ ] Tab / Shift+Tab / Enter / Esc all work; focus ring visible only for keyboard users.
- [ ] Layer toggles persist to `user_preferences.ui.highlight_layers` for authed users and `localStorage` for guests.
- [ ] Clicking a span of each kind opens the correct side panel (topic / keyword / drushtaant / flowchart).
- [ ] No regression in `<AnvayarthaPanel>` / `<BhaavarthPanel>` text content (`textContent` invariant test green).

## Implementation notes

_(to be filled in after merge)_
