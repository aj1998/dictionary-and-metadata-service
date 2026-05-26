# Wiki: NikkYJain Ingestion (`workers/ingestion/nj/envelope.py`, `apply.py`)

Source design doc: `docs/design/data_sources/nikkyjain/02_ingestion_nj.md`

---

## What it does

Maps a `ShastraParseResult` (produced by the NJ parser — see `docs/wiki/nj_parser.md`) into Postgres, MongoDB, and Neo4j. The ingestion layer is also config-driven; no shastra identity is hard-coded here.

Two main components:
- **`envelope.py`** — `build_envelope(result, cfg)` builds a structured preview (golden JSON) of all DB writes without touching any DB.
- **`apply.py`** — `apply_nj_shastra_payload(envelope, pg_session, mongo_db, neo4j_driver, ...)` executes all writes idempotently.

---

## Natural key conventions

All label segments in natural keys use **Hindi words** (matching JainKosh style).

Label constants defined in `envelope.py`:
- `गाथा` — gatha label
- `कलश` — kalash label
- `टीका` — teeka content label (in compound keys, distinct from the teeka NK itself)
- `भावार्थ` — bhaavarth label
- `अध्याय` — chapter label

### Postgres entity natural keys

| Entity | Pattern | Samaysar example |
|---|---|---|
| Shastra | `{shastra_nk}` | `समयसार` |
| Author | `{author_nk}` | `कुन्दकुन्दाचार्य` |
| Primary teekakar | `{teekakar_a_nk}` | `अमृतचंद्राचार्य` |
| Secondary teekakar | `{teekakar_j_nk}` | `जयसेनाचार्य` |
| Primary teeka | `{teeka_a_nk}` | `समयसार:आत्मख्याति` |
| Secondary teeka | `{teeka_j_nk}` | `समयसार:तात्पर्यवृत्ति` |
| Primary publication | `{pub_a_nk}` | `समयसार:आत्मख्याति:0` |
| Secondary publication | `{pub_j_nk}` | `समयसार:तात्पर्यवृत्ति:0` |
| Gatha | `{shastra_nk}:गाथा:{N}` | `समयसार:गाथा:1` (no leading zeros) |
| Primary kalash | `{teeka_a_nk}:कलश:{N}` | `समयसार:आत्मख्याति:कलश:1` |
| Secondary kalash | `{teeka_j_nk}:कलश:{N}` | `समयसार:तात्पर्यवृत्ति:कलश:11` |
| Teeka chapter | `{teeka_a_nk}:अध्याय:{N}` | `समयसार:आत्मख्याति:अध्याय:1` |

**Number normalization**: leading zeros are stripped everywhere (`"001"` → `"1"`). Applied by `_norm_num()` in `envelope.py`.

**Publisher ID**: numeric string `"0"` for nikkyjain (not the ASCII string `"nikkyjain"`).

### MongoDB doc natural keys

| Collection | Pattern |
|---|---|
| `gatha_prakrit` | `{gatha_nk}:prakrit` |
| `gatha_sanskrit` | `{gatha_nk}:sanskrit` |
| `gatha_hindi_chhand` | `{gatha_nk}:chhand:{N}` |
| `teeka_gatha_mapping` (primary only) | `{teeka_a_nk}:{gatha_number}` |
| `gatha_teeka_sanskrit` (primary) | `{teeka_a_nk}:{gatha_number}:टीका:san` |
| `gatha_teeka_sanskrit` (secondary) | `{teeka_j_nk}:{gatha_number}:टीका:san` |
| `gatha_teeka_bhaavarth_hindi` (primary) | `{pub_a_nk}:{gatha_number}:भावार्थ:hi` |
| `gatha_teeka_bhaavarth_hindi` (secondary) | `{pub_j_nk}:{gatha_number}:भावार्थ:hi` |
| `kalash_sanskrit` | `{kalash_a_nk}:san` |
| `kalash_hindi` | `{kalash_a_nk}:hi` |
| `kalash_word_meanings` | `{kalash_a_nk}:word_meanings` |

For **secondary-only kalash pages**, `{gatha_nk}` in `gatha_prakrit` is replaced by `{kalash_j_nk}`.

---

## Postgres write order (FK dependency)

