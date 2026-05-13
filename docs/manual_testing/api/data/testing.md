# Manual Testing Guide — Data Service API (`docs/design/api/data/01_spec.md`)

This guide covers starting the service locally and verifying every endpoint group by hand using `curl`. The data service is read-heavy — keywords, gathas, topics, and kalashas are written by the ingestion pipeline, not by this service. This guide seeds minimal data directly via SQL so every endpoint can be exercised without a full ingestion run.

---

## Prerequisites

| Tool | Version / Install |
|---|---|
| PostgreSQL 16 running | `brew services start postgresql@16` |
| MongoDB 7 running | `brew services start mongodb-community@7.0` |
| `jain_kb_dev` database migrated | `alembic upgrade head` |
| Python venv activated | `source .venv/bin/activate` |
| `fastapi`, `uvicorn`, `pydantic-settings`, `motor` installed | `pip install -e ".[dev]"` |

---

## 1. Start the service

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export MONGO_URL="mongodb://localhost:27017"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"

uvicorn services.data_service.main:app --port 8002 --reload
```

Confirm it's up:

```bash
curl -s http://localhost:8002/healthz
# {"status":"ok"}
```

OpenAPI schema (all 19 routes listed):

```bash
curl -s http://localhost:8002/openapi.json | python -m json.tool | head -40
```

---

## 2. Seed test data

The data service reads what the ingestion pipeline writes. For manual testing, insert rows directly into Postgres and documents into MongoDB.

### 2a. Seed Postgres rows

```bash
psql "postgresql://$(whoami)@localhost/jain_kb_dev" <<'SQL'

-- Author
INSERT INTO authors (id, natural_key, display_name, kind)
VALUES (
  gen_random_uuid(),
  'kundkundacharya',
  '[{"lang":"hin","script":"Deva","text":"कुन्दकुन्दाचार्य"}]',
  'acharya'
) ON CONFLICT (natural_key) DO NOTHING;

-- Teekakar
INSERT INTO authors (id, natural_key, display_name, kind)
VALUES (
  gen_random_uuid(),
  'amritchandracharya',
  '[{"lang":"hin","script":"Deva","text":"अमृतचन्द्राचार्य"}]',
  'acharya'
) ON CONFLICT (natural_key) DO NOTHING;

-- Shastra
INSERT INTO shastras (id, natural_key, title, author_id)
VALUES (
  gen_random_uuid(),
  'pravachansaar',
  '[{"lang":"hin","script":"Deva","text":"प्रवचनसार"}]',
  (SELECT id FROM authors WHERE natural_key = 'kundkundacharya')
) ON CONFLICT (natural_key) DO NOTHING;

-- Teeka
INSERT INTO teekas (id, natural_key, shastra_id, teekakar_id)
VALUES (
  gen_random_uuid(),
  'pravachansaar:amritchandra',
  (SELECT id FROM shastras WHERE natural_key = 'pravachansaar'),
  (SELECT id FROM authors WHERE natural_key = 'amritchandracharya')
) ON CONFLICT (natural_key) DO NOTHING;

-- Two gathas
INSERT INTO gathas (id, natural_key, shastra_id, gatha_number, adhikaar, heading)
VALUES
  (
    gen_random_uuid(),
    'pravachansaar:001',
    (SELECT id FROM shastras WHERE natural_key = 'pravachansaar'),
    '001',
    '[{"lang":"hin","script":"Deva","text":"ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}]',
    '[{"lang":"hin","script":"Deva","text":"परमार्थ आत्मा का निरूपण"}]'
  ),
  (
    gen_random_uuid(),
    'pravachansaar:039',
    (SELECT id FROM shastras WHERE natural_key = 'pravachansaar'),
    '039',
    '[{"lang":"hin","script":"Deva","text":"ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}]',
    '[{"lang":"hin","script":"Deva","text":"भूत-भावि पर्यायों की असद्भूत संज्ञा"}]'
  )
ON CONFLICT (natural_key) DO NOTHING;

