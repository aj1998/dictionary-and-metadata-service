# Manual Verification Checklist — Phase 1: `keyword_resolve_batch`

## Prerequisites

1. Start query-service:
   ```bash
   DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
   ADMIN_USER=admin ADMIN_PASSWORD=secret \
   python -m uvicorn services.query_service.main:app --port 8004 --reload
   ```

2. Verify service is up:
   ```bash
   curl http://localhost:8004/healthz
   # Expected: {"status":"ok"}
   ```

---

## Test cases

### 1. Health check
```bash
curl -s http://localhost:8004/healthz | python3 -m json.tool
```
Expected: `{"status": "ok"}`

---

### 2. Exact match
Requires a keyword `आत्मा` to exist in the `keywords` table.

```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा"], "include_definitions": false}' \
  | python3 -m json.tool
```

Expected:
```json
{
  "resolutions": [
    {
      "input_token": "आत्मा",
      "match_kind": "exact",
      "keyword_natural_key": "आत्मा",
      "keyword_id": "<uuid>",
      "definitions": null,
      "suggestions": null
    }
  ],
  "tool_trace_id": "<uuid>"
}
```

---

### 3. Alias match
Requires alias `आतम` → `आत्मा` to exist in `keyword_aliases`.

```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आतम"], "include_definitions": false}' \
  | python3 -m json.tool
```

Expected: `match_kind: "alias"`, `keyword_natural_key: "आत्मा"`

---

### 4. Suffix-strip match
Requires keyword `द्रव्य` to exist (token `द्रव्यों` should strip to `द्रव्य`).

```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["द्रव्यों"], "include_definitions": false}' \
  | python3 -m json.tool
```

Expected: `match_kind: "suffix_strip"`, `keyword_natural_key: "द्रव्य"`

---

### 5. Fuzzy match (no-match with suggestions)
Token with a typo that doesn't match anything exactly but is similar to an existing keyword.

```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["कर्मा"], "fuzzy_top_k": 3, "min_similarity": 0.2, "include_definitions": false}' \
  | python3 -m json.tool
```

Expected: `match_kind: "none"`, `suggestions` is a list of objects with `keyword_natural_key` and `similarity` fields, ordered by similarity desc.

---

### 6. Batched request — mixed kinds
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["आत्मा", "आतम", "द्रव्यों", "xyzunknown123"],
    "fuzzy_top_k": 3,
    "include_definitions": false
  }' | python3 -m json.tool
```

Expected: 4 resolutions in order: exact, alias, suffix_strip, none

---

### 7. With definitions
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा"], "include_definitions": true, "definitions_per_keyword": 2}' \
  | python3 -m json.tool
```

Expected: `definitions` is a list (may be empty if no Mongo doc exists). If populated:
- Each item has `source_natural_key`, `block_index`, `text_hi`
- `text_hi` is Hindi text (Devanagari), max 1500 chars
- No Sanskrit or English blocks in the list

---

### 8. Token cap enforcement
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z","aa","bb","cc","dd","ee","ff","gg"]}' \
  | python3 -m json.tool
```

Expected: HTTP 422 with `{"detail": {"code": "tokens_too_many", "message": "Max 32 tokens"}}`

---

### 9. Response order matches request order
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["xyzunknown1", "आत्मा", "xyzunknown2"], "include_definitions": false}' \
  | python3 -m json.tool
```

Expected: resolutions[0].input_token = "xyzunknown1", resolutions[1].input_token = "आत्मा", resolutions[2].input_token = "xyzunknown2"

---

### 10. Deduplication
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा", "आत्मा", "आत्मा"], "include_definitions": false}' \
  | python3 -m json.tool
```

Expected: `resolutions` has exactly 1 item (deduplicated by input_token)

---

## Running automated tests

```bash
# From repo root
python -m pytest services/query_service/tests/ -v

# Expected: 21 passed (Phase 1)
```

## Applying migration (against real DB)

```bash
alembic upgrade 0015
```

Verify index was created:
```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'keywords' AND indexname = 'keywords_natural_key_trgm_idx';
```

---

# Manual Verification Checklist — Phase 2: `topics_match` + `graphrag`

## Prerequisites

1. Start query-service with Neo4j config:
   ```bash
   DATABASE_URL="postgresql+asyncpg://..." \
   MONGO_URL="mongodb://localhost:27017" \
   NEO4J_URL="bolt://localhost:7687" \
   NEO4J_USER=neo4j NEO4J_PASSWORD=<password> \
   NEO4J_DATABASE=neo4j \
   ADMIN_USER=admin ADMIN_PASSWORD=secret \
   python -m uvicorn services.query_service.main:app --port 8004 --reload
   ```

2. Apply migration:
   ```bash
   alembic upgrade 0016
   ```

3. Verify topics trigram index exists:
   ```sql
   SELECT indexname, indexdef FROM pg_indexes
   WHERE tablename = 'topics' AND indexname = 'topics_natural_key_trgm_idx';
   ```

---

## `POST /v1/query/topics_match` — Test Cases

### A. Phrase search (parent-aware)
Requires at least one topic with `natural_key` containing `द्रव्य` (e.g. `द्रव्य/स्वतंत्रता/लक्षण`).

```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "द्रव्य स्वतंत्रता",
    "limit": 5,
    "include_extracts": false,
    "include_references": false
  }' | python3 -m json.tool
