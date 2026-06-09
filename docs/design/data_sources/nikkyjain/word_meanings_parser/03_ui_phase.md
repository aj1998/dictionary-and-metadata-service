# Phase 3 — API + UI: Underlined Anchors + Meaning Popover

> Prereq: Phases 1–2 merged. Read [`00_overview.md`](00_overview.md), [`../../../../../ui/README.md`](../../../../../ui/README.md) (esp. §8 BhaavarthPanel, ShabdaArthSection).

## Goal

Surface shortFont entries for **all** bhaavarth sources (primary gatha bhaavarth, secondary gatha bhaavarth, kalash Hindi) — every `BhaavarthPanel` instance plus the kalash Hindi panel inside the संबंधित tabs. Same component, same tokens.

## API (core-service)

The gatha-detail response already hydrates bhaavarth blocks (see `services/core_service/` gatha endpoint). Add per-bhaavarth `shortfont_entries` alongside the existing `text` / `naturalKey`:

```json
{
  "naturalKey": "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161",
  "text": "अब मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है। …",
  "shortfont_entries": [
    {
      "marker_number": 4,
      "marker_devanagari": "४",
      "anchor_text": "मोक्ष-मार्ग-प्रपंच-सूचक",
      "meaning": "मोक्ष का विस्तार बतलाने वाली, …",
      "is_definition": true,
      "occurrences": [{"start_offset": 1284, "end_offset": 1308}]
    }
  ]
}
```

Hydration: fetch from Mongo `gatha_teeka_bhaavarth_shortfont` keyed by `bhaavarth_natural_key` (single `find` per gatha covers all bhaavarths). Reuse the existing `langs/lang_text` plumbing pattern from `kalash_word_meanings`.

Add hydration tests in `tests/services/data/` and a hydration unit test in `tests/common/hydration/`.

## UI types (`ui/src/lib/types.ts`)

```ts
export interface BhaavarthShortFontOccurrence {
  startOffset: number;
  endOffset: number;
}
export interface BhaavarthShortFontEntry {
  markerNumber: number;
  markerDevanagari: string;
  anchorText: string;
  meaning: string;
  isDefinition: boolean;
  occurrences: BhaavarthShortFontOccurrence[];
}
```

Add `shortFontEntries?: BhaavarthShortFontEntry[]` to the existing bhaavarth item type used by the gatha page (and to `GathaKalash` if Phase 0/Q2 extends to kalash).

## Rendering — `ui/src/components/BhaavarthPanel.tsx`

`BhaavarthPanel` already routes text through `parseBhaavarthSegments` → `teekaMarkdownToHtml`. We need to overlay shortFont anchors on top of the resulting HTML without breaking existing chip/highlight logic.

Approach (least-invasive):

1. **Before** `teekaMarkdownToHtml` runs on a prose segment, splice the raw Markdown by `occurrences`. For each occurrence whose `[start,end)` falls inside the current segment's bounds, wrap the slice in a sentinel token like `⟦sf:idx⟧anchor⟦/sf⟧`.
2. After Markdown→HTML, replace the sentinel tokens with the actual React node (since `dangerouslySetInnerHTML` cannot host React, do a `parseHtmlAndInject` pass using `html-react-parser` or a small regex-based splitter — there is already precedent for sentinel rewriting in `ShabdaArthSection`).
3. The React node is a new component `ShortFontAnchor` (below).

Edge case: an occurrence that falls inside a chip block (`ShabdaArthSection` already handles the bracketed terms) should still resolve — chips and shortFont anchors are independent decorations. Validate with a fixture where both coexist.

## New component — `ui/src/components/ShortFontAnchor.tsx`

`'use client'`. Renders:

```tsx
<Popover>
  <PopoverTrigger asChild>
    <button
      type="button"
      className="underline decoration-2 decoration-[var(--shortfont-underline)] underline-offset-4 hover:bg-[var(--shortfont-soft)]"
    >
      {anchorText}
    </button>
  </PopoverTrigger>
  <PopoverContent className="max-w-sm">
    <div className="text-xs text-foreground-muted mb-1">
      टिप्पणी {markerDevanagari}
    </div>
    <div className="font-serif-hindi text-body whitespace-pre-wrap">
      {meaning}
    </div>
  </PopoverContent>
</Popover>
```

Use the existing shadcn `Popover` already in the catalogue. Trigger has `aria-haspopup="dialog"`.

## Tokens (`ui/src/styles/theme.css`)

Add two CSS variables; map via `@theme inline` in `globals.css` if needed:

```css
--shortfont-underline: #B7791F;   /* dark yellow / amber-700 */
--shortfont-soft: #FEF3C7;        /* amber-100 hover wash */
```

(Avoid hardcoding hex in the component — per design-system rule in `ui/README.md` §5.)

## Tests (`ui/`)

- Vitest unit test for the segment-splicing util: given `text` + `occurrences`, returns the correct tokenised string.
- Component test: clicking the underlined anchor opens the popover and renders the meaning.
- Snapshot/integration test for `BhaavarthPanel` with a 4-marker fixture mirroring 161.html.

## Verification (manual)

```bash
cd ui && pnpm dev
# Navigate to /shastras/पञ्चास्तिकाय/gathas/161
# Confirm: "मोक्ष-मार्ग-प्रपंच-सूचक" is underlined dark-yellow,
# click → popover shows "मोक्ष का विस्तार बतलाने वाली …"
# Confirm: no stray Devanagari digits in the bhaavarth body.
```

Also run the **verify** skill on the local app per `ui/AGENTS.md`.

## Done when

- [ ] API hydrates `shortfont_entries` on every gatha bhaavarth that has a Mongo doc.
- [ ] `BhaavarthPanel` underlines anchors and opens the popover on click.
- [ ] Existing chip / highlight logic still works on segments containing anchors.
- [ ] `pnpm build`, `pnpm test` green.
- [ ] Manual reader test on at least 1 page with markers passes.
- [ ] Implementation notes appended here and in [`../../../../../ui/README.md`](../../../../../ui/README.md) §8.
