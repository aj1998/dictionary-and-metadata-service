# Data Service API — Specification

FastAPI service exposing keyword definitions, gatha content, topics, and kalashas. Reads from **Postgres** (index rows, IDs, filters) and **MongoDB** (long-form text). No Neo4j access — graph relationships and alias writes are owned by the navigation service.

## Service identity

- **Module path**: `services/data_service/`
- **Default port**: `8002`
- **Base path**: `/v1`
- **Auth**: `GET` endpoints are public (unauthenticated). Admin writes under `/v1/admin/...` require HTTP Basic Auth (`ADMIN_USER` / `ADMIN_PASSWORD`).

---

## Endpoints

### Health

```
GET /healthz
```
```json
{"status": "ok"}
```

---

### Keywords

#### List keywords

```
GET /v1/keywords?q=&letter=&limit=50&offset=0
```

- `q` — prefix + pg_trgm fuzzy match against `keywords.display_text` and `keyword_aliases.alias_text`.
- `letter` — filter by Devanagari starting letter (`अ`, `आ`, …).
- Returns lightweight summaries — no Mongo fetch.

```json
{
  "pagination": {"total": 1234, "limit": 50, "offset": 0},
  "items": [
    {
      "id": "uuid",
      "natural_key": "आत्मा",
      "display_text": "आत्मा",
      "source_url": "https://www.jainkosh.org/wiki/आत्मा"
    }
  ]
}
```

#### Letter index

```
GET /v1/keywords/letters
```

Returns `[{letter, count}]` for the sidebar alphabet nav. Computed from `keywords.display_text` first character. Cached in-process (TTL 1h).

```json
[
  {"letter": "अ", "count": 312},
  {"letter": "आ", "count": 87}
]
```

#### Keyword detail

```
GET /v1/keywords/{id|natural_key}
```

Fetches Postgres row + all aliases + Mongo `keyword_definitions` document in one `asyncio.gather`.

```json
{
  "id": "uuid",
  "natural_key": "आत्मा",
  "display_text": "आत्मा",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा",
  "aliases": [
    {"id": "uuid", "alias_text": "आतम", "source": "jainkosh_redirect"}
  ],
  "definition": {
    "natural_key": "आत्मा",
    "page_sections": [
      {
        "section_index": 0,
        "section_kind": "siddhantkosh",
        "heading": [{"lang": "hin", "script": "Deva", "text": "सिद्धांतकोष से"}],
        "definitions": [
          {
            "definition_index": 1,
            "blocks": [
              {
                "kind": "sanskrit_text",
                "text_devanagari": "...",
                "hindi_translation": "...",
                "references": []
              }
            ]
          }
        ]
      }
    ]
  }
}
```

If no Mongo document exists yet (`definition_doc_ids` is empty), `definition` is `null`.

#### Admin: update keyword

```
PATCH /v1/admin/keywords/{id}
```

Manual correction of Postgres fields only. Alias management lives in the navigation service.

**Request body (all fields optional):**
```json
{
  "display_text": "आत्मा",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा"
}
```

Returns the updated keyword detail (same shape as `GET /v1/keywords/{id}`).

---

### Topics

#### List topics

```
GET /v1/topics?q=&parent_keyword_id=&source=&is_leaf=&limit=50&offset=0
```

- `q` — ILIKE match against `display_text::text`.
- `parent_keyword_id` — filter to topics extracted from a specific keyword page.
- `source` — filter by `ingestion_source` enum (`jainkosh`, `nj`, …).
- `is_leaf` — `true` / `false` to filter leaf vs container topics.

```json
{
  "pagination": {"total": 892, "limit": 50, "offset": 0},
  "items": [
    {
      "id": "uuid",
      "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
      "display_text": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
      "source": "jainkosh",
      "is_leaf": true,
      "topic_path": "बहिरात्मादि-3-भेद",
      "parent_keyword": {
        "id": "uuid",
        "natural_key": "आत्मा",
        "display_text": "आत्मा"
      }
    }
  ]
}
```