```

Expected:
- `matches` is an array sorted by `score` DESC
- Topics whose `natural_key` contains `द्रव्य` or `स्वतंत्रता` appear
- Each match has `ancestors_hi` (path segments minus leaf), e.g. `["द्रव्य"]`
- Each match has `similarity` and `score` fields; `score = similarity * 0.6` for containers, `score = similarity` for leaves
- `tool_trace_id` present

---

### B. Keywords array input
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["द्रव्य", "गुण", "पर्याय"], "include_extracts": false}' \
  | python3 -m json.tool
```

Expected: identical behavior to phrase `"द्रव्य गुण पर्याय"`

---

### C. leaf_only filter
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{"phrase": "द्रव्य", "leaf_only": true, "include_extracts": false}' \
  | python3 -m json.tool
```

Expected: all returned matches have `"is_leaf": true`

---

### D. With extracts (Hindi only)
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "द्रव्य",
    "include_extracts": true,
    "include_references": true,
    "limit": 3
  }' | python3 -m json.tool
```

Expected:
- `extracts_hi` is a list of `{block_index, text_hi}` objects; all text is Devanagari
- No Sanskrit or Prakrit text in `text_hi` fields
- `references` is a list (may be empty) of `{shastra_natural_key, gatha_number, teeka_natural_key, page_number}` objects

---

### E. Missing input validation
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}' | python3 -m json.tool
```

Expected: HTTP 422

---

## `POST /v1/query/graphrag` — Test Cases

### F. Basic GraphRAG call
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["द्रव्य", "स्वतंत्रता"],
    "max_hops": 2,
    "limit": 5,
    "include_extracts": false,
    "include_neighbors": false,
    "include_references": false
  }' | python3 -m json.tool
```

Expected:
- `ranked_topics` is sorted by `score` DESC
- `unresolved_tokens` contains any tokens that had no keyword match
- Each topic has `ancestors_hi`, `matched_seed_keywords`, `overlap_count`, `score`
- `tool_trace_id` present

---

### G. Unknown tokens → unresolved
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["xyznonexistent123"], "include_extracts": false, "include_neighbors": false}' \
  | python3 -m json.tool
```

Expected: `ranked_topics: []`, `unresolved_tokens: ["xyznonexistent123"]`

---

### H. With neighbors
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["आत्मा"],
    "include_extracts": false,
    "include_neighbors": true,
    "include_references": false
  }' | python3 -m json.tool
```

Expected: each topic in `ranked_topics` has `neighbors` with keys `related_topics`, `mentioned_in_gathas`, `related_keywords`. Values may be empty arrays if no neighbors in Neo4j.

---

### I. Fuzzy mode
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आतम"], "fuzzy": true, "include_extracts": false, "include_neighbors": false}' \
  | python3 -m json.tool
```

Expected: `आतम` → resolves via fuzzy to `आत्मा` (or similar) → traversal runs → topics returned. Without `"fuzzy": true`, `आतम` goes to `unresolved_tokens`.

---

## Running all automated tests

```bash
python -m pytest services/query_service/tests/ -v
# Expected: 40 passed
```

## UI Verification

1. Start backend services + UI: `cd ui && pnpm dev`
2. Open `http://localhost:3000/topics`
3. Without search: paginated listing from data-service (exact behavior unchanged)
4. Search for `द्रव्य स्वतंत्रता` in the search box → click "लागू करें"
5. Verify:
   - Results show cards with breadcrumb ancestors (e.g. `द्रव्य › स्वतंत्रता › `)
   - Match percentage shown (e.g. `71% मिलान`)
   - Topics not found by exact match but similar via trigram now appear
   - "विषय खोलें →" links work

## Applying migrations

```bash
alembic upgrade head  # runs both 0015 and 0016
```

---

# Manual Verification Checklist — Phase 3: Metadata Fuzzy Match

## Prerequisites