-- Kalash
INSERT INTO kalashas (id, natural_key, teeka_id, kalash_number)
VALUES (
  gen_random_uuid(),
  'pravachansaar:amritchandra:kalash:001',
  (SELECT id FROM teekas WHERE natural_key = 'pravachansaar:amritchandra'),
  '001'
) ON CONFLICT (natural_key) DO NOTHING;

-- Keyword
INSERT INTO keywords (id, natural_key, display_text, source_url, definition_doc_ids)
VALUES (
  gen_random_uuid(),
  'आत्मा',
  'आत्मा',
  'https://www.jainkosh.org/wiki/%E0%A4%86%E0%A4%A4%E0%A5%8D%E0%A4%AE%E0%A4%BE',
  '[]'
) ON CONFLICT (natural_key) DO NOTHING;

-- Keyword alias
INSERT INTO keyword_aliases (id, keyword_id, alias_text, source)
VALUES (
  gen_random_uuid(),
  (SELECT id FROM keywords WHERE natural_key = 'आत्मा'),
  'आत्मन्',
  'jainkosh_redirect'
) ON CONFLICT (keyword_id, alias_text) DO NOTHING;

-- Topic (root, under keyword)
INSERT INTO topics (id, natural_key, display_text, source, parent_keyword_id, is_leaf, topic_path)
VALUES (
  gen_random_uuid(),
  'आत्मा:आत्मा-के-भेद',
  '[{"lang":"hin","script":"Deva","text":"आत्मा के भेद"}]',
  'jainkosh',
  (SELECT id FROM keywords WHERE natural_key = 'आत्मा'),
  false,
  'आत्मा-के-भेद'
) ON CONFLICT (natural_key) DO NOTHING;

-- Topic (child, with parent_topic)
INSERT INTO topics (id, natural_key, display_text, source, parent_keyword_id, parent_topic_id, is_leaf, topic_path)
VALUES (
  gen_random_uuid(),
  'आत्मा:बहिरात्मादि-3-भेद',
  '[{"lang":"hin","script":"Deva","text":"आत्मा के बहिरात्मादि 3 भेद"}]',
  'jainkosh',
  (SELECT id FROM keywords WHERE natural_key = 'आत्मा'),
  (SELECT id FROM topics WHERE natural_key = 'आत्मा:आत्मा-के-भेद'),
  true,
  'बहिरात्मादि-3-भेद'
) ON CONFLICT (natural_key) DO NOTHING;

SQL
```

Verify rows:

```bash
psql "postgresql://$(whoami)@localhost/jain_kb_dev" -c "
SELECT 'authors' AS tbl, COUNT(*) FROM authors WHERE natural_key IN ('kundkundacharya','amritchandracharya')
UNION ALL SELECT 'shastras', COUNT(*) FROM shastras WHERE natural_key='pravachansaar'
UNION ALL SELECT 'teekas', COUNT(*) FROM teekas WHERE natural_key='pravachansaar:amritchandra'
UNION ALL SELECT 'gathas', COUNT(*) FROM gathas WHERE shastra_id=(SELECT id FROM shastras WHERE natural_key='pravachansaar')
UNION ALL SELECT 'kalashas', COUNT(*) FROM kalashas
UNION ALL SELECT 'keywords', COUNT(*) FROM keywords WHERE natural_key='आत्मा'
UNION ALL SELECT 'topics', COUNT(*) FROM topics WHERE natural_key LIKE 'आत्मा:%';"
```

Expected: `2 / 1 / 1 / 2 / 1 / 1 / 2`.

### 2b. Seed MongoDB documents (optional)

These are only needed for detail endpoints to return non-null content. Without them, detail endpoints still return 200 — Mongo fields are `null` / empty arrays.

```python
# python seed_mongo.py
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def seed():
    db = AsyncIOMotorClient("mongodb://localhost:27017")["jain_kb"]

    await db.gatha_prakrit.update_one(
        {"natural_key": "pravachansaar:039:prakrit"},
        {"$set": {
            "natural_key": "pravachansaar:039:prakrit",
            "gatha_natural_key": "pravachansaar:039",
            "text": [{"lang": "pra", "script": "Deva", "text": "जे णेव हि संजाया..."}],
            "is_kalash": False,
        }},
        upsert=True,
    )

    await db.keyword_definitions.update_one(
        {"natural_key": "आत्मा"},
        {"$set": {
            "natural_key": "आत्मा",
            "page_sections": [
                {
                    "section_index": 0,
                    "section_kind": "siddhantkosh",
                    "heading": [{"lang": "hin", "script": "Deva", "text": "सिद्धांतकोष से"}],
                    "definitions": [],
                }
            ],
        }},
        upsert=True,
    )

    await db.topic_extracts.update_one(
        {"natural_key": "आत्मा:बहिरात्मादि-3-भेद"},
        {"$set": {
            "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
            "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
            "blocks": [{"kind": "hindi_text", "text_devanagari": "...", "references": []}],
        }},
        upsert=True,
    )

    print("Mongo seed done.")

