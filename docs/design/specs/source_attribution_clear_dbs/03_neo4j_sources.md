# Phase 03 — Neo4j multi-source `sources` property

Read [overview](00_overview.md) first.

## Goal

Every Neo4j node written by either ingestor carries a `sources: list<string>`
property maintained as a distinct set union, so that
`MATCH (n) WHERE 'jainkosh' IN n.sources` can be used to scope a delete in
phase 04.

Labels affected: `Keyword`, `Shastra`, `Teeka`, `Publication`, `Gatha`,
`Kalash`, `GathaTeeka`, `GathaTeekaBhaavarth`, `KalashBhaavarth`, `Page`,
`Alias`. (`Topic` and `Table` keep their existing single-valued `source`
but **also** get the new `sources` list for uniform clear semantics — see
"Topic/Table dual write" below.)

## Set-union pattern (plain Cypher, no APOC)

```cypher
SET n.sources = CASE
  WHEN $src IS NULL THEN coalesce(n.sources, [])
  WHEN $src IN coalesce(n.sources, []) THEN n.sources
  ELSE coalesce(n.sources, []) + $src
END
```

This snippet is appended to every `MERGE …` / `SET` block in:

- [`packages/jain_kb_common/jain_kb_common/db/neo4j/stubs.py`](../../../../packages/jain_kb_common/jain_kb_common/db/neo4j/stubs.py)
  (`sync_stub_node`)
- [`packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py`](../../../../packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py)
  (`sync_keyword`, `sync_topic`, `sync_gatha`, `sync_shastra`, etc.)

Each helper grows a `source: str | None` kwarg threaded from the ingestion
apply layers updated in phase 02. The existing `stub_source` property is
deprecated but left in place for now (still written for one cycle to ease
rollback). A follow-up cleanup can drop it.

## Topic / Table dual write

Both already carry a single-valued `source` that drives downstream graph
behaviour (edge labelling, etc.). Phase 03 **adds** `sources = [source]` on
their writes so the phase-04 clear predicate is uniform across all labels.
Future readers should still use the single-valued `source` for semantic
queries.

## Edges

Edges don't need a multi-source list — they're cascaded by `DETACH DELETE`
when either endpoint is removed. No edge schema change.

## Tests

`tests/db/neo4j/test_sources_multi.py`:

1. `sync_stub_node(label="Shastra", nk="X", source="jainkosh")` → node has
   `sources = ['jainkosh']`.
2. Repeat with `source="nj"` → `sources` becomes `['jainkosh','nj']`
   (order-insensitive).
3. Repeat with `source="jainkosh"` again → still length 2.
4. `source=None` → leaves `sources` untouched.

## Manual verification

```cypher
// after a full both-source ingestion:
MATCH (s:Shastra {natural_key:'samaysaar'}) RETURN s.sources;
// → ['jainkosh','nj']

MATCH (g:Gatha) RETURN DISTINCT g.sources LIMIT 3;
// → [['nj']]
```

## Implementation notes

- Added `_sources_clause(var, param="src")` helper in both `stubs.py` and `upserts.py`; returns the CASE WHEN set-union Cypher fragment parameterised by node variable and param name.
- `sync_stub_node` gains `source: str | None = None`; `$src` param passed alongside existing `$stub_source`. The `stub_source` field is kept for one cycle (rollback safety) as specified.
- All upsert helpers (`sync_keyword`, `sync_shastra`, `sync_teeka`, `sync_publication`, `sync_kalash`, `sync_gatha`, `sync_gatha_teeka`, `sync_gatha_teeka_bhaavarth`, `sync_kalash_bhaavarth`) gain `source: str | None = None` and pass `src=source` to Cypher.
- `sync_topic` and `sync_table` are dual-write: their existing required `source: str` parameter is reused as the CASE WHEN param (`_sources_clause('t', 'source')` / `_sources_clause('t', 'source')`), so no new parameter is needed and `source` is never `None`.
- `sync_keyword` alias sub-query: renamed the existing `$src` param to `$alias_src` (the alias provenance field) to avoid collision with the new `$src` ingestion source param.
- All 13 new tests pass; full Neo4j suite (42 tests) passes with no regressions.
