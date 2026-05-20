# Phase 3 — Metadata Fuzzy Match (shastras / authors / teekas)

Extends the existing metadata-service listing endpoints so chat can fetch
closest-match entities for user queries like *"समयसर"* → `samaysaar` or
*"jaichand"* → `Pandit Jaychand Chhabbra`.

Existing endpoints (per `services/metadata_service/routers/`):

- `GET /v1/shastras?q=` — currently exact/`ILIKE` over name
- `GET /v1/authors?q=` — same
- `GET /v1/teekas?q=` — same

## Change

Add `fuzzy: bool = false` and `limit: int = 10` query params to each of the
three listing endpoints. When `fuzzy=true`, switch the SQL from `ILIKE` to
`pg_trgm similarity()` and order by similarity DESC.

### Query shape (shastras)

```sql
SELECT id, natural_key, name_hi, name_en,
       GREATEST(
         similarity(name_hi, :q),
         similarity(coalesce(name_en, ''), :q),
         similarity(natural_key, :q)
       ) AS sim
FROM shastras
WHERE GREATEST(
        similarity(name_hi, :q),
        similarity(coalesce(name_en, ''), :q),
        similarity(natural_key, :q)
      ) >= :min_similarity
ORDER BY sim DESC
LIMIT :limit;
```

Analogous queries for authors (`display_name_hi`, `display_name_en`,
`natural_key`) and teekas.

### Response addition

Each row gets an optional `similarity: float` field (only when `fuzzy=true`).
Existing pagination/response envelope is preserved.

### Indexes (migration)

```
CREATE INDEX shastras_name_hi_trgm   ON shastras USING gin (name_hi gin_trgm_ops);
CREATE INDEX shastras_name_en_trgm   ON shastras USING gin (name_en gin_trgm_ops);
CREATE INDEX shastras_nk_trgm        ON shastras USING gin (natural_key gin_trgm_ops);
-- repeat for authors, teekas
```

### Defaults

- `min_similarity` 0.25 (lower than topic match — shorter strings, higher
  variance).
- `limit` 10, hard cap 50.

### Tests

- Each endpoint: golden query → expected canonical row first in result.
- Cutoff respected (no garbage matches).
- Non-fuzzy path unchanged (regression).

### DoD

- [x] Three migrations + indexes. (`migrations/versions/0017_metadata_trgm_indexes.py`)
- [x] Three endpoints updated; OpenAPI regenerated.
- [x] Existing tests still green; new fuzzy tests added. (84 passed, 24 new)