asyncio.run(seed())
```

---

## 3. Keywords

### 3a. List keywords

```bash
curl -s "http://localhost:8002/v1/keywords" | python -m json.tool
# pagination.total: 1, items[0].natural_key: "आत्मा"
```

Check `Cache-Control` header:

```bash
curl -sI "http://localhost:8002/v1/keywords" | grep Cache-Control
# Cache-Control: public, max-age=60
```

### 3b. Letter filter

```bash
curl -s "http://localhost:8002/v1/keywords?letter=आ" | python -m json.tool
# 1 result — आत्मा starts with आ

curl -s "http://localhost:8002/v1/keywords?letter=क" | python -m json.tool
# 0 results
```

### 3c. Text search

```bash
curl -s "http://localhost:8002/v1/keywords?q=आत्मा" | python -m json.tool
# matches display_text

curl -s "http://localhost:8002/v1/keywords?q=आत्मन्" | python -m json.tool
# matches via alias
```

### 3d. Letter index (cached 1h)

```bash
curl -s "http://localhost:8002/v1/keywords/letters" | python -m json.tool
# [{"letter": "आ", "count": 1}]
```

### 3e. Keyword detail — no Mongo doc

```bash
curl -s "http://localhost:8002/v1/keywords/आत्मा" | python -m json.tool
# definition: null  (no Mongo doc seeded yet)
# aliases: [{alias_text: "आत्मन्", source: "jainkosh_redirect"}]
```

### 3f. Keyword detail — with Mongo doc (after running the seed script)

```bash
curl -s "http://localhost:8002/v1/keywords/आत्मा" | python -m json.tool
# definition.natural_key: "आत्मा"
# definition.page_sections: [...]
```

### 3g. Fetch by UUID

```bash
KW_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM keywords WHERE natural_key='आत्मा';" | tr -d ' \n')

curl -s "http://localhost:8002/v1/keywords/$KW_ID" | python -m json.tool
# same result as natural_key lookup
```

### 3h. 404

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/keywords/nonexistent
# 404
```

### 3i. Admin PATCH

```bash
KW_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM keywords WHERE natural_key='आत्मा';" | tr -d ' \n')

# Update display_text
curl -s -X PATCH "http://localhost:8002/v1/admin/keywords/$KW_ID" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"display_text": "आत्मा (updated)"}' | python -m json.tool
# display_text: "आत्मा (updated)"

# Restore
curl -s -X PATCH "http://localhost:8002/v1/admin/keywords/$KW_ID" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"display_text": "आत्मा"}' > /dev/null

# Unknown field → 422
curl -s -X PATCH "http://localhost:8002/v1/admin/keywords/$KW_ID" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"natural_key": "sneaky"}' | python -m json.tool
# 422 validation_error

# Wrong credentials → 401
curl -s -o /dev/null -w "%{http_code}" \
  -X PATCH "http://localhost:8002/v1/admin/keywords/$KW_ID" \
  -u admin:wrong \
  -H "Content-Type: application/json" \
  -d '{"display_text": "x"}'
# 401
```

