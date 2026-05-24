# 03 — Data Model Changes (nikkyjain ingestion)

Required schema additions and modifications to support the nikkyjain per-file HTML ingestion
(`01_parser_nj.md`, `02_ingestion_nj.md`). All changes are additive — no existing fields removed.

---

## 1. Postgres Changes

### 1.1 `kalashas` table — add `gatha_id` FK

Add a nullable UUID foreign key from `kalashas` to `gathas`. This records which gatha
"owns" each kalash:
- For primary-teeka kalashes: the gatha page on which the kalash appears.
- For secondary-teeka standalone kalashes: the last primary-gatha that preceded the kalash file
  in sorted file order.

**SQLAlchemy model change** (`packages/jain_kb_common/jain_kb_common/db/postgres/kalashas.py`):

```python
# ADD (new field, nullable to avoid breaking existing rows):
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

class Kalash(Base, TimestampMixin):
    __tablename__ = "kalashas"
    __table_args__ = (
        Index("idx_kalashas_teeka", "teeka_id"),
        Index("idx_kalashas_gatha", "gatha_id"),   # NEW
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    teeka_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teekas.id", ondelete="CASCADE"), nullable=False
    )
    kalash_number: Mapped[str] = mapped_column(Text, nullable=False)
    gatha_id: Mapped[uuid.UUID | None] = mapped_column(   # NEW
        UUID(as_uuid=True),
        ForeignKey("gathas.id", ondelete="SET NULL"),
        nullable=True,
    )
    sanskrit_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    hindi_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    bhaavarth_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
```

**Alembic migration** (`migrations/versions/0018_kalashas_gatha_id_fk.py`):

```python
"""add gatha_id FK to kalashas

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"

def upgrade() -> None:
    op.add_column(
        "kalashas",
        sa.Column("gatha_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_kalashas_gatha_id",
        "kalashas", "gathas",
        ["gatha_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_kalashas_gatha", "kalashas", ["gatha_id"])


def downgrade() -> None:
    op.drop_index("idx_kalashas_gatha", table_name="kalashas")
    op.drop_constraint("fk_kalashas_gatha_id", "kalashas", type_="foreignkey")
    op.drop_column("kalashas", "gatha_id")
```

---

## 2. MongoDB Schema Changes

### 2.1 `GathaWordMeanings` — add `full_anyavaarth`

**File**: `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py`

```python
# BEFORE
class GathaWordMeanings(BaseModel):
    natural_key: str
    gatha_natural_key: str
    source_language: str
    entries: list[WordMeaningEntry]
    ingestion_run_id: Optional[str] = None

# AFTER
class GathaWordMeanings(BaseModel):
    natural_key: str
    gatha_natural_key: str
    source_language: str
    full_anyavaarth: Optional[str] = None   # NEW: complete Hindi anyavartha text (no markup)
    entries: list[WordMeaningEntry]
    ingestion_run_id: Optional[str] = None
```

`full_anyavaarth` stores the complete anyavartha sentence as plain text (BOM-stripped, NFC-normalized),
without the leading `"अन्वयार्थ :"` prefix.
Optional for backwards compatibility; all new nikkyjain-ingested docs will have it.

### 2.2 `TeekaGathaMapping` — add `is_related` and `full_anyavaarth`

```python
# BEFORE
class TeekaGathaMapping(BaseModel):
    natural_key: str
    teeka_natural_key: str
    gatha_natural_key: str
    anvayartha: list[LangText]
    tagged_terms: list[TaggedTerm] = []
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None

# AFTER
class TeekaGathaMapping(BaseModel):
    natural_key: str
    teeka_natural_key: str
    gatha_natural_key: str
    anvayartha: list[LangText]
    tagged_terms: list[TaggedTerm] = []
    full_anyavaarth: Optional[str] = None   # NEW: plain text anyavartha
    is_related: list[str] = []              # NEW: gatha_numbers of siblings on multi-gatha pages
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None
```

`is_related` contains the gatha_number strings of the other gathas that share the same HTML page.
Empty list for all non-combined pages.

### 2.3 New: `KalashWordMeanings`

Add to `schemas.py`:

```python
class KalashWMEntry(BaseModel):
    source_word: str    # Sanskrit/Prakrit key (from maroon-colored text)
    meaning: str        # Hindi meaning
    position: int       # 1-based

class KalashWordMeanings(BaseModel):
    natural_key: str                # e.g. "samaysar:amritchandra:kalash:001:word_meanings"
    kalash_natural_key: str         # e.g. "samaysar:amritchandra:kalash:001"
    teeka_natural_key: str          # e.g. "samaysar:amritchandra"
    kalash_number: str              # e.g. "001"
    entries: list[KalashWMEntry]
    ingestion_run_id: Optional[str] = None
```

---

## 3. MongoDB Collections

### 3.1 New constant