#### Topic detail

```
GET /v1/topics/{id|natural_key}
```

Fetches Postgres row + all Mongo `topic_extracts` documents in one `asyncio.gather`.

```json
{
  "id": "uuid",
  "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
  "display_text": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
  "source": "jainkosh",
  "is_leaf": true,
  "is_synthetic": false,
  "topic_path": "बहिरात्मादि-3-भेद",
  "parent_keyword": {
    "id": "uuid",
    "natural_key": "आत्मा",
    "display_text": "आत्मा"
  },
  "parent_topic": {
    "id": "uuid",
    "natural_key": "आत्मा:आत्मा-के-भेद",
    "display_text": [{"lang": "hin", "script": "Deva", "text": "आत्मा के भेद"}]
  },
  "extracts": [
    {
      "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
      "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
      "blocks": [
        {
          "kind": "hindi_text",
          "text_devanagari": "...",
          "references": []
        }
      ]
    }
  ]
}
```

`parent_topic` is `null` if this is a root-level topic under a keyword. `extracts` is an empty array if no Mongo docs exist yet.

Graph neighbors (IS_A, PART_OF, RELATED_TO edges) and topic mentions are **not** in this response — use the navigation service.

---

### Gathas

#### List gathas

```
GET /v1/gathas?shastra_id=&q=&limit=50&offset=0
```

- `shastra_id` — UUID or natural_key of parent shastra.
- `q` — ILIKE match against `gatha_number`, `adhikaar::text`, `heading::text`.

```json
{
  "pagination": {"total": 500, "limit": 50, "offset": 0},
  "items": [
    {
      "id": "uuid",
      "natural_key": "pravachansaar:039",
      "gatha_number": "039",
      "shastra": {"natural_key": "pravachansaar", "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]},
      "adhikaar": [{"lang": "hin", "script": "Deva", "text": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}],
      "heading": [{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत संज्ञा है"}]
    }
  ]
}
```

#### Gatha detail

```
GET /v1/gathas/{id|natural_key}?include=teeka_mapping,teeka_sanskrit,teeka_hindi,teeka_bhaavarth
```

The `include` query param is a comma-separated list controlling which teeka-level Mongo collections are fetched. All are **off by default** to keep baseline responses fast. Core gatha content (Prakrit, Sanskrit, Hindi chhand, word meanings) is always returned.

**`include` values:**

| Value | Mongo collection | Description |
|---|---|---|
| `teeka_mapping` | `teeka_gatha_mapping` | Anvayartha (commentary) per teeka |
| `teeka_sanskrit` | `gatha_teeka_sanskrit` | Sanskrit text of the teeka commentary |
| `teeka_hindi` | `gatha_teeka_hindi` | Hindi text of the teeka commentary |
| `teeka_bhaavarth` | `gatha_teeka_bhaavarth_hindi` | Hindi bhaavarth (essence/meaning) per publication |

All included collections are fetched in a single `asyncio.gather` alongside core content.