---

## 4. Topics

### 4a. List topics

```bash
curl -s "http://localhost:8002/v1/topics" | python -m json.tool
# pagination.total: 2
```

### 4b. Filters

```bash
# Leaf topics only
curl -s "http://localhost:8002/v1/topics?is_leaf=true" | python -m json.tool
# 1 result: बहिरात्मादि-3-भेद

# Non-leaf
curl -s "http://localhost:8002/v1/topics?is_leaf=false" | python -m json.tool
# 1 result: आत्मा-के-भेद

# By parent keyword ID
KW_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM keywords WHERE natural_key='आत्मा';" | tr -d ' \n')
curl -s "http://localhost:8002/v1/topics?parent_keyword_id=$KW_ID" | python -m json.tool
# 2 results

# By source
curl -s "http://localhost:8002/v1/topics?source=jainkosh" | python -m json.tool
# 2 results

# Text search
curl -s "http://localhost:8002/v1/topics?q=भेद" | python -m json.tool
```

### 4c. Topic detail — root topic (no parent_topic)

```bash
curl -s "http://localhost:8002/v1/topics/आत्मा:आत्मा-के-भेद" | python -m json.tool
# parent_topic: null
# parent_keyword.natural_key: "आत्मा"
# extracts: []
```

### 4d. Topic detail — child topic (parent_topic populated)

```bash
curl -s "http://localhost:8002/v1/topics/आत्मा:बहिरात्मादि-3-भेद" | python -m json.tool
# parent_topic.natural_key: "आत्मा:आत्मा-के-भेद"
# is_leaf: true
# extracts: [] (or populated if Mongo seed ran)
```

### 4e. 404

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/topics/nonexistent
# 404
```

---

## 5. Gathas

### 5a. List gathas

```bash
curl -s "http://localhost:8002/v1/gathas" | python -m json.tool
# pagination.total: 2
# items[*].shastra.natural_key: "pravachansaar"
```

### 5b. Filter by shastra

```bash
# By natural_key
curl -s "http://localhost:8002/v1/gathas?shastra_id=pravachansaar" | python -m json.tool
# 2 results

# By UUID
SHASTRA_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM shastras WHERE natural_key='pravachansaar';" | tr -d ' \n')
curl -s "http://localhost:8002/v1/gathas?shastra_id=$SHASTRA_ID" | python -m json.tool

# Text search on gatha_number
curl -s "http://localhost:8002/v1/gathas?q=039" | python -m json.tool
# 1 result
```

### 5c. Gatha detail — no `include` (teeka fields absent)

```bash
curl -s "http://localhost:8002/v1/gathas/pravachansaar:039" | python -m json.tool
# prakrit: null  (or populated if Mongo seed ran)
# hindi_chhand: []
# word_meanings: {prakrit: null, sanskrit: null}
# teeka_mapping is NOT present in the response at all
```

Confirm teeka fields are truly absent:

```bash
curl -s "http://localhost:8002/v1/gathas/pravachansaar:039" | \
  python -c "import sys,json; d=json.load(sys.stdin); print('teeka_mapping' in d)"
# False
```

### 5d. Gatha detail — selective `include`

```bash
# Request only teeka_mapping
curl -s "http://localhost:8002/v1/gathas/pravachansaar:039?include=teeka_mapping" | python -m json.tool
# teeka_mapping: []   ← present and empty (no Mongo docs yet)
# teeka_sanskrit is NOT in response

# Request all four
curl -s "http://localhost:8002/v1/gathas/pravachansaar:039?include=teeka_mapping,teeka_sanskrit,teeka_hindi,teeka_bhaavarth" | python -m json.tool
# All four fields present