**File**: `packages/jain_kb_common/jain_kb_common/db/mongo/collections.py`

```python
# ADD at end of file:
KALASH_WORD_MEANINGS = "kalash_word_meanings"
```

### 3.2 New indexes

**File**: `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py`

Add inside `ensure_indexes()`:

```python
# kalash_word_meanings (NEW collection)
await db.kalash_word_meanings.create_index(
    [("natural_key", pymongo.ASCENDING)], unique=True
)
await db.kalash_word_meanings.create_index(
    [("kalash_natural_key", pymongo.ASCENDING)]
)
await db.kalash_word_meanings.create_index(
    [("teeka_natural_key", pymongo.ASCENDING)]
)
```

---

## 4. MongoDB Upsert Functions

**File**: `packages/jain_kb_common/jain_kb_common/db/mongo/upserts.py`

Add a new function for the new collection:

```python
async def upsert_kalash_word_meanings(
    db: AsyncIOMotorDatabase,
    *,
    natural_key: str,
    kalash_natural_key: str,
    teeka_natural_key: str,
    kalash_number: str,
    entries: list[dict],           # list of {source_word, meaning, position}
    ingestion_run_id: str | None = None,
) -> ObjectId:
    doc_id = stable_id(natural_key)
    await db[KALASH_WORD_MEANINGS].update_one(
        {"_id": doc_id},
        {"$set": {
            "natural_key": nfc(natural_key),
            "kalash_natural_key": nfc(kalash_natural_key),
            "teeka_natural_key": nfc(teeka_natural_key),
            "kalash_number": kalash_number,
            "entries": entries,
            "ingestion_run_id": ingestion_run_id,
        }},
        upsert=True,
    )
    return doc_id
```

Also update the existing `upsert_gatha_word_meanings` and `upsert_teeka_gatha_mapping` function
signatures to accept the new fields:

```python
# upsert_gatha_word_meanings — add parameter:
async def upsert_gatha_word_meanings(
    db, *, natural_key, gatha_natural_key, source_language,
    full_anyavaarth: str | None = None,    # NEW
    entries, ingestion_run_id=None,
) -> ObjectId:
    # include "full_anyavaarth": full_anyavaarth in the $set dict

# upsert_teeka_gatha_mapping — add parameters:
async def upsert_teeka_gatha_mapping(
    db, *, natural_key, teeka_natural_key, gatha_natural_key,
    anvayartha, tagged_terms=None,
    full_anyavaarth: str | None = None,    # NEW
    is_related: list[str] | None = None,   # NEW
    raw_html_fragment=None, ingestion_run_id=None,
) -> ObjectId:
    # include both new fields in the $set dict
```

---

## 5. API Service Changes

**File**: `docs/design/api/data/01_spec.md`

### 5.1 New endpoint — Kalash word meanings

```
GET /v1/kalashas/{kalash_id}/word_meanings
```

**Response 200:**
```json
{
  "kalash_id": "uuid",
  "kalash_natural_key": "samaysar:amritchandra:kalash:001",
  "teeka_natural_key": "samaysar:amritchandra",
  "kalash_number": "001",
  "entries": [
    {"source_word": "स्वानुभूत्या चकासते", "meaning": "स्वानुभूति से प्रकाशित", "position": 1}
  ]
}
```

**Response 404:** `{"detail": "No word meanings found for kalash {kalash_id}"}`

The endpoint looks up `kalash_word_meanings` collection by `kalash_natural_key` (resolved from the
Postgres `Kalash.natural_key` via `kalash_id`).

### 5.2 Updated endpoint — Gatha word meanings

```
GET /v1/gathas/{gatha_id}/word_meanings
```

Add `full_anyavaarth` to the existing response:

```json
{
  "gatha_id": "uuid",
  "source_language": "pra",
  "full_anyavaarth": "ध्रुव, अचल और अनुपम गति को प्राप्त हुए...",
  "entries": [...]
}
```

### 5.3 Updated endpoint — Teeka-Gatha mapping

```
GET /v1/teekas/{teeka_id}/gathas/{gatha_id}/mapping
```

Add `full_anyavaarth` and `is_related` to the existing response:

```json
{
  "teeka_natural_key": "samaysar:amritchandra",
  "gatha_natural_key": "samaysar:001",
  "anvayartha": [...],
  "tagged_terms": [...],
  "full_anyavaarth": "...",
  "is_related": []
}
```

---

## 6. UI Changes

**Reference**: `ui/README.md`

The following UI components need updating to consume the new API fields:

| Component | Change |
|---|---|
| `GathaWordMeaningsPanel` | Display `full_anyavaarth` as a continuous prose block above the tagged terms table. |
| `KalashPanel` | Add a "Word Meanings" sub-section fetching `GET /v1/kalashas/{id}/word_meanings`. |
| `TeekaGathaMappingView` | Show `is_related` as a list of linked gatha numbers when non-empty. |
| `GathaWordMeaningsPanel` | No UI change for `is_related` (it's a backend cross-reference field). |

---

## 7. jain_kb_common Package — Summary of File Changes

| File | Change |
|---|---|
| `db/postgres/kalashas.py` | Add `gatha_id` nullable FK column + `idx_kalashas_gatha` index |
| `db/mongo/collections.py` | Add `KALASH_WORD_MEANINGS = "kalash_word_meanings"` |
| `db/mongo/schemas.py` | Add `full_anyavaarth` to `GathaWordMeanings`; add `full_anyavaarth` + `is_related` to `TeekaGathaMapping`; add new `KalashWMEntry` + `KalashWordMeanings` models |
| `db/mongo/indexes.py` | Add three indexes for `kalash_word_meanings` collection |
| `db/mongo/upserts.py` | Add `upsert_kalash_word_meanings()`; extend `upsert_gatha_word_meanings()` + `upsert_teeka_gatha_mapping()` signatures |

**Migrations:**
| File | Change |
|---|---|
| `migrations/versions/0018_kalashas_gatha_id_fk.py` | Add `gatha_id` column, FK, and index to `kalashas` |

---

## 8. Definition of Done

- [ ] Migration `0018` runs successfully on a fresh DB and on a DB with existing kalash rows.
- [ ] `kalashas` PG rows written by `ingest_nj_apply.py` have non-null `gatha_id` for new inserts.
- [ ] `gatha_word_meanings` Mongo docs have `full_anyavaarth` populated for all nikkyjain-sourced gathas.
- [ ] `teeka_gatha_mapping` docs have `is_related` populated for multi-gatha pages; empty list for normal pages.
- [ ] `kalash_word_meanings` collection is queryable by `kalash_natural_key`.
- [ ] `GET /v1/kalashas/{id}/word_meanings` returns 200 for a kalash that has word meanings; 404 otherwise.
- [ ] `GET /v1/gathas/{id}/word_meanings` returns `full_anyavaarth` field.
- [ ] `ensure_indexes()` creates all three `kalash_word_meanings` indexes without error.
- [ ] Existing tests (not touching kalashas or word meanings) continue to pass after the migration.

---

## 9. Implementation Notes (2026-05-24)

All items in sections 1–5 are implemented. Diversions from the spec:

### 9.1 Postgres model (`kalashas.py`)
Implemented exactly as spec. `gatha_id` nullable FK added with `ondelete="SET NULL"`.

### 9.2 MongoDB upsert signatures
The spec showed fully explicit keyword-arg signatures for `upsert_gatha_word_meanings` and `upsert_teeka_gatha_mapping`. To preserve backward compatibility with existing callers (which pass `doc: dict`), the `doc: dict` parameter was retained and the new fields (`full_anyavaarth`, `is_related`) were added as **optional** keyword arguments that merge into the doc dict when non-`None`. This is functionally equivalent to the spec intent.

`upsert_kalash_word_meanings` uses explicit keyword args as spec'd (it is a new function with no existing callers).

### 9.3 API endpoint
`GET /v1/kalashas/{ident}/word_meanings` looks up the MongoDB `kalash_word_meanings` collection by `natural_key = f"{kalash.natural_key}:word_meanings"`. Returns 404 for both "kalash not found" and "kalash found but no word_meanings document" cases (combined into one 404, per spec wording).

### 9.4 Section 5 (API) — gatha word_meanings / teeka_mapping endpoints
These fields appear automatically in existing responses since those endpoints return raw MongoDB dicts; no router code changes were needed. The `full_anyavaarth` and `is_related` fields will be present in responses once ingestion populates them.

### 9.5 Section 6 (UI)
Implemented 2026-05-24. Changes:

- `ui/src/lib/types.ts`: Added proper TypeScript types for `GathaWordMeanings` (with `full_anyavaarth`), `TeekaGathaMapping` (with `full_anyavaarth`, `is_related`), `KalashDetail`, `KalashWordMeanings`, `KalashWordMeaningEntry`.
- `ui/src/lib/api/data.ts`: Updated `getGatha()` to accept `options.include` query param; added `getKalash()` and `getKalashWordMeanings()` (returns `null` on 404).
- `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`: Fetches with `?include=teeka_mapping`; shows `full_anyavaarth` prose block above tagged-terms in शब्दार्थ; uses `word_meanings.prakrit.entries` for popovers (falls back to token-split if absent); टीका section now renders `TeekaGathaMapping[]` with `full_anyavaarth`, `tagged_terms`, `anvayartha`, and `is_related` sibling links.
- `ui/src/app/[locale]/(reading)/shastras/[nk]/kalashas/[number]/page.tsx` (new): Kalash reading page with Sanskrit/Hindi text panels, शब्दार्थ section from `KalashWordMeanings`, and भावार्थ section.
