# 04 — Neo4j Graph Data Model

Authoritative for: keyword↔topic relationships used by the GraphRAG query path. The graph is a **mirror** of select Postgres rows — Postgres remains the source of truth. Re-syncing the graph from Postgres + Mongo must always be safe and produce the same result.

## Engine

- **Neo4j 5 Community Edition** (single instance, no clustering for v1).
- Database: `jainkb`.
- Driver: official `neo4j` Python driver (async).

## Node labels

| Label | Identifier | Stored properties | Source of truth |
|---|---|---|---|
| `Keyword` | `natural_key` (NFC Devanagari, e.g. `आत्मा`) | `pg_id` (uuid string), `display_text`, `source_url`, `is_stub`, `created_at`, `updated_at` | Postgres `keywords` |
| `Topic` | `natural_key` (e.g. `आत्मा:बहिरात्मादि-3-भेद`) | `pg_id`, `display_text_hi`, `source` (enum), `parent_keyword_natural_key`, `topic_path`, `is_stub`, `created_at`, `updated_at` | Postgres `topics` |
| `Alias` | `alias_text` (NFC Devanagari) | `pg_id`, `source` (`jainkosh_redirect` \| `admin` \| `manual_seed`), `created_at` | Postgres `keyword_aliases` |
| `Table` | `natural_key` (e.g. `table:jainkosh:द्रव्य:षट्द्रव्य:01`) | `pg_id`, `source`, `parent_natural_key`, `parent_kind`, `seq`, `caption_hi`, `is_stub`, `created_at`, `updated_at` | Postgres `tables` |
| `Gatha` | `natural_key` (e.g. `pravachansaar:039`) | `pg_id`, `shastra_natural_key`, `gatha_number`, `heading_hi`, `is_stub` | Postgres `gathas` |
| `Shastra` | `natural_key` | `pg_id`, `title_hi`, `author_natural_key` | Postgres `shastras` |
| `Teeka` | `natural_key` (e.g. `pravachansaar:amritchandra`) | `pg_id`, `shastra_natural_key`, `teekakar_natural_key` | Postgres `teekas` |
| `Publication` | `natural_key` (e.g. `pravachansaar:amritchandra:todarmal`) | `pg_id`, `teeka_natural_key`, `publisher_id` | Postgres `publications` |
| `GathaTeeka` | `natural_key` (e.g. `pravachansaar:amritchandra:039`) | `shastra_natural_key`, `teeka_natural_key`, `gatha_number`, `is_stub` | Derived during ingestion |
| `GathaTeekaBhaavarth` | `natural_key` (e.g. `pravachansaar:amritchandra:todarmal:039`) | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `gatha_number`, `is_stub` | Derived during ingestion |
| `Kalash` | `natural_key` (e.g. `pravachansaar:amritchandra:kalash:001`) | `teeka_natural_key`, `kalash_number`, `is_stub` | Postgres `kalashas` |
| `KalashBhaavarth` | `natural_key` (e.g. `pravachansaar:amritchandra:todarmal:kalash:001`) | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `kalash_number`, `is_stub` | Derived during ingestion |
| `Page` | `natural_key` (e.g. `pravachansaar:amritchandra:todarmal:p-042`) | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `page_number`, `is_stub` | Derived during ingestion |

**Stub nodes**: Nodes created during ingestion before the full Postgres row is approved carry `is_stub = true`. The real sync (`sync_keyword`, `sync_topic`, etc.) sets `is_stub = false`. Stub properties use `coalesce()` to never overwrite real data.

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
| `MENTIONS_TOPIC` | directed | `Gatha\|GathaTeeka\|GathaTeekaBhaavarth\|Kalash\|KalashBhaavarth\|Page → Topic` | `weight`, `source` | Source citation node (resolved from a JainKosh ref) cites a topic. Block-kind decides whether the source endpoint is the Gatha vs. the GathaTeeka/Bhaavarth — see `workers/ingestion/jainkosh/reference_edges.py`. |
| `CONTAINS_DEFINITION` | directed | `Gatha\|GathaTeeka\|GathaTeekaBhaavarth\|Kalash\|KalashBhaavarth\|Page → Keyword` | `weight`, `source`, `mention_path` | Source citation node appears inside a Keyword's JainKosh definition body. (Direction is **citation → Keyword** — the edge points outward from the cited gatha-family node to the keyword whose definition contains it.) |
| `HAS_TEEKA` | directed | `Shastra → Teeka` | — | Structural: shastra owns this teeka |
| `HAS_PUBLICATION` | directed | `Teeka → Publication` (also `Shastra → Publication` in NJ) | — | Structural: teeka owns this publication |
| `IN_SHASTRA` | directed | `Gatha → Shastra` | — | Structural: gatha belongs to shastra |
| `IN_TEEKA` | directed | `GathaTeeka\|Kalash → Teeka` | — | Structural: node belongs to teeka |
| `IN_PUBLICATION` | directed | `GathaTeekaBhaavarth\|KalashBhaavarth\|Page → Publication` | — | Structural: bhaavarth/page belongs to publication |
| `CONTAINS_TABLE` | directed | `Keyword\|Topic → Table` | `source` | Keyword or Topic page contains this table |
| `MENTIONS_TABLE` | directed | `Gatha\|Kalash\|Page → Table` | `weight`, `source`, `mention_path`, `source_natural_key` | Citation node (resolved from a table cell GRef) is cited within this table |

