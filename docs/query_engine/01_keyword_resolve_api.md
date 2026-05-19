# Phase 1 — Batched Keyword Resolve + Nearest Neighbours

Adds a single batched endpoint in `query-service` that the chat service calls
*after* Step1 to validate jain-specific keywords against the dictionary and
fetch nearest-neighbour suggestions for misses.

## Endpoint

`POST /v1/query/keyword_resolve_batch`

### Request

```json
{
  "tokens": ["आत्मा", "आतम", "द्रव्य स्वतंत्रता", "ksudra"],
  "fuzzy_top_k": 5,
  "min_similarity": 0.35,
  "include_definitions": true,
  "definitions_per_keyword": 0,
  "language": "hi"
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `tokens` | yes | — | array of strings, max 32. Already classified as "jain" by chat. |
| `fuzzy_top_k` | no | 5 | top-N neighbour suggestions per *missing* token |
| `min_similarity` | no | 0.35 | trigram cutoff; lower = wider |
| `include_definitions` | no | true | attach Hindi definition blocks for *matched* tokens |
| `definitions_per_keyword` | no | 0 (=all) | cap per keyword if >0 |
| `language` | no | `"hi"` | future-proof; only `hi` supported in v1 |

### Resolution pipeline (per token, reusing `12_query_engine.md` Stage 3)

1. **NFC normalize + ZWJ/ZWNJ strip** (`pipeline/normalize.py`).
2. **Pass 1**: exact match against `keywords.natural_key` OR
   `keyword_aliases.alias_text` (single batched SQL for all tokens).
3. **Pass 2**: suffix-strip on misses, re-lookup.
4. **Pass 3 (fuzzy)**: pg_trgm `similarity()` against
   `keywords.natural_key ∪ keyword_aliases.alias_text`, ORDER BY similarity
   DESC LIMIT `fuzzy_top_k`, WHERE similarity >= `min_similarity`. Only run
   for tokens still unresolved after Pass 2.

The first three passes are **identical** to query-service Stage 3 — share the
implementation in `pipeline/resolve.py`. Add a `fuzzy_suggestions()` helper
that wraps the third pass and is callable independently.

### Response

```json
{
  "resolutions": [
    {
      "input_token": "आत्मा",
      "match_kind": "exact",
      "keyword_natural_key": "आत्मा",
      "keyword_id": "uuid-…",
      "definitions": [
        { "source_natural_key": "आत्मा", "block_index": 0, "text_hi": "…" }
      ]
    },
    {
      "input_token": "आतम",
      "match_kind": "alias",
      "keyword_natural_key": "आत्मा",
      "keyword_id": "uuid-…",
      "definitions": [ … ]
    },
    {
      "input_token": "द्रव्य स्वतंत्रता",
      "match_kind": "suffix_strip",
      "keyword_natural_key": "द्रव्य स्वतंत्र",
      "definitions": [ … ]
    },
    {
      "input_token": "ksudra",
      "match_kind": "none",
      "suggestions": [
        { "keyword_natural_key": "क्षुद्र", "similarity": 0.58 },
        { "keyword_natural_key": "क्षुधा",  "similarity": 0.41 }
      ]
    }
  ],
  "tool_trace_id": "uuid-…"
}
```

Order of `resolutions[]` matches order of `tokens[]` in the request.

`match_kind ∈ { exact, alias, suffix_strip, none }`. Suggestions are only
present when `match_kind = none`.

Hindi definitions: pull from Mongo `keyword_definitions` collection; project
only `blocks[].text` whose `lang = "hi"`, in original block order. Truncate
each block to 1500 chars (reuse the cap from `12_query_engine.md` Stage 6).

## Implementation notes

- Single Postgres roundtrip for Passes 1+2 (UNION over `keywords` and
  `keyword_aliases`).
- Single Postgres roundtrip for Pass 3 (CROSS JOIN LATERAL with `similarity()`
  per unresolved token).
- Single Mongo roundtrip for definitions (`find({_id: {$in: [...]}})`).
- pg_trgm extension must be installed (`CREATE EXTENSION IF NOT EXISTS
  pg_trgm;`) — add an Alembic migration if not present.
- GIN index `keywords_natural_key_trgm_idx ON keywords USING gin (natural_key
  gin_trgm_ops)` and the analogous one on `keyword_aliases.alias_text`.

## Logging

Per request: `len(tokens)`, exact/alias/suffix/fuzzy/none counts, total
roundtrip ms, and per-token `match_kind` at DEBUG level.

## Tests (Phase 1)

- `test_resolve_batch_exact_and_alias.py` — covers passes 1+2 for known
  golden tokens.
- `test_resolve_batch_fuzzy.py` — token typo → expected suggestions in order
  of similarity; cutoff respected.
- `test_resolve_batch_definitions.py` — Hindi-only projection; non-Hindi
  blocks excluded; truncation applied.
- `test_resolve_batch_ordering.py` — response order matches request order;
  duplicates de-duplicated by `input_token`.
- `test_resolve_batch_caps.py` — `tokens` length cap enforced (32);
  `fuzzy_top_k` clamps at 20.

## DoD

- [ ] Endpoint live in query-service.
- [ ] Reuses `pipeline/normalize.py` + `pipeline/resolve.py`.
- [ ] pg_trgm migration committed; indexes created.
- [ ] Tests above pass against testcontainer Postgres + Mongo.
- [ ] Manual test snippet documented in
  `docs/manual_testing/api/query/keyword_resolve_batch.md`.
