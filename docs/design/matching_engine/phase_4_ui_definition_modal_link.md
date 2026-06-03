# Phase 4 — DefinitionModal: "View in Shastra" link

Depends on [`phase_2_storage_and_cli.md`](phase_2_storage_and_cli.md)
(populates `extract_matches`) and
[`phase_3_ui_gatha_page.md`](phase_3_ui_gatha_page.md) (renders the
highlight when the gatha page is opened with `?match=`).

Wires the matcher's output into the place users discover it: each
block in the `DefinitionModal` (keyword path **and** topic path) gets
a small **"View in Shastra"** CTA that opens the gatha reading page in
a new tab, jumping straight to the highlighted line.

## 1. Data layer

### 1.1 Backend — hydrate matches inline with definitions

To avoid one round-trip per block, extend the data-service responses
that feed the modal:

| Endpoint | Field added |
|---|---|
| `GET /v1/keywords/{nk}` | each `blocks[i]` gets `match_natural_keys: string[]` (0..n) |
| `GET /v1/topics/{nk}` | same |

Hydration logic (server-side): for each block, run a single Mongo
query against `extract_matches` keyed by
`source.parent_natural_key + source.block_index` (+ `section_index` /
`definition_index` for keywords). Return `[]` if no rows.

Owning code paths:
- `services/core_service/data/keywords.py` — extend the keyword
  hydrator.
- `services/core_service/data/topics.py` — extend the topic hydrator.
- Tests: extend `tests/services/data/test_keywords.py` and
  `test_topics.py` with one fixture row in `extract_matches` and
  assert `match_natural_keys` propagates to the response.

### 1.2 UI types

Add to [`ui/src/lib/types.ts`](../../ui/src/lib/types.ts):

```ts
export interface DefinitionBlock {
  // ...existing fields
  match_natural_keys?: string[];   // 0..n
}
```

Apply the same field to `topicExtracts[].blocks[]`.

## 2. UI changes — `DefinitionModal`

File: `ui/src/components/DefinitionModal.tsx`.

For every block that renders (within
`KeywordDefinitionBlocks` and `TopicExtractsSection`), if
`block.match_natural_keys?.length > 0`:

1. Render a small CTA at the bottom-right of the block:

   ```tsx
   <ViewInShastraButton match_natural_keys={block.match_natural_keys} />
   ```

   - Uses `--accent` color; label: **"शास्त्र में देखें"** (hi) /
     **"View in Shastra"** (en).
   - Icon: `ExternalLink` from `lucide-react` (add to
     `src/lib/icons.ts` if absent).

2. If exactly one match: render an `<a target="_blank" rel="noopener
   noreferrer" href={buildGathaHref(match)}>...</a>`.

3. If multiple matches (e.g. block cites two gathas in different
   shastras): render a small popover listing each match with
   `shastra_name + gatha_number` as label; clicking each opens in a
   new tab.

### 2.1 `buildGathaHref`

Pure helper, added to `ui/src/lib/gatha-content.ts` (existing file):

```ts
export function buildGathaHref(match: ExtractMatch): string {
  const shastraNk = match.target.natural_key.split(':')[0];
  const gathaNumber = extractGathaNumberFromTargetNk(match.target.natural_key);
  // /shastras/<shastra-nk>/gathas/<gatha-number>?match=<match.natural_key>
  return `/shastras/${encodeURIComponent(shastraNk)}/gathas/${gathaNumber}` +
         `?match=${encodeURIComponent(match.natural_key)}`;
}
```

Unit-test in `ui/src/__tests__/lib/gatha-content.test.ts` — already
exists; add cases for the new helper.

The `match` object needed to build the href can be fetched lazily on
click via `getExtractMatch(nk)` (added in Phase 3) — keeps the modal
payload small.

### 2.2 Loading + error UX

- Click → button enters a disabled "loading" state while
  `getExtractMatch` resolves; on success, `window.open(href, '_blank',
  'noopener,noreferrer')`.
- On error or `status !== 'matched'`: show a tiny inline error message
  **"शास्त्र में नहीं मिला"** for 2s, then revert.

## 3. Tests

Extend `ui/src/__tests__/components/DefinitionModal.test.ts`:

- New cases for the new pure helpers (`buildGathaHref`,
  `extractGathaNumberFromTargetNk`).
- Selection logic test: given a block with `match_natural_keys: ['a',
  'b']`, the helper returns 2 entries; given `[]`, returns null.

No JSX render tests — consistent with the existing test policy.

## 4. Acceptance / DoD

- [ ] Backend tests pass (`pytest tests/services/data/`).
- [ ] UI tests pass (`pnpm test`) and build succeeds (`pnpm build`).
- [ ] Opening the `DefinitionModal` for a keyword/topic that has
      matches shows the CTA only on matched blocks; unmatched blocks
      look unchanged.
- [ ] Clicking the CTA opens `/shastras/.../gathas/...?match=...` in a
      new tab; the gatha page (Phase 3) scrolls to and highlights the
      matched range.
- [ ] Multi-match path: the popover lists shastra + gatha labels and
      each link works.
- [ ] Failure path: when the matched row vanishes in Mongo (manually
      delete and re-open), the modal CTA shows the inline error and
      does not throw.

## 5. Manual verification

```bash
# Backend up + Phase 2 matcher previously run
cd ui && pnpm dev

# Browse to e.g.:
# http://localhost:3000/dictionary/आत्मा
# → Click "पूरा वर्णन पढ़ें"
# → Inside the modal, locate a block with the new CTA
# → Click "शास्त्र में देखें" → opens new tab → matched line highlighted
```

## 6. Out of scope (defer)

- Backfilling the modal with confidence scores or "approximate match"
  visual treatment for `shingle_fuzzy` results — for v1, fuzzy + above
  threshold renders identically to exact.
- Highlighting multiple ranges per page (e.g. the block matched 2
  different sub-sentences in the same gatha teeka body) — single
  `[start, end]` per match.

## Implementation Notes / Diversions

_To be filled in by the implementing agent._