**Extending edge types:** add the new type name to `parser_configs/_meta/edge_types.yaml`. Validation on graph writes consults this file. Adding a type requires no migration.

## Natural-key format conventions (and known edge case)

The canonical Neo4j `natural_key` for citation-target labels (Gatha-family + Kalash-family + Page) is built by `workers/ingestion/jainkosh/reference_edges.py` and used as the endpoint of `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` / `MENTIONS_TABLE` edges:

| Label | Canonical nk format | Example |
|---|---|---|
| `Gatha` | `{shastra}:गाथा:{n}` | `समयसार:गाथा:8` |
| `GathaTeeka` | `{shastra}:{teeka}:गाथा:टीका:{n}` | `समयसार:आत्मख्याति:गाथा:टीका:8` |
| `GathaTeekaBhaavarth` | `{shastra}:{teeka}:{publisher_id}:गाथा:टीका:भावार्थ:{n}` | `समयसार:आत्मख्याति:राजचंद्र:गाथा:टीका:भावार्थ:8` |
| `Kalash` | `{shastra}:{teeka}:कलश:{k}` | `समयसार:आत्मख्याति:कलश:8` |
| `KalashBhaavarth` | `{shastra}:{teeka}:{publisher_id}:कलश:भावार्थ:{k}` | — |
| `Page` | `{shastra}:{teeka}:{publisher_id}:पृष्ठ:{p}` | — |

**⚠ Edge case — Mongo text-doc `natural_key` ≠ Neo4j node `natural_key`.** The NJ ingester (`workers/ingestion/nj/envelope.py`) writes the gatha-text Mongo documents (`gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`, etc.) with a `natural_key` that identifies the **text document**, not the abstract entity node:

| Mongo collection | `natural_key` field | Sibling field carrying the entity key |
|---|---|---|
| `gatha_teeka_sanskrit` | `{teeka_nk}:{g}:टीका:san` (e.g. `समयसार:आत्मख्याति:8:टीका:san`) | `gatha_teeka_natural_key = {teeka_nk}:{g}` |
| `gatha_teeka_bhaavarth_hindi` | `{publication_nk}:{g}:भावार्थ:hi` | `gatha_teeka_bhaavarth_natural_key`, `gatha_teeka_natural_key` |
| `kalash_sanskrit` / `kalash_hindi` | `{kalash_nk}:san` / `{kalash_nk}:hi` | `kalash_natural_key` (already canonical) |

Neither the Mongo `natural_key` nor the Mongo `gatha_teeka_natural_key` matches the canonical Neo4j `GathaTeeka.natural_key`. So a consumer that holds a Mongo doc and wants to query its outbound graph edges **cannot** pass `mongo_doc.natural_key` to Cypher — it will match no node. The consumer must reconstruct the Neo4j nk:

```ts
// GathaTeeka (sanskrit teeka / bhaavarth tabs in the gatha reader):
//   `{shastra}:{teeka}:गाथा:टीका:{g}`
// GathaTeekaBhaavarth:
//   `{shastra}:{teeka}:{publisher_id}:गाथा:टीका:भावार्थ:{g}`
```

The `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx` page (`gathaTeekaNeo4jNk`, `gathaTeekaBhaavarthNeo4jNk`) is the canonical example of this reconstruction. Until the Mongo↔Neo4j nk schemes are unified, any new graph traversal that originates from a UI panel showing Mongo-stored text must apply the same canonicalisation. Future work: drop the trailing `:टीका:san` / `:भावार्थ:hi` discriminators in Mongo so that `gatha_teeka_natural_key` and `GathaTeeka.natural_key` agree.

