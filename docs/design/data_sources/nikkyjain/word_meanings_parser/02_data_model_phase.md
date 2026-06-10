# Phase 2 — Data Model + Ingestion: shortFont collections

Two new Mongo collections — `gatha_teeka_bhaavarth_shortfont` (covers both primary and secondary teeka bhaavarth, distinguished by NK) and `kalash_bhaavarth_shortfont` (for kalash Hindi).

> Prereq: Phase 1 merged. Read [`00_overview.md`](00_overview.md), [`../nj_ingestion.md`](../nj_ingestion.md), [`../../../data_model/data_model_mongo.md`](../../../data_model/data_model_mongo.md).

## Goal

Persist `ShortFontEntry[]` produced by Phase 1 to MongoDB with a stable NK derived from the parent bhaavarth, and wire it through the envelope + apply layer idempotently.

## New Mongo collection — `gatha_teeka_bhaavarth_shortfont`

Add to `docs/design/data_model/data_model_mongo.md` as collection **#17** (after `kalash_word_meanings`):

```json
{
  "_id": "ObjectId(...)",
  "natural_key": "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161:shortfont",
  "bhaavarth_natural_key": "समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:161",
  "publication_natural_key": "समयसार:आत्मख्याति:0",
  "gatha_natural_key": "समयसार:गाथा:161",
  "gatha_number": "161",
  "entries": [
    {
      "marker_number": 4,
      "marker_devanagari": "४",
      "anchor_text": "मोक्ष-मार्ग-प्रपंच-सूचक",
      "meaning": "मोक्ष का विस्तार बतलाने वाली, मोक्षमार्ग का विस्तार से कथन करने वाली, मोक्षमार्ग का विस्तृत कथन करने वाली।",
      "is_definition": true,
      "occurrences": [
        {"start_offset": 1284, "end_offset": 1308}
      ]
    }
  ],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**:
- `{natural_key: 1}` UNIQUE
- `{bhaavarth_natural_key: 1}`
- `{gatha_natural_key: 1}`

**NK pattern**: `{pub_nk}:गाथा:टीका:भावार्थ:{N}:shortfont` — suffix `:shortfont` is the only delta from the parent bhaavarth NK.

Sibling collection `kalash_bhaavarth_shortfont` uses the same doc shape with `kalash_natural_key` + `teeka_natural_key` replacing the bhaavarth/gatha keys. NK pattern: `{kalash_a_nk}:shortfont`.

## Pydantic schemas

Add to `packages/jain_kb_common/db/mongo/schemas.py`:

```python
class BhaavarthShortFontEntry(BaseModel):
    marker_number: int
    marker_devanagari: str
    anchor_text: str
    meaning: str
    is_definition: bool
    occurrences: list[BhaavarthShortFontOccurrence]

class BhaavarthShortFontOccurrence(BaseModel):
    start_offset: int
    end_offset: int

class BhaavarthShortFontDoc(BaseModel):
    natural_key: str
    bhaavarth_natural_key: str
    publication_natural_key: str
    gatha_natural_key: str
    gatha_number: str
    entries: list[BhaavarthShortFontEntry]
    ingestion_run_id: str | None = None