# Verify each key independently
curl -s "http://localhost:8002/v1/gathas/pravachansaar:039?include=teeka_hindi,teeka_bhaavarth" | \
  python -c "import sys,json; d=json.load(sys.stdin); print(sorted(d.keys()))"
# teeka_hindi and teeka_bhaavarth present; teeka_mapping and teeka_sanskrit absent
```

### 5e. Fetch by UUID

```bash
GATHA_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM gathas WHERE natural_key='pravachansaar:039';" | tr -d ' \n')
curl -s "http://localhost:8002/v1/gathas/$GATHA_ID" | python -m json.tool
```

### 5f. 404

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/gathas/pravachansaar:999
# 404
```

---

## 6. Kalashas

### 6a. List kalashas

```bash
curl -s "http://localhost:8002/v1/kalashas" | python -m json.tool
# pagination.total: 1
# items[0].teeka.natural_key: "pravachansaar:amritchandra"
# items[0].teeka.teekakar.natural_key: "amritchandracharya"
```

### 6b. Filter by teeka

```bash
# By natural_key
curl -s "http://localhost:8002/v1/kalashas?teeka_id=pravachansaar:amritchandra" | python -m json.tool
# 1 result

# By UUID
TEEKA_ID=$(psql "postgresql://$(whoami)@localhost/jain_kb_dev" -t -c \
  "SELECT id FROM teekas WHERE natural_key='pravachansaar:amritchandra';" | tr -d ' \n')
curl -s "http://localhost:8002/v1/kalashas?teeka_id=$TEEKA_ID" | python -m json.tool
```

### 6c. Kalash detail — default include (all three Mongo collections)

```bash
curl -s "http://localhost:8002/v1/kalashas/pravachansaar:amritchandra:kalash:001" | python -m json.tool
# teeka.id, teeka.teekakar.natural_key: "amritchandracharya"
# sanskrit: null, hindi: null  (no Mongo docs yet)
# bhaavarth: []  ← always an array, even when empty
```

Verify bhaavarth is an array (not null):

```bash
curl -s "http://localhost:8002/v1/kalashas/pravachansaar:amritchandra:kalash:001" | \
  python -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d['bhaavarth'], list); print('bhaavarth is array ✓')"
```

### 6d. Selective include

```bash
# Only sanskrit
curl -s "http://localhost:8002/v1/kalashas/pravachansaar:amritchandra:kalash:001?include=sanskrit" | python -m json.tool
# hindi and bhaavarth are still present — partial include still returns all three, just fetches selectively

# Empty include (no Mongo fetches)
curl -s "http://localhost:8002/v1/kalashas/pravachansaar:amritchandra:kalash:001?include=" | python -m json.tool
# sanskrit: null, hindi: null, bhaavarth: []
```

### 6e. 404

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/kalashas/nonexistent:kalash:999
# 404
```

---

## 7. Browse

### 7a. All shastras (cached 1h)

```bash
curl -s "http://localhost:8002/v1/browse/shastras" | python -m json.tool
# [{natural_key: "pravachansaar", total_gathas: 2, total_teekas: 1, author: {...}}]
```

Verify counts live:

```bash
curl -s "http://localhost:8002/v1/browse/shastras" | \
  python -c "import sys,json; s=json.load(sys.stdin)[0]; print('gathas:', s['total_gathas'], 'teekas:', s['total_teekas'])"
# gathas: 2 teekas: 1
```

### 7b. Shastra table of contents

```bash
curl -s "http://localhost:8002/v1/browse/shastras/pravachansaar/index" | python -m json.tool
# shastra.natural_key: "pravachansaar"
# adhikaars: 1 entry (both gathas share the same adhikaar)
# adhikaars[0].gathas: 2 entries
```

### 7c. Teeka table of contents

```bash
curl -s "http://localhost:8002/v1/browse/teekas/pravachansaar:amritchandra/index" | python -m json.tool
# teeka.natural_key: "pravachansaar:amritchandra"
# teeka.teekakar.display_name present
# entries: [{kind:"gatha",...}, {kind:"gatha",...}, {kind:"kalash",...}]
```

Check entry kinds:

```bash
curl -s "http://localhost:8002/v1/browse/teekas/pravachansaar:amritchandra/index" | \
  python -c "import sys,json; entries=json.load(sys.stdin)['entries']; print([e['kind'] for e in entries])"
