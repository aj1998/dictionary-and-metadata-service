# Manual Testing Guide — MongoDB Data Model (doc 03)

This guide covers verifying the MongoDB collections, indexes, Pydantic schemas, and upsert layer by hand.

---

## Prerequisites

| Tool | Install |
|---|---|
| MongoDB 7 | `brew install mongodb-community@7.0 && brew services start mongodb-community@7.0` |
| `mongosh` | installed with MongoDB Community or `brew install mongosh` |
| Python 3.12 venv | already at `.venv/` |
| `jain-kb-common` installed | `pip install -e packages/jain_kb_common` |

Set the env var before every session:
```bash
export MONGO_URL="mongodb://localhost:27017"
```

---

## 1. Automated test suite

```bash
MONGO_URL="mongodb://localhost:27017" \
  .venv/bin/python -m pytest tests/db/mongo/ -v
```

Expected: **13 passed** (5 offline + 8 round-trip). Each round-trip test:
- Calls the same `upsert_*` function twice with the same `natural_key` but different field values on the second call.
- Asserts exactly **1 document** exists after both calls.
- Asserts stored values reflect the **second** call (update won).

Without `MONGO_URL`, 8 round-trip tests skip (`s`), 5 offline tests always pass.

---

## 2. Verify indexes are created

Connect with `mongosh` and check that `ensure_indexes` built all indexes:

```python
# In Python REPL
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from jain_kb_common.db.mongo.indexes import ensure_indexes

async def check():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["jain_kb_test"]
    await ensure_indexes(db)
    for col in ["gatha_prakrit", "gatha_sanskrit", "gatha_hindi_chhand",
                "gatha_word_meanings", "teeka_gatha_mapping",
                "keyword_definitions", "topic_extracts", "raw_html_snapshots"]:
        idxs = await db[col].index_information()
        print(col, list(idxs.keys()))
    client.close()

asyncio.run(check())
```

Expected output shows a `natural_key_1` (unique) index for every collection, plus compound indexes for `gatha_prakrit`, `gatha_hindi_chhand`, and `teeka_gatha_mapping`, and a text index for `topic_extracts`.

---

## 3. stable_id idempotency

```python
from jain_kb_common.db.mongo.upserts import stable_id

nk = "pravachansaar:039:prakrit"
print(stable_id(nk))   # e.g. ObjectId('a3f2...')
print(stable_id(nk))   # identical on every call
print(stable_id(nk) == stable_id(nk))  # True
```

Run the call from two separate Python processes — the `ObjectId` must be identical, proving that Postgres references to Mongo `_id` survive re-scrapes.

---

## 4. Manual upsert round-trip (Python REPL)

```bash
export MONGO_URL="mongodb://localhost:27017"
.venv/bin/python
```

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from jain_kb_common.db.mongo.upserts import upsert_keyword_definition, upsert_gatha_prakrit
from jain_kb_common.db.mongo.indexes import ensure_indexes

async def demo():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["jain_kb_dev"]
    await ensure_indexes(db)

    # Insert keyword definition
    nk = "आत्मा"
    doc = {
        "keyword_id": "test-uuid-001",
        "source_url": "https://www.jainkosh.org/wiki/आत्मा",
        "page_sections": [],
        "redirect_aliases": ["आतम"],
    }
    id1 = await upsert_keyword_definition(db, natural_key=nk, doc=doc)
    print("First insert:", id1)

    # Upsert again — new aliases
    doc2 = {**doc, "redirect_aliases": ["आतम", "आत्मन्"]}
    id2 = await upsert_keyword_definition(db, natural_key=nk, doc=doc2)
    print("Second upsert:", id2)
    print("Same _id?", id1 == id2)  # must be True

    count = await db.keyword_definitions.count_documents({"natural_key": nk})
    print("Document count:", count)  # must be 1

    stored = await db.keyword_definitions.find_one({"_id": id1})
    print("redirect_aliases:", stored["redirect_aliases"])  # ["आतम", "आत्मन्"]
    print("created_at:", stored["created_at"])
    print("updated_at:", stored["updated_at"])

    # Insert gatha_prakrit
    gid = await upsert_gatha_prakrit(db, natural_key="pravachansaar:039:prakrit", doc={
        "shastra_natural_key": "pravachansaar",
        "gatha_natural_key": "pravachansaar:039",
        "gatha_number": "039",
        "text": [{"lang": "pra", "script": "Deva",
                  "text": "जे णेव हि संजाया जे खलु णट्‌ठा भवीय पज्जया ।"}],
        "is_kalash": False,
    })
    print("gatha_prakrit _id:", gid)

    client.close()

