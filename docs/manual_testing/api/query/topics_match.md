# Manual Testing — `POST /v1/query/topics_match`

## Prerequisites

```bash
DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
alembic upgrade 0016  # topics trigram index
```

---

## curl examples

### Phrase search (parent-aware)
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
**Expected shape:**
```json
{
  "matches": [{
    "topic_natural_key": "द्रव्य/स्वतंत्रता/लक्षण",
    "display_text_hi": "लक्षण",
    "ancestors_hi": ["द्रव्य", "स्वतंत्रता"],
    "is_leaf": true,
    "similarity": 0.72,
    "score": 0.72,
    "extracts_hi": null,
    "references": null
  }],
  "tool_trace_id": "<uuid>"
}
```

---

### leaf_only filter
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_match \
  -H "Content-Type: application/json" \
  -d '{"phrase": "द्रव्य", "leaf_only": true, "include_extracts": false}' \
  | python3 -m json.tool
```
Expected: all `matches[].is_leaf == true`

---

### With extracts + references
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
- `extracts_hi[]` contains only Devanagari Hindi text (`{block_index, text_hi}`)
- Text longer than 1500 chars is suffixed with `…`
- `references[]` shape: `{shastra_natural_key, gatha_number, teeka_natural_key, page_number}`

---

## Diagnostic SQL

Topics trigram index hit:
```sql
EXPLAIN ANALYZE
SELECT natural_key, similarity(REPLACE(natural_key,'/','  '), 'द्रव्य स्वतंत्रता') AS sim
FROM topics
WHERE similarity(REPLACE(natural_key,'/',' '), 'द्रव्य स्वतंत्रता') >= 0.30
ORDER BY sim DESC LIMIT 5;
```
Expected: `Bitmap Index Scan on topics_natural_key_trgm_idx` (not Seq Scan).
