# 15 — Multilingual Keyword & Topic Label Storage Spec

Scope context: [`scope/05_multilingual_strategy.md`](../../scope/05_multilingual_strategy.md) and [`docs/design/02_data_model_postgres.md`](../02_data_model_postgres.md) (`keywords`, `topics`, and any other `label` / `display_text` columns currently typed `TEXT`).

Today, `keywords.label`, `topics.label`, `topics.display_text`, and a handful of other label columns store a single Hindi string. With Kannada + Gujarati + Sanskrit + Prakrit overlays landing (see spec 16) the schema must hold multiple `(lang, script, text, transliteration?)` records per row. This spec migrates those columns from `TEXT` to multilingual JSONB, backfills existing rows non-destructively, enforces NFC on insert, and ships a `get_label()` helper with a deterministic fallback chain.

Single-phase: one migration + model updates + helper + endpoint patches + tests.

## Module paths

```
services/data-service/alembic/versions/
└── 0034_multilingual_labels.py        # the migration

packages/jain_kb_common/models/
├── keywords.py                        # ORM updated, label_multilingual added
├── topics.py
└── multilingual.py                    # new: helpers + Pydantic models

packages/jain_kb_common/text/
└── normalisation.py                   # nfc(), enforce_nfc_jsonb_label() trigger helper

services/data-service/app/routers/
├── keywords.py                        # GET /v1/keywords?q=&lang=&script=
└── topics.py                          # idem

tests/multilingual/
├── conftest.py
├── fixtures/
│   ├── pre_migration_seed.sql
│   └── multi_script_seed.sql
├── test_migration_backfill_correctness.py
├── test_nfc_enforcement.py
├── test_fallback_chain.py
├── test_search_across_scripts.py
└── test_round_trip_preserves_transliteration.py
```

## Canonical JSONB shape

```json
[
  {"lang": "hi", "script": "Deva", "text": "आत्मा"},
  {"lang": "hi", "script": "Latn", "text": "ātmā", "transliteration": "IAST"},
  {"lang": "en", "script": "Latn", "text": "Soul"},
  {"lang": "sa", "script": "Deva", "text": "आत्मन्"},
  {"lang": "kn", "script": "Knda", "text": "ಆತ್ಮ"},
  {"lang": "gu", "script": "Gujr", "text": "આત્મા"}
]
```

Field rules:
- `lang` — ISO-639-1 (2-letter) where it exists, ISO-639-3 (3-letter) otherwise. Allowed: `hi`, `en`, `sa`, `pr` (Prakrit), `kn`, `gu`. (Additional codes are *not* rejected but should be added consciously.)
- `script` — ISO-15924 4-letter. `Deva`, `Latn`, `Knda`, `Gujr`, `Brah` allowed.
- `text` — NFC-normalised; non-empty.
- `transliteration` — optional; one of `IAST`, `ISO15919`, `Velthuis`, `ITRANS`, `Hunterian`. Only valid when `script='Latn'`.

The JSONB is a list (order = preferred display order set by the editor), not a map keyed by `lang`. Multiple entries per `(lang, script)` are allowed (alternate spellings).

## Migration `0034_multilingual_labels.py`

Affected columns (audited from `02_data_model_postgres.md`):

| Table | Column | New column |
|---|---|---|
| `keywords` | `label` (TEXT) | `label_multilingual` (JSONB) |
| `topics` | `label` (TEXT) | `label_multilingual` (JSONB) |
| `topics` | `display_text` (TEXT) | folded into `label_multilingual` |
| `shastras` | `title` (TEXT) | `title_multilingual` (JSONB) |
| `adhikaars` | `heading` (TEXT) | `heading_multilingual` (JSONB) |
| `research_categories` | (already JSONB per spec 13) | — |

The DDL adds the new columns alongside the legacy ones (no `DROP COLUMN` in this migration; legacy columns are dropped in a follow-up after one release cycle).

```sql
-- Forward
ALTER TABLE keywords ADD COLUMN label_multilingual JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE topics   ADD COLUMN label_multilingual JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE shastras ADD COLUMN title_multilingual JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE adhikaars ADD COLUMN heading_multilingual JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Backfill: legacy text → single hi/Deva record
UPDATE keywords SET label_multilingual = jsonb_build_array(
  jsonb_build_object('lang','hi','script','Deva','text', label))
WHERE label IS NOT NULL AND label <> '' AND label_multilingual = '[]'::jsonb;

UPDATE topics SET label_multilingual = jsonb_build_array(
  jsonb_build_object('lang','hi','script','Deva','text', COALESCE(display_text, label)))
WHERE (label IS NOT NULL OR display_text IS NOT NULL)
  AND label_multilingual = '[]'::jsonb;

UPDATE shastras SET title_multilingual = jsonb_build_array(
  jsonb_build_object('lang','hi','script','Deva','text', title))
WHERE title IS NOT NULL AND title_multilingual = '[]'::jsonb;

UPDATE adhikaars SET heading_multilingual = jsonb_build_array(
  jsonb_build_object('lang','hi','script','Deva','text', heading))
WHERE heading IS NOT NULL AND heading_multilingual = '[]'::jsonb;

-- Shape constraint
ALTER TABLE keywords ADD CONSTRAINT chk_keywords_label_ml_shape
  CHECK (jsonb_typeof(label_multilingual) = 'array');
ALTER TABLE topics   ADD CONSTRAINT chk_topics_label_ml_shape
  CHECK (jsonb_typeof(label_multilingual) = 'array');
-- (similar for shastras, adhikaars)

-- GIN indexes for search across scripts
CREATE INDEX idx_keywords_label_ml_gin ON keywords USING gin (label_multilingual jsonb_path_ops);
CREATE INDEX idx_topics_label_ml_gin   ON topics   USING gin (label_multilingual jsonb_path_ops);
```

