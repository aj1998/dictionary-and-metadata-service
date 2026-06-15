# Phase 02 — Wire source through ingestion apply layers

Read [overview](00_overview.md) and complete [phase 01](01_pg_schema_and_upserts.md) first.

## Files touched

- [`workers/ingestion/jainkosh/apply.py`](../../../../workers/ingestion/jainkosh/apply.py)
- [`workers/ingestion/nj/apply.py`](../../../../workers/ingestion/nj/apply.py)

Both modules call the upserts updated in phase 01. The change is mechanical:
pass `source=IngestionSource.jainkosh` or `source=IngestionSource.nj` to
every entity upsert.

## jainkosh apply (`workers/ingestion/jainkosh/apply.py`)

Pass `source=IngestionSource.jainkosh` to:

- `upsert_keyword`
- `upsert_author` (when jainkosh seeds an author from a wiki page)
- `upsert_shastra` (lazy stub from a reference cite)
- `upsert_teeka` (lazy stub)
- `upsert_publication` (lazy stub)
- `upsert_book` / `upsert_pravachan` if/when jainkosh stubs them

`upsert_topic` and `upsert_table` already pass
`source=IngestionSource.jainkosh` via their existing single-valued
`source` — leave unchanged.

## nj apply (`workers/ingestion/nj/apply.py`)

Pass `source=IngestionSource.nj` to:

- `upsert_author`
- `upsert_shastra`
- `upsert_teeka`
- `upsert_teeka_chapter`
- `upsert_publication`
- `upsert_gatha`
- `upsert_kalash`
- `upsert_keyword` (if/when nj writes any — currently nj does not, but the
  parameter is added defensively)

## Tests

`tests/ingestion/jainkosh/test_apply_sources.py`:

1. Apply one jainkosh golden → assert every newly-created `keywords`,
   `shastras`, `teekas` row has `sources = ['jainkosh']`.

`tests/ingestion/nj/test_apply_sources.py`:

1. Apply one nj shastra → assert `gathas`, `kalashas`, `teeka_chapters`,
   `publications` have `sources = ['nj']`; `shastras`, `teekas`, `authors`
   have `sources` containing `'nj'`.

`tests/ingestion/test_cross_source_union.py`:

1. Apply jainkosh golden that lazy-stubs `samaysaar` (`sources = ['jainkosh']`).
2. Apply nj `samaysaar` → re-fetch row: `sources = {'jainkosh','nj'}`.
3. Re-apply jainkosh → still `{'jainkosh','nj'}` (no duplicate).

## Manual verification

```bash
python scripts/clear_dbs.py
python scripts/ingest_goldens_apply.py --shastra-hierarchy
python scripts/ingest_nj_apply.py --all

psql jain_kb_dev -c "
  SELECT natural_key, sources FROM shastras ORDER BY natural_key;
  SELECT natural_key, sources FROM teekas   ORDER BY natural_key;
"
```

Expect `samaysaar` and other shastras referenced by goldens to show
`{jainkosh,nj}`; nj-only shastras to show `{nj}`.

## Implementation notes

…
