# Manual Testing — `POST /v1/query/graphrag`

## Prerequisites

```bash
DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
NEO4J_URL="bolt://localhost:7687" NEO4J_USER=neo4j NEO4J_PASSWORD=<password> \
NEO4J_DATABASE=neo4j ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
```

---

## curl examples

### Basic GraphRAG call
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
**Expected shape:**
```json
{
  "ranked_topics": [{
    "topic_natural_key": "...",
    "score": 0.85,
    "overlap_count": 2,
    "matched_seed_keywords": ["द्रव्य", "स्वतंत्रता"],
    "ancestors_hi": ["..."],
    "is_leaf": true,
    "extracts_hi": null,
    "references": null,
    "neighbors": null
  }],
  "unresolved_tokens": [],
  "tool_trace_id": "<uuid>"
}
```

---

### Unknown token → unresolved
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["xyznonexistent123"], "include_extracts": false, "include_neighbors": false}' \
  | python3 -m json.tool
```
Expected: `ranked_topics: []`, `unresolved_tokens: ["xyznonexistent123"]`

---

### With extracts + references (single Mongo query — Phase 5)
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
Expected:
- `extracts_hi` has only Hindi Devanagari blocks (suffixed `…` if truncated at 1500 chars)
- `references` flat list of `{shastra_natural_key, gatha_number, teeka_natural_key, page_number}`

---

### Fuzzy mode
```bash
curl -s -X POST http://localhost:8004/v1/query/graphrag \
  -H "Content-Type: application/json" \
  -d '{"tokens": ["आतम"], "fuzzy": true, "include_extracts": false, "include_neighbors": false}' \
  | python3 -m json.tool
```
Expected: `आतम` resolves via fuzzy to `आत्मा` → traversal runs → topics returned.

---

## Diagnostic Cypher

Verify traversal from a seed keyword:
```cypher
MATCH (k:Keyword {natural_key: "आत्मा"})-[:HAS_TOPIC|RELATED_TO*1..2]->(t:Topic)
RETURN t.natural_key, count(*) AS hits
ORDER BY hits DESC LIMIT 10
```
