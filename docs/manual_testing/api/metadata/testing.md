# Manual Testing Guide — Metadata Service API (`docs/design/api/metadata/01_spec.md`)

This guide covers starting the service locally and verifying every endpoint group by hand using `curl`.

---

## Prerequisites

| Tool | Version / Install |
|---|---|
| PostgreSQL 16 running | `brew services start postgresql@16` |
| `jain_kb_dev` database migrated | `alembic upgrade head` |
| Python venv activated | `source .venv/bin/activate` |
| `fastapi`, `uvicorn`, `pydantic-settings` installed | `pip install -e ".[dev]"` |

---

## 1. Start the service

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"

uvicorn services.metadata_service.main:app --port 8001 --reload
```

Confirm it's up:

```bash
curl -s http://localhost:8001/healthz
# {"status":"ok"}
```

OpenAPI schema:

```bash
curl -s http://localhost:8001/openapi.json | python -m json.tool | head -30
```

---

## 2. Anuyogas (read-only, seeded by migration)

```bash
curl -s http://localhost:8001/v1/anuyogas | python -m json.tool
```

Expected: 4 rows — `prathmanuyoga`, `karananuyoga`, `charananuyoga`, `dravyanuyoga`, each with a Hindi `display_name`.

---

## 3. Publishers (read-only, from `publishers.json`)

```bash
curl -s http://localhost:8001/v1/publishers | python -m json.tool
```

Expected: 29 entries. Spot-check publisher_id `"17"` → `"परम श्रुत प्रभावक मण्डल"`.

---

## 4. Authors

### 4a. Create two authors

```bash
curl -s -X POST http://localhost:8001/v1/admin/authors \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{
    "natural_key": "kundkundacharya",
    "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}],
    "kind": "acharya"
  }' | python -m json.tool
```

Save the returned `id` as `AUTHOR_ID`:

```bash
AUTHOR_ID=$(curl -s http://localhost:8001/v1/authors/kundkundacharya | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo $AUTHOR_ID
```

Create a second author (teekakar):

```bash
curl -s -X POST http://localhost:8001/v1/admin/authors \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{
    "natural_key": "amritchandracharya",
    "display_name": [{"lang": "hin", "script": "Deva", "text": "अमृतचन्द्राचार्य"}],
    "kind": "acharya"
  }' | python -m json.tool

