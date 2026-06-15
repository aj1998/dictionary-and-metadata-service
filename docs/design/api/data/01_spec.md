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
- `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}` — compound-aware gatha fetch (phase 5)
- `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}/adjacent` — prev/next navigation (phase 5)
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


## `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}` — compound-aware gatha route (phase 5)

`raw_id` is the **compact URL form** of the gatha identifier:
- Legacy shastras: plain gatha number, e.g. `8`
- Compound shastras: comma-separated values in declaration order, e.g. `1,2`

The route resolves `raw_id` → full Postgres natural key by looking up `gatha_identifier`
in `shastra.json` and calling `build_compound_suffix`. Returns the same shape as
`GET /v1/gathas/{ident}` plus an `identifier` block:

```json
{
  "natural_key": "परमात्मप्रकाश:अधिकार:1:गाथा:2",
  "gatha_number": "अधिकार:1:गाथा:2",
  "identifier": {
    "fields": [
      { "name": "अधिकार", "label": "अधिकार", "value": "1" },
      { "name": "परमात्मप्रकाशगाथा", "label": "गाथा", "value": "2" }
    ],
    "compact": "1,2",
    "is_compound": true
  },
  ...
}
```

For legacy shastras: `is_compound: false`, `fields` has one entry, `compact` is the gatha number.

**Error codes:**
- `400` — `raw_id` has wrong number of comma-separated values for a compound shastra
- `404` — gatha not found

## `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}/adjacent` — prev/next navigation (phase 5)

Returns the previous and next gathas relative to `raw_id`, sorted **numerically**
(not lexically). Cross-adhikaar navigation is enabled: last gatha in adhikaar 1 →
first gatha in adhikaar 2.

Response shape:
```json
{
  "shastra_nk": "परमात्मप्रकाश",
  "current_nk": "परमात्मप्रकाश:अधिकार:1:गाथा:21",
  "previous": { "natural_key": "...", "compact": "1,10", "gatha_number": "अधिकार:1:गाथा:10" },
  "next":     { "natural_key": "...", "compact": "2,1",  "gatha_number": "अधिकार:2:गाथा:1"  }
}
```

`previous` / `next` are `null` when the gatha is the first / last in the shastra.

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

---

## Compound identifiers — implementation notes & bugfixes

Full wiki: [`docs/design/specs/compound_identifiers/README.md`](../../specs/compound_identifiers/README.md).

### Endpoints

- `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}` — `raw_id` is the compact
  form (`1,001` for compound, bare number for legacy). Resolves to the full
  natural key via `gatha_nk_for_request`. Falls back to numeric-equality
  fuzzy match (`_find_compound_gatha_fuzzy`) so users can type unpadded
  values like `1,9`.
- `GET /v1/shastras/{shastra_nk}/gathas/{raw_id}/adjacent` — returns
  `previous` / `next` siblings, numerically sorted across the compound key.
- Response includes an `identifier` block:
  ```json
  {
    "fields": [
      {"name": "अधिकार", "label": "अधिकार", "value": "1"},
      {"name": "परमात्मप्रकाशगाथा", "label": "गाथा", "value": "001"}
    ],
    "compact": "1,001",
    "is_compound": true
  }
  ```

### Bugfixes

- **`adhikaar` schema ValidationError**
  `services/core_service/domains/data/schemas/gathas.py:_coerce` previously
  assumed `adhikaar` was a `LangText[]`. The phase-3 diversion stores the
  compound `identifier_values` dict in this JSONB column instead. Fix:
  `_coerce` now drops any dict whose keys aren't exactly `{lang, script, text}`
  and unwraps single-item dicts safely.

- **`/adjacent` 500 — TypeError on mixed-type sort**
  `services/core_service/domains/data/services/gathas.py:get_adjacent_gathas`
  computed sort keys as `(int, str)` tuples whenever any identifier value was
  non-numeric or a field was missing. Comparison then crashed with
  `'<' not supported between instances of 'str' and 'int'`. Fix: `_sort_key`
  now returns uniformly numeric tuples, coercing any non-numeric / missing
  value to `float("inf")`.

- **Teeka-panel collapse across adhikaars**
  Symptom: three identical `परमात्मप्रकाश:टीका` tabs, each carrying content
  from gathas 1, 2, 3 of adhikaar 1 piled together. Root cause: `get_detail`
  queried Mongo with `gatha_number="1"` and a regex
  `^परमात्मप्रकाश:अधिकार:1:` — but teeka NKs use the publication NK
  (`परमात्मप्रकाश:टीका:0:…`) which has no adhikaar segment in front, so the
  regex over-matched anything sharing the bare gatha_number across
  publications and adhikaars. Fix: the query is now end-anchored on the
  per-gatha `mongo_seg` (`gatha_teeka_natural_key` matches
  `^{shastra_nk}:.*:{mongo_seg}$`). `mongo_seg` is the compound suffix
  (`अधिकार:1:गाथा:001`) for compound shastras and the zero-stripped bare
  number for legacy.

- **`mongo_seg` derivation in the service layer**
  Computed by walking `gatha.natural_key` and trimming the compound suffix
  whenever `get_identifier_fields(shastra_nk, "gatha")` returns a non-empty
  list. Bare `gatha_number` (zero-stripped) is retained for legacy NK
  construction (e.g. the bhaavarth-shortfont attachment lookup).

- **Fuzzy compound lookup**
  `_find_compound_gatha_fuzzy` (`routers/gathas.py`) re-resolves a missed
  exact NK by comparing `int(identifier_values[f])` across all gathas of the
  shastra. Lets the UI route `1,9` to the row stored as
  `…:अधिकार:1:गाथा:009`.
