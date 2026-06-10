# 04 — Keyword Hover / Click Expansion Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/archived/03_shastra_reader.md), section "Keyword expansion (hover / click)".

Inline tagging of any rendered Hindi/Prakrit text token that matches a `Keyword`. Hover → small popover with short definition. Click → docked side-panel with full definition, related topics, "open in Graph", "open in dictionary".

Single phase.

Depends on:
- Runtime keyword matches of the gatha with the Keywords stored in the database (in the inital phases)
- The extraction-pipeline `spans` table from [`08_translation_pipeline_extraction_spec.md`](./08_translation_pipeline_extraction_spec.md). This spec assumes that table exists and exposes per-text spans `{start, end, kind, natural_key, confidence, reviewed}`. [Future]
- The existing `<TaggedTermPopover>` component listed in [`docs/design/14_public_ui.md`](../archived/14_public_ui.md). This spec **extends** that component — does not replace it.
- The `<KeywordSidePanel>` lives inside the reader's `<RightRail>` from [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md).

## Annotated-word contract

Every word returned by data-service that should support hover expansion comes back as `AnnotatedWord`:

```python
# packages/jain_kb_common/contracts/annotated_text.py
class Span(BaseModel):
    start: int                            # char offset into html_text (post-render, NFC)
    end: int                              # exclusive
    kind: Literal["keyword"]
    natural_key: str                      # e.g. "आत्मा"
    confidence: float                     # 0.0–1.0; from extraction pipeline
    reviewed: bool                        # True if admin-approved, False if AI-candidate

class AnnotatedWord(BaseModel):
    html_text: str                        # sanitized HTML (no <script>, no inline event handlers)
    spans: list[Span]                     # sorted by .start ASC
    text_natural_key: str                 # source addressable id (e.g. teeka mapping NK)
```

## Frontend integration

### `<TaggedTermPopover>` (extended)

Existing component is HTML-around-a-word. Extend its props:

```ts
// ui/components/TaggedTermPopover.tsx
type Props = {
  span: Span;
  children: React.ReactNode;        // the highlighted text
  onClick?: (span: Span) => void;   // open side panel
};
```

Behaviour:
- **Hover** (focus, mouseenter, longpress on touch): fetches `/v1/keywords/{nk}/preview` (cached client-side in `react-query`, `staleTime: 5min`) → renders `{title, short_definition, counter}` in a Radix Popover.
- **Click**: invokes `onClick(span)` which sets `selected_span` in `ReaderShellContext`; that opens `<KeywordSidePanel>` in the right rail and pushes the span onto the popover-stack widget.

Color rules (also drive overlay — spec 12):

| Condition | Color | Style |
|---|---|---|
| `kind=keyword`, definition exists, reviewed | indigo-600 | solid underline |
| `kind=keyword`, alias-only, no definition | amber-500 | solid underline |

A `<span class="tt" data-kind="keyword" data-nk="...">` wraps each highlighted run. Styling is CSS-driven; the JS toggles the parent's `data-highlights` attribute (spec 12).

### `<KeywordSidePanel>`

```
ui/app/shastra-explorer/_components/KeywordSidePanel.tsx
```

Renders to the right of `<PanelStack>` (or as a Sheet on mobile). Composition:

```
┌──────────────────────────────────────┐
│ [✕]   आत्मा  [open in graph]          
├──────────────────────────────────────┤
│  उल्लेख: 47 बार समयसार में <- counter chips
├──────────────────────────────────────┤
│  परिभाषा (top 3 blocks from definition)
│  ▸ संदर्भ: धवला...
├──────────────────────────────────────┤
│  संबंधित विषय (chips)
├──────────────────────────────────────┤
│  संबंधित कीवर्ड (graph neighbours)
└──────────────────────────────────────┘
```

Fetches:

1. `GET /v1/keywords/{nk}` — full keyword payload (already exists per [`docs/design/api/data/01_spec.md`](../api/data/01_spec.md)).
2. `GET /v1/keywords/{nk}/counters` — new endpoint, see below.
3. `GET /v1/navigation/keywords/{nk}/neighbours?depth=1` — existing navigation-service endpoint.

## New data-service endpoints

```
GET /v1/texts/{text_natural_key}/annotated
    query: include_candidates: bool = false
    response: AnnotatedWord

GET /v1/keywords/{nk}/preview
    response: { natural_key, display_text, short_definition, counter: {shastra: int, global: int} }

GET /v1/keywords/{nk}/counters
    response: { shastra_breakdown: [{shastra_nk, count}], anuyoga_breakdown: [...], global: int }
```

`short_definition` is the first 2–3 logical lines of `keyword_definitions.page_sections[0].definitions[0].blocks` rendered to plain text with `references` stripped. Cap at 280 characters. For amber (alias-only) keywords, returns `short_definition: null` and the popover displays "परिभाषा अभी संग्रहीत नहीं". Counters served from the materialized counter tables (spec 10).