```json
{
  "id": "uuid",
  "natural_key": "pravachansaar:039",
  "gatha_number": "039",
  "shastra": {
    "natural_key": "pravachansaar",
    "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]
  },
  "adhikaar": [{"lang": "hin", "script": "Deva", "text": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}],
  "heading": [{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत संज्ञा है"}],
  "prakrit": {
    "natural_key": "pravachansaar:039:prakrit",
    "text": [{"lang": "pra", "script": "Deva", "text": "जे णेव हि संजाया..."}],
    "is_kalash": false
  },
  "sanskrit": {
    "natural_key": "pravachansaar:039:sanskrit",
    "text": [{"lang": "san", "script": "Deva", "text": "..."}]
  },
  "hindi_chhand": [
    {
      "natural_key": "pravachansaar:039:chhand:01",
      "chhand_index": 1,
      "chhand_type": "harigeet",
      "text": [{"lang": "hin", "script": "Deva", "text": "..."}]
    }
  ],
  "word_meanings": {
    "prakrit": {
      "natural_key": "pravachansaar:039:word_meanings:prakrit",
      "source_language": "pra",
      "entries": [
        {"source_word": [{"lang": "pra", "script": "Deva", "text": "णेव"}],
         "meanings": [{"lang": "hin", "script": "Deva", "text": "नहीं"}],
         "position": 1}
      ]
    },
    "sanskrit": null
  },
  "teeka_mapping": [
    {
      "natural_key": "pravachansaar:amritchandra:039",
      "teeka_natural_key": "pravachansaar:amritchandra",
      "anvayartha": [{"lang": "hin", "script": "Deva", "text": "..."}],
      "tagged_terms": []
    }
  ],
  "teeka_sanskrit": [
    {
      "natural_key": "pravachansaar:amritchandra:039:sanskrit",
      "teeka_natural_key": "pravachansaar:amritchandra",
      "text": [{"lang": "san", "script": "Deva", "text": "..."}]
    }
  ],
  "teeka_hindi": [],
  "teeka_bhaavarth": []
}
```

Fields `teeka_mapping`, `teeka_sanskrit`, `teeka_hindi`, `teeka_bhaavarth` are absent from the response when not requested via `include`.

---

### Kalashas

