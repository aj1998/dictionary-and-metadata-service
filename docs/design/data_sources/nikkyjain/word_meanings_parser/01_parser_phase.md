# Phase 1 — Parser: Extract `shortFont` Glossary + Anchor Offsets

> Prereq: read [`00_overview.md`](00_overview.md) and [`../nj_parser.md`](../nj_parser.md).

## Goal

Augment the bhaavarth parsers — `workers/ingestion/nj/parse_primary_teeka.py`, `parse_secondary_teeka.py`, and the kalash Hindi path — to:

1. Detect `<span class=shortFont>` at the tail of the bhaavarth subtree.
2. Parse its `<sup>N</sup>word= meaning ।` (and bare `<sup>N</sup>explanation`) lines into a structured list.
3. Walk the rest of the bhaavarth subtree and, for every inline `<sup>N</sup>` followed by an anchor token, record `{marker_number, anchor_text, start_offset, end_offset}` against the cleaned text.
4. Strip the inline `<sup>N</sup>` digits from the Markdown that feeds `gatha_teeka_bhaavarth_md` so the user-visible text reads `अब मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।` (instead of `अब ४मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।`).

## Models

Add to `workers/ingestion/nj/models.py`:

```python
class ShortFontEntry(BaseModel):
    marker_number: int                  # 1, 2, 3, ...  (Devanagari digits normalised)
    marker_devanagari: str              # "१", "२", ...  (kept for display)
    anchor_text: str                    # term the marker was attached to in the body
    meaning: str                        # right-hand side of "= " in the shortFont line; or full text for bare lines
    is_definition: bool                 # True if line had `= ` separator; False for narrative footnote
    occurrences: list[ShortFontAnchor]  # zero or more body anchor positions

class ShortFontAnchor(BaseModel):
    start_offset: int   # char index in the cleaned bhaavarth Markdown (post strip)
    end_offset: int     # exclusive
```

Attach to every bhaavarth-carrying model:
- `PrimaryTeeka.gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = []`
- `SecondaryTeeka.gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = []`
- `KalashHindiEntry.shortfont: list[ShortFontEntry] = []`

A shared `_extract_shortfont(node) -> (cleaned_md, entries)` helper is invoked from all three call sites; it is shastra/teeka-agnostic.

## Algorithm

`_extract_shortfont(node) -> tuple[str_md_cleaned, list[ShortFontEntry]]`:

1. **Find the `<span class=shortFont>` element** as a direct child of `steeka0` subtree or its tail siblings. Remove it from the tree before Markdown conversion so it does not leak into the bhaavarth body.
2. **Parse glossary lines**: split the `shortFont` innerText on `<br>` (or on newline after HTML→text). For each line:
   - Strip leading whitespace, BOM, ZWJ.
   - Expect a leading `<sup>N</sup>` (Devanagari digit). Normalise via `unicodedata.numeric` or a small map `{"१":1, "२":2, …, "९":9, "०":0}` and multi-digit support.
   - Split on the first `=` (with any surrounding whitespace). If present → `anchor_text` = LHS, `meaning` = RHS (strip trailing `।`); `is_definition = True`.
   - If no `=` → entire remainder is `meaning`; `anchor_text` = "" initially (filled from body anchor); `is_definition = False`.
3. **Walk the body subtree** that will produce the bhaavarth Markdown. Maintain a running `cleaned_md` cursor. For every `<sup>N</sup>`:
   - Read N. Look ahead to the next text run; the contiguous Devanagari/`-` token immediately following is the `anchor_text` body candidate.
   - Skip the `<sup>` node so the digit does not appear in `cleaned_md`.
   - After the anchor token is appended, record `{start_offset, end_offset}` (offsets relative to the final cleaned Markdown string).
   - Append the anchor to the matching `ShortFontEntry.occurrences`. If the glossary line had no `anchor_text` (bare narrative footnote), backfill it from the body.
4. **Multiple occurrences**: if a marker reappears in the body (rare), append another anchor.
5. **Orphan handling**:
   - Body has `<sup>N</sup>` but no glossary line → warn `shortfont_missing_glossary` and keep the digit stripped (no entry emitted).
   - Glossary has a line but no body `<sup>N</sup>` → emit `ShortFontEntry` with empty `occurrences`. Surface via warning `shortfont_orphan_glossary`.

## Offset correctness

The bhaavarth flows through `html_to_markdown.node_to_markdown`. Offsets must point into the **post-conversion, NFC-normalised** string that ends up in `gatha_teeka_bhaavarth_md`. Recommended path:

- Convert HTML → Markdown first (with `<sup>` nodes removed during conversion, anchors tracked as `(marker_number, anchor_text)` tuples).
- Then run a single deterministic walk: for each `(marker_number, anchor_text)` in source order, do `cleaned_md.index(anchor_text, cursor)` to lock the offset, then advance the cursor past it (same pattern used for `teeka_gatha_mapping.tagged_terms` offsets — see [`../nj_parser.md` § Anyavartha char offsets](../nj_parser.md)).
- This avoids the pitfall of recomputing offsets across an unrelated transform pass.

