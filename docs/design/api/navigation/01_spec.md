# Navigation Service API — Specification

FastAPI service that is the single point of contact for **Neo4j graph operations**: keyword-to-keyword alias resolution, topic neighborhood traversal, graph edge administration, and graph health. Acts as the bridge between the data service (Postgres/Mongo reads) and the query service (GraphRAG pipeline).

This service also owns all writes that touch Neo4j — alias CRUD (Postgres + Neo4j ALIAS_OF edge together) and manual topic-edge management.

## Service identity

- **Module path**: `services/navigation_service/`
- **Default port**: `8003`
- **Base path**: `/v1`
- **Auth**: `GET` endpoints are public. Admin writes under `/v1/admin/...` require HTTP Basic Auth (`ADMIN_USER` / `ADMIN_PASSWORD`).
- **DB access**: Neo4j (primary), Postgres (keyword/alias resolution and alias writes).

---

## Endpoints

### Health

```
GET /healthz
```
```json
{"status": "ok", "neo4j": "ok", "postgres": "ok", "graph_node_count": 12345}
```

`graph_node_count` is a cached count from Neo4j (`MATCH (n) RETURN count(n)`), refreshed every 5 minutes.

---

### Keyword resolution

Used by the query service to resolve raw text tokens into keyword natural keys before graph traversal. Runs two passes: exact match, then alias-aware match.

```
GET /v1/keywords/{token}/resolve
```

- `{token}` — NFC-normalized Devanagari string.
- Tries Postgres `keywords.natural_key` exact match first; falls back to `keyword_aliases.alias_text`; then tries the same two lookups after a light Hindi-suffix strip.

```json
{
  "input": "आतम",
  "matched_keyword_natural_key": "आत्मा",
  "match_kind": "alias"
}
```

`match_kind` values: `exact` · `alias` · `suffix_strip` · `none`

When `match_kind` is `none`, `matched_keyword_natural_key` is `null` and status is still `200`.

---

### Topic graph neighbors

```
GET /v1/topics/{natural_key}/neighbors?edge_types=IS_A,PART_OF,RELATED_TO&depth=1&exclude_stubs=true
```

Runs a Neo4j traversal from the given topic node outward via the specified edge types.

| Param | Default | Notes |
|---|---|---|
| `edge_types` | `IS_A,PART_OF,RELATED_TO` | Comma-separated; structural edges (`IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION`) are never traversed here |
| `depth` | `1` | Max `3` |
| `exclude_stubs` | `true` | When true, filters out nodes with `is_stub=true` from the result |

```json
{
  "topic_natural_key": "आत्मा:बहिरात्मादि-3-भेद",
  "neighbors": [
    {
      "natural_key": "आत्मा:अंतरात्मा",
      "display_text_hi": "अंतरात्मा",
      "label": "Topic",
      "edge_type": "IS_A",
      "edge_direction": "outbound",
      "weight": 1.0,
      "is_stub": false
    },
    {
      "natural_key": "आत्मा:परमात्मा",
      "display_text_hi": "परमात्मा",
      "label": "Topic",
      "edge_type": "IS_A",
      "edge_direction": "outbound",
      "weight": 1.0,
      "is_stub": false
    }
  ]
}
```

`edge_direction`: `outbound` (this node is the source) · `inbound` (this node is the target) · `undirected` (RELATED_TO).

---

### Keyword → topics

Topics reachable from a keyword via the graph. Used to render the topic cloud for a keyword detail page.

```
GET /v1/keywords/{natural_key}/topics?depth=1&edge_types=HAS_TOPIC,MENTIONS_KEYWORD&exclude_stubs=true
```

| Param | Default | Notes |
|---|---|---|
| `edge_types` | `HAS_TOPIC,MENTIONS_KEYWORD` | Edge types from keyword outward toward topics |
| `depth` | `1` | Max `2` |
| `exclude_stubs` | `true` | Filter stubs |

```json
{
  "keyword_natural_key": "आत्मा",
  "topics": [
    {
      "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
      "display_text_hi": "आत्मा के बहिरात्मादि 3 भेद",
      "edge_type": "HAS_TOPIC",
      "is_stub": false
    }
  ]
}
```

---

### Topic → keywords

