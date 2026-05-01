# Manual Testing Guide — Postgres Data Model (doc 02)

This guide covers verifying the Postgres schema, migrations, and upsert layer by hand.

---

## Prerequisites

| Tool | Install |
|---|---|
| PostgreSQL 16 | `brew install postgresql@16 && brew services start postgresql@16` |
| Python 3.12 venv | already at `.venv/` |
| `jain-kb-common` installed | `pip install -e packages/jain_kb_common` |
| Test database | `psql postgres -c "CREATE DATABASE jain_kb_test;"` |

Set the env var before every session:
```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
```

---

## 1. Automated test suite

```bash
DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test" \
  .venv/bin/python -m pytest tests/ -v
```

Expected: **8 passed**. Each test:
- Calls the same `upsert_*` function twice with the same `natural_key` but different field values on the second call.
- Asserts exactly **1 row** exists after both calls.
- Asserts the stored values reflect the **second** call (i.e., the update won).

Without `DATABASE_URL`, all 8 tests skip gracefully (`s` not `E`).

---

## 2. Running Alembic migrations against a fresh database

Create a fresh database (separate from the test DB to avoid conftest teardown conflicts):

```bash
psql postgres -c "CREATE DATABASE jain_kb_dev;"
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
```

Run all migrations:
```bash
.venv/bin/alembic upgrade head
```

Expected output: 9 migration steps, no errors.

Verify tables exist:
```bash
psql jain_kb_dev -c "\dt"
```

Expected tables (15 total):
```
authors, shastras, anuyogas, shastra_anuyogas, teekas, books, book_anuyogas,
pravachans, keywords, keyword_aliases, gathas, topics, topic_mentions,
parser_configs, ingestion_runs, ingestion_review_queue,
topic_candidates, chat_puller_state, query_logs
```

Verify enums:
```bash
psql jain_kb_dev -c "SELECT typname, enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid ORDER BY typname, enumlabel;"
```

Verify anuyoga seed (from migration 0002):
```bash
psql jain_kb_dev -c "SELECT kind, display_name FROM anuyogas;"
```

Expected: 4 rows — prathmanuyoga, karananuyoga, charananuyoga, dravyanuyoga, each with Hindi + English labels.

---

## 3. Verify indexes

```bash
psql jain_kb_dev -c "\di"
```

Key indexes to spot:
- `idx_keywords_text_trgm` — GIN with `gin_trgm_ops` on `keywords.display_text`
- `idx_keyword_aliases_alias_trgm` — GIN with `gin_trgm_ops` on `keyword_aliases.alias_text`
- `idx_gathas_keyword_ids` — GIN with `jsonb_path_ops` on `gathas.keyword_ids`
- `idx_gathas_topic_ids` — GIN with `jsonb_path_ops` on `gathas.topic_ids`

---

## 4. Manual upsert round-trip (psql)

```bash
psql jain_kb_dev
```

### Insert an author twice, confirm idempotency:
```sql
-- First insert
INSERT INTO authors (natural_key, display_name, kind)
VALUES (
  'kundkundacharya',
  '[{"lang":"hi","script":"devanagari","text":"कुन्दकुन्द"}]',
  'acharya'
)
ON CONFLICT (natural_key) DO UPDATE
  SET display_name = EXCLUDED.display_name, updated_at = now();

-- Verify
SELECT id, natural_key, kind FROM authors;

-- Second upsert (same key, different kind)
INSERT INTO authors (natural_key, display_name, kind)
VALUES (
  'kundkundacharya',
  '[{"lang":"hi","script":"devanagari","text":"कुन्दकुन्द आचार्य"}]',
  'gyaani'
)
ON CONFLICT (natural_key) DO UPDATE
  SET display_name = EXCLUDED.display_name, kind = EXCLUDED.kind, updated_at = now();

-- Must still be 1 row, kind should be 'gyaani'
SELECT count(*), kind FROM authors WHERE natural_key = 'kundkundacharya' GROUP BY kind;
```

### Verify `updated_at` trigger fires:
```sql
SELECT created_at, updated_at FROM authors WHERE natural_key = 'kundkundacharya';
-- updated_at should be later than created_at after the second upsert
```

---

## 5. Manual upsert via Python REPL

```bash
.venv/bin/python
```

```python
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from jain_kb_common.db.postgres.upserts import upsert_author, upsert_keyword
from jain_kb_common.db.postgres.enums import AuthorKind

URL = os.environ["DATABASE_URL"]
engine = create_async_engine(URL, echo=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def demo():
    async with Session() as s:
        aid = await upsert_author(
            s,
            natural_key="test-author",
            display_name=[{"lang": "hi", "text": "परीक्षण"}],
            kind=AuthorKind.scholar,
        )
        await s.commit()
        print("author id:", aid)

        kid = await upsert_keyword(
            s,
            natural_key="परीक्षण",
            display_text="परीक्षण",
            definition_doc_ids=["mongo-abc-123"],
        )
        await s.commit()
        print("keyword id:", kid)

asyncio.run(demo())
```

With `echo=True` you'll see the exact SQL issued, including `ON CONFLICT DO UPDATE`.

---

## 6. Rollback / downgrade test

```bash
.venv/bin/alembic downgrade base
```

All tables and types should be dropped. Then re-apply:
```bash
.venv/bin/alembic upgrade head
```

---

## 7. Fuzzy search index smoke test

After inserting a keyword:
```sql
SELECT display_text FROM keywords
WHERE display_text % 'आत्म';  -- pg_trgm similarity match
```

This uses the `gin_trgm_ops` index and should work once at least one keyword whose text is similar to `आत्म` exists.

---

## 8. `topic_mentions` CHECK constraint

Verify that inserting a row with zero or two source refs is rejected:
```sql
-- Should fail: no source set
INSERT INTO topic_mentions (topic_id)
VALUES ('00000000-0000-0000-0000-000000000001');

-- Should fail: two sources set
INSERT INTO topic_mentions (topic_id, teeka_id, gatha_id)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000003'
);
```

Both should raise `ERROR: new row ... violates check constraint "chk_topic_mention_single_source"`.

---

## 9. `chat_puller_state` singleton constraint

```sql
-- First insert works
INSERT INTO chat_puller_state (id) VALUES (1);

-- Second insert should fail (PK collision)
INSERT INTO chat_puller_state (id) VALUES (1);

-- Non-1 id should fail (CHECK violation)
INSERT INTO chat_puller_state (id) VALUES (2);
```

---

## Notes

- The test fixture in `tests/conftest.py` creates and drops all tables (plus PG enum types) around each test function. It does NOT use Alembic migrations — it uses SQLAlchemy's `create_all`/`drop_all`. This means schema changes must be reflected in both the models and the migration files.
- `DATABASE_URL` uses the `postgresql+asyncpg://` scheme for async connections.
- The `jain_kb_dev` database is for manual/migration testing. The `jain_kb_test` database is for the automated pytest suite.
