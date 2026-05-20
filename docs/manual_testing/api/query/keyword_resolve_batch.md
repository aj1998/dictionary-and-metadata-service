# Manual Testing — `POST /v1/query/keyword_resolve_batch`

## Prerequisites

```bash
DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
```

---

## curl examples

### Exact match
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा"], "include_definitions": false}' \
  | python3 -m json.tool
```
**Expected shape:**
```json
{
  "resolutions": [{
    "input_token": "आत्मा",
    "match_kind": "exact",
    "keyword_natural_key": "आत्मा",
    "keyword_id": "<uuid>",
    "definitions": null,
    "suggestions": null
  }],
  "tool_trace_id": "<uuid>"
}
```

---

### Alias match
Requires alias `आतम` → `आत्मा` in `keyword_aliases`.
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आतम"], "include_definitions": false}' \
  | python3 -m json.tool
```
Expected: `match_kind: "alias"`, `keyword_natural_key: "आत्मा"`

---

### Suffix-strip match
Requires keyword `द्रव्य`.
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["द्रव्यों"], "include_definitions": false}' \
  | python3 -m json.tool
```
Expected: `match_kind: "suffix_strip"`, `keyword_natural_key: "द्रव्य"`

---

### With definitions (Hindi only, truncated at 1500 chars + `…`)
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आत्मा"], "include_definitions": true, "definitions_per_keyword": 2}' \
  | python3 -m json.tool
```
Expected: each `definitions[]` item has `source_natural_key`, `block_index`, `text_hi` (Devanagari, max 1500 chars content; suffixed with `…` if truncated).

---

### Token cap enforcement
```bash
curl -s -X POST http://localhost:8004/v1/query/keyword_resolve_batch \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z","aa","bb","cc","dd","ee","ff","gg"]}' \
  | python3 -m json.tool
```
Expected: HTTP 422 `{"detail": {"code": "tokens_too_many", "message": "Max 32 tokens"}}`

---

## Diagnostic SQL

Verify keyword + alias rows:
```sql
SELECT k.natural_key, ka.alias_text
FROM keywords k
LEFT JOIN keyword_aliases ka ON ka.keyword_id = k.id
WHERE k.natural_key IN ('आत्मा', 'द्रव्य');
```

Verify trigram index is active:
```sql
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'keywords' AND indexname LIKE '%trgm%';
```