```
1. upsert authors        (text author + teekakar authors)
2. upsert shastra
3. upsert teekas
4. upsert publications
5. upsert gathas         (one per GathaExtract after multi-page expansion)
6. upsert primary kalashas  (global counter order; gatha_id FK required)
7. upsert secondary kalashas (gatha_id → preceding primary gatha)
8. upsert teeka_chapters    (grouped by adhikaar_number; primary teeka only)
```

`apply.py` builds a `gatha_nk → uuid` cache from step 5 to resolve FK references in steps 6–8 without extra queries.

### `teeka_chapters` table

Migration `0019_teeka_chapters.py`. Chapters are groups of gathas within the same `adhikaar_number` from `myItem.js`. Only primary teeka is chaptered.

- `natural_key`: `{teeka_a_nk}:अध्याय:{adhikaar_number}`
- `start_gatha_natural_key` / `end_gatha_natural_key` = first/last gathas in the adhikaar batch
- Gathas with `adhikaar_number = None` are skipped

---

## MongoDB write collections

| Collection | Condition |
|---|---|
| `gatha_prakrit` | Always (even if `prakrit_text` is None, doc is written with null text) |
| `gatha_sanskrit` | Only if `extract.sanskrit_text is not None` |
| `gatha_hindi_chhand` | One doc per chhand; skipped if `hindi_chhands = []` |
| `gatha_word_meanings` | Always; `full_anyavaarth` required, `entries` may be empty |
| `teeka_gatha_mapping` | Primary teeka only; `is_related` populated for multi-gatha pages |
| `gatha_teeka_sanskrit` | Only if `gatha_teeka_san` is non-None |
| `gatha_teeka_bhaavarth_hindi` | Only if `gatha_teeka_bhaavarth_md` is non-empty |
| `kalash_sanskrit` | One per primary kalash |
| `kalash_hindi` | One per primary kalash with Hindi text |
| `kalash_word_meanings` | Only if kalash has maroon-color word meanings; skipped if entries = [] |

**`teeka_gatha_mapping` note**: only the **primary** teeka gets a mapping doc. Secondary teeka serves a different ingestion path.

**Multi-gatha pages**: both `teeka_gatha_mapping` and `gatha_teeka_*` docs are written once per individual gatha (duplicate content with different natural keys). `is_related` field lists the other gathas from the same combined page.

---

## Neo4j graph

### Node labels and key patterns

| Label | Key pattern | Samaysar example |
|---|---|---|
| `Shastra` | `{shastra_nk}` | `समयसार` |
| `Teeka` | `{teeka_nk}` | `समयसार:आत्मख्याति` |
| `Publication` | `{pub_nk}` | `समयसार:आत्मख्याति:0` |
| `Topic` | heading text (deduplicated) | `सिद्धों को नमस्कार` |
| `Gatha` | `{shastra_nk}:गाथा:{N}` | `समयसार:गाथा:1` |
| `GathaTeeka` | `{teeka_nk}:गाथा:टीका:{N}` | `समयसार:आत्मख्याति:गाथा:टीका:1` |
| `GathaTeekaBhaavarth` | `{pub_nk}:गाथा:टीका:भावार्थ:{N}` | `समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:1` |
| `Kalash` | `{teeka_nk}:कलश:{N}` | `समयसार:आत्मख्याति:कलश:1` |
| `KalashBhaavarth` | `{pub_nk}:कलश:भावार्थ:{N}` | `समयसार:आत्मख्याति:0:कलश:भावार्थ:1` |

### Edge types

| Edge | From | To |
|---|---|---|
| `HAS_TEEKA` | Shastra | Teeka |
| `HAS_PUBLICATION` | Teeka | Publication |
| `HAS_PUBLICATION` | Shastra | Publication |
| `MENTIONS_TOPIC` | Gatha | Topic |
| `HAS_GATHA_TEEKA` | Teeka | GathaTeeka |
| `HAS_BHAAVARTH` | Publication | GathaTeekaBhaavarth |
| `HAS_KALASH` | Teeka | Kalash |
| `HAS_BHAAVARTH` | Publication | KalashBhaavarth |

Topic nodes are **deduplicated** by `heading_hi` text. No `MENTIONS_TOPIC` edge is emitted for gathas with `heading_hi = None`.

