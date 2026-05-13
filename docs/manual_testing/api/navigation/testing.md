# Manual Testing Guide — Navigation Service API (`docs/design/api/navigation/01_spec.md`)

The navigation service owns all Neo4j graph operations: keyword resolution, topic neighborhood traversal, graph edge administration, and alias CRUD. This guide walks through starting the service and verifying every endpoint group by hand using `curl`.

---

## Prerequisites

| Tool | Version / Install |
|---|---|
| PostgreSQL 16 running | `brew services start postgresql@16` |
| Neo4j 5+ running | `/opt/homebrew/opt/neo4j/bin/neo4j start` |
| `jain_kb_dev` database migrated | `alembic upgrade head` |
| Python venv activated | `source .venv/bin/activate` |
| `neo4j`, `pydantic-settings`, `fastapi`, `uvicorn` installed | `pip install -e packages/jain_kb_common` |

---

## 1. Start the service

```bash
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"

uvicorn services.navigation_service.main:app --port 8003 --reload
```

Confirm startup:

```bash
curl -s http://localhost:8003/healthz | python3 -m json.tool
```

Expected:
```json
{
  "status": "ok",
  "neo4j": "ok",
  "postgres": "ok",
  "graph_node_count": 0
}
```

`graph_node_count` is a 5-minute cached MATCH count from Neo4j. It will be 0 on a fresh database.

---

## 2. Seed test data

Before testing graph endpoints, seed a keyword and a topic into both Postgres and Neo4j.

### Postgres seed

```bash
psql jain_kb_dev -c "
INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids)
VALUES (gen_random_uuid(), 'आत्मा', 'आत्मा', '[]')
ON CONFLICT (natural_key) DO NOTHING;
"
```

### Neo4j seed (Cypher Browser at http://localhost:7474)

```cypher
// Keyword node
MERGE (k:Keyword {natural_key: 'आत्मा'})
SET k.display_text = 'आत्मा', k.is_stub = false,
    k.created_at = datetime(), k.updated_at = datetime();

// Two topic nodes with IS_A edge
MERGE (t1:Topic {natural_key: 'आत्मा:बहिरात्मादि-3-भेद'})
SET t1.display_text_hi = 'आत्मा के बहिरात्मादि 3 भेद',
    t1.is_stub = false, t1.created_at = datetime(), t1.updated_at = datetime();

MERGE (t2:Topic {natural_key: 'आत्मा:अंतरात्मा'})
SET t2.display_text_hi = 'अंतरात्मा', t2.is_stub = false,
    t2.created_at = datetime(), t2.updated_at = datetime();

MERGE (t3:Topic {natural_key: 'आत्मा:परमात्मा'})
SET t3.display_text_hi = 'परमात्मा', t3.is_stub = false,
    t3.created_at = datetime(), t3.updated_at = datetime();

// Edges
MERGE (t1)-[:IS_A {weight: 1.0}]->(t2);
MERGE (t1)-[:IS_A {weight: 1.0}]->(t3);
MERGE (k)-[:HAS_TOPIC {weight: 1.0}]->(t1);
MERGE (t1)-[:MENTIONS_KEYWORD {weight: 1.0}]->(k);

// Alias node
MERGE (a:Alias {alias_text: 'आतम'})
SET a.source = 'test', a.created_at = datetime()
WITH a
MATCH (kw:Keyword {natural_key: 'आत्मा'})
MERGE (a)-[:ALIAS_OF]->(kw);
```

---

## 3. Keyword resolution

### Exact match

```bash
curl -s "http://localhost:8003/v1/keywords/आत्मा/resolve" | python3 -m json.tool
```

Expected:
```json
{
  "input": "आत्मा",
  "matched_keyword_natural_key": "आत्मा",
  "match_kind": "exact"
}
```

### Alias match

```bash
# Insert alias into Postgres first (or use the admin endpoint below)
psql jain_kb_dev -c "
INSERT INTO keyword_aliases (id, alias_text, keyword_id, source)
SELECT gen_random_uuid(), 'आतम', id, 'test' FROM keywords WHERE natural_key = 'आत्मा'
ON CONFLICT DO NOTHING;
"

curl -s "http://localhost:8003/v1/keywords/आतम/resolve" | python3 -m json.tool
```

