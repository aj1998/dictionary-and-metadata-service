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

## Implementation Notes — relational fan-out for shastra fuzzy match

The shastra fuzzy search (`fuzzy_search_shastras`,
`services/core_service/domains/metadata/services/shastras.py`) was widened
beyond the shastra's own name so the UI global search behaves the way users
expect:

- **Teeka-name match → parent shastra.** Searching a teeka name such as
  `राजवार्तिक` (a teeka of `तत्त्वार्थसूत्र`) now surfaces the parent shastra. The
  query LEFT JOINs an aggregate over `teekas`, taking the max trigram
  similarity of both the full `natural_key` and `split_part(natural_key, ':', 2)`
  (the bare teeka name, so the shastra prefix doesn't dilute the score).
- **Teekakar (commentator) match → parent shastra.** Searching a teekakar name
  such as `अकलंक` surfaces `तत्त्वार्थसूत्र` (whose `राजवार्तिक` teeka is by आचार्य
  अकलंकदेव). The teeka aggregate joins `authors` via `teekakar_id` and also
  scores `word_similarity(:q, display_name_text)` (gated at 0.5) so a bare name
  fragment matches a longer honorific name — plain `similarity` drops too low
  once the `आचार्य …देव` affixes dilute the trigram (0.29 < 0.4 cutoff, vs
  word_similarity 0.83). The 0.5 gate keeps out coincidental single-syllable
  overlaps (`कुन्दकुन्द` vs `नेमिचंद्र` ≈ 0.4). The same gated word_similarity is
  applied to the shastra-author match.
- **Author-name match → their shastras.** Searching an author name such as
  `कुन्दकुन्द` now surfaces every shastra authored by them. The query LEFT JOINs
  per-author similarity over `natural_key` and the concatenated `display_name`
  text values (`string_agg(elem->>'text', ' ')` over the JSONB array — extracting
  the text avoids the JSON-key noise that diluted a naive `display_name::text`).

A shastra's final score is the GREATEST of its own name/title similarity, its
best teeka-name similarity, and its author similarity. Verified on dev data at
the UI's 0.4 cutoff: `राजवार्तिक` → `तत्त्वार्थसूत्र` (1.0), `कुन्दकुन्द` → all five
Kundkund shastras (0.57) while non-Kundkund shastras stay below cutoff.

Each fuzzy shastra row also carries **why it matched** so the UI can badge it:
`match_field` (`"name"` | `"author"` | `"teeka"` | `"teekakar"`) and `match_detail`
(the matched teeka or teekakar name; null for name/author — the author name is
already on the row's `author` field). On ties the shastra's own name wins, so a
badge only appears for related-entity matches. The UI global search renders a
"लेखक" / "टीका" / "टीकाकार" pill on these rows (`ui/.../search/page.tsx`).

Tests: `tests/services/metadata/test_fuzzy_metadata.py` —
`test_fuzzy_matches_teeka_name_returns_parent_shastra`,
`test_fuzzy_matches_author_name_returns_their_shastras`.
