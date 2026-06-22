# Phase 4 — Sub-workflow Endpoints

Backs the three chat sub-workflows (`direct_retrieval`,
`search_shastra_for_topics`, `search_topic_in_shastra`). Reuses existing
endpoints where possible; adds two new query-service endpoints.

## 4A. `direct_retrieval` — backed by existing `data-service`

Use cases:
- *"समयसार की 6th गाथा बताओ"*
- *"समयसार की 6th गाथा की संस्कृत समझाओ"*

**Reuse**: `GET /v1/gathas?shastra={nk}&number={n}` already exists
(`services/data_service/routers/gathas.py`). Verify the response includes:

```json
{
  "shastra_natural_key": "samaysaar",
  "number": 6,
  "prakrit": "…",
  "sanskrit_chhaya": "…",
  "hindi_anyavaarth": "…",
  "bhavarth_hi": "…",
  "teeka_blocks_hi": [ { "teeka_natural_key": "…", "text_hi": "…" } ],
  "page_numbers": [42, 43]
}
```

If any of `sanskrit_chhaya`, `hindi_anyavaarth`, `bhavarth_hi`,
`teeka_blocks_hi` are missing, extend the existing `GathaDetail` schema. No
new endpoint; just a schema audit + extension.

**Spec deliverable**: an audit doc listing which fields exist today and which
are missing, plus a migration/projection PR.

---

## 4B. `POST /v1/query/topics_in_shastra` — NEW

Use case: *"समयसार की 6th गाथा में किन किन विषयों का वर्णन आया है"* and the
broader *"समयसार में किन किन विषयों का वर्णन है"*.

### Request

```json
{
  "shastra_natural_key": "samaysaar",
  "gatha_number": 6,
  "limit": 25,
  "include_extracts": false
}
```

`gatha_number` is optional. When absent, returns top topics across the whole
shastra (ranked by mention count).

### Implementation (Cypher)

Per-gatha:
```cypher
MATCH (s:Shastra {natural_key: $s})<-[:IN_SHASTRA]-(g:Gatha {number: $n})
MATCH (g)-[:MENTIONS_TOPIC]->(t:Topic)
RETURN t, count(*) AS mention_count
ORDER BY mention_count DESC, t.natural_key
LIMIT $limit
```

Whole-shastra: drop the `{number: $n}` constraint, `MATCH (g:Gatha)` only.

### Response

```json
{
  "topics": [
    {
      "topic_natural_key": "द्रव्य/स्वतंत्रता",
      "display_text_hi": "स्वतंत्रता",
      "ancestors_hi": ["द्रव्य"],
      "is_leaf": true,
      "mention_count": 3
    }
  ],
  "tool_trace_id": "uuid-…"
}
```

---

## 4C. `POST /v1/query/shastras_for_topic` — NEW

Use case: *"द्रव्य की स्वतंत्रता का वर्णन कोन कोन से शास्त्रों और गाथाओं
में आया है?"*

### Request

```json
{
  "topic_natural_key": "द्रव्य/स्वतंत्रता",
  "include_gathas": true,
  "limit_shastras": 10,
  "limit_gathas_per_shastra": 10
}
```

Alternative input: instead of `topic_natural_key`, accept `keywords[]` and
internally run Phase 2's `topics_match` first, take top 1, then proceed.

### Implementation (Cypher)

```cypher
MATCH (t:Topic {natural_key: $t})<-[:MENTIONS_TOPIC]-(g:Gatha)-[:IN_SHASTRA]->(s:Shastra)
WITH s, collect({number: g.number, gatha_nk: g.natural_key, page: g.page_number}) AS gathas, count(g) AS c
ORDER BY c DESC
LIMIT $limit_shastras
RETURN s, gathas[0..$limit_gathas_per_shastra] AS gathas, c
```

### Response

```json
{
  "topic_natural_key": "द्रव्य/स्वतंत्रता",
  "shastras": [
    {
      "shastra_natural_key": "samaysaar",
      "name_hi": "समयसार",
      "total_mentions": 5,
      "gathas": [
        { "number": 6,  "page_number": 42 },
        { "number": 49, "page_number": 110 }
      ]
    }
  ],
  "tool_trace_id": "uuid-…"
}
```

---