## Tests (`tests/workers/nj/`)

New file `test_shortfont_parser_unit.py`:

| Case | Expectation |
|---|---|
| 161.html-style fixture with 4 markers, all `=` definitions | 4 entries, each with one anchor; cleaned text has no Devanagari digits adjacent to anchors |
| Bare narrative footnote (`<sup>३</sup>केवली-भगवान को …` with no `=`) | `is_definition = False`, `anchor_text` filled from body |
| Marker repeats twice in body | `occurrences` has length 2 with monotonically increasing offsets |
| Glossary present, body marker missing | warning emitted; entry kept with `occurrences=[]` |
| Body marker present, glossary missing | warning emitted; digit still stripped; no entry |
| Offset round-trip | `cleaned_md[start:end] == anchor_text` for every occurrence |
| `<span class=notes>(…)</span>` parentheticals | untouched in cleaned_md; not treated as glossary |

Add a fixture HTML file under `workers/ingestion/nj/tests/fixtures/shortfont/161_excerpt.html` (trimmed to the steeka0 block of the linked page).

## Verification

```bash
python -m pytest tests/workers/nj/test_shortfont_parser_unit.py -v
# Regenerate goldens for an affected shastra to confirm no regressions:
python -m workers.ingestion.nj.cli parse \
  --config parser_configs/nj/panchaastikaya.yaml --format golden
```

## Done when

- [x] `ShortFontEntry` / `ShortFontAnchor` models added; existing tests pass.
- [x] Primary-teeka parser extracts and strips for the 161.html fixture and 1 secondary-shastra fixture.
- [x] Offset round-trip test green.
- [x] No regressions in `tests/workers/nj/` full suite.
- [ ] Implementation notes appended to this doc and [`../nj_parser.md`](../nj_parser.md) under "Bhaavarth shortFont".

## Implementation Notes

**Implemented:** 2026-06-10

### Files changed

| File | Change |
|---|---|
| `workers/ingestion/nj/models.py` | Added `ShortFontAnchor`, `ShortFontEntry`; added `gatha_teeka_bhaavarth_shortfont` to `PrimaryTeeka` and `SecondaryTeeka`; added `shortfont` to `KalashHindiEntry` |
| `workers/ingestion/nj/shortfont_parser.py` | New — `extract_shortfont(nodes, warnings) -> (cleaned_md, entries)` |
| `workers/ingestion/nj/parse_primary_teeka.py` | Changed bhaavarth collection from `node_to_markdown` loop to `extract_shortfont` |
| `workers/ingestion/nj/parse_secondary_teeka.py` | Same as above |
| `workers/ingestion/nj/tests/fixtures/shortfont/161_excerpt.html` | New fixture file |
| `tests/workers/nj/test_shortfont_parser_unit.py` | 10 new unit tests |

### Design decisions / diversions

- `extract_shortfont` accepts `list[NavigableString | Tag]` (not a single Tag) so both parsers can pass their already-collected bhaavarth node lists directly; this avoids coupling the function to teeka-specific DOM structure.
- Deep-copy is done inside `extract_shortfont` so callers' BS4 trees are never mutated. The slight copy cost is acceptable; bhaavarth nodes are small.
- `<sup>` nodes are decomposed (not just tracked) from the deep-copied tree before `node_to_markdown` is called. No change to `html_to_markdown.py` was needed — sup removal is handled entirely within the shortfont path.
- Cursor advancement after each anchor find is `cursor = end` (past the matched text), using the same pattern as `teeka_gatha_mapping.tagged_terms`.
- `KalashHindiEntry.shortfont` is added per spec but not yet wired to any parsing logic (no kalash bhaavarth parsing exists yet).
- The regex for Devanagari + hyphen tokens uses `[ऀ-ॿ\-]+` which covers all Unicode Devanagari block characters.

### Fixes — 2026-06-10 (post-merge)

**Bug 1 — top-level `<sup>` siblings not stripped/matched.** In panchaastikaya HTML (e.g. `005.html`), the Hindi bhaavarth lives as loose sibling nodes of `div#teeka0` (not wrapped in a content div), so `<sup>` tags are themselves top-level siblings. `extract_shortfont` previously iterated nodes and only called `find_all("sup")` on Tag children, missing top-level sup tags entirely. Also, `copy.deepcopy(n)` per-node detached siblings, so `_get_following_token` (which reads `sup.next_sibling`) returned `""`. Fix: wrap nodes in a single in-memory `<div>` wrapper before deep-copying, then call `find_all("sup")` on the wrapper.

**Bug 2 — asterisk markers (`<sup>*</sup>`) unsupported.** Some bhaavarths (e.g. panchaastikaya `006.html`) use `*` instead of a Devanagari digit. `_dev_to_int` now maps a run of asterisks to a negative int (`*` → -1, `**` → -2, ...) so they get a unique slot without colliding with numeric markers; `_int_to_dev` renders negatives back to the literal asterisks for display.

Regression tests: `test_top_level_sup_siblings_are_stripped_and_matched`, `test_asterisk_marker_round_trip`.