TEEKAKAR_ID=$(curl -s http://localhost:8001/v1/authors/amritchandracharya | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

### 4b. List authors

```bash
curl -s "http://localhost:8001/v1/authors" | python -m json.tool
# items: 2, pagination.total: 2
```

### 4c. Fetch by natural_key and by UUID

```bash
curl -s "http://localhost:8001/v1/authors/kundkundacharya" | python -m json.tool
curl -s "http://localhost:8001/v1/authors/$AUTHOR_ID" | python -m json.tool
```

### 4d. Update

```bash
curl -s -X PATCH "http://localhost:8001/v1/admin/authors/$AUTHOR_ID" \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"bio": [{"lang": "hin", "script": "Deva", "text": "दिगम्बर जैन आचार्य, मूलाचार के रचयिता"}]}' \
  | python -m json.tool
# bio field now populated
```

### 4e. Auth checks

```bash
# Wrong password → 401
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8001/v1/admin/authors \
  -u admin:wrongpassword \
  -H "Content-Type: application/json" \
  -d '{"natural_key":"x","display_name":[],"kind":"acharya"}'

# Missing required field → 422
curl -s -X POST http://localhost:8001/v1/admin/authors \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"natural_key": "x"}' | python -m json.tool

# Duplicate natural_key → 409
curl -s -X POST http://localhost:8001/v1/admin/authors \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d '{"natural_key":"kundkundacharya","display_name":[{"lang":"hin","script":"Deva","text":"x"}],"kind":"acharya"}' \
  | python -m json.tool

# 404
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/authors/nonexistent
```

---

## 5. Shastras

### 5a. Create a shastra

Get the dravyanuyoga UUID first:

```bash
DRAVYA_ID=$(curl -s http://localhost:8001/v1/anuyogas | python -c "
import sys, json
rows = json.load(sys.stdin)
print(next(r['id'] for r in rows if r['kind'] == 'dravyanuyoga'))
")
echo $DRAVYA_ID
```

```bash
curl -s -X POST http://localhost:8001/v1/admin/shastras \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"pravachansaar\",
    \"title\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"प्रवचनसार\"}],
    \"author_id\": \"$AUTHOR_ID\",
    \"anuyoga_ids\": [\"$DRAVYA_ID\"],
    \"source_url\": \"https://example.com/pravachansaar\"
  }" | python -m json.tool

SHASTRA_ID=$(curl -s http://localhost:8001/v1/shastras/pravachansaar | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

### 5b. Fetch detail — confirm author + anuyogas embedded + stats present

```bash
curl -s http://localhost:8001/v1/shastras/pravachansaar | python -m json.tool
# author.natural_key: "kundkundacharya"
# anuyogas[0].kind: "dravyanuyoga"
# stats.total_gathas: 0
# stats.total_teekas: 0
```

### 5c. List + filters

```bash
# All shastras
curl -s "http://localhost:8001/v1/shastras" | python -m json.tool

# Filter by author
curl -s "http://localhost:8001/v1/shastras?author_id=$AUTHOR_ID" | python -m json.tool

# Filter by anuyoga kind
curl -s "http://localhost:8001/v1/shastras?anuyoga=dravyanuyoga" | python -m json.tool

# Text search (ILIKE on title JSON)
curl -s "http://localhost:8001/v1/shastras?q=प्रवचन" | python -m json.tool
```

---

## 6. Teekas

### 6a. Create a teeka

```bash
curl -s -X POST http://localhost:8001/v1/admin/teekas \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"pravachansaar:amritchandra\",
    \"shastra_id\": \"$SHASTRA_ID\",
    \"teekakar_id\": \"$TEEKAKAR_ID\",
    \"publisher\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"परम श्रुत प्रभावक मण्डल\"}],
    \"cataloguesearch_shastra_id\": \"cs-12345\"
  }" | python -m json.tool

