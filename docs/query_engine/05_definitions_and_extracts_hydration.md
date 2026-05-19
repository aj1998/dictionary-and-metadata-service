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
