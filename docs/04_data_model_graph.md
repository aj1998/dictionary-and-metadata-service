# 04 — Neo4j Graph Data Model

Authoritative for: keyword↔topic relationships used by the GraphRAG query path. The graph is a **mirror** of select Postgres rows — Postgres remains the source of truth. Re-syncing the graph from Postgres + Mongo must always be safe and produce the same result.

## Engine

- **Neo4j 5 Community Edition** (single instance, no clustering for v1).
- Database: `jainkb`.
- Driver: official `neo4j` Python driver (async).

## Node labels

| Label | Identifier | Stored properties | Source of truth |
|---|---|---|---|
| `Keyword` | `natural_key` (NFC Devanagari, e.g. `आत्मा`) | `pg_id` (uuid string), `display_text`, `source_url`, `created_at`, `updated_at` | Postgres `keywords` |
| `Topic` | `natural_key` (e.g. `jainkosh:आत्मा:बहिरात्मादि-3-भेद`) | `pg_id`, `display_text_hi`, `source` (enum), `parent_keyword_natural_key`, `created_at`, `updated_at` | Postgres `topics` |
| `Alias` | `alias_text` (NFC Devanagari) | `pg_id`, `source` (`jainkosh_redirect` \| `admin` \| `manual_seed`), `created_at` | Postgres `keyword_aliases` |
| `Gatha` | `natural_key` (e.g. `pravachansaar:039`) | `pg_id`, `shastra_natural_key`, `gatha_number`, `heading_hi` | Postgres `gathas` |
| `Shastra` | `natural_key` | `pg_id`, `title_hi`, `author_natural_key` | Postgres `shastras` |

Note: only properties needed for traversal/ranking live on graph nodes. Anything heavier (full text, multilingual arrays) stays in Postgres/Mongo and is fetched on demand using `pg_id`.

## Edge types

All edges are directed unless noted. Edge type names are uppercase (Neo4j convention).

| Type | Direction | From → To | Properties | Meaning |
|---|---|---|---|---|
| `IS_A` | directed | `Topic → Topic` or `Keyword → Keyword` | `weight` (float, default 1.0), `source` | Hyponym/hypernym (e.g. `अंतरात्मा IS_A आत्मा`) |
| `PART_OF` | directed | `Topic → Topic` | `weight`, `source` | Topic is a sub-topic of another (e.g. `बहिरात्मादि-3-भेद PART_OF आत्मा`) |
| `RELATED_TO` | undirected (stored as 2 reciprocal edges or queried with `-[:RELATED_TO]-`) | `Topic ↔ Topic` or `Keyword ↔ Keyword` | `weight`, `source` | Soft association |
| `ALIAS_OF` | directed | `Alias → Keyword` | `source` | Synonym / variant spelling |
| `MENTIONS_KEYWORD` | directed | `Topic → Keyword` | `weight`, `source_chunk_id` (nullable) | Topic body mentions this keyword (used to seed query) |
| `HAS_TOPIC` | directed | `Keyword → Topic` | `weight`, `source` | Keyword's JainKosh page yielded this topic |
| `MENTIONS_TOPIC` | directed | `Gatha → Topic` | `weight`, `source` | Gatha is associated with a topic (heading or extracted) |
| `IN_SHASTRA` | directed | `Gatha → Shastra` | — | Structural |

**Extending edge types:** add the new type name to `parser_configs/_meta/edge_types.yaml`. Validation on graph writes consults this file. Adding a type requires no migration.

## Constraints & indexes

```cypher
// Uniqueness
CREATE CONSTRAINT keyword_natural_key IF NOT EXISTS
  FOR (n:Keyword) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT topic_natural_key IF NOT EXISTS
  FOR (n:Topic) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT alias_text IF NOT EXISTS
  FOR (n:Alias) REQUIRE n.alias_text IS UNIQUE;

CREATE CONSTRAINT gatha_natural_key IF NOT EXISTS
  FOR (n:Gatha) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT shastra_natural_key IF NOT EXISTS
  FOR (n:Shastra) REQUIRE n.natural_key IS UNIQUE;

// Lookup speed
CREATE INDEX keyword_pg_id IF NOT EXISTS FOR (n:Keyword) ON (n.pg_id);
CREATE INDEX topic_pg_id IF NOT EXISTS FOR (n:Topic) ON (n.pg_id);
```

## Sync from Postgres

The graph is rebuilt from Postgres+Mongo by the `graph_sync` Celery task. It must be **idempotent**.

### Trigger points

1. After every successful `ingestion_run` (incremental — only entities touched in that run).
2. After admin approves an item from the review queue.
3. Manual `POST /admin/graph/resync?scope=full|keyword|topic` for full rebuild.

### Sync algorithm (incremental)