TEEKA_ID=$(curl -s "http://localhost:8001/v1/teekas/pravachansaar:amritchandra" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

### 6b. Fetch detail — confirm shastra + teekakar + stats embedded

```bash
curl -s "http://localhost:8001/v1/teekas/pravachansaar:amritchandra" | python -m json.tool
# shastra.natural_key: "pravachansaar"
# teekakar.natural_key: "amritchandracharya"
# stats.total_publications: 0
```

### 6c. List teekas for a shastra

```bash
# Via shastra sub-resource
curl -s "http://localhost:8001/v1/shastras/pravachansaar/teekas" | python -m json.tool

# stats.total_teekas on shastra should now be 1
curl -s "http://localhost:8001/v1/shastras/pravachansaar" | python -c "import sys,json; d=json.load(sys.stdin); print('teekas:', d['stats']['total_teekas'])"
```

---

## 7. Publications

### 7a. Create a publication

```bash
curl -s -X POST http://localhost:8001/v1/admin/publications \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"pravachansaar:amritchandra:17\",
    \"teeka_id\": \"$TEEKA_ID\",
    \"publisher_id\": \"17\",
    \"publisher\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"परम श्रुत प्रभावक मण्डल\"}],
    \"public_url\": \"https://example.com/pub/17\"
  }" | python -m json.tool
```

### 7b. Fetch and list

```bash
curl -s "http://localhost:8001/v1/publications/pravachansaar:amritchandra:17" | python -m json.tool
# teeka.natural_key: "pravachansaar:amritchandra"
# publisher_id: "17"

curl -s "http://localhost:8001/v1/teekas/pravachansaar:amritchandra/publications" | python -m json.tool
# 1 item

# teeka stats should now reflect 1 publication
curl -s "http://localhost:8001/v1/teekas/pravachansaar:amritchandra" | python -c "import sys,json; d=json.load(sys.stdin); print('publications:', d['stats']['total_publications'])"
```

---

## 8. Books

### 8a. Create a book linked to a shastra

```bash
curl -s -X POST http://localhost:8001/v1/admin/books \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"pravachansaar-book-pspm\",
    \"title\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"प्रवचनसार (पुस्तक)\"}],
    \"shastra_id\": \"$SHASTRA_ID\",
    \"anuyoga_ids\": [\"$DRAVYA_ID\"],
    \"publisher\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"परम श्रुत प्रभावक मण्डल\"}]
  }" | python -m json.tool
```

### 8b. Fetch + filter

```bash
curl -s "http://localhost:8001/v1/books/pravachansaar-book-pspm" | python -m json.tool
# shastra embedded, anuyogas: [dravyanuyoga]

curl -s "http://localhost:8001/v1/books?shastra_id=$SHASTRA_ID" | python -m json.tool
curl -s "http://localhost:8001/v1/books?anuyoga=dravyanuyoga" | python -m json.tool
```

---

## 9. Pravachans

```bash
curl -s -X POST http://localhost:8001/v1/admin/pravachans \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"pravachansaar-pravachan-kanjiswami\",
    \"title\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"प्रवचनसार प्रवचन\"}],
    \"shastra_id\": \"$SHASTRA_ID\",
    \"speaker_id\": \"$AUTHOR_ID\"
  }" | python -m json.tool

curl -s "http://localhost:8001/v1/pravachans/pravachansaar-pravachan-kanjiswami" | python -m json.tool
# shastra + speaker embedded

curl -s "http://localhost:8001/v1/pravachans?shastra_id=$SHASTRA_ID" | python -m json.tool
curl -s "http://localhost:8001/v1/pravachans?speaker_id=$AUTHOR_ID" | python -m json.tool
```

---

## 10. Pagination

```bash
# Create a second shastra to test pagination
curl -s -X POST http://localhost:8001/v1/admin/shastras \
  -u admin:secret \
  -H "Content-Type: application/json" \
  -d "{
    \"natural_key\": \"samaysaar\",
    \"title\": [{\"lang\": \"hin\", \"script\": \"Deva\", \"text\": \"समयसार\"}],
    \"author_id\": \"$AUTHOR_ID\",
    \"anuyoga_ids\": []
  }" > /dev/null

# Page 1 of 1
curl -s "http://localhost:8001/v1/shastras?limit=1&offset=0" | python -m json.tool
# items: 1 item, pagination.total: 2

# Page 2
curl -s "http://localhost:8001/v1/shastras?limit=1&offset=1" | python -m json.tool
# items: 1 item (different shastra)
```

---

## 11. Admin search

```bash
# Search across all entity types
curl -s -u admin:secret \
  "http://localhost:8001/v1/admin/search?q=प्रवचन" | python -m json.tool
# results sorted by score descending; entity_type in [shastra, teeka, book, pravachan]

# Restrict to specific types
curl -s -u admin:secret \
  "http://localhost:8001/v1/admin/search?q=प्रवचन&types=shastra,book" | python -m json.tool

# Admin search requires auth
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8001/v1/admin/search?q=test"
# 401
```

---

## 12. Automated test suite

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
python -m pytest services/metadata_service/tests/ -v
```

Expected: **60 passed, 0 skipped** — no Mongo or Neo4j required.

---

## Notes

- All `GET` endpoints are unauthenticated. `POST`/`PATCH` and `/v1/admin/*` require HTTP Basic Auth.
- Every `GET /{resource}/{ident}` accepts both a UUID string and a `natural_key` string.
- JSONB multilingual fields (`display_name`, `title`, `publisher`, etc.) are always returned as arrays of `{lang, script, text}` objects.
- The `stats` block on shastras/teekas is computed via live `COUNT(*)` queries; it reflects data committed at request time.
- Publishers are loaded from `parser_configs/_manual_configs/publishers.json` at startup — no DB write is needed to populate `/v1/publishers`.
- The service does **not** run Alembic migrations on startup. Run `alembic upgrade head` separately before the first start.
