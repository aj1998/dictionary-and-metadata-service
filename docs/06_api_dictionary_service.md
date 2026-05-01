# 06 — Dictionary Service API

FastAPI service exposing keyword definitions, gathas, and topics. Uses Postgres for indexing and Mongo for body text. Read-only on the public surface; ingestion happens in worker processes (see `08_*`, `09_*`).

## Service identity

- **Module path**: `services/dictionary_service/`
- **Default port**: `8002`
- **Base path**: `/v1`
- **Auth**: `GET` is public. Admin operations under `/v1/admin/...` (basic auth).

## Endpoints

### Keywords

```
GET /v1/keywords?q=&letter=&limit=&offset=
```
- `q` does prefix + trigram fuzzy match against `keywords.display_text` and `keyword_aliases.alias_text`.
- `letter` filters by Devanagari starting letter (`अ`, `आ`, ...).

```json
{
  "pagination": {"total": 1234, "limit": 50, "offset": 0},
  "items": [
    {
      "id": "uuid",
      "natural_key": "आत्मा",
      "display_text": "आत्मा",
      "source_url": "https://www.jainkosh.org/wiki/आत्मा",
      "summary_hi": "द्वादशांग का नाम आत्मा है, क्योंकि वह आत्मा का परिणाम है ..."
    }
  ]
}
```

