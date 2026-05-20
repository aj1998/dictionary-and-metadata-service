# Manual Testing — `POST /v1/query/topics_in_shastra`

## Prerequisites

```bash
DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
NEO4J_URL="bolt://localhost:7687" NEO4J_USER=neo4j NEO4J_PASSWORD=<password> \
NEO4J_DATABASE=neo4j ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
```

Ensure Neo4j has `Shastra`, `Gatha`, and `Topic` nodes connected via
`IN_SHASTRA` and `MENTIONS_TOPIC` edges.

---

## curl examples

### Per-gatha topics
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{
    "shastra_natural_key": "samaysaar",
    "gatha_number": 6,
    "limit": 25
  }' | python3 -m json.tool
```
**Expected shape:**
```json
{
  "topics": [{
    "topic_natural_key": "द्रव्य/जीव",
    "display_text_hi": "जीव",
    "ancestors_hi": ["द्रव्य"],
    "is_leaf": true,
    "mention_count": 3
  }],
  "tool_trace_id": "<uuid>"
}
```
- Items sorted by `mention_count` DESC.

---

### Whole-shastra rollup (no gatha_number)
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{
    "shastra_natural_key": "samaysaar",
    "limit": 25
  }' | python3 -m json.tool
```
Expected: aggregated across all gathas; more topics than per-gatha query.

---

### Unknown shastra → empty list
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{"shastra_natural_key": "nonexistent_shastra"}' | python3 -m json.tool
```
Expected: `{"topics": [], "tool_trace_id": "..."}`

---

### Missing required field → 422
```bash
curl -s -X POST http://localhost:8004/v1/query/topics_in_shastra \
  -H "Content-Type: application/json" \
  -d '{"gatha_number": 6}' | python3 -m json.tool
```
Expected: HTTP 422.

---

## Diagnostic Cypher

```cypher
EXPLAIN
MATCH (s:Shastra {natural_key: "samaysaar"})<-[:IN_SHASTRA]-(g:Gatha {number: 6})
MATCH (g)-[:MENTIONS_TOPIC]->(t:Topic)
RETURN t.natural_key, count(*) AS mention_count
ORDER BY mention_count DESC
LIMIT 25
```
Expected: `NodeIndexSeek` on `Shastra(natural_key)` — no full scan.