**UI graph links**: The "ग्राफ में खोलें" action in `PanelActionsMenu` passes `sourceNk` directly as the `?node=` parameter. Each panel's `actionsSourceNk` must therefore be the canonical Neo4j node key (not the Postgres or Mongo key). The gatha page constructs these as follows:
- Gatha: `${shastraPrefix}:गाथा:${gathaNumStr}` — the `Gatha` node key
- GathaTeeka: `gathaTeekaNeo4jNk(teekaNk)` → `{shastra}:{teeka}:गाथा:टीका:{g}`
- GathaTeekaBhaavarth: `gathaTeekaBhaavarthNeo4jNk(bh)` → `{shastra}:{teeka}:{publisher_id}:गाथा:टीका:भावार्थ:{g}`
- Kalash: `kalash.natural_key` → already canonical (`{shastra}:{teeka}:कलश:{k}`)

## Constraints & indexes

```cypher
// Uniqueness — one per node label
CREATE CONSTRAINT keyword_natural_key IF NOT EXISTS FOR (n:Keyword) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT topic_natural_key IF NOT EXISTS FOR (n:Topic) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT alias_text IF NOT EXISTS FOR (n:Alias) REQUIRE n.alias_text IS UNIQUE;
CREATE CONSTRAINT gatha_natural_key IF NOT EXISTS FOR (n:Gatha) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT shastra_natural_key IF NOT EXISTS FOR (n:Shastra) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT teeka_natural_key IF NOT EXISTS FOR (n:Teeka) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT publication_natural_key IF NOT EXISTS FOR (n:Publication) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT gatha_teeka_natural_key IF NOT EXISTS FOR (n:GathaTeeka) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT gatha_teeka_bhaavarth_natural_key IF NOT EXISTS FOR (n:GathaTeekaBhaavarth) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT kalash_natural_key IF NOT EXISTS FOR (n:Kalash) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT kalash_bhaavarth_natural_key IF NOT EXISTS FOR (n:KalashBhaavarth) REQUIRE n.natural_key IS UNIQUE;
CREATE CONSTRAINT page_natural_key IF NOT EXISTS FOR (n:Page) REQUIRE n.natural_key IS UNIQUE;

// Lookup speed — pg_id for fast Postgres cross-reference
CREATE INDEX keyword_pg_id IF NOT EXISTS FOR (n:Keyword) ON (n.pg_id);
CREATE INDEX topic_pg_id IF NOT EXISTS FOR (n:Topic) ON (n.pg_id);
CREATE INDEX teeka_pg_id IF NOT EXISTS FOR (n:Teeka) ON (n.pg_id);
CREATE INDEX publication_pg_id IF NOT EXISTS FOR (n:Publication) ON (n.pg_id);
CREATE INDEX kalash_pg_id IF NOT EXISTS FOR (n:Kalash) ON (n.pg_id);

// Traversal speed
CREATE INDEX topic_kw_path IF NOT EXISTS FOR (n:Topic) ON (n.parent_keyword_natural_key, n.topic_path);

// Stub node identification (used to find nodes that haven't been fully synced yet)
CREATE INDEX keyword_is_stub IF NOT EXISTS FOR (n:Keyword) ON (n.is_stub);
CREATE INDEX topic_is_stub IF NOT EXISTS FOR (n:Topic) ON (n.is_stub);
CREATE INDEX gatha_is_stub IF NOT EXISTS FOR (n:Gatha) ON (n.is_stub);
CREATE INDEX gatha_teeka_is_stub IF NOT EXISTS FOR (n:GathaTeeka) ON (n.is_stub);
CREATE INDEX gatha_teeka_bhaavarth_is_stub IF NOT EXISTS FOR (n:GathaTeekaBhaavarth) ON (n.is_stub);
CREATE INDEX kalash_is_stub IF NOT EXISTS FOR (n:Kalash) ON (n.is_stub);
CREATE INDEX kalash_bhaavarth_is_stub IF NOT EXISTS FOR (n:KalashBhaavarth) ON (n.is_stub);
CREATE INDEX page_is_stub IF NOT EXISTS FOR (n:Page) ON (n.is_stub);
```

