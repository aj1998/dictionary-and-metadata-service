# Manual Testing Guide — Neo4j Graph Data Model (`04_data_model_graph.md`)

## Prerequisites

- Neo4j 5 Community installed (`brew install neo4j`)
- Python 3.12 venv with `neo4j` and `pyyaml` packages installed
- `cypher-shell` in PATH (installed alongside neo4j via brew)

---

## 1. Start Neo4j

```bash
# Start (if not already running)
/opt/homebrew/opt/neo4j/bin/neo4j start

# Verify it's accepting connections (should print "1")
cypher-shell -u neo4j -p jainkb_password "RETURN 1 AS test"
```

**Default credentials used in this project**: `neo4j / jainkb_password`

To set the password on a fresh install:
```bash
brew services stop neo4j
/opt/homebrew/opt/neo4j/bin/neo4j-admin dbms set-initial-password jainkb_password
/opt/homebrew/opt/neo4j/bin/neo4j start
```

---

## 2. Run automated tests (zero skips)

```bash
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"

.venv/bin/python -m pytest tests/db/neo4j/ -v
# Expected: 20 passed

# Full suite
.venv/bin/python -m pytest tests/ -v
# Expected: 41 passed, 0 skipped
```

---

## 3. Smoke test — manually via cypher-shell

### 3a. Constraints and indexes

After running `ensure_constraints()` (done automatically by the test fixture), verify:

```cypher
SHOW CONSTRAINTS;
```

Expected output includes these names:
- `keyword_natural_key`
- `topic_natural_key`
- `alias_text`
- `gatha_natural_key`
- `shastra_natural_key`

```cypher
SHOW INDEXES;
```

Expected: `keyword_pg_id` and `topic_pg_id` indexes.

### 3b. Insert a keyword and topic, verify the graph

Run in `cypher-shell`:

```cypher
-- Create a Keyword node
MERGE (k:Keyword {natural_key: "आत्मा"})
SET k.pg_id = "00000000-0000-0000-0000-000000000001",
    k.display_text = "आत्मा",
    k.source_url = "https://www.jainkosh.org/wiki/आत्मा",
    k.created_at = datetime(),
    k.updated_at = datetime();

-- Create a Topic node linked to the Keyword
MERGE (t:Topic {natural_key: "jainkosh:आत्मा:बहिरात्मादि-3-भेद"})
SET t.pg_id = "00000000-0000-0000-0000-000000000002",
    t.display_text_hi = "आत्मा के बहिरात्मादि 3 भेद",
    t.source = "jainkosh",
    t.parent_keyword_natural_key = "आत्मा",
    t.created_at = datetime(),
    t.updated_at = datetime();

-- HAS_TOPIC edge
MATCH (k:Keyword {natural_key: "आत्मा"}), (t:Topic {natural_key: "jainkosh:आत्मा:बहिरात्मादि-3-भेद"})
MERGE (k)-[r:HAS_TOPIC]->(t)
SET r.weight = 1.0, r.source = "jainkosh";

-- Alias node
MERGE (a:Alias {alias_text: "आतम"})
SET a.pg_id = "00000000-0000-0000-0000-000000000003",
    a.source = "jainkosh_redirect",
    a.created_at = datetime();

-- ALIAS_OF edge
MATCH (a:Alias {alias_text: "आतम"}), (k:Keyword {natural_key: "आत्मा"})
MERGE (a)-[r:ALIAS_OF]->(k)
SET r.source = "jainkosh_redirect";
```

Verify with:

```cypher
MATCH (k:Keyword {natural_key: "आत्मा"})-[:HAS_TOPIC]->(t:Topic)
RETURN k.display_text AS keyword, t.display_text_hi AS topic;
```

Expected: `keyword = "आत्मा"`, `topic = "आत्मा के बहिरात्मादि 3 भेद"`.

```cypher
MATCH (a:Alias {alias_text: "आतम"})-[:ALIAS_OF]->(k:Keyword)
RETURN a.alias_text AS alias, k.natural_key AS resolves_to;
```

Expected: `alias = "आतम"`, `resolves_to = "आत्मा"`.

### 3c. Test alias-aware token resolution

```cypher
-- Direct keyword lookup
MATCH (k:Keyword {natural_key: "आत्मा"})
RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id;

-- Alias lookup
MATCH (a:Alias {alias_text: "आतम"})-[:ALIAS_OF]->(k:Keyword)
RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id;
```

### 3d. Test topic traversal from seed keyword

```cypher
UNWIND ["आत्मा"] AS kw
MATCH (k:Keyword {natural_key: kw})
MATCH (k)-[:HAS_TOPIC|MENTIONS_KEYWORD|RELATED_TO|IS_A|PART_OF*1..2]-(t:Topic)
WITH t, count(DISTINCT k) AS overlap
RETURN t.natural_key AS topic_nk, t.display_text_hi AS heading, overlap
ORDER BY overlap DESC
LIMIT 5;
```

Expected: at least one row with `topic_nk = "jainkosh:आत्मा:बहिरात्मादि-3-भेद"`.

### 3e. Test shortest path

First add a second topic:

```cypher
MERGE (t2:Topic {natural_key: "jainkosh:आत्मा:अंतरात्मा"})
SET t2.pg_id = "00000000-0000-0000-0000-000000000004",
    t2.display_text_hi = "अंतरात्मा",
    t2.source = "jainkosh",
    t2.created_at = datetime(),
    t2.updated_at = datetime();

-- IS_A edge: अंतरात्मा IS_A बहिरात्मादि-3-भेद topic (via keyword)
MATCH (k:Keyword {natural_key: "आत्मा"}), (t2:Topic {natural_key: "jainkosh:आत्मा:अंतरात्मा"})
MERGE (k)-[:HAS_TOPIC]->(t2);
```

Then find the shortest path:

```cypher
MATCH p = shortestPath(
  (a:Topic {natural_key: "jainkosh:आत्मा:बहिरात्मादि-3-भेद"})-[*..6]-
  (b:Topic {natural_key: "jainkosh:आत्मा:अंतरात्मा"})
)
RETURN [n IN nodes(p) | coalesce(n.natural_key, '')] AS node_keys, length(p) AS path_length;
```

Expected: a path through the `Keyword` node with `path_length = 2`.

---

## 4. Schema check — edge_types.yaml

Verify the YAML is loaded correctly:

```python
from jain_kb_common.db.neo4j.schema_check import validate_edge_type, UnknownEdgeTypeError

# Should pass silently
validate_edge_type("IS_A")
validate_edge_type("HAS_TOPIC")
validate_edge_type("IN_SHASTRA")

# Should raise
try:
    validate_edge_type("INVENTED_EDGE")
except UnknownEdgeTypeError as e:
    print(e)
```

---

## 5. Idempotency re-run

Run the upsert tests twice to confirm no duplicates:

```bash
NEO4J_URL="bolt://localhost:7687" NEO4J_USER="neo4j" NEO4J_PASSWORD="jainkb_password" \
  .venv/bin/python -m pytest tests/db/neo4j/ -v -k "idempotent"
```

All idempotency tests should pass on both runs without errors.

---

## 6. Cleanup

```cypher
-- Wipe all nodes from the database (dev/test only)
MATCH (n) DETACH DELETE n;
```
