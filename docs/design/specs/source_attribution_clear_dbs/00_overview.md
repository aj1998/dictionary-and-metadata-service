# Spec — Per-source clear of ingested data (jainkosh / nj)

## Goal

Extend [`scripts/clear_dbs.py`](../../../../scripts/clear_dbs.py) so the operator can wipe only what one ingestor wrote, leaving the other ingestor's data intact:

```bash
python scripts/clear_dbs.py --source all        # current behaviour (default)
python scripts/clear_dbs.py --source jainkosh   # only jainkosh-produced rows/nodes/docs
python scripts/clear_dbs.py --source nj         # only nj-produced rows/nodes/docs
```

For data co-owned by **both** ingestors (e.g. a `Shastra` that the jainkosh
parser lazily stubbed and the nj parser fully ingested) the row carries the
union `{"jainkosh", "nj"}` and is deleted under **either** `--source` value so
the database can be brought to a clean empty state with two consecutive
single-source clears.

## Background — current source attribution

| Layer | Has source today? | Notes |
|---|---|---|
| Postgres `topics`, `tables`, `parser_configs`, `ingestion_runs` | yes (`ingestion_source` enum, single value) | matches the writing ingestor |
| Postgres `authors`, `shastras`, `teekas`, `gathas`, `kalashas`, `publications`, `teeka_chapters`, `books`, `pravachans`, `keywords`, `keyword_aliases`, `shastra_anuyogas`, `book_anuyogas` | **no** | must be added (or derived transitively for link tables) |
| Neo4j `Topic`, `Table` | yes (`source` string) | single-value |
| Neo4j `Keyword`, `Shastra`, `Teeka`, `Publication`, `Gatha`, `Kalash`, `GathaTeeka`, `GathaTeekaBhaavarth`, `KalashBhaavarth`, `Page`, `Alias` | **no** (only a one-shot `stub_source` at create time) | must be added as a multi-value `sources` list |
| Mongo collections | implicit by collection name | already partitioned in `_MONGO_COLLECTIONS` |

## Design choice — multi-value `sources`

For every shared table/node we add a **string array** column/property named
`sources` (not the existing single-valued `source` — that is kept for the
tables where it is already authoritative and single-writer).

- Postgres: `sources TEXT[] NOT NULL DEFAULT '{}'`, with a GIN index for
  efficient `WHERE 'jainkosh' = ANY(sources)` filtering.
- Neo4j: `sources :: list<string>`. Maintained via Cypher set-union on every
  write (no APOC; uses plain list arithmetic — see phase 03).

The existing single-valued `source` on `topics` / `tables` / `parser_configs`
/ `ingestion_runs` stays unchanged — those are owned end-to-end by one
ingestor, and `topics.natural_key` already disallows the `jainkosh:` / `nj:`
prefix per the existing CHECK constraint, so a topic row is never co-owned.

## Phase index

| # | File | Outcome |
|---|---|---|
| 01 | [`01_pg_schema_and_upserts.md`](01_pg_schema_and_upserts.md) | Alembic migration `0024_add_sources`, SQLAlchemy models, upsert merge helper, unit tests |
| 02 | [`02_ingestion_apply_layers.md`](02_ingestion_apply_layers.md) | Wire `source=jainkosh` / `source=nj` through every upsert call in `workers/ingestion/jainkosh/apply.py` and `workers/ingestion/nj/apply.py`; integration tests |
| 03 | [`03_neo4j_sources.md`](03_neo4j_sources.md) | Multi-source `sources` property on every node label written by either ingestor; sync_* helpers updated; tests |
| 04 | [`04_clear_dbs_flag.md`](04_clear_dbs_flag.md) | `--source {all,jainkosh,nj}` flag on `scripts/clear_dbs.py`; per-source delete predicates for Postgres, Mongo, Neo4j; e2e test |

Each phase is self-contained — an implementing agent should be able to finish
one phase end-to-end (migration + code + tests + docs) inside a single
context window.

## Non-goals

- Backfilling pre-existing rows with accurate sources. Phase 01 stamps
  existing data with a best-effort heuristic (see that phase's "Backfill"
  section); operators may wipe-and-reingest if a perfectly clean slate
  matters.
- Per-`ingestion_run_id` deletion. The new flag operates at the
  `ingestion_source` granularity, not per-run.
- Changing the existing `_MONGO_COLLECTIONS` partition; Mongo handling is
  purely additive in phase 04 (split the tuple into `_JK_MONGO` / `_NJ_MONGO`).

## Cross-cutting conventions

- All new column/property writes are **idempotent set-union**: rerunning the
  same ingestion never produces duplicates inside `sources`.
- All new upsert signatures take `source: IngestionSource | None`. `None`
  means "don't touch sources" (e.g. for re-syncs from the graph_sync worker
  that don't represent a fresh ingestion).
- Neo4j writes use plain Cypher (`SET n.sources = CASE WHEN $src IN
  coalesce(n.sources, []) THEN n.sources ELSE coalesce(n.sources, []) + $src
  END`) — no APOC dependency.
- The `source` value passed in is always the `IngestionSource` enum's string
  (`"jainkosh"` / `"nj"`).
