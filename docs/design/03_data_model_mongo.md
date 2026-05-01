# 03 — MongoDB Data Model

Authoritative for: long-form text extracts (Devanagari, Sanskrit, Prakrit). Postgres holds the IDs and references; Mongo holds the body text.

## Conventions

- Database: `jain_kb`
- Every document has a `_id` (ObjectId) and `natural_key` (TEXT, unique within its collection).
- `langs` array uses ISO-639-3 + ISO-15924 (`{lang: "hin", script: "Deva", text: "..."}`). Common values:
  - `{lang: "hin", script: "Deva"}` — Hindi
  - `{lang: "san", script: "Deva"}` — Sanskrit
  - `{lang: "pra", script: "Deva"}` — Prakrit (Ardha-magadhi etc.)
  - Future: `{lang: "guj", script: "Gujr"}`, `{lang: "tam", script: "Taml"}`
- All text is NFC-normalized before insert (use `unicodedata.normalize('NFC', s)`).
- Mongo IDs are referenced from Postgres rows as opaque strings (`str(obj_id)`).

## Collections

### 1. `gatha_prakrit`

Original Prakrit gatha text.

```json
{
  "_id": "ObjectId(...)",
  "natural_key": "pravachansaar:039:prakrit",
  "shastra_natural_key": "pravachansaar",
  "gatha_natural_key": "pravachansaar:039",
  "gatha_number": "039",
  "text": [
    {"lang": "pra", "script": "Deva",
     "text": "जे णेव हि संजाया जे खलु णट्‌ठा भवीय पज्जया ।\nते होंति असब्भूदा पज्जाया णाणपच्चक्खा ॥39॥"}
  ],
  "is_kalash": "true|false" // is gatha a kalash (special commentary gathas added by teekakars)
  "raw_html_fragment": "<div class='gatha'>...</div>",     // for debug
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes:**
- `{natural_key: 1}` UNIQUE
- `{shastra_natural_key: 1, gatha_number: 1}`

### 2. `gatha_sanskrit`

Sanskrit chhaya / equivalent. Same shape as `gatha_prakrit`, with `text[].lang = "san"`.

```json
{
  "natural_key": "pravachansaar:039:sanskrit",
  "shastra_natural_key": "pravachansaar",
  "gatha_natural_key": "pravachansaar:039",
  "gatha_number": "039",
  "text": [{"lang": "san", "script": "Deva", "text": "..."}],
  ...
}
```

### 3. `gatha_hindi_chhand`

Hindi harigeet / chhand verse(s) for a gatha. May contain multiple chhand variants.

```json
{
  "natural_key": "pravachansaar:039:chhand:01",
  "gatha_natural_key": "pravachansaar:039",
  "chhand_index": 1,
  "chhand_type": "harigeet",      // free-text label: harigeet | chaupai | etc.
  "translator": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  ...
}
```

**Indexes:** `{natural_key: 1}` UNIQUE; `{gatha_natural_key: 1, chhand_index: 1}`.

### 4. `gatha_word_meanings`

Word-by-word maps for a gatha. One document per source-language (Prakrit or Sanskrit).

```json
{
  "natural_key": "pravachansaar:039:word_meanings:prakrit",
  "gatha_natural_key": "pravachansaar:039",
  "source_language": "pra",
  "entries": [
    {
      "source_word": [{"lang": "pra", "script": "Deva", "text": "णेव"}],
      "meanings": [
        {"lang": "hin", "script": "Deva", "text": "नहीं"}
      ],
      "position": 1
    },
    ...
  ],
  ...
}
```

**Indexes:** `{natural_key: 1}` UNIQUE.

### 5. `teeka_gatha_mapping`

Per-(teeka, gatha) Hindi anvayartha (teeka commentary).

```json
{
  "natural_key": "pravachansaar:amritchandra:039",
  "teeka_natural_key": "pravachansaar:amritchandra",
  "gatha_natural_key": "pravachansaar:039",
  "anvayartha": [
    {"lang": "hin", "script": "Deva", "text": "उन (जीवादि) द्रव्य-जातियों की..."}
  ],
  "tagged_terms": [
    {"source_word": "तासाम् द्रव्यजातीनाम्", "meaning": "उन द्रव्य-जातियों की"}
  ],
  "raw_html_fragment": "<div class='paragraph'>...</div>",
  ...
}
```

**Indexes:** `{natural_key: 1}` UNIQUE; `{teeka_natural_key: 1}`; `{gatha_natural_key: 1}`.

### 6. `keyword_definitions`

JainKosh keyword page, one document per keyword (overwritten on re-scrape). Splits the page into ordered sections.

```json
{
  "_id": "...",
  "natural_key": "आत्मा",
  "keyword_id": "<uuid from postgres keywords.id>",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा",
  "page_sections": [
    {
      "section_index": 0,
      "section_kind": "siddhantkosh",         // 'siddhantkosh' | 'puraankosh' | 'misc'
      "heading": [{"lang": "hin", "script": "Deva", "text": "सिद्धांतकोष से"}],
      "subsections": [
        {
          "subsection_index": 1,
          "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
          "is_topic_seed": true,
          "topic_natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
          "blocks": [
            {
              "kind": "reference",
              "ref_text": "धवला पुस्तक 13/5,5,50/282/9"
            },
            {
              "kind": "sanskrit",
              "text": [{"lang": "san", "script": "Deva", "text": "..."}]
            },
            {
              "kind": "prakrit",
              "text": [{"lang": "pra", "script": "Deva", "text": "..."}]
            },
            {
              "kind": "hindi",
              "text": [{"lang": "hin", "script": "Deva", "text": "..."}]
            },
            {
              "kind": "see_also",
              "target_keyword": "जीव",
              "target_url": "/wiki/जीव"
            }
          ]
        }
      ]
    }
  ],
  "redirect_aliases": ["आतम", "आत्मन्"],     // mined from page redirects + 'देखें X' links
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes:**
- `{natural_key: 1}` UNIQUE
- `{keyword_id: 1}`
- `{ingestion_run_id: 1}`

### 7. `topic_extracts`

Body text of a topic — a slice of a keyword definition or a manually defined topic.

```json
{
  "_id": "...",
  "natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
  "topic_id": "<uuid from postgres topics.id>",
  "source": "jainkosh",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा#बहिरात्मादि_3_भेद",
  "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
  "blocks": [/* same kind/text shape as keyword_definitions.blocks */],
  "extracted_keyword_natural_keys": ["आत्मा", "बहिरात्मा", "अंतरात्मा", "परमात्मा"],
  "ingestion_run_id": "uuid",
  ...
}
```

**Indexes:**
- `{natural_key: 1}` UNIQUE
- `{topic_id: 1}`
- Text index for fallback admin search: `{ "blocks.text.text": "text", "heading.text": "text" }` (Devanagari-aware via `default_language: "none"`).

### 8. `raw_html_snapshots`

Optional. Mirrors what we wrote to disk so we can re-parse without rescraping. Set `MONGO_STORE_RAW_HTML=false` to skip.

```json
{
  "natural_key": "jainkosh:आत्मा:2026-05-01T12:00:00",
  "source": "jainkosh",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा",
  "fetched_at": ISODate(...),
  "ingestion_run_id": "uuid",
  "html": "<!DOCTYPE html>...",
  "content_hash": "sha256:..."
}
```

**Indexes:** `{natural_key: 1}` UNIQUE; `{ingestion_run_id: 1}`; TTL index on `fetched_at` set to 365d.

### 9. `ocr_pages` (future, scaffolded)

Scaffold for `vyakaran_vishleshan` OCR output. Implementation deferred.

```json
{
  "natural_key": "vyakaran_vishleshan:pravachansaar:gatha-1:page-1",
  "shastra_natural_key": "pravachansaar",
  "gatha_natural_key": "pravachansaar:001",
  "page": 1,
  "image_path": "vyakaran_vishleshan/pravachansaar/gatha1.png",
  "ocr_engine": "tesseract-5.x-hin+san",
  "ocr_text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "tables": [/* extracted tabular data, schema TBD */],
  "review_status": "raw",     // 'raw' | 'reviewed' | 'corrected'
  ...
}
```

## Reference resolution

| From | To | How |
|---|---|---|
| Postgres `keywords.definition_doc_ids[i]` | Mongo `keyword_definitions._id` | string array of ObjectIds |
| Postgres `gathas.prakrit_doc_id` | Mongo `gatha_prakrit._id` | single ObjectId string |
| Postgres `gathas.sanskrit_doc_id` | Mongo `gatha_sanskrit._id` | |
| Postgres `gathas.hindi_chhand_doc_ids` | Mongo `gatha_hindi_chhand._id` | array |
| Postgres `gathas.teeka_mapping_doc_ids` | Mongo `teeka_gatha_mapping._id` | array (one per teeka) |
| Postgres `topics.extract_doc_ids` | Mongo `topic_extracts._id` | array |

When a row is overwritten on re-scrape, the new Mongo doc keeps the same `natural_key` (deterministic upsert key). The Mongo `_id` may also be kept stable by upserting with an explicit `_id`. We do this:

```python
# Always upsert by natural_key. Generate _id from a UUID5 of natural_key
# so the same natural_key produces the same _id forever.
import uuid
def stable_id(natural_key: str) -> ObjectId:
    h = hashlib.sha1(natural_key.encode("utf-8")).digest()[:12]
    return ObjectId(h)
```

This way Postgres references never break across re-scrapes.

## Async Motor client layout

```
packages/jain_kb_common/db/mongo/
├── __init__.py        # AsyncIOMotorClient factory from env
├── collections.py     # collection-name constants
├── schemas.py         # Pydantic v2 models for documents
├── upserts.py         # upsert_keyword_definition, upsert_gatha_prakrit, ...
└── indexes.py         # ensure_indexes() called on app startup
```

## Sample upsert

```python
# packages/jain_kb_common/db/mongo/upserts.py
async def upsert_keyword_definition(db, *, natural_key: str, doc: dict) -> ObjectId:
    _id = stable_id(natural_key)
    doc = {**doc, "natural_key": natural_key, "updated_at": datetime.utcnow()}
    await db.keyword_definitions.update_one(
        {"_id": _id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True,
    )
    return _id
```

## Devanagari handling

- Always pass strings through `unicodedata.normalize('NFC', s)` before insert.
- Strip ZWJ (`\u200D`) and ZWNJ (`\u200C`) only when they are *not* between consonants requiring a half-form (rule of thumb: in JainKosh wiki text these are stylistic, in nikkyjain HTML they may be semantic — check parser config flag `strip_zwj`).
- Don't lowercase. Devanagari has no case.

## Definition of Done

- [ ] All collections created with their indexes via `ensure_indexes()` on service startup.
- [ ] `stable_id(natural_key)` proven idempotent across two ingest runs.
- [ ] Sample fixture inserts: ≥1 keyword definition, ≥1 gatha (Prakrit + Sanskrit + Hindi chhand), ≥1 teeka mapping, ≥1 topic extract.
- [ ] Pydantic schemas validate every fixture without errors.
- [ ] Round-trip test: upsert → fetch → upsert again → row count unchanged, fields overwritten.
