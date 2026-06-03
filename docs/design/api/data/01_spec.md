# Data API Spec (Core Service)

> This domain is now served by [`core-service`](../../archived/refactoring/01_merge_metadata_data_navigation.md) from `services/core_service/`.
> Legacy pre-merge spec is archived at [archived/01_spec.md](./archived/01_spec.md).

## Runtime
- Service: `core-service`
- Module path: `services/core_service/`
- Port: `8001`
- Base path: `/v1`

## Data routes
- `GET /v1/keywords`
- `GET /v1/keywords/letters`
- `GET /v1/keywords/{ident}`
- `PATCH /v1/admin/keywords/{ident}`
- `GET /v1/topics`
- `GET /v1/topics/{ident}`
- `GET /v1/gathas`
- `GET /v1/gathas/{ident}`
- `GET /v1/kalashas`
- `GET /v1/kalashas/{ident}`
- `GET /v1/browse/letters`
- `GET /v1/browse/{entity}`
- `GET /v1/search`
- `GET /v1/stats`
- `GET /v1/extract-matches/{natural_key}`

## Notes
- Most endpoint contracts are unchanged from the archived spec.
- Module/layout moved from `services/data_service/` to `services/core_service/domains/data/`.

## Matching Engine Additions

The matching engine now extends the Data domain in two places.

### 1. Block payload hydration

When the service returns:

- `GET /v1/keywords/{ident}`
- `GET /v1/topics/{ident}`

their embedded definition/extract blocks may include:

```json
{
  "match_natural_keys": [
    "match:keyword_definition:...:target:..."
  ]
}
```

Semantics:

- the array is block-level, not reference-level
- values are foreign keys into Mongo `extract_matches`
- `matched`, `unmatched`, and `target_missing` rows are all included
- the UI uses these keys to decide whether to render a deep-link into the reading view

Hydration is implemented in:

- `services/core_service/domains/data/services/keywords.py`
- `services/core_service/domains/data/services/topics.py`

### 2. Extract-match lookup

`GET /v1/extract-matches/{natural_key}` returns a single stored extract-match document.

Current response shape:

```json
{
  "natural_key": "match:keyword_definition:atma:s0:d0:b0:target:samaysar:गाथा:1:prakrit",
  "source": {
    "kind": "keyword_definition",
    "parent_natural_key": "atma",
    "section_index": 0,
    "definition_index": 0,
    "block_index": 0,
    "block_kind": "prakrit_gatha",
    "text_devanagari": "जे णेव हि संजाया",
    "reference_text": "समयसार गाथा 1"
  },
  "target": {
    "collection": "gatha_prakrit",
    "natural_key": "samaysar:गाथा:1:prakrit",
    "stub_label": "Gatha",
    "shastra_natural_key": "samaysar",
    "gatha_natural_key": "samaysar:गाथा:1",
    "lang": "pra"
  },
  "match": {
    "status": "matched",
    "method": "exact_normalized",
    "score": 1.0,
    "char_start": 0,
    "char_end": 16,
    "threshold": 0.9
  },
  "matcher_version": "1.0.0",
  "ingestion_run_id": "..."
}
```

Status meanings:

- `matched`: offsets are valid and the UI may highlight
- `unmatched`: target exists, but the matcher did not clear threshold
- `target_missing`: Neo4j target resolved, but the routed Mongo target doc was missing

UI usage:

- `DefinitionModal` fetches these docs to render "View in Shastra" links
- the reading page consumes the same doc via `?match=<natural_key>` and highlights only for `matched`