NFC enforcement is via a `BEFORE INSERT OR UPDATE` trigger (Python migrations write the trigger function):

```sql
CREATE OR REPLACE FUNCTION enforce_multilingual_label_nfc() RETURNS TRIGGER AS $$
DECLARE
  elem jsonb;
  rebuilt jsonb := '[]'::jsonb;
BEGIN
  IF NEW.label_multilingual IS NULL THEN
    RETURN NEW;
  END IF;
  FOR elem IN SELECT * FROM jsonb_array_elements(NEW.label_multilingual) LOOP
    IF (elem->>'text') IS NULL OR length(elem->>'text') = 0 THEN
      RAISE EXCEPTION 'multilingual label entry missing text';
    END IF;
    -- normalize() requires PG 13+; uses Unicode NFC
    rebuilt := rebuilt || jsonb_build_object(
      'lang',   elem->>'lang',
      'script', elem->>'script',
      'text',   normalize(elem->>'text', NFC),
      'transliteration', elem->'transliteration');
  END LOOP;
  NEW.label_multilingual := rebuilt;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_keywords_label_nfc BEFORE INSERT OR UPDATE OF label_multilingual
  ON keywords FOR EACH ROW EXECUTE FUNCTION enforce_multilingual_label_nfc();
-- (same for topics; analogous trigger functions for title_multilingual / heading_multilingual)
```

Down-migration: drop the new columns + triggers + indexes; legacy `label` / `display_text` / `title` / `heading` columns remain untouched, so a downgrade is loss-free.

## Pydantic models (`packages/jain_kb_common/models/multilingual.py`)

```python
class MultilingualLabel(BaseModel):
    lang: Literal['hi','en','sa','pr','kn','gu']
    script: Literal['Deva','Latn','Knda','Gujr','Brah']
    text: str = Field(min_length=1)
    transliteration: Literal['IAST','ISO15919','Velthuis','ITRANS','Hunterian'] | None = None

    @field_validator('text')
    @classmethod
    def _nfc(cls, v: str) -> str:
        return unicodedata.normalize('NFC', v)

    @model_validator(mode='after')
    def _translit_only_if_latn(self) -> 'MultilingualLabel':
        if self.transliteration and self.script != 'Latn':
            raise ValueError('transliteration only allowed when script=Latn')
        return self


MultilingualLabelList = list[MultilingualLabel]
```

## Lookup helpers

```python
# packages/jain_kb_common/models/multilingual.py

DEFAULT_FALLBACK = ('hi-Deva', 'hi-Latn', 'en-Latn', 'sa-Deva', 'sa-Latn',
                    'pr-Deva', 'kn-Knda', 'gu-Gujr')

def get_label(rows: list[dict] | list[MultilingualLabel],
              preferences: list[str] | None = None,
              *, default: str | None = None) -> str:
    """
    preferences: list of 'lang-script' tokens, in priority order
                 ('hi', 'hi-Deva', 'en' all accepted; 'hi' matches any script).
    Returns the first matching `text`, or `default`, or the first entry's text,
    or '' if rows is empty.
    """
    prefs = tuple(preferences or DEFAULT_FALLBACK)
    rows = [r if isinstance(r, dict) else r.model_dump() for r in rows]
    for pref in prefs:
        for r in rows:
            if _matches(r, pref):
                return r['text']
    if rows:
        return rows[0]['text']
    return default or ''

def _matches(row: dict, pref: str) -> bool:
    if '-' in pref:
        lang, script = pref.split('-', 1)
        return row.get('lang') == lang and row.get('script') == script
    return row.get('lang') == pref

def best_label(rows, user_prefs: list[str] | None = None) -> str:
    """Convenience wrapper used by the response serializer."""
    return get_label(rows, user_prefs)
```

## Endpoint updates

### `services/data-service/app/routers/keywords.py`

```python
@router.get('/v1/keywords')
async def list_keywords(q: str | None = None,
                        lang: str | None = None,
                        script: str | None = None,
                        page: int = 1, size: int = 50):
    stmt = select(Keyword)
    if q:
        q_nfc = nfc(q)
        # match any element whose text contains q_nfc, regardless of (lang, script)
        stmt = stmt.where(text("""
            EXISTS (
              SELECT 1 FROM jsonb_array_elements(label_multilingual) e
              WHERE e->>'text' ILIKE :pat
                AND (:lang IS NULL OR e->>'lang' = :lang)
                AND (:script IS NULL OR e->>'script' = :script)
            )""")).params(pat=f'%{q_nfc}%', lang=lang, script=script)
    rows = await pg.execute(stmt.offset((page-1)*size).limit(size))
    return [_serialize(r, user_prefs=resolve_user_prefs()) for r in rows]
```