## Color → CSS mapping (Tailwind)

```ts
// ui/lib/highlight/classes.ts
export const spanClasses = (s: Span, hasDefinition: boolean) => {
  if (!s.reviewed) return "text-slate-500 underline decoration-dashed";
  if (s.kind === "keyword" && hasDefinition) return "text-indigo-700 underline";
  return "text-amber-600 underline"; // keyword, alias-only
};
```

`hasDefinition` arrives on the span by joining against `keywords.definition_doc_ids != []` at API time and surfacing as `span.has_definition: bool` (added to the `Span` model above as a server-set optional field).

## Server-side render

Server Component takes `AnnotatedWord` and emits the HTML by walking spans:

```ts
// ui/lib/highlight/render.tsx (Server Component compatible)
export function renderAnnotated(text: AnnotatedWord): React.ReactNode {
  const out: React.ReactNode[] = [];
  let cursor = 0;
  for (const s of text.spans) {
    if (s.start > cursor) out.push(text.html_text.slice(cursor, s.start));
    const inner = text.html_text.slice(s.start, s.end);
    out.push(
      <TaggedTermPopover span={s}>
        <span className={spanClasses(s, !!s.has_definition)} data-kind={s.kind} data-nk={s.natural_key}>
          {inner}
        </span>
      </TaggedTermPopover>
    );
    cursor = s.end;
  }
  if (cursor < text.html_text.length) out.push(text.html_text.slice(cursor));
  return out;
}
```

`text.html_text` is treated as sanitized text, not raw HTML. Existing markup inside (`<b>`, `<i>`) is unsupported in v1; the extraction pipeline strips it. If markup is reintroduced later, a fragment parser must be added; flagged as TODO.

## Tests (TDD)

1. `tests/api/test_annotated_text.py::test_returns_spans_for_known_text` — seed Mongo teeka mapping + PG spans → `GET /v1/texts/.../annotated` returns both.
2. `test_annotated_text.py::test_filters_unreviewed_by_default` — `reviewed=false` row not in response.
3. `test_annotated_text.py::test_includes_candidates_when_flag_set` — `?include_candidates=1` returns the unreviewed row, `Span.reviewed=False`.
4. `test_annotated_text.py::test_drops_misaligned_spans` — text mutated post-extraction → misaligned span dropped + warning logged.
5. `test_annotated_text.py::test_rejects_overlapping_same_kind_spans` — two keyword spans on same range → 500 in dev, drop + log in prod.
6. `test_keyword_preview.py::test_short_definition_capped_at_280_chars` — long block truncated cleanly.
7. `test_keyword_preview.py::test_alias_only_returns_null_definition` — keyword with no `definition_doc_ids` → `short_definition: null`.
8. `ui/tests/render_annotated.test.tsx::renders_spans_in_order` — `renderAnnotated({html_text:"abc", spans:[{start:1,end:2,...}]})` → `["a", <span>b</span>, "c"]`.
9. `ui/tests/render_annotated.test.tsx::color_classes_match_spec` — for each (kind, reviewed, has_definition) combo, asserts the expected Tailwind class.
10. Playwright `tests/e2e/hover_popover.spec.ts::shows_definition_on_hover` — hover a keyword in samaysaar gatha 1, popover appears with counter chip.
11. Playwright `click_opens_side_panel.spec.ts` — click a keyword span, `<KeywordSidePanel>` becomes visible, breadcrumb intact.
12. Playwright `popover_under_200ms.spec.ts` — measure mouseenter→popover-visible latency at p95 < 200 ms (excludes first fetch).

## Manual verification

```bash
# Seed a known text + spans (uses fixtures from extraction-pipeline spec 08)
python scripts/seed_test_spans.py --gatha samaysaar:001

# Fetch annotated text
curl 'http://localhost:8002/v1/texts/pravachansaar:amritchandra:039/annotated' | jq '.spans | length'

# Open reader, hover a coloured word in the bhaavarth panel
open http://localhost:3000/shastra-explorer/samaysaar/adhikaar/1/gatha/001
```

## Definition of done

- [ ] `AnnotatedWord` model + `Span` model exist in `jain_kb_common/contracts/` and are imported by data-service + ui.
- [ ] `/v1/texts/{nk}/annotated`, `/v1/keywords/{nk}/preview`, `/v1/keywords/{nk}/counters` return correctly.
- [ ] `<TaggedTermPopover>` renders the four color states from the rules table.
- [ ] `<KeywordSidePanel>` opens on click and fetches `/v1/keywords/{nk}` + counters + neighbours.
- [ ] All listed tests pass.
- [ ] Hover popover p95 latency < 200 ms after warm cache.
- [ ] Hover/click works inside the anvayartha and bhaavarth panels of samaysaar gatha 1.

## Implementation notes

_(to be filled in after merge)_