Keywords referenced by a topic (inverse of above). Used to show which keywords a topic body mentions.

```
GET /v1/topics/{natural_key}/keywords?exclude_stubs=true
```

Follows `MENTIONS_KEYWORD` edges outbound from the topic node.

```json
{
  "topic_natural_key": "आत्मा:बहिरात्मादि-3-भेद",
  "keywords": [
    {
      "natural_key": "बहिरात्मा",
      "display_text": "बहिरात्मा",
      "edge_type": "MENTIONS_KEYWORD",
      "is_stub": false
    }
  ]
}
```

---

### Shortest path (admin / debugging)

```
GET /v1/graph/shortest_path?from={topic_nk}&to={topic_nk}
```

Finds the shortest path between two Topic nodes in Neo4j. Max depth 6. Intended for admin graph debugging, not production traffic.

```json
{
  "from": "आत्मा:बहिरात्मादि-3-भेद",
  "to": "द्रव्य:द्रव्य-गुण-पर्याय-भेद",
  "path_length": 3,
  "nodes": [
    "आत्मा:बहिरात्मादि-3-भेद",
    "आत्मा",
    "द्रव्य:आत्मा-द्रव्य",
    "द्रव्य:द्रव्य-गुण-पर्याय-भेद"
  ]
}
```

Returns `404` if no path exists within depth 6.

---

### Admin: Alias management

Alias writes touch both Postgres (`keyword_aliases` row) and Neo4j (`ALIAS_OF` edge) in the same operation.

#### Add alias

```
POST /v1/admin/keywords/{id}/aliases
```

```json
{
  "alias_text": "आतम",
  "source": "admin"
}
```

**Steps**:
1. Write row to `keyword_aliases` (Postgres).
2. `MERGE (a:Alias {alias_text})-[:ALIAS_OF]->(k:Keyword {natural_key})` (Neo4j).
3. Return created alias.

```json
{
  "id": "uuid",
  "alias_text": "आतम",
  "source": "admin",
  "keyword_natural_key": "आत्मा",
  "created_at": "2026-05-13T10:00:00Z"
}
```

#### Remove alias

```
DELETE /v1/admin/keywords/{id}/aliases/{alias_id}
```

Deletes the `keyword_aliases` Postgres row and detaches the Neo4j `Alias` node (removes `ALIAS_OF` edge; deletes the `Alias` node if it has no other edges).

---

### Admin: Topic graph edges

Manual curation of Topic→Topic semantic edges. Writes only to Neo4j — no Postgres table.

#### Add edge

```
POST /v1/admin/topics/{natural_key}/edges
```

```json
{
  "target_topic_natural_key": "द्रव्य:द्रव्य-गुण-पर्याय-भेद",
  "edge_type": "RELATED_TO",
  "weight": 1.0
}
```

`edge_type` must be in `parser_configs/_meta/edge_types.yaml` (validated via `schema_check.validate_edge_type`). Allowed semantic types for admin: `IS_A`, `PART_OF`, `RELATED_TO`. Structural types (`IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION`) are rejected.

Uses idempotent `MERGE` so re-posting the same edge is safe.

```json
{
  "source_topic_natural_key": "आत्मा:बहिरात्मादि-3-भेद",
  "target_topic_natural_key": "द्रव्य:द्रव्य-गुण-पर्याय-भेद",
  "edge_type": "RELATED_TO",
  "weight": 1.0,
  "source": "admin"
}
```

#### Remove edge

```
DELETE /v1/admin/topics/{natural_key}/edges
```

```json
{
  "target_topic_natural_key": "द्रव्य:द्रव्य-गुण-पर्याय-भेद",
  "edge_type": "RELATED_TO"
}
```

---

### Admin: Graph resync

```
POST /v1/admin/graph/resync?scope=full|keyword|topic|shastra
```

Triggers a full or scoped rebuild of the Neo4j graph from Postgres + Mongo.

| Scope | What gets rebuilt |
|---|---|
| `full` | All nodes and edges — wipe and rebuild. Requires confirmation header `X-Confirm: resync-full`. |
| `keyword` | All Keyword + Alias nodes and their edges. |
| `topic` | All Topic nodes and their semantic edges. |
| `shastra` | All Shastra + Gatha nodes and structural edges. |