# ['gatha', 'gatha', 'kalash']
```

### 7d. 404

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/browse/shastras/nonexistent/index
# 404

curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/v1/browse/teekas/nonexistent/index
# 404
```

---

## 8. Search

### 8a. Basic keyword match

```bash
curl -s "http://localhost:8002/v1/search?q=आत्मा" | python -m json.tool
# query: "आत्मा"
# items: results across keyword, topic, gatha entity types
# items[0] should be the exact keyword match (score ~1.0)
```

### 8b. Type filter

```bash
# Only keywords
curl -s "http://localhost:8002/v1/search?q=आत्मा&types=keyword" | python -m json.tool
# All items have entity_type: "keyword"

# Only topics
curl -s "http://localhost:8002/v1/search?q=भेद&types=topic" | python -m json.tool
# Returns topics matching "भेद"

# Multiple types
curl -s "http://localhost:8002/v1/search?q=आत्मा&types=keyword,topic" | python -m json.tool
```

### 8c. Limit

```bash
curl -s "http://localhost:8002/v1/search?q=आत्मा&limit=1" | python -m json.tool
# At most 1 item

# Max limit is 50
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/v1/search?q=आत्मा&limit=51"
# 422
```

### 8d. Validation errors

```bash
# q too short (< 2 chars)
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/v1/search?q=अ"
# 422

# q missing
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/v1/search"
# 422

# Invalid type
curl -s "http://localhost:8002/v1/search?q=आत्मा&types=invalid" | python -m json.tool
# 422 validation_error
```

### 8e. Cache-Control header

```bash
curl -sI "http://localhost:8002/v1/search?q=आत्मा" | grep Cache-Control
# Cache-Control: public, max-age=60
```

---

## 9. Pagination

```bash
# First page
curl -s "http://localhost:8002/v1/gathas?limit=1&offset=0" | python -m json.tool
# items: 1 gatha, pagination.total: 2

# Second page
curl -s "http://localhost:8002/v1/gathas?limit=1&offset=1" | python -m json.tool
# items: 1 different gatha

# Past end
curl -s "http://localhost:8002/v1/gathas?limit=50&offset=100" | python -m json.tool
# items: [], pagination.total: 2
```

---

## 10. Automated test suite

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
python -m pytest services/data_service/tests/ -v
```

Expected: **60 passed, 0 skipped** — MongoDB is mocked in tests; only a real Postgres test database is required.

---

## Notes

- All `GET` endpoints are unauthenticated. Only `PATCH /v1/admin/keywords/{id}` requires HTTP Basic Auth.
- Every `GET /{resource}/{ident}` accepts both a UUID string and a `natural_key` string.
- Keywords, gathas, topics, and kalashas are created by the ingestion pipeline — there are no admin POST endpoints in this service for those entities.
- Gatha detail: `teeka_mapping`, `teeka_sanskrit`, `teeka_hindi`, `teeka_bhaavarth` fields are **absent** from the response (not null) unless explicitly requested via the `include` query parameter.
- Kalasha detail: all three Mongo collections (`sanskrit`, `hindi`, `bhaavarth`) are fetched by default. Pass `?include=` (empty) to skip all Mongo fetches.
- `bhaavarth` on kalasha detail is always an array (one entry per publication) — never null.
- `GET /v1/keywords/letters` and `GET /v1/browse/shastras` use in-process LRU caches with a 1-hour TTL. The caches are not shared across workers — restart the process to force a reload.
- `Cache-Control: public, max-age=60` is set on every public `GET` response.
- The service does **not** run Alembic migrations on startup. Run `alembic upgrade head` separately before the first start.