(`summary_hi` is the first ~200 chars of the first Hindi block of the keyword's definition, computed at ingest time and cached on the keyword row as `summary_hi` — add this column in a follow-up migration if missing.)

```
GET /v1/keywords/{id|natural_key}
```

```json
{
  "id": "uuid",
  "natural_key": "आत्मा",
  "display_text": "आत्मा",
  "aliases": ["आतम", "आत्मन्"],
  "definition": {
    "page_sections": [/* full keyword_definitions document from Mongo */]
  },
  "related_topics": [
    {"id": "uuid", "natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद", "display_text_hi": "बहिरात्मादि 3 भेद"}
  ]
}
```

```
GET /v1/keywords/{id}/topics            // topics linked from this keyword (via Neo4j)
GET /v1/keywords/letters                // {letter, count} list for sidebar nav
POST   /v1/admin/keywords/{id}/aliases       add manual alias
DELETE /v1/admin/keywords/{id}/aliases/{alias_id}
```

### Topics

```
GET /v1/topics?q=&parent_keyword=&source=&limit=&offset=
GET /v1/topics/{id|natural_key}
```

**Topic detail response:**
```json
{
  "id": "uuid",
  "natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
  "display_text": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
  "source": "jainkosh",
  "parent_keyword": {"id": "uuid", "natural_key": "आत्मा", "display_text": "आत्मा"},
  "extracts": [/* topic_extracts documents from Mongo */],
  "mentioned_keywords": [
    {"natural_key": "बहिरात्मा", "display_text": "बहिरात्मा"},
    {"natural_key": "अंतरात्मा", "display_text": "अंतरात्मा"}
  ],
  "mentions": [
    {"kind": "gatha", "gatha_natural_key": "samaysaar:017", "page": null},
    {"kind": "cataloguesearch_chunk", "cataloguesearch_chunk_id": "cs-chunk-998877"}
  ],
  "graph_neighbors": {
    "is_a":      [{"natural_key": "...", "display_text_hi": "..."}],
    "part_of":   [...],
    "related_to":[...]
  }
}
```

```
GET /v1/topics/{id}/neighbors?edge_type=is_a|part_of|related_to&depth=1
```

### Gathas

```
GET /v1/gathas?shastra_id=&q=&limit=&offset=
GET /v1/gathas/{id|natural_key}
```

**Gatha detail response:**
```json
{
  "id": "uuid",
  "natural_key": "pravachansaar:039",
  "shastra": {"natural_key": "pravachansaar", "title_hi": "प्रवचनसार"},
  "gatha_number": "039",
  "adhikaar": [{"lang": "hin", "script": "Deva", "text": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}],
  "heading":  [{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत--अविद्यमान संज्ञा है"}],
  "prakrit":  {"text": [{"lang": "pra", "script": "Deva", "text": "..."}]},
  "sanskrit": {"text": [{"lang": "san", "script": "Deva", "text": "..."}]},
  "hindi_chhand": [{"chhand_index": 1, "chhand_type": "harigeet", "text": [...]}],
  "word_meanings": {
    "prakrit":  {"entries": [/* from gatha_word_meanings */]},
    "sanskrit": {"entries": [...]}
  },
  "teeka_mappings": [
    {
      "teeka": {"natural_key": "pravachansaar:amritchandra", "display": "अमृतचंद्राचार्य की टीका"},
      "anvayartha": [{"lang": "hin", "script": "Deva", "text": "..."}],
      "tagged_terms": [...]
    }
  ],
  "topics": [{"natural_key": "...", "display_text_hi": "..."}],
  "keywords": [{"natural_key": "पर्याय", "display_text": "पर्याय"}]
}
```

### Browse helpers

```
GET /v1/browse/shastras                      // all shastras with gatha counts (cached 1h)
GET /v1/browse/shastras/{nk}/index           // shastra ToC: adhikaars + gatha numbers + headings
```

### Public search (cross-entity)

```
GET /v1/search?q=&types=keyword,topic,gatha&limit=20
```
- Lightweight search against `display_text` and aliases.
- Returns ranked matches across keyword, topic, gatha entities.
- **Not** the GraphRAG endpoint — that one lives in `query-service` (see `07_*`).

### Admin

```
POST   /v1/admin/topics/{id}/mentions               add a manual mention
DELETE /v1/admin/topics/{id}/mentions/{mention_id}
POST   /v1/admin/topics/{id}/edges                  add Topic→Topic graph edge
DELETE /v1/admin/topics/{id}/edges/{edge_id}
POST   /v1/admin/keywords/{id}/aliases              add alias
PATCH  /v1/admin/keywords/{id}                      manual edit (rare)
```

All admin writes are mirrored into Neo4j by the `graph_sync` Celery task triggered after the DB transaction commits.

## Module layout

```
services/dictionary_service/
├── main.py
├── config.py
├── routers/
│   ├── keywords.py
│   ├── topics.py
│   ├── gathas.py
│   ├── browse.py
│   ├── search.py
│   └── admin.py
├── services/
│   ├── keywords.py        # joins postgres + mongo + neo4j
│   ├── topics.py
│   ├── gathas.py
│   └── search.py
├── schemas/
└── tests/
```

## Cross-store fetch pattern

```python
# services/dictionary_service/services/keywords.py
async def get_keyword_detail(pg, mongo, neo4j, ident: str) -> KeywordDetail:
    kw = await keywords_repo.get_by_id_or_natural_key(pg, ident)
    if kw is None:
        raise NotFound("keyword", ident)

    # batched fetch
    aliases_task = keyword_aliases_repo.list_for_keyword(pg, kw.id)
    definition_task = mongo.keyword_definitions.find_one({"natural_key": kw.natural_key})
    related_topics_task = topics_repo.related_to_keyword(neo4j, kw.natural_key)
    aliases, definition, related_topics = await asyncio.gather(
        aliases_task, definition_task, related_topics_task
    )
    return KeywordDetail.compose(kw, aliases, definition, related_topics)
```

## Caching

- All `GET` responses set `Cache-Control: public, max-age=60` for public endpoints. CDN/nginx can cache.
- `browse/shastras` keeps an in-process LRU cache (size 1, ttl 3600s).
- Cache is invalidated by admin writes via a `cache_version` row in Postgres bumped on each admin write; readers include version in cache key.

## Definition of Done

- [ ] All endpoints implemented and reachable.
- [ ] Cross-store fetches use `asyncio.gather` (no sequential awaits).
- [ ] Keyword/topic/gatha detail endpoints validate response Pydantic models.
- [ ] OpenAPI spec includes example payloads for every endpoint.
- [ ] Integration tests cover: keyword list+detail, topic detail with graph_neighbors, gatha detail with all teeka mappings.
- [ ] Admin writes trigger `graph_sync` task and the resulting edge appears in Neo4j.
- [ ] Service starts with `uvicorn services.dictionary_service.main:app --port 8002`.