Kalashas are special commentary stanzas added by teekakaars. A kalash belongs to a teeka; its bhaavarth is publication-specific (different publishers may have different bhaavarths for the same teeka's kalash).

#### List kalashas

```
GET /v1/kalashas?teeka_id=&limit=50&offset=0
```

- `teeka_id` — UUID or natural_key of parent teeka.

```json
{
  "pagination": {"total": 44, "limit": 50, "offset": 0},
  "items": [
    {
      "id": "uuid",
      "natural_key": "pravachansaar:amritchandra:kalash:001",
      "kalash_number": "001",
      "teeka": {
        "natural_key": "pravachansaar:amritchandra",
        "shastra": {"natural_key": "pravachansaar", "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]}
      }
    }
  ]
}
```

#### Kalash detail

```
GET /v1/kalashas/{id|natural_key}?include=sanskrit,hindi,bhaavarth
```

The `include` query param controls which Mongo collections are fetched. All are **on by default** (kalasha fetches are rarer and detail is usually needed).

| Value | Mongo collection | Description |
|---|---|---|
| `sanskrit` | `kalash_sanskrit` | Sanskrit text of the kalash |
| `hindi` | `kalash_hindi` | Hindi translation |
| `bhaavarth` | `kalash_bhaavarth_hindi` | Hindi bhaavarth (publication-specific) |

```json
{
  "id": "uuid",
  "natural_key": "pravachansaar:amritchandra:kalash:001",
  "kalash_number": "001",
  "teeka": {
    "id": "uuid",
    "natural_key": "pravachansaar:amritchandra",
    "shastra": {"natural_key": "pravachansaar", "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]},
    "teekakar": {"natural_key": "amritchandra", "display_name": [{"lang": "hin", "script": "Deva", "text": "अमृतचंद्राचार्य"}]}
  },
  "sanskrit": {
    "natural_key": "pravachansaar:amritchandra:kalash:001:sanskrit",
    "text": [{"lang": "san", "script": "Deva", "text": "..."}]
  },
  "hindi": {
    "natural_key": "pravachansaar:amritchandra:kalash:001:hindi",
    "text": [{"lang": "hin", "script": "Deva", "text": "..."}]
  },
  "bhaavarth": [
    {
      "natural_key": "pravachansaar:amritchandra:kalash:001:bhaavarth:pub-001",
      "publisher_id": "pub-001",
      "text": [{"lang": "hin", "script": "Deva", "text": "..."}]
    }
  ]
}
```

`bhaavarth` is an array because multiple publications may provide different bhaavarths for the same kalash.

---

### Browse

#### All shastras

```
GET /v1/browse/shastras
```

Returns all shastras with total gatha counts. In-process LRU cache (size 1, TTL 1h).

```json
[
  {
    "natural_key": "pravachansaar",
    "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
    "author": {"natural_key": "kundkundacharya", "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}]},
    "total_gathas": 275,
    "total_teekas": 3
  }
]
```

#### Shastra table of contents

```
GET /v1/browse/shastras/{nk}/index
```

Shastra ToC: gathas grouped by adhikaar, with gatha number and heading. No Mongo fetches — Postgres only.

```json
{
  "shastra": {"natural_key": "pravachansaar", "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]},
  "adhikaars": [
    {
      "adhikaar": [{"lang": "hin", "script": "Deva", "text": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार"}],
      "gathas": [
        {
          "natural_key": "pravachansaar:039",
          "gatha_number": "039",
          "heading": [{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत संज्ञा है"}]
        }
      ]
    }
  ]
}
```

#### Teeka table of contents

```
GET /v1/browse/teekas/{nk}/index
```

Teeka ToC: ordered list of gathas (with their kalashas interleaved after the gatha they comment on). No Mongo fetches — Postgres only.

```json
{
  "teeka": {
    "natural_key": "pravachansaar:amritchandra",
    "teekakar": {"display_name": [{"lang": "hin", "script": "Deva", "text": "अमृतचंद्राचार्य"}]},
    "shastra": {"natural_key": "pravachansaar", "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}]}
  },
  "entries": [
    {
      "kind": "gatha",
      "natural_key": "pravachansaar:039",
      "gatha_number": "039",
      "heading": [{"lang": "hin", "script": "Deva", "text": "भूत-भावि पर्यायों की असद्भूत संज्ञा है"}]
    },
    {
      "kind": "kalash",
      "natural_key": "pravachansaar:amritchandra:kalash:001",
      "kalash_number": "001"
    }
  ]
}
```

---

### Search

```
GET /v1/search?q=&types=keyword,topic,gatha,kalasha&limit=20
```

Lightweight cross-entity search against display text and aliases. Uses pg_trgm similarity. Returns ranked matches across entity types.

- `q` — required; minimum 2 characters.
- `types` — comma-separated; defaults to all four types.
- `limit` — max 50.

Not the GraphRAG endpoint — for semantic/graph-based retrieval see the query service.

```json
{
  "query": "आत्मा",
  "items": [
    {
      "entity_type": "keyword",
      "id": "uuid",
      "natural_key": "आत्मा",
      "display_text": "आत्मा",
      "score": 1.0
    },
    {
      "entity_type": "topic",
      "id": "uuid",
      "natural_key": "आत्मा:बहिरात्मादि-3-भेद",
      "display_text": "आत्मा के बहिरात्मादि 3 भेद",
      "score": 0.82
    }
  ]
}
```

---

## Module layout

```
services/data_service/
├── main.py               # FastAPI app, lifespan (indexes cache warm-up)
├── config.py             # pydantic-settings: DATABASE_URL, MONGO_URL, ADMIN_USER, ADMIN_PASSWORD
├── deps.py               # get_session(), get_mongo_db(), require_admin()
├── routers/
│   ├── keywords.py
│   ├── topics.py
│   ├── gathas.py
│   ├── kalashas.py
│   ├── browse.py
│   └── search.py
├── services/
│   ├── keywords.py       # Postgres queries + Mongo fetch
│   ├── topics.py
│   ├── gathas.py         # include-param gated Mongo fetches via asyncio.gather
│   ├── kalashas.py
│   ├── browse.py
│   └── search.py
├── schemas/
│   ├── common.py         # LangText, Pagination, ShastraSummary, TeekaSummary, etc.
│   ├── keywords.py
│   ├── topics.py
│   ├── gathas.py
│   └── kalashas.py
└── tests/
    ├── test_keywords.py
    ├── test_topics.py
    ├── test_gathas.py
    ├── test_kalashas.py
    ├── test_browse.py
    └── test_search.py
```

## Cross-store fetch pattern

All detail endpoints gather Postgres + Mongo in a single `asyncio.gather`:

```python
async def get_gatha_detail(pg, mongo, ident: str, include: set[str]) -> GathaDetail:
    gatha = await gathas_repo.get_by_ident(pg, ident)
    if gatha is None:
        raise NotFound("gatha", ident)

    tasks = {
        "shastra": pg.get(Shastra, gatha.shastra_id),
        "prakrit": mongo.gatha_prakrit.find_one({"natural_key": f"{gatha.natural_key}:prakrit"}),
        "sanskrit": mongo.gatha_sanskrit.find_one({"natural_key": f"{gatha.natural_key}:sanskrit"}),
        "hindi_chhand": mongo.gatha_hindi_chhand.find({"gatha_natural_key": gatha.natural_key}).to_list(None),
        "wm_prakrit": mongo.gatha_word_meanings.find_one({"natural_key": f"{gatha.natural_key}:word_meanings:prakrit"}),
        "wm_sanskrit": mongo.gatha_word_meanings.find_one({"natural_key": f"{gatha.natural_key}:word_meanings:sanskrit"}),
    }
    if "teeka_mapping" in include:
        tasks["teeka_mapping"] = mongo.teeka_gatha_mapping.find({"gatha_natural_key": gatha.natural_key}).to_list(None)
    if "teeka_sanskrit" in include:
        tasks["teeka_sanskrit"] = mongo.gatha_teeka_sanskrit.find({"gatha_natural_key": gatha.natural_key}).to_list(None)
    if "teeka_hindi" in include:
        tasks["teeka_hindi"] = mongo.gatha_teeka_hindi.find({"gatha_natural_key": gatha.natural_key}).to_list(None)
    if "teeka_bhaavarth" in include:
        tasks["teeka_bhaavarth"] = mongo.gatha_teeka_bhaavarth_hindi.find({"gatha_natural_key": gatha.natural_key}).to_list(None)

    results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))
    return GathaDetail.compose(gatha, **results)
```

## Caching

- `GET /v1/browse/shastras` — in-process LRU (size 1, TTL 3600s).
- `GET /v1/keywords/letters` — in-process LRU (size 1, TTL 3600s).
- All other `GET` responses: `Cache-Control: public, max-age=60`.
- Cache is busted by admin writes bumping a `cache_version` counter in the app state.

## Run

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export MONGO_URL="mongodb://localhost:27017"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"
uvicorn services.data_service.main:app --port 8002 --reload
```

## Definition of Done

- [ ] All endpoints implemented and reachable.
- [ ] Gatha detail: all four Mongo doc types gated behind `include` query param; fetched in a single `asyncio.gather`.
- [ ] Kalasha detail: bhaavarth returns array (one entry per publication).
- [ ] Browse endpoints return no Mongo data (Postgres-only joins).
- [ ] Search covers keyword, topic, gatha, kalasha in one pg_trgm query.
- [ ] Admin keyword PATCH validated with Pydantic, rejects unknown fields.
- [ ] Integration tests cover: keyword list + detail (with/without Mongo doc), topic detail (with parent_topic populated), gatha detail with all `include` combinations, kalasha detail, browse shastra index, browse teeka index.
- [ ] `Cache-Control` headers set on all public GET responses.
- [ ] OpenAPI spec includes example payloads for every endpoint.
- [ ] Service starts with `uvicorn services.data_service.main:app --port 8002`.

---

## Implementation Notes

- Added `GET /v1/stats/counts` to return aggregate counts for `shastras`, `gathas`, `topics`, and `keywords` from Postgres.
- Added `GET /v1/activity/recent` to return latest ingestion runs with fields `{id, run_at, source, entities_touched}`.
- `run_at` is selected from `finished_at`, then `started_at`, then `created_at`.
- `entities_touched` is sourced from `ingestion_runs.stats.entities_touched` and defaults to `0` when absent.
- Both endpoints set `Cache-Control: public, max-age=60` and emit basic info logs on fetch.