All constraints and indexes are created by `ensure_constraints()` in `packages/jain_kb_common/db/neo4j/constraints.py` on service startup.

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
├── constraints.py     # ensure_constraints() at startup (all node labels + is_stub indexes)
├── upserts.py         # sync_keyword, sync_topic, sync_gatha, sync_shastra
├── stubs.py           # sync_stub_node, sync_reference_edge — idempotent stub helpers used during ingestion before admin approval
├── queries.py         # resolve_token, traverse_topics, shortest_path
└── schema_check.py    # validates edge type names against parser_configs/_meta/edge_types.yaml
```

## Backups & re-derivation

Because the graph mirrors Postgres+Mongo, **graph backup is optional** — full rebuild from Postgres+Mongo is the recovery procedure. Still, take a nightly Neo4j backup (`neo4j-admin database dump`) for fast recovery (see `deployment.md`).

## Definition of Done

- [ ] All constraints + indexes are created via `ensure_constraints()` on service startup.
- [ ] `sync_keyword`, `sync_topic`, `sync_gatha`, `sync_shastra` all idempotent (proven by re-running on the same input).
- [ ] `graph_sync` Celery task wires into ingestion completion.
- [ ] Admin endpoint `POST /admin/graph/resync` exists and triggers a full rebuild.
- [ ] `parser_configs/_meta/edge_types.yaml` lists the canonical edge types; `schema_check.py` rejects writes with unknown types.
- [ ] Smoke test: ingest 2 sample JainKosh keywords + 1 nikkyjain shastra → graph has correct labels, 5+ nodes, ≥1 edge of each defined type.

## SAAR additions (additive)

New labels and edge types are introduced by their owning scope spec. Each must also be appended to `parser_configs/_meta/edge_types.yaml`.

### New node labels

| Label | Identifier | Owning spec |
|---|---|---|
| `Translation` | `natural_key = "<entity_kind>:<entity_nk>:<lang>:<script>"` | [`scope/15_multilingual_keyword_storage_spec.md`](../scope/15_multilingual_keyword_storage_spec.md) |
| `Flowchart` | `natural_key = "fig:<source>:<page>:<bbox-hash>"` | [`scope/20_flowchart_table_graph_scanner_spec.md`](../scope/20_flowchart_table_graph_scanner_spec.md) |
| `JinswaraQnA` | `natural_key` (e.g. `jinswara:<author>:<qid>`) | [`scope/19_jinswara_qna_ingest_spec.md`](../scope/19_jinswara_qna_ingest_spec.md) |
| `PravachanChunk` | `natural_key = "<pravachan_nk>:<sequence>"` | [`scope/18_av_rag_pipeline_spec.md`](../scope/18_av_rag_pipeline_spec.md) |
| `ResearchCategory` | `code` (e.g. `maths`, `astronomy`) | [`scope/13_categorisation_pipeline_spec.md`](../scope/13_categorisation_pipeline_spec.md) |

### New edge types

| Type | From → To | Owning spec |
|---|---|---|
| `TRANSLATES_TO` | `Keyword|Topic → Translation` | [`scope/15`](../scope/15_multilingual_keyword_storage_spec.md) |
| `HAS_FLOWCHART` | `Topic|Gatha → Flowchart` | [`scope/20`](../scope/20_flowchart_table_graph_scanner_spec.md) |
| `ANSWERS` | `Author → JinswaraQnA` | [`scope/19`](../scope/19_jinswara_qna_ingest_spec.md) |
| `MENTIONS_TOPIC` (extended) | `JinswaraQnA|PravachanChunk → Topic` | [`scope/18`](../scope/18_av_rag_pipeline_spec.md), [`scope/19`](../scope/19_jinswara_qna_ingest_spec.md) |
| `MENTIONS_KEYWORD` (extended) | `JinswaraQnA|PravachanChunk → Keyword` | same |
| `IN_PRAVACHAN` | `PravachanChunk → Pravachan` (Pravachan node added to mirror PG) | [`scope/18`](../scope/18_av_rag_pipeline_spec.md) |
| `CATEGORISED_AS` | `Topic|Keyword|Gatha → ResearchCategory` | [`scope/13`](../scope/13_categorisation_pipeline_spec.md) |
| `DRUSHTAANT_OF` | `DrushtaantImage → Gatha` (DrushtaantImage node optional; PG-only acceptable) | [`scope/05`](../scope/05_drushtaant_image_gen_spec.md) |

All new edges carry the standard `{weight, source}` properties. Sync is still Postgres-driven; the `graph_sync` worker grows new helpers per spec.