asyncio.run(demo())
```

---

## 5. NFC normalization check

```python
import unicodedata
from jain_kb_common.db.mongo.schemas import LangText

# Construct with a string that may have decomposed Devanagari
raw = "ऩ"   # U+0928 (न) + U+093C (nukta) — decomposed form of ऩ
lt = LangText(lang="hin", script="Deva", text=raw)
print(lt.text == unicodedata.normalize("NFC", raw))  # True
```

---

## 6. created_at immutability

```python
import asyncio, time
from motor.motor_asyncio import AsyncIOMotorClient
from jain_kb_common.db.mongo.upserts import upsert_keyword_definition

async def test_timestamps():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["jain_kb_dev"]

    nk = "test:timestamps"
    doc = {"keyword_id": "x", "source_url": "http://x.com"}
    await upsert_keyword_definition(db, natural_key=nk, doc=doc)
    s1 = await db.keyword_definitions.find_one({"natural_key": nk})
    print("created_at:", s1["created_at"])
    print("updated_at:", s1["updated_at"])

    time.sleep(0.05)

    await upsert_keyword_definition(db, natural_key=nk, doc={**doc, "source_url": "http://y.com"})
    s2 = await db.keyword_definitions.find_one({"natural_key": nk})
    print("created_at unchanged:", s1["created_at"] == s2["created_at"])  # True
    print("updated_at changed:", s2["updated_at"] > s1["updated_at"])     # True

    client.close()

asyncio.run(test_timestamps())
```

---

## 7. Pydantic schema validation

```python
from jain_kb_common.db.mongo.schemas import (
    GathaPrakrit, GathaHindiChhand, GathaWordMeanings,
    TeekaGathaMapping, KeywordDefinition, TopicExtract,
    LangText, Block, PageSection, Subsection,
)

# Full keyword_definition with nested blocks
kd = KeywordDefinition(
    natural_key="आत्मा",
    keyword_id="uuid-001",
    source_url="https://www.jainkosh.org/wiki/आत्मा",
    page_sections=[
        PageSection(
            section_index=0,
            section_kind="siddhantkosh",
            heading=[LangText(lang="hin", script="Deva", text="सिद्धांतकोष से")],
            subsections=[
                Subsection(
                    subsection_index=1,
                    heading=[LangText(lang="hin", script="Deva", text="आत्मा के बहिरात्मादि 3 भेद")],
                    is_topic_seed=True,
                    topic_natural_key="jainkosh:आत्मा:बहिरात्मादि-3-भेद",
                    blocks=[
                        Block(kind="reference", ref_text="धवला पुस्तक 13/5,5,50/282/9"),
                        Block(kind="hindi", text=[LangText(lang="hin", script="Deva", text="बहिरात्मा…")]),
                        Block(kind="see_also", target_keyword="जीव", target_url="/wiki/जीव"),
                    ],
                )
            ],
        )
    ],
    redirect_aliases=["आतम", "आत्मन्"],
)
print("KeywordDefinition valid ✓")
print("sections:", len(kd.page_sections))
print("subsections:", len(kd.page_sections[0].subsections))
print("blocks:", len(kd.page_sections[0].subsections[0].blocks))
```

---

## 8. text index search (Devanagari)

After inserting at least one `topic_extract` with Hindi text in `blocks`:

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def text_search():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["jain_kb_dev"]

    # Insert a topic extract first
    from jain_kb_common.db.mongo.upserts import upsert_topic_extract
    await upsert_topic_extract(db, natural_key="jainkosh:आत्मा:test", doc={
        "topic_id": "t-001",
        "source": "jainkosh",
        "source_url": "http://example.com",
        "heading": [{"lang": "hin", "script": "Deva", "text": "बहिरात्मा"}],
        "blocks": [{"kind": "hindi", "text": [{"lang": "hin", "script": "Deva", "text": "बहिरात्मा की परिभाषा"}]}],
    })

    results = await db.topic_extracts.find(
        {"$text": {"$search": "बहिरात्मा"}}
    ).to_list(10)
    print("text search hits:", len(results))  # ≥ 1
    client.close()

asyncio.run(text_search())
```

---

## Notes

- The test fixture in `tests/db/mongo/test_mongo_upsert.py` drops all collections in `jain_kb_test` after each test function — it never touches `jain_kb_dev`.
- `MONGO_URL` must use the standard MongoDB URI format (`mongodb://host:port`). No auth needed for local dev.
- `ensure_indexes` is idempotent — safe to call multiple times; Motor skips creation if the index already exists with matching options.
- `stable_id` uses SHA-1 truncated to 12 bytes. Collision probability for typical `natural_key` counts (millions) is negligible.
