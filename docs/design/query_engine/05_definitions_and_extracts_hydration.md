# Phase 5 — Shared Hydration Helpers

Tiny phase. Centralizes the "Hindi-only blocks, truncated, in-order"
projection used by Phases 1, 2 and 4 so we don't repeat the logic.

## `hydrate_definitions_hi(keyword_nks: list[str], cap_per_keyword: int = 0) -> dict`

- Single `find({_id: {$in: keyword_nks}})` against `keyword_definitions`.
- For each doc, walk `sections[].definitions[].blocks[]`, keep only
  `block.lang == "hi"`, preserve order.
- Truncate each block's `text` to 1500 chars (suffix `…` if truncated).
- If `cap_per_keyword > 0`, keep only the first N blocks per keyword.
- Return `{ keyword_nk: [ { source_natural_key, block_index, text_hi } ] }`.

## `hydrate_topic_extracts_hi(topic_nks: list[str], block_index_per_topic: dict[str, int] | None = None, cap_per_topic: int = 0) -> dict`

- Single `find({_id: {$in: topic_nks}})` against `topic_extracts`.
- If a `block_index` is given for a topic, slice that block only (matches
  the `block_index`-aware hydration from `12_query_engine.md` Stage 6).
- Otherwise return all `lang == "hi"` blocks, capped.
- Returns `{ topic_nk: [ { block_index, text_hi, references[] } ] }` where
  `references` is the `{shastra, gatha, teeka, page}` shape from
  `00_overview.md`.

## `extract_references(blocks: list[dict]) -> list[dict]`

Pure function. Walks block inline annotations and returns the unique set of
references in document order. Used by chat's guided-filter projection.

## Location

`packages/jain_kb_common/jain_kb_common/hydration/` so all four services can
import.

## Tests

- Hindi-only filtering across mixed-language fixture docs.
- Truncation marker (`…`) appended exactly once.
- `block_index_per_topic` slicing.
- `cap_per_keyword` / `cap_per_topic` honoured.

## DoD

- [ ] Three functions live in `jain_kb_common`.
- [ ] Phases 1, 2, 4 import from here (no duplicated projection code).
- [ ] Unit tests in `tests/hydration/`.

## Implementation Notes (2026-06-21) — block-kind selection fix

The original hydrators kept only blocks whose `kind` was in
`{"hindi_text", "hindi_gatha"}` and read `text_devanagari`. Against the real
`topic_extracts` / `keyword_definitions` data this dropped almost everything:
the scriptural content lives in `prakrit_text` / `sanskrit_text` /
`prakrit_gatha` / `sanskrit_gatha` blocks (the original verse in
`text_devanagari`, its **Hindi meaning** in `hindi_translation`), and the gatha
kinds are `prakrit_gatha` / `sanskrit_gatha` — `hindi_gatha` never appears in
the data. Net effect: topics whose extracts were all verse returned
`extracts_hi: []` even though `extract_count > 0` (e.g. the
`आत्मा:…बहिरात्मादि-3-भेद` topics), so the chat Step2 context showed topic
headings with no extracts.

Fix: a shared helper `jain_kb_common/hydration/blocks.py` now drives both
`hydrate_definitions_hi` and `hydrate_topic_extracts_hi`:

- `EXCLUDED_BLOCK_KINDS = {"see_also", "table"}` — the only kinds with no inline
  text. Every other kind is kept.
- `block_text_hi(block)` emits `hindi_translation` (the Hindi meaning), falling
  back to `text_devanagari` when there is no translation (pure-Hindi blocks and
  any verse lacking a translation). Same 1500-char `…` truncation as before.

So non-Hindi verse now contributes its **Hindi meaning only** (the raw
prakrit/sanskrit verse is not emitted when a translation exists). `block_index`
on topic extracts remains the absolute position in `blocks[]`, so
`block_index`-aware slicing is unchanged.

This is purely additive for consumers (topics_match, graphrag, topic_neighbors,
keyword definitions): previously-empty `extracts_hi` now populate; `hindi_text`
content is unchanged. The public UI is unaffected — it renders raw blocks from
the data-service (`/v1/topics/{nk}`, `/v1/keywords/{nk}`) itself and does not
consume these hydrators (its query-service search calls pass
`include_extracts=false`).

## Implementation Notes (2026-06-21) — per-extract `main_reference`

To let the chat Step2 context attach a reference to **each** extract (instead of
one flattened topic-level ref list merged across blocks),
`hydrate_topic_extracts_hi` now attaches a `main_reference` to every block dict:

```jsonc
{ "block_index": 7, "text_hi": "…", "references": [...],
  "main_reference": { "shastra_name": "मोक्ष पाहुड़", "teeka_name": null,
                      "resolved_fields": [{ "field": "गाथा", "value": 8 }] } }
```

- `main_reference` is `pick_refs_to_show(block.references)[0]` (the first
  non-inline resolved reference — the same "primary" ref the DefinitionModal
  surfaces), or `None` when the block has none. Computed by the new
  `main_reference_for_block(block)` helper in `hydration/topic_extracts.py`.
- It carries the **full** `resolved_fields` plus `shastra_name`/`teeka_name`;
  field filtering (dropping पुस्तक/पृष्ठ/पंक्ति) and shastra-prefix stripping are
  left to the presentation layer (chat), not the hydrator.
- Exposed through the query-service `ExtractBlock` schema (new `MainReference` /
  `ResolvedFieldOut` models) on all three hydration paths: `topics_match`
  (`fetch_topic_extracts_batch`), `graphrag.hydrate_topics`, and
  `topic_neighbors.expand_neighbors`. Additive and optional — existing consumers
  that ignore the field are unaffected; the topic-level flattened `references`
  list is unchanged.

## Implementation Notes (2026-06-21) — displayable extract count

After the block-kind fix above made verse topics hydrate, a regression surfaced
in the UI: `extract_count` (which the `/search` and `/topics` cards use to show
a count badge and gate the "पढ़ें" affordance) still counted **every** raw block
via `$size(blocks)` — including `see_also` / `table` pointers and text-less
blocks. So a container/seed topic whose blocks are all `see_also` pointers
(e.g. `बहिरात्मा, अंतरात्मा व परमात्मा`) advertised `पढ़ें` over an empty modal.

Fix: a shared `count_displayable_extract_blocks(mongo_db, natural_keys)` in
`hydration/topic_extracts.py` counts only blocks that are **not** in
`EXCLUDED_BLOCK_KINDS` **and** carry text (`text_devanagari` or
`hindi_translation`) — i.e. exactly the blocks the modal/hydrator render. Both
consumers now use it:

- query-service `topics_match.count_topic_extract_blocks` delegates to it.
- core-service `/v1/topics` listing router calls it directly (replacing its
  inline `$size` aggregation).

Net effect: pointer-only topics count 0 (no false `पढ़ें`); topics with real
Hindi extracts count their displayable blocks. UI `/search` additionally stops
passing `isLeaf` to `TopicNavAction`, so a non-leaf container that *does* carry
its own extracts opens the `पढ़ें` modal instead of the dictionary link.