1. Apply migration:
   ```bash
   alembic upgrade 0017
   ```

2. Verify indexes were created:
   ```sql
   SELECT indexname FROM pg_indexes
   WHERE tablename IN ('shastras', 'authors', 'teekas')
     AND indexname LIKE '%trgm%';
   -- Expected 5 rows: shastras_nk_trgm, shastras_title_trgm,
   --   authors_nk_trgm, authors_display_name_trgm, teekas_nk_trgm
   ```

3. Start metadata-service:
   ```bash
   DATABASE_URL="postgresql+asyncpg://..." \
   ADMIN_USER=admin ADMIN_PASSWORD=secret \
   python -m uvicorn services.metadata_service.main:app --port 8001 --reload
   ```

---

## `GET /v1/shastras?q=&fuzzy=true` — Test Cases

### A. Typo match (Latin)
Requires a shastra with `natural_key="samaysaar"`.

```bash
curl -s "http://localhost:8001/v1/shastras?q=samaysar&fuzzy=true&limit=5" \
  | python3 -m json.tool
```

Expected:
- `items[0].natural_key == "samaysaar"`
- `items[0].similarity` is a float between 0 and 1
- `pagination.total` equals number of items returned

---

### B. Devanagari typo match
Requires a shastra with Hindi title containing "समयसार".

```bash
curl -s "http://localhost:8001/v1/shastras?q=समयसर&fuzzy=true&limit=5" \
  | python3 -m json.tool
```

Expected: `samaysaar` appears in results (matched via `title::text` similarity)

---

### C. Cutoff — no garbage
```bash
curl -s "http://localhost:8001/v1/shastras?q=xyzunknownentity999&fuzzy=true" \
  | python3 -m json.tool
```

Expected: `items: []`

---

### D. Non-fuzzy q unchanged (ILIKE)
```bash
curl -s "http://localhost:8001/v1/shastras?q=समय" | python3 -m json.tool
```

Expected: shastras whose title contains "समय" (no `similarity` field in items)

---

### E. No similarity in non-fuzzy list
```bash
curl -s "http://localhost:8001/v1/shastras" | python3 -m json.tool
```

Expected: `items[*].similarity` is null (or absent)

---

## `GET /v1/authors?q=&fuzzy=true` — Test Cases

### F. Partial match
Requires an author with `natural_key="kundkundacharya"`.

```bash
curl -s "http://localhost:8001/v1/authors?q=kundkund&fuzzy=true&limit=5" \
  | python3 -m json.tool
```

Expected:
- `items[0].natural_key == "kundkundacharya"`
- `items[0].similarity` is a float > 0

---

### G. Non-fuzzy q with ILIKE
```bash
curl -s "http://localhost:8001/v1/authors?q=kundkund" | python3 -m json.tool
```

Expected: `kundkundacharya` in results; no `similarity` field

---

### H. Cutoff
```bash
curl -s "http://localhost:8001/v1/authors?q=xyzunknownentity999&fuzzy=true" \
  | python3 -m json.tool
```

Expected: `items: []`

---

## `GET /v1/teekas?q=&fuzzy=true` — Test Cases

### I. Partial natural_key match
Requires a teeka with `natural_key="samaysaar:amritchandra"`.

```bash
curl -s "http://localhost:8001/v1/teekas?q=samaysaar:amrit&fuzzy=true&limit=5" \
  | python3 -m json.tool
```

Expected:
- `items[0].natural_key == "samaysaar:amritchandra"`
- `items[0].similarity` is a float > 0

---

### J. Non-fuzzy q with ILIKE
```bash
curl -s "http://localhost:8001/v1/teekas?q=samaysaar" | python3 -m json.tool
```

Expected: `samaysaar:amritchandra` in results; no `similarity` field

---

### K. Limit cap
```bash
curl -s "http://localhost:8001/v1/teekas?q=samaysaar&fuzzy=true&limit=200" \
  | python3 -m json.tool
```

Expected: responds 200; actual result count ≤ 50

---

## Running automated tests

```bash
python -m pytest services/metadata_service/tests/ -v
# Expected: 84 passed
```

## Applying migrations

```bash
alembic upgrade 0017
```

---

# Manual Verification Checklist — Phase 4: Sub-workflow Endpoints

## Prerequisites

1. Start query-service with Neo4j config (same as Phase 2):
   ```bash
   DATABASE_URL="postgresql+asyncpg://..." \
   MONGO_URL="mongodb://localhost:27017" \
   NEO4J_URL="bolt://localhost:7687" \
   NEO4J_USER=neo4j NEO4J_PASSWORD=<password> \
   NEO4J_DATABASE=neo4j \
   ADMIN_USER=admin ADMIN_PASSWORD=secret \
   python -m uvicorn services.query_service.main:app --port 8004 --reload
   ```

