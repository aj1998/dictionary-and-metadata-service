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
