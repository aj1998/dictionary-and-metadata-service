# Phase 3 — UI Gatha Reading Page: Sanskrit Teeka + Bhaavarth split + Highlight

Depends on [`phase_2_storage_and_cli.md`](phase_2_storage_and_cli.md)
(needs the `extract_matches` collection populated for highlights, but
the layout changes can land first and degrade gracefully when no
match is present).

Targets the page at `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`
(see [`ui/README.md` §12](../../ui/README.md#12-content-pages)).

## Goals

1. **Add a Sanskrit teeka window** — currently the page renders Prakrit
   gatha, Sanskrit chhaya, Hindi harigeet, and Hindi teeka. There is no
   section for `gatha_teeka_sanskrit`.
2. **Split current "teeka" window** — move the **Hindi bhaavarth**
   (`gatha_teeka_bhaavarth_hindi`) into its **own window/section**,
   separate from the Hindi anvayartha (`teeka_gatha_mapping.anvayartha`).
3. **Add kalash sections** — Sanskrit + Hindi + Bhaavarth, when a kalash
   is associated with the gatha page (via `kalashas.gatha_id` FK).
4. **Highlight matched range** — when the URL contains
   `?match=<extract_match natural_key>` (or `?match=<base64-of-it>`),
   fetch the match row, locate the corresponding window by
   `target.collection`, and highlight the substring at
   `[char_start, char_end]` of the rendered text.

## 1. Data layer additions

### 1.1 New backend endpoints / fields

The `getGatha` data-service call currently returns Prakrit, Sanskrit,
harigeet, and teeka mapping. Extend the response to also include:

| Field | Source collection | Spec |
|---|---|---|
| `sanskritTeekas[]` | `gatha_teeka_sanskrit` | per (gatha, teeka) |
| `hindiBhaavarths[]` | `gatha_teeka_bhaavarth_hindi` | per (gatha, teeka, publication) |
| `kalashes[]` | `kalashas` joined with `kalash_sanskrit` / `kalash_hindi` / `kalash_bhaavarth_hindi` | only kalashes with `gatha_id == this gatha.id` |

Each item carries: `natural_key`, `text` (string, NFC-normalized; the
exact same string the matcher used), and a label
(`teekakar_name` / `publication_name`).

Owning code path: `services/core_service/data/gathas.py` — extend
`GET /v1/gathas/{nk}`. Add a new test under
`tests/services/data/test_gathas_sanskrit_teeka.py`.

### 1.2 New backend endpoint — `GET /v1/extract-matches/{natural_key}`

Returns the `extract_matches` row by `natural_key`. Used by the gatha
page to fetch highlight coordinates without round-tripping through the
matcher.

```json
{
  "natural_key": "...",
  "target": { "collection": "...", "natural_key": "...", "lang": "..." },
  "match": { "status": "matched", "char_start": 1842, "char_end": 1891 }
}
```

Owning code path: `services/core_service/data/extract_matches.py`
(new file). Test: `tests/services/data/test_extract_matches.py`.

### 1.3 New UI types

In `ui/src/lib/types.ts`:

```ts
export type ExtractMatchTargetCollection =
  | 'gatha_prakrit' | 'gatha_sanskrit'
  | 'gatha_teeka_sanskrit' | 'gatha_teeka_bhaavarth_hindi'
  | 'kalash_sanskrit' | 'kalash_hindi' | 'kalash_bhaavarth_hindi';

export interface ExtractMatch {
  natural_key: string;
  target: {
    collection: ExtractMatchTargetCollection;
    natural_key: string;
    lang: 'pra' | 'san' | 'hin';
  };
  match: {
    status: 'matched' | 'unmatched' | 'target_missing';
    char_start: number | null;
    char_end: number | null;
  };
}
```

New API client: `ui/src/lib/api/data.ts` → `getExtractMatch(naturalKey)`.

## 2. Page restructure

File: `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`.

Current sections (from [`ui/README.md`](../../ui/README.md)):
1. Prakrit gatha
2. Sanskrit chhaya
3. Hindi harigeet/chhand
4. Hindi teeka (combined anvayartha + bhaavarth — current)

Target sections (top-to-bottom on the reader column; Shell C):
1. **प्राकृत गाथा** — `gatha_prakrit.text[0].text`
2. **संस्कृत छाया** — `gatha_sanskrit.text[0].text`
3. **हिन्दी हरिगीत** — each `gatha_hindi_chhand` doc (existing)
4. **शब्दार्थ** — `gatha_word_meanings` (existing)
5. **संस्कृत टीका** _(NEW)_ — for each `sanskritTeekas[i]`, render in
   its own block. Use `GathaPanel lang="sanskrit"` styling.
6. **हिन्दी टीका** — `teeka_gatha_mapping.anvayartha` (existing, but
   trimmed: bhaavarth now lives below).
7. **हिन्दी भावार्थ** _(NEW window)_ — for each `hindiBhaavarths[i]`,
   render in a new section with its own heading and publication label.
8. **कलश** _(NEW, repeating)_ — per kalash on this gatha page:
   - **कलश संस्कृत** — `kalash_sanskrit`
   - **कलश हिन्दी** — `kalash_hindi`
   - **कलश भावार्थ** — `kalash_bhaavarth_hindi`

Each section is its own card with a `data-match-target="<natural_key>"`
attribute on the card root so the highlight effect (below) can target it.

### 2.1 Component changes

- Reuse [`GathaPanel`](../../ui/src/components/GathaPanel.tsx) for new
  Sanskrit teeka section (`lang="sanskrit"`).
- New component `BhaavarthPanel.tsx` (mirrors `GathaPanel` but neutral
  left border) — used for the bhaavarth window and kalash bhaavarth.
- Kalash sections wrap the existing panels with a kalash-tinted card
  header using `--cat-kalash`.

## 3. Highlight rendering

Behavior: when the URL has `?match=<natural_key>`:

1. On the **server** (page component), call `getExtractMatch(nk)`.
2. Find the section whose
   `data-match-target === match.target.natural_key`.
3. Pass `{ start, end }` into that section as a prop; the panel splits
   the rendered text into `[before][mark][after]`. Use a `<mark>` with
   class `bg-[var(--accent-soft)] text-[var(--accent)] rounded`.
4. Add a small client component `HighlightScrollIntoView.tsx` that
   runs on mount and scrolls `data-match-target="..."` into view with
   `behavior: 'smooth', block: 'center'`.
5. Use NFC-normalize the panel input once at the boundary
   (`normalizeNFC` from
   [`lib/format/devanagari.ts`](../../ui/src/lib/format/devanagari.ts))
   so offsets stay aligned with the matcher's writes.

Edge cases:
- If `match.status !== 'matched'` → render normally, no highlight,
  no scroll.
- If `char_end > text.length` → log a console warning and skip
  highlight (do not throw); UI must remain functional.

## 4. Tests

Pure-logic vitest tests under `ui/src/__tests__/`:

| File | Asserts |
|---|---|
| `lib/api/data.extractMatches.test.ts` | `getExtractMatch` URL & error pass-through |
| `components/BhaavarthPanel.test.ts` | Renders with no highlight props; renders `<mark>` when `highlight` is given; null-safe when offsets are out of range |
| `lib/highlight.test.ts` | Pure helper that splits text by `(start, end)` — boundary cases (0 / len / overlapping) |

No JSX mount tests (consistent with existing UI testing style).

## 5. Acceptance / DoD

- [ ] `pnpm test` green; `pnpm build` green.
- [ ] Gatha page renders all 8 sections for a shastra with full data
      (samaysar gatha 1 — has Prakrit, Sanskrit, harigeet, teeka,
      bhaavarth, and at least 1 kalash).
- [ ] Loading the page with `?match=<known-nk>` highlights the target
      span and scrolls it into view.
- [ ] Loading without `?match` renders normally (no regressions).
- [ ] Backend `GET /v1/extract-matches/{nk}` returns 404 cleanly when
      the row does not exist; client surfaces `ApiError`.

## 6. Manual verification

```bash
# Backend (assumes Phase 2 already populated the collection)
curl http://localhost:8001/v1/extract-matches/<nk> | jq

# UI
cd ui && pnpm dev
# Open: http://localhost:3000/shastras/samaysar/gathas/1
# Open with highlight:
# http://localhost:3000/shastras/samaysar/gathas/1?match=<extract-match-nk>
```

Manually verify:
1. New Sanskrit teeka window appears below harigeet, above Hindi teeka.
2. Hindi bhaavarth is in its own window below Hindi teeka.
3. Kalash sections appear at the bottom when a kalash belongs to the
   page.
4. With `?match=...`, the matched span is wrapped in a red-soft `<mark>`
   and centered in the viewport.

## Implementation Notes / Diversions

_To be filled in by the implementing agent._
