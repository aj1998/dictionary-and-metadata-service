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

## `GET /v1/topics` — query params & response shape

Query params:
- `q` (string, optional) — case-insensitive ILIKE over `display_text::text`.
- `parent_keyword_id` (uuid, optional)
- `source` (string, optional) — e.g. `jainkosh`, `nj`, `chat_candidate`.
- `is_leaf` (bool, optional) — restrict to leaf / non-leaf topics.
- `has_topic_path` (bool, optional) — `true` keeps only topics with a non-null `topic_path` (excludes "अन्य विषय" / unordered seeds); `false` returns only the null-path subset. **Used by the UI topics page as the default filter** (combined with `is_leaf=true`) so the listing shows only readable leaf topics; the "मध्यवर्ती विषय भी दिखाएँ" toggle drops both filters.
- `limit` (1–200, default 50), `offset` (default 0).

`TopicSummary` items include:

```json
{
  "id": "uuid",
  "natural_key": "string",
  "display_text": [{"lang": "hin", "script": "Deva", "text": "…"}],
  "source": "jainkosh",
  "is_leaf": true,
  "topic_path": "1.2" ,
  "parent_keyword": {"id": "uuid", "natural_key": "…", "display_text": "…"},
  "extract_count": 4
}
```

- `extract_count` is the total number of `blocks[]` entries across all Mongo `topic_extracts` documents whose `natural_key` matches this topic. Computed in a single batched `$match` + `$size` + `$group` aggregation over the natural_keys returned by the current page (one round-trip per page). The UI topics-page card displays this as the right-side numeric badge.


## `GET /v1/gathas/{ident}?include=kalashas` — GathaKalash shape

When `include=kalashas` is requested, each element of the `kalashas` array has the following shape:

```json
{
  "natural_key": "समयसार:आत्मख्याति:कलश:1",
  "kalash_number": "1",
  "teeka_natural_key": "समयसार:आत्मख्याति",
  "is_secondary": false,
  "prakrit": null,
  "sanskrit": { "natural_key": "...", "text": [...] },
  "hindi":   { "natural_key": "...", "text": [...] },
  "bhaavarth": [],
  "word_meanings": {
    "natural_key": "समयसार:आत्मख्याति:कलश:1:word_meanings",
    "entries": [
      { "source_word": "स्वानुभूत्या चकासते", "meaning": "स्वानुभूति से प्रकाशित,", "position": 1 }
    ]
  }
}
```

**Primary kalashas** (`is_secondary: false`): content fetched from `kalash_sanskrit`, `kalash_hindi`, `kalash_bhaavarth_hindi`, and `kalash_word_meanings` Mongo collections. `prakrit` is always `null`.

**Secondary kalashas** (`is_secondary: true`): These are Jaysenacharya's standalone gatha pages stored as kalashas. Content fetched from `gatha_prakrit` (using `gatha_natural_key`), `gatha_teeka_sanskrit`, and `gatha_teeka_bhaavarth_hindi` Mongo collections. `hindi` and `word_meanings` are always `null`.

Kalashas are returned sorted ascending by `kalash_number` (numeric), then by `teeka.role` for stable ordering. The `is_secondary` flag is derived from `teekas.role` via a JOIN — business logic does not live in the UI.

**UI label convention** (gatha reader "संबंधित" panel):
- Primary: `कलश:{teeka_short}:{N}` e.g. `कलश:आत्मख्याति:1`
- Secondary: `गाथा:{teeka_short}:{N}` e.g. `गाथा:तात्पर्यवृत्ति:11`

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