Response includes both the chosen display string (per user prefs) and the full multilingual list:

```python
class KeywordOut(BaseModel):
    id: UUID
    natural_key: str
    label: str                                  # resolved via get_label()
    label_multilingual: list[MultilingualLabel]
```

Identical pattern for `/v1/topics`. The user-preference list is sourced from `user_preferences.lang_default` + `lang_overlay` (spec 01) when a JWT is present, falling back to `DEFAULT_FALLBACK` otherwise.

## Tests (TDD)

1. `test_migration_backfill_correctness.py` — seed pre-migration corpus: 100 keyword rows with non-null `label`. Run upgrade. Every row's `label_multilingual` equals `[{lang:'hi', script:'Deva', text: <nfc(label)>}]`. Empty/null source labels yield `[]`.
2. `test_nfc_enforcement.py` — insert a keyword with a denormalised Devanagari sequence (e.g. precomposed vs decomposed `क + ्`) → fetched row has the NFC form. Inserting with `text=''` raises.
3. `test_fallback_chain.py` — keyword row with `[{lang:'hi','script':'Deva','text':'आत्मा'},{lang:'en','script':'Latn','text':'Soul'}]`. `get_label(row, ['kn-Knda'])` falls through `DEFAULT_FALLBACK` and returns `'आत्मा'`. `get_label(row, ['en','hi'])` returns `'Soul'`. Empty list returns `''`.
4. `test_search_across_scripts.py` — seed multi-script rows from `multi_script_seed.sql`. Query `/v1/keywords?q=ātmā` matches the row with `[…, {lang:'hi', script:'Latn', text:'ātmā'}]` even though the canonical Devanagari entry is also present. `?q=ಆತ್ಮ` matches the Kannada entry. `?q=आत्मा&lang=hi&script=Deva` returns only the Devanagari hit.
5. `test_round_trip_preserves_transliteration.py` — POST a keyword with `{lang:'hi','script':'Latn','text':'ātmā','transliteration':'IAST'}`. GET returns the same record with `transliteration` preserved. Attempting `{script:'Deva', transliteration:'IAST'}` returns 422.
6. `test_legacy_text_columns_unchanged.py` — after migration, `keywords.label` (legacy) is bit-identical to its pre-migration value; the migration is purely additive.

## Manual verification

```bash
# 1. Pre-migration snapshot
psql -c "SELECT id, label FROM keywords ORDER BY id LIMIT 5;" > /tmp/before.txt

# 2. Apply migration
alembic upgrade 0034_multilingual_labels

# 3. Confirm backfill
psql -c "SELECT id, label, label_multilingual FROM keywords ORDER BY id LIMIT 5;"

# 4. Insert a multi-script row
psql -c "UPDATE keywords SET label_multilingual = label_multilingual ||
         '[{\"lang\":\"en\",\"script\":\"Latn\",\"text\":\"Soul\"},
           {\"lang\":\"kn\",\"script\":\"Knda\",\"text\":\"ಆತ್ಮ\"}]'::jsonb
         WHERE natural_key='आत्मा';"

# 5. Search by English
curl 'http://localhost:8001/v1/keywords?q=soul'

# 6. Search by Kannada
curl 'http://localhost:8001/v1/keywords?q=ಆತ್ಮ'

# 7. Fallback chain (Kannada user prefs)
curl -b cookies_kn_user.txt 'http://localhost:8001/v1/keywords/आत्मा'
# → response.label = 'ಆತ್ಮ' (kn-Knda matches before en-Latn fallback)

# 8. NFC enforcement
psql -c "INSERT INTO keywords (natural_key, label_multilingual) VALUES
         ('test', '[{\"lang\":\"hi\",\"script\":\"Deva\",\"text\":\"क्\"}]');"
psql -c "SELECT label_multilingual FROM keywords WHERE natural_key='test';"
# → 'text' is NFC-normalised in the stored value
```

## Definition of done

- [ ] Migration `0034_multilingual_labels.py` applies clean, including triggers and indexes.
- [ ] Backfill produces a non-empty `label_multilingual` for every previously non-null `label`.
- [ ] All 6 tests pass.
- [ ] Legacy `label` / `display_text` / `title` / `heading` columns remain untouched (no data loss).
- [ ] `get_label()` is consumed by the `/v1/keywords` and `/v1/topics` serializers and respects `user_preferences`.
- [ ] Search endpoints accept queries in any of `hi/en/sa/kn/gu` and return matching rows.
- [ ] Downstream specs 13 and 16 read `label_multilingual` directly (no dependency on legacy columns).

## Implementation notes

_(to be filled in after merge)_
