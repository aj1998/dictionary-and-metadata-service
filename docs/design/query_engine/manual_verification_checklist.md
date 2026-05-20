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

# Expected: 21 passed
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