```

Register the collection name in `collections.py` (`GATHA_TEEKA_BHAAVARTH_SHORTFONT = "gatha_teeka_bhaavarth_shortfont"`) and add the upsert + index in `upserts.py` / `indexes.py` following the pattern used by `kalash_word_meanings`.

## Envelope (`workers/ingestion/nj/envelope.py`)

Emit one Mongo doc for **each** non-empty `shortfont` field — primary teeka gatha bhaavarth (`pub_a_nk`), secondary teeka gatha bhaavarth (`pub_j_nk`), and each `KalashHindiEntry.shortfont`. Skip when entries are empty. For primary teeka:

- `table`/`collection`: `gatha_teeka_bhaavarth_shortfont`
- `natural_key`: `{pub_a_nk}:गाथा:टीका:भावार्थ:{gatha_number}:shortfont` (use existing `_norm_num`)
- Populate `entries` directly from the parser model
- Skip when `entries == []`

Multi-gatha pages: write one doc per individual gatha NK (same pattern as `gatha_teeka_bhaavarth_hindi`). The `entries` are duplicated across the expanded gathas — matches current shared-content behaviour.

Add two new `idempotency_contract` rows — one per new collection:

```python
{
  "store": "mongo",
  "collection": "gatha_teeka_bhaavarth_shortfont",
  "conflict_key": "natural_key",
  "on_conflict": "replace",
  "fields_replace": ["entries", "ingestion_run_id", "updated_at"],
}
```

## Apply (`workers/ingestion/nj/apply.py`)

No new FK dependency — the collection is a sibling of `gatha_teeka_bhaavarth_hindi` and shares its write phase. Add a call to the new upsert in the same block.

## Tests

`tests/workers/nj/test_envelope.py` — add cases:
- doc emitted when parser produces entries; absent otherwise
- NK pattern correctness
- multi-gatha duplication

`tests/workers/nj/test_apply_unit.py` — add cases:
- NFC normalisation of `anchor_text` + `meaning`
- idempotency: running apply twice keeps doc count stable
- `entries` ordering preserved by `marker_number`

`tests/db/mongo/test_mongo_upsert.py` — add a round-trip test for the new upsert + unique-NK constraint.

## Verification

```bash
python -m pytest tests/workers/nj/test_envelope.py tests/workers/nj/test_apply_unit.py -v
python -m pytest tests/db/mongo/ -v

# Smoke: re-ingest one shastra and inspect Mongo
python scripts/ingest_nj_apply.py --config parser_configs/nj/panchaastikaya.yaml --gatha 161
mongosh jain_kb --eval 'db.gatha_teeka_bhaavarth_shortfont.findOne({gatha_number: "161"})'
```

## Done when

- [x] Collection + indexes ensured via `ensure_indexes()` on service startup.
- [x] Envelope emits docs only when entries exist; idempotency contract present.
- [x] Apply test suite green; full NJ suite green.
- [ ] [`data_model_mongo.md`](../../../data_model/data_model_mongo.md) updated.
- [ ] Implementation notes appended here and in [`../nj_ingestion.md`](../nj_ingestion.md).

## Implementation Notes

**Implemented 2026-06-10.**

### NK convention
The `bhaavarth_natural_key` and shortfont `natural_key` are derived from the **Neo4j `GathaTeekaBhaavarth` node key** (not the Mongo `gatha_teeka_bhaavarth_hindi` doc NK, which uses a different segment order):

- Gatha bhaavarth NK: `{pub_nk}:गाथा:टीका:भावार्थ:{N}` (matches `_build_neo4j` existing pattern)
- Shortfont NK: `{bhaavarth_nk}:shortfont` (suffix-only delta as specced)
- Kalash shortfont NK: `{kalash_nk}:shortfont` where `kalash_nk = {teeka_nk}:कलश:{N}`

### Files changed
- `packages/jain_kb_common/jain_kb_common/db/mongo/collections.py` — added `GATHA_TEEKA_BHAAVARTH_SHORTFONT`, `KALASH_BHAAVARTH_SHORTFONT`
- `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py` — added `BhaavarthShortFontOccurrence`, `BhaavarthShortFontEntry`, `BhaavarthShortFontDoc`, `KalashBhaavarthShortFontDoc`
- `packages/jain_kb_common/jain_kb_common/db/mongo/upserts.py` — added `upsert_gatha_teeka_bhaavarth_shortfont`, `upsert_kalash_bhaavarth_shortfont`
- `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py` — added 6 new indexes
- `workers/ingestion/nj/envelope.py` — added `_shortfont_entries()` helper, shortfont emission for primary/secondary gatha bhaavarth + primary kalash hindi + secondary kalash bhaavarth; two new idempotency contracts
- `workers/ingestion/nj/apply.py` — added import + call to both new upserts

### Coverage
101 NJ tests green; 28 mongo upsert tests green (including 4 new schema/round-trip tests).