2. Ensure Neo4j has `Shastra`, `Gatha`, and `Topic` nodes connected via
   `IN_SHASTRA` and `MENTIONS_TOPIC` edges.

---

## 4A — `GET /v1/gathas/{ident}` Shape Audit

### A1. Basic fields present
```bash
curl -s http://localhost:8002/v1/gathas/samaysaar:006 | python3 -m json.tool
```
Expected: response contains `gatha_number`, `shastra.natural_key`, `prakrit`, `sanskrit`, `hindi_chhand`, `word_meanings`.

---

### A2. Bhāvarth and Teeka Hindi via include
```bash
curl -s "http://localhost:8002/v1/gathas/samaysaar:006?include=teeka_hindi,teeka_bhaavarth" \
  | python3 -m json.tool
```
Expected: `teeka_hindi` and `teeka_bhaavarth` fields present (arrays, may be empty).

---

### A3. page_numbers gap
```bash
curl -s http://localhost:8002/v1/gathas/samaysaar:006 | python3 -c "import sys,json; d=json.load(sys.stdin); print('page_numbers' in d)"
```
Expected: `False` — field not yet in model (documented gap).

---

## 4B — `POST /v1/query/topics_in_shastra`

### B1. Per-gatha topics
Requires Gatha node `{number: 6}` in shastra `samaysaar` with `MENTIONS_TOPIC` edges in Neo4j.

```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{
    "shastra_natural_key": "samaysaar",
    "gatha_number": 6,
    "limit": 25
  }' | python3 -m json.tool
```

Expected:
- `topics` is a non-empty array
- Items sorted by `mention_count` DESC
- Each item has `topic_natural_key`, `display_text_hi`, `ancestors_hi`, `is_leaf`, `mention_count`
- `tool_trace_id` present

---

### B2. Whole-shastra rollup (no gatha_number)
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{
    "shastra_natural_key": "samaysaar",
    "limit": 25
  }' | python3 -m json.tool
```

Expected: more topics than per-gatha query (aggregated across all gathas); sorted by `mention_count` DESC.

---

### B3. Unknown shastra → empty list
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{"shastra_natural_key": "nonexistent_shastra"}' | python3 -m json.tool
```
Expected: `{"topics": [], "tool_trace_id": "..."}` (empty, not an error).

---

### B4. Missing required field → 422
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{"gatha_number": 6}' | python3 -m json.tool
```
Expected: HTTP 422 with validation error for `shastra_natural_key`.

---

### B5. ancestors_hi derived from natural_key
For a topic `द्रव्य/स्वतंत्रता` in the response:
- `ancestors_hi` must be `["द्रव्य"]`
- `display_text_hi` must be `"स्वतंत्रता"` (leaf text)

---

## 4C — `POST /v1/query/shastras_for_topic`

### C1. Basic by topic_natural_key
Requires `Topic {natural_key: "द्रव्य/स्वतंत्रता"}` with `MENTIONS_TOPIC` edges in Neo4j.

```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{
    "topic_natural_key": "द्रव्य/स्वतंत्रता",
    "include_gathas": true,
    "limit_shastras": 5,
    "limit_gathas_per_shastra": 5
  }' | python3 -m json.tool
```

Expected:
- `topic_natural_key == "द्रव्य/स्वतंत्रता"`
- `shastras` sorted by `total_mentions` DESC
- Each shastra has `shastra_natural_key`, `name_hi`, `total_mentions`, `gathas`
- Each gatha entry has `number` (int) and `page_number` (int or null)

---

### C2. limit_gathas_per_shastra cap
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{
    "topic_natural_key": "द्रव्य/स्वतंत्रता",
    "include_gathas": true,
    "limit_gathas_per_shastra": 2
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d['shastras']:
    assert len(s['gathas']) <= 2, f'{s[\"shastra_natural_key\"]} has {len(s[\"gathas\"])} gathas'
print('cap verified')
"
```
Expected: `cap verified`

---

### C3. include_gathas=false → empty gatha lists
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"topic_natural_key": "द्रव्य/स्वतंत्रता", "include_gathas": false}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d['shastras']:
    assert s['gathas'] == [], f'Expected empty gathas for {s[\"shastra_natural_key\"]}'
