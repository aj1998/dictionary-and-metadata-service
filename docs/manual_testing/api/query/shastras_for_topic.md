# Manual Testing — `POST /v1/query/shastras_for_topic`

## Prerequisites

```bash
DATABASE_URL="postgresql+asyncpg://..." MONGO_URL="mongodb://localhost:27017" \
NEO4J_URL="bolt://localhost:7687" NEO4J_USER=neo4j NEO4J_PASSWORD=<password> \
NEO4J_DATABASE=neo4j ADMIN_USER=admin ADMIN_PASSWORD=secret \
python -m uvicorn services.query_service.main:app --port 8004 --reload
```

---

## curl examples

### By topic_natural_key
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
**Expected shape:**
```json
{
  "topic_natural_key": "द्रव्य/स्वतंत्रता",
  "shastras": [{
    "shastra_natural_key": "samaysaar",
    "name_hi": "समयसार",
    "total_mentions": 10,
    "gathas": [
      {"number": 6, "page_number": 42}
    ]
  }],
  "tool_trace_id": "<uuid>"
}
```
- `shastras` sorted by `total_mentions` DESC.

---

### limit_gathas_per_shastra cap
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"topic_natural_key": "द्रव्य/स्वतंत्रता", "include_gathas": true, "limit_gathas_per_shastra": 2}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d['shastras']:
    assert len(s['gathas']) <= 2, f'cap violated for {s[\"shastra_natural_key\"]}'
print('cap verified')
"
```

---

### include_gathas=false → empty gatha lists
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"topic_natural_key": "द्रव्य/स्वतंत्रता", "include_gathas": false}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d['shastras']:
    assert s['gathas'] == []
print('ok')
"
```

---

### keywords fallback (trigram resolve)
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["स्वतंत्रता"], "include_gathas": true}' | python3 -m json.tool
```
Expected: `topic_natural_key` is the resolved topic's key.

---

### No input → 422
```bash
curl -s -X POST http://localhost:8004/v1/query/shastras_for_topic \
  -H "Content-Type: application/json" \
  -d '{"include_gathas": true}' | python3 -m json.tool
```
Expected: HTTP 422.

---

## Diagnostic Cypher

```cypher
EXPLAIN
MATCH (t:Topic {natural_key: "द्रव्य/स्वतंत्रता"})<-[:MENTIONS_TOPIC]-(g:Gatha)-[:IN_SHASTRA]->(s:Shastra)
WITH s, collect({number: g.number, page_number: g.page_number}) AS all_gathas, count(g) AS total_mentions
ORDER BY total_mentions DESC
LIMIT 10
RETURN s.natural_key, total_mentions, all_gathas[0..5] AS gathas
```
Expected: `NodeIndexSeek` on `Topic(natural_key)`.