---

## Idempotency

All DB writes are idempotent:
- Postgres: `ON CONFLICT (natural_key) DO UPDATE`
- MongoDB: `update_one({"natural_key": ...}, ..., upsert=True)`
- Neo4j: `MERGE` on `key` property

Running the apply script twice produces identical row/document counts.

The envelope also exposes `idempotency_contracts` — a list of 25 contracts (one per collection/label) with `conflict_key`, `on_conflict`, `fields_replace`, and `stores` metadata. Used for verification and future tooling.

---

## `apply.py` function signature

```python
async def apply_nj_shastra_payload(
    *,
    envelope: dict,
    pg_session: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    neo4j_driver: AsyncDriver,
    neo4j_database: str = "neo4j",
    ingestion_run_id: str | None = None,
) -> None
```

All strings are NFC-normalized on entry. Writes happen in the FK dependency order shown above. Safe to call multiple times (idempotent throughout).

---

## Envelope structure (`build_envelope` output)

```json
{
  "shastra_parse_result": { ... },     // raw ShastraParseResult
  "would_write": {
    "postgres": [ ... ],               // list of {table, row} objects
    "mongo": [ ... ],                  // list of {collection, doc} objects
    "neo4j": {
      "nodes": [ ... ],                // {label, key, props}
      "edges": [ ... ]                 // {type, from_key, to_key}
    },
    "idempotency_contracts": [ ... ]   // 25 contracts
  }
}
```

---

## Running the apply script

```bash
export DATABASE_URL="postgresql+asyncpg://..."
export MONGO_URL="mongodb://localhost:27017"
export MONGO_DB_NAME="jain_kb"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export NIKKYJAIN_LOCAL_PATH="/path/to/nikkyjain.github.io"

# Dry run (parse + print summary, no DB writes)
python scripts/ingest_nj_apply.py \
  --config parser_configs/nj/samaysaar.yaml \
  --dry-run

# Apply single gatha (for testing)
python scripts/ingest_nj_apply.py \
  --config parser_configs/nj/samaysaar.yaml \
  --gatha 001

# Full apply
python scripts/ingest_nj_apply.py \
  --config parser_configs/nj/samaysaar.yaml
```

---

## Tests

```bash
# Unit tests — no DB required
python -m pytest tests/workers/nj/test_envelope.py -v
python -m pytest tests/workers/nj/test_apply_unit.py -v

# Full NJ suite
python -m pytest tests/workers/nj/ -v
# Expected: 72 passed
```

`test_apply_unit.py` covers (16 tests):
- NFC normalization of envelope strings
- Envelope structure completeness
- Postgres row field requirements (gatha_natural_key on kalashes, start/end on chapters)
- Idempotency of `build_envelope`
- `stable_id` determinism
- Multi-gatha merge (`is_related` population, separate docs per gatha)
- Cross-source merge (NJ × JK): gatha NKs are consistent

`test_envelope.py` covers:
- `gatha_word_meanings` absent from mongo section
- `teeka_gatha_mapping` primary-only assertion
- Neo4j Shastra / Topic / Gatha nodes and `MENTIONS_TOPIC` edges
- `teeka_chapters` grouping, name format, null-adhikaar skip
- Secondary kalash `gatha_natural_key` uses last gatha number from combined page
- `table`/`collection` fields on all rows/docs
- 25 idempotency contracts with all required fields

---

## Known open items

- **Cross-source Gatha NK (NJ × JK)**: NJ emits `समयसार:गाथा:8`; JK lazy GathaTeeka stubs may still derive `समयसार:8`. JK parser must adopt the `गाथा` label for cross-source MERGE to work.
- **`ingest_nj_apply.py` script**: specified in `§5` of the design doc; a thin async wrapper around `apply.py` that reads env vars and accepts `--dry-run`/`--gatha` flags. Status: partially wired; verify before production use.
- **DB integration tests**: `test_apply_unit.py` is unit-based. Live DB integration tests are deferred; add under `--run-db-tests` flag when CI DB environment is available.
- **Golden files**: regenerate with `python -m workers.ingestion.nj.cli parse --config parser_configs/nj/samaysaar.yaml --format golden` (requires `NIKKYJAIN_LOCAL_PATH`).