```python
# workers/enrichment/graph_sync.py
async def sync_keyword(neo4j, pg_kw_row, aliases):
    await neo4j.run("""
        MERGE (k:Keyword {natural_key: $nk})
        SET k.pg_id = $pg_id,
            k.display_text = $display,
            k.source_url = $url,
            k.updated_at = datetime()
        ON CREATE SET k.created_at = datetime()
    """, nk=pg_kw_row.natural_key, pg_id=str(pg_kw_row.id),
         display=pg_kw_row.display_text, url=pg_kw_row.source_url)

    for alias in aliases:
        await neo4j.run("""
            MERGE (a:Alias {alias_text: $alias})
            SET a.pg_id = $pg_id, a.source = $src
            WITH a
            MATCH (k:Keyword {natural_key: $nk})
            MERGE (a)-[r:ALIAS_OF]->(k)
            SET r.source = $src
        """, alias=alias.alias_text, pg_id=str(alias.id),
             src=alias.source, nk=pg_kw_row.natural_key)

async def sync_topic(neo4j, pg_topic_row, mentioned_keywords, parent_keyword_nk):
    await neo4j.run("""
        MERGE (t:Topic {natural_key: $nk})
        SET t.pg_id = $pg_id,
            t.display_text_hi = $display,
            t.source = $source,
            t.parent_keyword_natural_key = $parent,
            t.updated_at = datetime()
        ON CREATE SET t.created_at = datetime()
    """, nk=pg_topic_row.natural_key, pg_id=str(pg_topic_row.id),
         display=pick_hindi(pg_topic_row.display_text), source=pg_topic_row.source,
         parent=parent_keyword_nk)

    if parent_keyword_nk:
        await neo4j.run("""
            MATCH (k:Keyword {natural_key: $kw}), (t:Topic {natural_key: $tp})
            MERGE (k)-[r:HAS_TOPIC]->(t)
            SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
        """, kw=parent_keyword_nk, tp=pg_topic_row.natural_key)

    for kw_nk in mentioned_keywords:
        await neo4j.run("""
            MATCH (t:Topic {natural_key: $tp}), (k:Keyword {natural_key: $kw})
            MERGE (t)-[r:MENTIONS_KEYWORD]->(k)
            SET r.weight = coalesce(r.weight, 1.0)
        """, tp=pg_topic_row.natural_key, kw=kw_nk)
```

`mentioned_keywords` for a topic is computed from the topic's Mongo extract by simple string matching against the keyword index (admin can refine via the admin UI).

### Full rebuild

```cypher
// Wipe and rebuild — only run from admin UI with confirmation
MATCH (n) DETACH DELETE n;
// Then run sync_keyword / sync_topic / sync_gatha / sync_shastra for every Postgres row.
```

## Query patterns (for reference; see `12_query_engine.md` for the full query path)

### Resolve a query token to a `Keyword` (alias-aware)

```cypher
// Try direct keyword match first
MATCH (k:Keyword {natural_key: $token})
RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id;

// Else try alias
MATCH (a:Alias {alias_text: $token})-[:ALIAS_OF]->(k:Keyword)
RETURN k.natural_key AS keyword_nk, k.pg_id AS keyword_pg_id;
```

### Topics reached from a set of seed keywords (depth ≤ 2)

```cypher
UNWIND $seed_keyword_nks AS kw
MATCH (k:Keyword {natural_key: kw})
MATCH (k)-[r1:HAS_TOPIC|MENTIONS_KEYWORD|RELATED_TO|IS_A|PART_OF*1..2]-(t:Topic)
WITH t, count(DISTINCT k) AS overlap, sum(coalesce(r1[0].weight, 1.0)) AS weight_sum
RETURN t.natural_key AS topic_nk,
       t.display_text_hi AS heading,
       t.pg_id AS topic_pg_id,
       overlap,
       weight_sum
ORDER BY overlap DESC, weight_sum DESC
LIMIT $top_k;
```

(Note: this Cypher is illustrative; the actual ranking lives in `query_service/ranking.py` so it can be unit-tested in Python rather than tuning Cypher.)

### Find shortest path between two topics (admin / debugging)

```cypher
MATCH p = shortestPath((a:Topic {natural_key: $from})-[*..6]-(b:Topic {natural_key: $to}))
RETURN p;
```

## Driver layout

```
packages/jain_kb_common/db/neo4j/
├── __init__.py        # AsyncDriver factory
├── constraints.py     # ensure_constraints() at startup
├── upserts.py         # sync_keyword, sync_topic, sync_gatha, sync_shastra
├── queries.py         # resolve_token, traverse_topics, shortest_path
└── schema_check.py    # validates edge type names against parser_configs/_meta/edge_types.yaml
```

## Backups & re-derivation

Because the graph mirrors Postgres+Mongo, **graph backup is optional** — full rebuild from Postgres+Mongo is the recovery procedure. Still, take a nightly Neo4j backup (`neo4j-admin database dump`) for fast recovery (see `15_deployment.md`).

## Definition of Done

- [ ] All constraints + indexes are created via `ensure_constraints()` on service startup.
- [ ] `sync_keyword`, `sync_topic`, `sync_gatha`, `sync_shastra` all idempotent (proven by re-running on the same input).
- [ ] `graph_sync` Celery task wires into ingestion completion.
- [ ] Admin endpoint `POST /admin/graph/resync` exists and triggers a full rebuild.
- [ ] `parser_configs/_meta/edge_types.yaml` lists the canonical edge types; `schema_check.py` rejects writes with unknown types.
- [ ] Smoke test: ingest 2 sample JainKosh keywords + 1 nikkyjain shastra → graph has correct labels, 5+ nodes, ≥1 edge of each defined type.