```json
{"status": "queued", "scope": "topic", "task_id": "uuid"}
```

In v1, resync runs synchronously in the request (no Celery required). For `full` scope, this is a slow operation — client should use a long timeout or poll `/healthz` for `graph_node_count` changes.

---

### Admin: Stub audit

```
GET /v1/admin/graph/stubs?label=&limit=50&offset=0
```

Lists Neo4j nodes with `is_stub=true`. Used to track which cross-page references have not yet been filled by real ingestion.

- `label` — optional filter: `Keyword`, `Topic`, `Gatha`, `GathaTeeka`, etc.

```json
{
  "pagination": {"total": 34, "limit": 50, "offset": 0},
  "items": [
    {
      "natural_key": "द्रव्य:षट्-द्रव्य",
      "label": "Topic",
      "stub_source": "jainkosh_ingestion",
      "created_at": "2026-05-13T08:00:00Z"
    }
  ]
}
```

---

## Module layout

```
services/navigation_service/
├── main.py               # FastAPI app, lifespan (verify Neo4j connection)
├── config.py             # NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD, DATABASE_URL, ADMIN_USER, ADMIN_PASSWORD
├── deps.py               # get_neo4j_driver(), get_session(), require_admin()
├── routers/
│   ├── keywords.py       # /keywords/{token}/resolve, /keywords/{nk}/topics
│   ├── topics.py         # /topics/{nk}/neighbors, /topics/{nk}/keywords
│   ├── graph.py          # /graph/shortest_path
│   └── admin.py          # aliases, edges, resync, stubs
├── services/
│   ├── resolution.py     # token → keyword_natural_key (Postgres queries)
│   ├── traversal.py      # Neo4j neighbor + keyword-topic queries
│   ├── aliases.py        # Postgres + Neo4j alias write/delete
│   ├── edges.py          # Neo4j topic-edge admin
│   └── resync.py         # graph rebuild from Postgres
├── schemas/
│   ├── resolution.py
│   ├── neighbors.py
│   └── admin.py
└── tests/
    ├── test_resolution.py
    ├── test_neighbors.py
    ├── test_aliases.py
    └── test_edges.py
```

## Key design constraints

- **One Cypher round-trip per neighbor query** — UNWIND the seed list, return all neighbors in one result set.
- **Postgres alias writes are committed before Neo4j writes** — if Neo4j fails, the Postgres row stays; a retry of the same POST is idempotent (MERGE on Neo4j).
- **Structural edge types never appear in public neighbor responses** — `IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION` are excluded from the edge_types filter set for public endpoints.
- **Stub exclusion is Cypher-side** (`WHERE NOT n.is_stub`) not Python-side, to avoid fetching unnecessary data.

## Run

```bash
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"
uvicorn services.navigation_service.main:app --port 8003 --reload
```

## Definition of Done

- [ ] `GET /v1/keywords/{token}/resolve` handles exact, alias, suffix-strip, and none cases; returns correct `match_kind`.
- [ ] `GET /v1/topics/{nk}/neighbors` runs one Cypher call; `exclude_stubs=true` filters at Cypher level.
- [ ] `GET /v1/keywords/{nk}/topics` and `GET /v1/topics/{nk}/keywords` run one Cypher call each.
- [ ] `GET /v1/graph/shortest_path` returns `404` cleanly when no path found.
- [ ] `POST /v1/admin/keywords/{id}/aliases` writes to Postgres first, then Neo4j MERGE; idempotent on retry.
- [ ] `DELETE /v1/admin/keywords/{id}/aliases/{alias_id}` removes Alias node from Neo4j only when it has no remaining edges.
- [ ] `POST /v1/admin/topics/{nk}/edges` validates edge_type against `edge_types.yaml`; rejects structural types with `400`.
- [ ] `POST /v1/admin/graph/resync?scope=full` requires `X-Confirm: resync-full` header; missing header returns `400`.
- [ ] Stub audit returns results with correct label filter.
- [ ] Integration tests cover: resolve (exact + alias + none), neighbors (depth 1 and 2), alias add/delete, edge add (valid + invalid type), stub audit.
- [ ] Service starts with `uvicorn services.navigation_service.main:app --port 8003`.