Expected `match_kind: "alias"`.

### Suffix strip match

```bash
# "आत्मा" ends in ा, stripping it gives "आत्म" — insert that as a keyword
psql jain_kb_dev -c "
INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids)
VALUES (gen_random_uuid(), 'मोक्ष', 'मोक्ष', '[]') ON CONFLICT (natural_key) DO NOTHING;
"
curl -s "http://localhost:8003/v1/keywords/मोक्षा/resolve" | python3 -m json.tool
```

Expected: `match_kind: "suffix_strip"`, `matched_keyword_natural_key: "मोक्ष"`.

### No match

```bash
curl -s "http://localhost:8003/v1/keywords/xyz_not_a_word/resolve" | python3 -m json.tool
```

Expected: `match_kind: "none"`, `matched_keyword_natural_key: null`, HTTP 200.

---

## 4. Topic neighbors

```bash
curl -s "http://localhost:8003/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors" \
  | python3 -m json.tool
```

Expected: two neighbors (`अंतरात्मा` and `परमात्मा`) with `edge_direction: "outbound"` and `edge_type: "IS_A"`.

### Depth 2

```bash
curl -s "http://localhost:8003/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors?depth=2" \
  | python3 -m json.tool
```

### Custom edge types

```bash
curl -s "http://localhost:8003/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors?edge_types=IS_A" \
  | python3 -m json.tool
```

### Include stubs

```bash
curl -s "http://localhost:8003/v1/topics/आत्मा:बहिरात्मादि-3-भेद/neighbors?exclude_stubs=false" \
  | python3 -m json.tool
```

### Depth validation (depth=4 → 422)

```bash
curl -s "http://localhost:8003/v1/topics/any/neighbors?depth=4"
# → 422 Unprocessable Entity
```

---

## 5. Keyword → topics

```bash
curl -s "http://localhost:8003/v1/keywords/आत्मा/topics" | python3 -m json.tool
```

Expected: one topic entry with `edge_type: "HAS_TOPIC"`.

---

## 6. Topic → keywords

```bash
curl -s "http://localhost:8003/v1/topics/आत्मा:बहिरात्मादि-3-भेद/keywords" \
  | python3 -m json.tool
```

Expected: keyword `आत्मा` with `edge_type: "MENTIONS_KEYWORD"`.

---

## 7. Shortest path

```bash
curl -s "http://localhost:8003/v1/graph/shortest_path?from=आत्मा:बहिरात्मादि-3-भेद&to=आत्मा:अंतरात्मा" \
  | python3 -m json.tool
```

Expected:
```json
{
  "from_": "आत्मा:बहिरात्मादि-3-भेद",
  "to": "आत्मा:अंतरात्मा",
  "path_length": 1,
  "nodes": ["आत्मा:बहिरात्मादि-3-भेद", "आत्मा:अंतरात्मा"]
}
```

### 404 when no path

```bash
curl -s "http://localhost:8003/v1/graph/shortest_path?from=आत्मा:बहिरात्मादि-3-भेद&to=nonexistent_topic"
# → 404
```

---

## 8. Admin: Alias management

All admin endpoints require HTTP Basic Auth (`admin` / `secret`).

### Add alias

```bash
# Get keyword UUID first
KW_ID=$(psql jain_kb_dev -t -c "SELECT id FROM keywords WHERE natural_key = 'आत्मा'" | tr -d ' \n')

curl -s -X POST "http://localhost:8003/v1/admin/keywords/${KW_ID}/aliases" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"alias_text": "आतम", "source": "admin"}' \
  | python3 -m json.tool
```

Expected: alias object with `id`, `alias_text`, `keyword_natural_key: "आत्मा"`, `created_at`.

### Add alias idempotent (re-posting same alias returns same id)

```bash
curl -s -X POST "http://localhost:8003/v1/admin/keywords/${KW_ID}/aliases" \
  -u admin:secret -H "Content-Type: application/json" \
  -d '{"alias_text": "आतम", "source": "admin"}' | python3 -m json.tool
# Same id as above
```