## Tests (Phase 4)

- `test_gatha_detail_shape.py` — confirms all `direct_retrieval` fields
  present for a golden gatha; backfill any missing.
- `test_topics_in_shastra_with_gatha.py` — per-gatha mentions sorted
  correctly.
- `test_topics_in_shastra_whole.py` — shastra-wide rollup.
- `test_shastras_for_topic.py` — gatha buckets capped per shastra.

## DoD

- [ ] GathaDetail schema audited / extended.
- [ ] Two new query-service endpoints + OpenAPI.
- [ ] Cypher queries indexed-safe (verified via `EXPLAIN` on testcontainer).
- [ ] Manual test commands documented.

---

## Implementation Notes (2026-06-22) — live-bug fixes

Three live-data bugs were found that made the chat sub-workflows return empty
results; all fixed:

1. **`topics_in_shastra` per-gatha always empty.** `_TOPICS_IN_GATHA_CYPHER`
   matched `(g:Gatha {number: $gatha_n})` with an integer, but the Neo4j node
   has **no `number` property** — the real one is `gatha_number`, stored as a
   **string** (`"15"`). Fixed in
   `services/query_service/pipeline/subworkflow.py`: property → `gatha_number`,
   and `fetch_topics_in_shastra` now coerces the int to `str(gatha_number)`.
   The whole-shastra path was unaffected (it doesn't filter by number).

2. **`shastras_for_topic` referenced non-existent props.**
   `_SHASTRAS_FOR_TOPIC_CYPHER` used `g.number` (→ `g.gatha_number`),
   `g.page_number` (does not exist → dropped), and `s.name_hi` (→ `s.title_hi`,
   aliased back to `name_hi` in `RETURN` to keep the response schema).

3. **`direct_retrieval` had no `(shastra, integer)` → gatha-content endpoint.**
   The chat client previously hit `GET /v1/gathas?shastra=&number=`, whose
   params are ignored by the list endpoint. Instead of a query-service endpoint,
   a **core-service** route was added where gatha content + identifier helpers
   already live:

   `GET /v1/shastras/{shastra_nk}/gathas/by-number/{number}` (in
   `services/core_service/domains/data/routers/gathas.py`). It resolves a plain
   integer to a Gatha, **compound-aware**: single-identifier shastras →
   `{nk}:गाथा:{n}`; compound shastras → scan and numeric-match the verse-number
   component. That component is chosen via
   `jain_kb_common.shastra_identifiers.gatha_component_field()`, which matches a
   field's canonical segment name against `GATHA_ENTITY_KEYWORDS`
   (गाथा/श्लोक/सूत्र/दोहक/वार्तिक — mirrors `reference.entity_keywords.gatha` in
   `parser_configs/jainkosh.yaml`), sourced from
   `parser_configs/_manual_configs/shastra.json`. Verified live for समयसार
   (गाथा), परमात्मप्रकाश (अधिकार+गाथा) and तत्त्वार्थसूत्र (अध्याय+सूत्र).

   The chat client (`cataloguesearch-chat/service/src/kb_api/client.js`,
   `gathaDetail`) calls this route and flattens the nested detail into the
   `want`-projectable fields (prakrit, sanskrit, anyavaarth, bhaavarth, teeka).

Tests added: `tests/services/query/test_subworkflow_cypher.py` (Cypher prop +
param-type regression) and `gatha_component_field` cases in
`tests/jain_kb_common/test_shastra_identifiers.py`.

**Follow-up — per-chapter disambiguation.** Compound shastras number verses
per-chapter (e.g. तत्त्वार्थसूत्र has a सूत्र 10 in every अध्याय), so an integer
alone is ambiguous. `GET /v1/shastras/{nk}/gathas/by-number/{n}` now accepts an
optional `?adhikaar={a}` query param; when present, the resolver additionally
matches the leading section field (अधिकार/अध्याय) so "अध्याय 6 सूत्र 10" maps to
`तत्त्वार्थसूत्र:अध्याय:6:सूत्र:10`. The chat side carries this as a new
`adhikaar_number` field on the `direct_retrieval` sub-workflow (Step1 schema +
prompt), and the Step2 synthesis prompt now treats the
`### KB Sub-workflow Results` block as authoritative canonical text.