print('ok')
"
```
Expected: `ok`

---

### C4. keywords input (fallback via topics_match)
Requires topic `द्रव्य/स्वतंत्रता` in Postgres topics table with trigram index.

```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["स्वतंत्रता"], "include_gathas": true}' | python3 -m json.tool
```

Expected:
- `topic_natural_key` is the resolved topic's natural_key (e.g. `"द्रव्य/स्वतंत्रता"`)
- `shastras` populated if Neo4j has data

---

### C5. No input → 422
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"include_gathas": true}' | python3 -m json.tool
```
Expected: HTTP 422

---

### C6. Unknown topic → empty shastras
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"topic_natural_key": "अज्ञात/अज्ञात", "include_gathas": true}' | python3 -m json.tool
```
Expected: `{"topic_natural_key": "अज्ञात/अज्ञात", "shastras": [], "tool_trace_id": "..."}`

---

## Running automated tests

```bash
# From repo root
python -m pytest services/query_service/tests/ services/data_service/tests/ -v
# Expected: 128 passed (Phase 1+2+3+4)
```

## Neo4j EXPLAIN checks (Cypher index safety)

Connect to Neo4j browser (`http://localhost:7474`) and run:

```cypher
EXPLAIN
MATCH (s:Shastra {natural_key: "samaysaar"})<-[:IN_SHASTRA]-(g:Gatha {number: 6})
MATCH (g)-[:MENTIONS_TOPIC]->(t:Topic)
RETURN t.natural_key, count(*) AS mention_count
ORDER BY mention_count DESC, t.natural_key
LIMIT 25
```
Expected: no full-scan (`NodeByLabelScan`) — should show `NodeIndexSeek` for `Shastra(natural_key)`.

```cypher
EXPLAIN
MATCH (t:Topic {natural_key: "द्रव्य/स्वतंत्रता"})<-[:MENTIONS_TOPIC]-(g:Gatha)-[:IN_SHASTRA]->(s:Shastra)
WITH s, collect({number: g.number, page_number: g.page_number}) AS all_gathas, count(g) AS total_mentions
ORDER BY total_mentions DESC
LIMIT 10
RETURN s.natural_key, total_mentions, all_gathas[0..5] AS gathas
```
Expected: `NodeIndexSeek` for `Topic(natural_key)` entry point.

---

# Manual Verification Checklist — Phase 5 & 6: Hydration Helpers + Rollout

## Prerequisites

Same as Phase 2 / Phase 4 (query-service running with Postgres + Mongo + Neo4j).

---

## Phase 5 — Truncation marker `…`

### 1. Definition block truncated at 1500 chars with `…` suffix
Requires a keyword `आत्मा` with a `keyword_definitions` doc containing a Hindi block of >1500 chars.

```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा"], "include_definitions": true}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for defn in d['resolutions'][0].get('definitions') or []:
    if len(defn['text_hi']) > 1499:
        assert defn['text_hi'].endswith('…'), 'truncated text must end with …'
        assert len(defn['text_hi']) == 1501
        print('truncation ok:', len(defn['text_hi']), 'chars')
"
```
Expected: `truncation ok: 1501 chars`

---

### 2. Topic extract truncated at 1500 chars with `…` suffix
Requires a topic with a `topic_extracts` doc with a Hindi block of >1500 chars.

```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{"phrase": "आत्मा", "include_extracts": true, "include_references": false}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for m in d['matches']:
    for e in m.get('extracts_hi') or []:
        if len(e['text_hi']) > 1499:
            assert e['text_hi'].endswith('…'), 'truncated extract must end with …'
            print('extract truncation ok')
"
```

---

### 3. GraphRAG single Mongo query (verify no extra query)
Enable query logging in Mongo (or add a breakpoint) and confirm only **one** `find()` on `topic_extracts` is made when `include_extracts=True` and `include_references=True`:

```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["आत्मा"],
    "include_extracts": true,
    "include_references": true,
    "include_neighbors": false
  }' | python3 -m json.tool
```
Expected: `extracts_hi` and `references` both populated; no duplicate Mongo calls in logs.

---

## Phase 6 — Env variables

### 4. Configurable limits honoured
Start the service with a custom env var override:
```bash
QUERY_TOPICS_MATCH_DEFAULT_LIMIT=2 \
DATABASE_URL="..." ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
```

Then verify the setting is loaded:
```python
from services.query_service.config import settings
assert settings.QUERY_TOPICS_MATCH_DEFAULT_LIMIT == 2
```

---

## Running all automated tests

```bash
# Unit tests for hydration helpers (no DB required)
python -m pytest packages/jain_kb_common/tests/hydration/ -v
# Expected: 26 passed

# Full query-service suite (requires DATABASE_URL)
python -m pytest services/query_service/tests/ -v
# Expected: 65 passed (Phases 1–6)
```