### Delete alias

```bash
ALIAS_ID=<id from above>
curl -s -X DELETE "http://localhost:8003/v1/admin/keywords/${KW_ID}/aliases/${ALIAS_ID}" \
  -u admin:secret
# → 204 No Content
```

### Unauthenticated request → 401

```bash
curl -s -X POST "http://localhost:8003/v1/admin/keywords/${KW_ID}/aliases" \
  -H "Content-Type: application/json" -d '{"alias_text": "test"}'
# → 401
```

---

## 9. Admin: Topic graph edges

### Add IS_A edge

```bash
curl -s -X POST "http://localhost:8003/v1/admin/topics/आत्मा:बहिरात्मादि-3-भेद/edges" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"target_topic_natural_key": "द्रव्य:षट्-द्रव्य", "edge_type": "RELATED_TO", "weight": 0.8}' \
  | python3 -m json.tool
```

Expected:
```json
{
  "source_topic_natural_key": "आत्मा:बहिरात्मादि-3-भेद",
  "target_topic_natural_key": "द्रव्य:षट्-द्रव्य",
  "edge_type": "RELATED_TO",
  "weight": 0.8,
  "source": "admin"
}
```

### Structural edge type → 422

```bash
curl -s -X POST "http://localhost:8003/v1/admin/topics/topic-a/edges" \
  -u admin:secret -H "Content-Type: application/json" \
  -d '{"target_topic_natural_key": "topic-b", "edge_type": "IN_SHASTRA"}'
# → 422
```

### Remove edge

```bash
curl -s -X DELETE "http://localhost:8003/v1/admin/topics/आत्मा:बहिरात्मादि-3-भेद/edges" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"target_topic_natural_key": "द्रव्य:षट्-द्रव्य", "edge_type": "RELATED_TO"}'
# → 204 No Content
```

---

## 10. Admin: Graph resync

### Keyword scope (safe, no wipe)

```bash
curl -s -X POST "http://localhost:8003/v1/admin/graph/resync?scope=keyword" \
  -u admin:secret | python3 -m json.tool
```

Expected: `{"status": "completed", "scope": "keyword", "task_id": "<uuid>"}`.

### Full scope without confirm → 400

```bash
curl -s -X POST "http://localhost:8003/v1/admin/graph/resync?scope=full" -u admin:secret
# → 400 confirmation_required
```

### Full scope with confirm (DESTRUCTIVE — wipes and rebuilds all Neo4j nodes)

```bash
curl -s -X POST "http://localhost:8003/v1/admin/graph/resync?scope=full" \
  -u admin:secret \
  -H "X-Confirm: resync-full" | python3 -m json.tool
# → {"status": "completed", "scope": "full", "task_id": "<uuid>"}
```

---

## 11. Admin: Stub audit

```bash
curl -s "http://localhost:8003/v1/admin/graph/stubs" -u admin:secret | python3 -m json.tool
```

Expected:
```json
{
  "pagination": {"total": 0, "limit": 50, "offset": 0},
  "items": []
}
```

### With label filter

```bash
curl -s "http://localhost:8003/v1/admin/graph/stubs?label=Topic" -u admin:secret \
  | python3 -m json.tool
```

### Create a stub to test

Run in Neo4j Browser:
```cypher
MERGE (t:Topic {natural_key: 'test:stub-topic'})
SET t.is_stub = true, t.stub_source = 'manual_test',
    t.created_at = datetime();
```

Then:
```bash
curl -s "http://localhost:8003/v1/admin/graph/stubs?label=Topic" -u admin:secret \
  | python3 -m json.tool
# Should show the stub node
```

---

## 12. Automated tests

```bash
# Requires PostgreSQL running with jain_kb_test database
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
export NEO4J_PASSWORD=jainkb_password

python -m pytest services/navigation_service/tests/ -v
# 32 tests, 0 skipped — Neo4j is mocked
```

No live Neo4j connection required for automated tests (the driver is mocked in conftest).
