# Manual Testing — JainKosh Ingestion Apply Layer

Tests for `workers/ingestion/jainkosh/apply.py` —
`apply_approved_keyword_payload`. Requires all three databases running locally.

---

## Prerequisites

```bash
# Services running
brew services start postgresql@16
brew services start mongodb-community@7.0
/opt/homebrew/opt/neo4j/bin/neo4j start   # or brew services start neo4j

# Env vars
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
```

---

## 1. Run the automated integration tests

```bash
python -m pytest tests/ingestion/ -v
```

Expected output (12 tests, 11 pass, 1 skip):

```
PASSED  tests/ingestion/test_apply.py::test_apply_idempotent_full_envelope[आत्मा-...]
PASSED  tests/ingestion/test_apply.py::test_apply_idempotent_full_envelope[द्रव्य-...]
PASSED  tests/ingestion/test_apply.py::test_apply_idempotent_full_envelope[पर्याय-...]
PASSED  tests/ingestion/test_apply.py::test_apply_idempotent_full_envelope[वस्तु-...]
PASSED  tests/ingestion/test_apply.py::test_apply_topics_parents_first[आत्मा-...]
PASSED  tests/ingestion/test_apply.py::test_apply_topics_parents_first[द्रव्य-...]
PASSED  tests/ingestion/test_apply.py::test_apply_topics_parents_first[पर्याय-...]
SKIPPED tests/ingestion/test_apply.py::test_apply_topics_parents_first[वस्तु-...]  # no sub-topics
PASSED  tests/ingestion/test_apply.py::test_apply_alias_dedup[आत्मा-...]
PASSED  tests/ingestion/test_apply.py::test_apply_alias_dedup[द्रव्य-...]
PASSED  tests/ingestion/test_apply.py::test_apply_alias_dedup[पर्याय-...]
PASSED  tests/ingestion/test_apply.py::test_apply_alias_dedup[वस्तु-...]
```

---

## 2. Full end-to-end from REPL

Parse a sample HTML file, build the envelope, and apply it manually.

```python
import asyncio, os
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.apply import apply_approved_keyword_payload

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints

async def main():
    # --- Parse ---
    config = load_config()
    html = open("workers/ingestion/jainkosh/tests/fixtures/आत्मा.html", encoding="utf-8").read()
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
    envelope = build_envelope(result).model_dump()
    print("Topics in envelope:", len(envelope["would_write"]["postgres"]["topics"]))

    # --- DB connections ---
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["jain_kb_manual"]
    driver = get_driver(os.environ["NEO4J_URL"], os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    await ensure_constraints(driver, database="neo4j")

    # --- Apply (twice to verify idempotency) ---
    async with Session() as session:
        await apply_approved_keyword_payload(
            envelope=envelope, pg_session=session,
            mongo_db=mongo, neo4j_driver=driver, neo4j_database="neo4j",
        )
        print("First apply done.")
        await apply_approved_keyword_payload(
            envelope=envelope, pg_session=session,
            mongo_db=mongo, neo4j_driver=driver, neo4j_database="neo4j",
        )
        print("Second apply done — no errors means idempotent.")

    await close_driver()
    await engine.dispose()
    mongo.client.close()

asyncio.run(main())
```

---

## 3. Verify Postgres rows

```bash
psql $DATABASE_URL -c "SELECT natural_key, topic_path, is_leaf, is_synthetic FROM topics LIMIT 20;"
psql $DATABASE_URL -c "SELECT natural_key, alias_text, source FROM keyword_aliases;"
```

Spot-checks:
- `आत्मा` keyword row exists in `keywords`.
- Topic rows have `topic_path` set (e.g. `1`, `1.1`, `2`, …).
- Root topics have `parent_topic_id = NULL`; child topics have it populated.
- `keyword_aliases` has `(keyword_id, alias_text)` uniqueness — inserting a
  duplicate alias a second time silently does nothing.

---

## 4. Verify MongoDB documents

```bash
mongosh jain_kb_manual --eval "db.keyword_definitions.findOne({}, {natural_key:1, page_sections:1})"
mongosh jain_kb_manual --eval "db.topic_extracts.countDocuments({})"
mongosh jain_kb_manual --eval "db.topic_extracts.findOne({}, {natural_key:1, topic_path:1, is_leaf:1})"
```

---

## 5. Verify Neo4j graph

Open the Neo4j Browser at `http://localhost:7474` and run:

```cypher
// All Topic nodes for आत्मा
MATCH (t:Topic {parent_keyword_natural_key: 'आत्मा'})
RETURN t.natural_key, t.topic_path, t.is_leaf LIMIT 30;

// PART_OF hierarchy
MATCH p=(child:Topic)-[:PART_OF]->(parent:Topic)
RETURN p LIMIT 20;

// Keyword node
MATCH (k:Keyword {natural_key: 'आत्मा'}) RETURN k;
```

---

## 6. Regression: run all tests

```bash
python -m pytest tests/ workers/ingestion/jainkosh/tests/ -v
```

All tests (parser + DB + ingestion apply) should be green.
