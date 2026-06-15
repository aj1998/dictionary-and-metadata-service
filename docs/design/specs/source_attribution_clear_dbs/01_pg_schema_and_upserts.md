# Phase 01 — Postgres schema + upsert merge

Read [overview](00_overview.md) first.

## Tables that get a new `sources` column

`authors`, `shastras`, `teekas`, `gathas`, `kalashas`, `publications`,
`teeka_chapters`, `books`, `pravachans`, `keywords`.

Link tables (`shastra_anuyogas`, `book_anuyogas`, `keyword_aliases`) inherit
provenance from their parent and are deleted via `ON DELETE CASCADE` already
present in the schema — no column change.

## Alembic migration — `migrations/0024_add_sources.py`

```sql
ALTER TABLE authors        ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE shastras       ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE teekas         ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE gathas         ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE kalashas       ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE publications   ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE teeka_chapters ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE books          ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE pravachans     ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];
ALTER TABLE keywords       ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{}'::text[];

CREATE INDEX idx_authors_sources        ON authors        USING gin (sources);
CREATE INDEX idx_shastras_sources       ON shastras       USING gin (sources);
CREATE INDEX idx_teekas_sources         ON teekas         USING gin (sources);
CREATE INDEX idx_gathas_sources         ON gathas         USING gin (sources);
CREATE INDEX idx_kalashas_sources       ON kalashas       USING gin (sources);
CREATE INDEX idx_publications_sources   ON publications   USING gin (sources);
CREATE INDEX idx_teeka_chapters_sources ON teeka_chapters USING gin (sources);
CREATE INDEX idx_books_sources          ON books          USING gin (sources);
CREATE INDEX idx_pravachans_sources     ON pravachans     USING gin (sources);
CREATE INDEX idx_keywords_sources       ON keywords       USING gin (sources);
```

`downgrade()` drops indexes + columns.

### Backfill (inside the migration, after `ADD COLUMN`)

Best-effort: stamp rows that obviously belong to one ingestor.

```sql
-- jainkosh-only artefacts: keywords always start there
UPDATE keywords SET sources = ARRAY['jainkosh'];

-- nj-only artefacts: gathas, kalashas, teeka_chapters, publications are nj-exclusive
UPDATE gathas         SET sources = ARRAY['nj'];
UPDATE kalashas       SET sources = ARRAY['nj'];
UPDATE teeka_chapters SET sources = ARRAY['nj'];
UPDATE publications   SET sources = ARRAY['nj'];

-- co-owned: shastras / teekas / authors. Mark with both if a matching
-- ingestion_runs row exists; else leave empty so the next ingestion stamps it.
UPDATE shastras SET sources =
  (SELECT array_agg(DISTINCT source::text)
   FROM ingestion_runs WHERE source IN ('jainkosh','nj'))
  WHERE TRUE;
UPDATE teekas   SET sources =
  (SELECT array_agg(DISTINCT source::text)
   FROM ingestion_runs WHERE source IN ('jainkosh','nj'))
  WHERE TRUE;
UPDATE authors  SET sources =
  (SELECT array_agg(DISTINCT source::text)
   FROM ingestion_runs WHERE source IN ('jainkosh','nj'))
  WHERE TRUE;
```

`books`, `pravachans` likely have no production rows yet; leave empty.

## SQLAlchemy model edits

For each of the ten models add:

```python
from sqlalchemy import ARRAY
sources: Mapped[list[str]] = mapped_column(
    ARRAY(Text), nullable=False, server_default=sa.text("'{}'::text[]")
)
```

## Upsert merge helper — `packages/jain_kb_common/db/postgres/upserts.py`

Add a private SQL builder used by every refactored upsert:

```python
from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import array

def _merge_sources(col, new_source: str | None):
    """Return SQL expression: distinct union of existing sources and new one.

    Pass None to leave sources untouched (re-sync from graph_sync).
    """
    if new_source is None:
        return col
    return func.array(
        func.unnest(func.array_cat(col, array([new_source])))
    ).distinct()
```

(Concrete implementation uses a CTE or `array(SELECT DISTINCT unnest(...))`;
exact form chosen during impl — both work in pg_insert SET clauses.)

Update each `upsert_*` for the ten tables:

- Add kwarg `source: IngestionSource | None = None`.
- In the INSERT `.values(...)` add `sources=[source.value] if source else []`.
- In `on_conflict_do_update` `set_={...}` add
  `"sources": _merge_sources(Model.sources, source.value if source else None)`.

Leave `upsert_topic` / `upsert_table` untouched (they keep their existing
single-valued `source`).

## Tests — `tests/db/postgres/test_sources_merge.py`

1. **Initial insert stamps source.** Upsert a new `keyword(source=jainkosh)`
   → `sources == ['jainkosh']`.
2. **Re-upsert same source is idempotent.** Repeating step 1 keeps
   `sources == ['jainkosh']` (no duplicates, length 1).
3. **Different-source upsert unions.** Upsert a `shastra` with
   `source=jainkosh`, then again with `source=nj` → `sources` is the set
   `{jainkosh, nj}` (order-insensitive comparison).
4. **`source=None` leaves sources untouched.** Pre-stamp `['nj']`, re-upsert
   without source → still `['nj']`.
5. **Migration backfill** (in `tests/migrations/test_0024_backfill.py`):
   seed the previous-revision schema with sample rows, run upgrade, assert
   the heuristic populated the expected values.

Run `DATABASE_URL=…jain_kb_test pytest tests/db/postgres/test_sources_merge.py -v`.

## Manual verification

```sql
-- After phase 01 + a re-run of both ingestions:
SELECT natural_key, sources FROM shastras WHERE natural_key='samaysaar';
--  → {jainkosh,nj}
SELECT natural_key, sources FROM keywords LIMIT 3;
--  → {jainkosh}
SELECT natural_key, sources FROM gathas LIMIT 3;
--  → {nj}
```

## Implementation notes (to be filled in by the implementer)

…
