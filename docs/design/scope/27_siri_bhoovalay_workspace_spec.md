# 27 — Siri Bhoovalay Workspace Spec

Scope context: [`scope/07_siri_bhoovalay_and_research_models.md`](../../scope/07_siri_bhoovalay_and_research_models.md). Depends on spec [`26_sanskrit_prakrit_model_spec`](./26_sanskrit_prakrit_model_spec.md) (Sa/Pr LoRA + model-serving routing) and spec [`23_model_serving_registry_spec`](./23_model_serving_registry_spec.md) (model_registry table + router endpoint).

A new `bhoovalay-service` (port 8009) owns chakra storage, mapping tables, path generation, and an LLM helper that scores decoded paths via model-serving. A Next.js workspace at `ui/app/research-tools/siri-bhoovalay/page.tsx` renders the chakra, lets the user pick or draw a path, and decodes client-side. The Sa/Pr model is called *only* when the user clicks "score" or "cross-reference" — the workspace must be usable with zero LLM calls.

The decoder is not novel cryptanalysis. v1 ships a *workspace* that makes decoding faster by giving the researcher (a) the chakra, (b) parametric path generators, (c) a configurable syllable map, (d) a perplexity score, and (e) a corpus cross-reference.

## Phase A — data layer

### Files

```
services/bhoovalay_service/
├── __init__.py
├── main.py                FastAPI app, /healthz, lifespan, CORS (port 8009)
├── config.py              Settings (DATABASE_URL, MODEL_SERVING_URL,
│                          CATALOGUESEARCH_URL, PORT=8009)
├── deps.py                AsyncSession dep, current_user_optional dep
├── routers/
│   ├── chakras.py         GET /v1/bhoovalay/chakras,
│   │                      GET /v1/bhoovalay/chakras/{n}
│   ├── mappings.py        GET /v1/bhoovalay/mappings,
│   │                      GET /v1/bhoovalay/mappings/{name}
│   ├── paths.py           GET /v1/bhoovalay/paths?chakra={n}&kind=canonical|user,
│   │                      POST /v1/bhoovalay/paths      (auth required, kind=user),
│   │                      DELETE /v1/bhoovalay/paths/{id}
│   └── decode.py          POST /v1/bhoovalay/decode    (server-side mapping helper)
├── path_engine/
│   ├── __init__.py
│   ├── generators.py      parametric path generators (see below)
│   └── decode.py          path + chakra + mapping → syllable stream
└── tests/
    ├── conftest.py
    ├── test_path_generators.py
    ├── test_decode_round_trip.py
    └── test_chakra_loader.py

packages/jain_kb_common/db/postgres/bhoovalay.py    SQLAlchemy models
parser_configs/bhoovalay/
├── chakras/0001.json            cell_values + source metadata
├── mappings/kannada_default.json
├── mappings/sanskrit_default.json
├── mappings/prakrit_default.json
└── canonical_paths.yaml         seed canonical patterns
```

### Postgres schema (migration `0050_bhoovalay.py`)

```sql
CREATE TYPE bhoovalay_target_script AS ENUM ('kn','sa','pr','deva','ka');
CREATE TYPE bhoovalay_path_kind AS ENUM ('canonical','user');

CREATE TABLE bhoovalay_chakras (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chakra_number INT  NOT NULL UNIQUE,                -- 1..1270
  cell_values   JSONB NOT NULL,                      -- 27x27 array of ints 1..64
  source        TEXT NOT NULL,                       -- e.g. 'shastra:siri_bhoovalay:vol1:p23'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_array_length(cell_values) = 27)
);

CREATE TABLE bhoovalay_mappings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,                -- e.g. 'kannada_default'
  mapping       JSONB NOT NULL,                      -- {"1": "अ", "2": "आ", ...} (string keys for JSON)
  target_script bhoovalay_target_script NOT NULL,
  source        TEXT NOT NULL,                       -- e.g. 'Yellappa Shastri 1953'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bhoovalay_paths (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chakra_id            UUID NOT NULL REFERENCES bhoovalay_chakras(id) ON DELETE CASCADE,
  name                 TEXT NOT NULL,
  path_cells           JSONB NOT NULL,               -- ordered list of [r,c] pairs, 0-indexed, both 0..26
  kind                 bhoovalay_path_kind NOT NULL,
  owner_user_id        UUID REFERENCES users(id) ON DELETE CASCADE,   -- NULL for canonical
  decoded_text_doc_id  TEXT,                         -- mongo id of stored decoded text (optional)
  language_guess       TEXT,                         -- 'sa' | 'pr' | 'kn' | 'unknown'
  score                FLOAT,                        -- perplexity (lower = better) from last scoring run
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((kind = 'canonical' AND owner_user_id IS NULL)
         OR (kind = 'user' AND owner_user_id IS NOT NULL))
);
CREATE INDEX idx_bhoovalay_paths_chakra ON bhoovalay_paths(chakra_id);
CREATE INDEX idx_bhoovalay_paths_owner ON bhoovalay_paths(owner_user_id);
CREATE UNIQUE INDEX idx_bhoovalay_paths_user_name
  ON bhoovalay_paths(owner_user_id, chakra_id, name) WHERE kind = 'user';
```

`cell_values` shape: `[[v00,v01,...,v0_26], [v10,...], ...]`. Validator enforces 27 rows × 27 cols, every value `1..64`.

### Pydantic contracts (excerpt)

```python
# packages/jain_kb_common/db/postgres/bhoovalay.py
class ChakraOut(BaseModel):
    id: UUID
    chakra_number: int
    cell_values: list[list[int]]  # 27x27
    source: str

class MappingOut(BaseModel):
    id: UUID
    name: str
    mapping: dict[str, str]        # JSON keys are strings
    target_script: Literal['kn','sa','pr','deva','ka']
    source: str

class PathIn(BaseModel):
    chakra_number: int
    name: constr(min_length=1, max_length=80)
    path_cells: list[tuple[int, int]]  # each tuple (r, c) 0..26
    language_guess: Literal['sa','pr','kn','unknown'] = 'unknown'

class PathOut(PathIn):
    id: UUID
    kind: Literal['canonical','user']
    owner_user_id: UUID | None
    decoded_text_doc_id: str | None
    score: float | None
    created_at: datetime
```

### Path data structure — parametric generators

Canonical patterns are stored as YAML in `parser_configs/bhoovalay/canonical_paths.yaml` and seeded into `bhoovalay_paths` (kind=canonical, owner_user_id=NULL, chakra_id resolved per chakra at seed time). A canonical entry is a *generator spec*; the seed migration expands it to an explicit `path_cells` list per chakra.

```yaml
# parser_configs/bhoovalay/canonical_paths.yaml
- name: horizontal_row_major
  generator: row_major          # cells in (0,0)..(0,26),(1,0)..(1,26),...
  params: {}
- name: vertical_column_major
  generator: column_major
  params: {}
- name: diagonal_nw_se
  generator: diagonal
  params: { start: [0,0], step: [1,1] }
- name: spiral_inward_cw
  generator: spiral
  params: { start: [0,0], direction: cw, inward: true }
- name: spiral_outward_ccw_from_center
  generator: spiral
  params: { start: [13,13], direction: ccw, inward: false }
- name: knight_tour_warnsdorff_from_0_0
  generator: knight
  params: { start: [0,0], heuristic: warnsdorff }
- name: knight_tour_warnsdorff_from_center
  generator: knight
  params: { start: [13,13], heuristic: warnsdorff }
- name: boustrophedon
  generator: serpentine
  params: { axis: row }
```

Generator contract (in `services/bhoovalay_service/path_engine/generators.py`):

```python
# Each generator returns list[tuple[int,int]] of length 729 (full 27x27 cover) or
# shorter (for partial paths like knight tours that don't fully cover).
def row_major() -> list[tuple[int,int]]: ...
def column_major() -> list[tuple[int,int]]: ...
def diagonal(start: tuple[int,int], step: tuple[int,int]) -> list[tuple[int,int]]: ...
def spiral(start: tuple[int,int], direction: Literal['cw','ccw'],
           inward: bool) -> list[tuple[int,int]]: ...
def serpentine(axis: Literal['row','col']) -> list[tuple[int,int]]: ...
def knight(start: tuple[int,int],
           heuristic: Literal['warnsdorff','none']) -> list[tuple[int,int]]:
    """Warnsdorff's rule: at each step pick the next cell with fewest onward moves.
       Falls back to lex-min on ties. Returns the longest tour reachable."""
```

All cells are `(row, col)` with `0 ≤ row,col ≤ 26`. Generators must (a) only return in-bounds cells, (b) never repeat a cell within the same path, (c) be deterministic for a given param set.

User-drawn paths bypass generators and are validated against the same invariants by `PathIn`.

### Decode algorithm

```python
def decode(cell_values: list[list[int]],
           path: list[tuple[int,int]],
           mapping: dict[str,str]) -> str:
    out = []
    for (r, c) in path:
        v = cell_values[r][c]            # int 1..64
        sy = mapping.get(str(v))         # mapping keys are JSON strings
        if sy is None:
            raise ValueError(f"mapping missing for value {v}")
        out.append(sy)
    return "".join(out)
```

No spacing, no joiner inserted. Whitespace/syllable-joining is the user's job (handled in the UI panel).

### Tests (TDD — write these first)

1. `test_path_generators.py::test_row_major_covers_all_729` — `len(set(row_major())) == 729`.
2. `test_path_generators.py::test_column_major_distinct_from_row_major`.
3. `test_path_generators.py::test_spiral_inward_cw_starts_topleft_ends_center`.
4. `test_path_generators.py::test_knight_warnsdorff_no_repeats` — every returned cell distinct.
5. `test_path_generators.py::test_knight_in_bounds` — every cell `0..26`.
6. `test_decode_round_trip.py` — small 27x27 chakra of all `1`s + mapping `{"1":"क"}` → output is `"क" * len(path)`.
7. `test_decode_round_trip.py::test_missing_mapping_raises`.
8. `test_chakra_loader.py::test_load_seed_chakra_validates_27x27`.
9. `test_chakra_loader.py::test_value_out_of_range_rejected` (a cell value 0 or 65 → 422).
10. `test_paths_router.py::test_canonical_path_read_no_auth` — guest can GET.
11. `test_paths_router.py::test_user_path_requires_auth` — POST without JWT → 401.
12. `test_paths_router.py::test_user_path_unique_per_user_chakra_name` — duplicate POST → 409.

### Seed migration

`0050_bhoovalay.py` runs in this order:
1. Create enums + tables.
2. Insert mapping rows from `parser_configs/bhoovalay/mappings/*.json`.
3. Insert chakra `1` (and any others present in `parser_configs/bhoovalay/chakras/`).
4. For every canonical entry in `canonical_paths.yaml`, expand the generator against every existing chakra and insert one `bhoovalay_paths` row per (chakra, pattern) with `kind='canonical'`.

## Phase B — workspace UI

### Files

```
ui/app/research-tools/siri-bhoovalay/
├── page.tsx                            server component shell
├── ChakraViewer.tsx                    27x27 SVG, hover/click cells
├── PatternPicker.tsx                   dropdown (canonical) + "draw" toggle
├── PathDrawCanvas.tsx                  client-side draw-mode overlay
├── MappingPicker.tsx                   select mapping (Kn / Sa / Pr)
├── DecodedPanel.tsx                    syllable stream + word-break controls
├── ScorePanel.tsx                      "Score with LLM" button, perplexity readout
├── CrossReferencePanel.tsx             cataloguesearch results
└── NotePadPanel.tsx                    save path + decoded text + notes (auth)

ui/lib/api/bhoovalay.ts                 fetch helpers against bhoovalay-service
ui/lib/bhoovalay/decode.ts              client-side mapping (mirrors path_engine.decode)
ui/lib/bhoovalay/generators.ts          client-side path generators (mirror server)
```

Reuse layout primitives from [`14_public_ui.md`](../14_public_ui.md): Devanagari fonts, citation badge, language toggle. Do not modify those primitives.

### Page layout

```
+-----------------------------------------------------------+
| top-nav (existing) + breadcrumb: ResearchTools > Siri Bhoovalay
+--------------------+--------------------------------------+
| ChakraViewer        | DecodedPanel                         |
|  - 27x27 SVG        |  syllable stream                     |
|  - chakra selector  |  word-break controls                 |
|  - hover shows (r,c,v)|------------------------------------|
|                     | ScorePanel  (button + score)        |
| PatternPicker       |------------------------------------|
|  - canonical drop   | CrossReferencePanel                  |
|  - draw mode toggle |  ranked gathas (cataloguesearch)    |
| MappingPicker       |------------------------------------|
|                     | NotePadPanel (auth required)        |
+--------------------+--------------------------------------+
```

### Client-side rendering rules

- `ChakraViewer` is pure SVG: 27 × 27 grid of `<rect>` + `<text>` (number 1..64). Cells highlighted along the active path by stroke colour; hover shows tooltip `(r=R, c=C, v=V → syllable)`.
- `PathDrawCanvas` overlays the SVG; on cell click, append to the current draft path. Backspace pops. Shift-click clears.
- `DecodedPanel` runs `decode()` client-side every render — no network round-trip per cell.
- `MappingPicker` defaults to the mapping whose `target_script` matches the user's language preference (from spec 01 `user_preferences.lang_overlay`), else `sanskrit_default`.

### Data fetch

- `GET /v1/bhoovalay/chakras/{n}` on mount.
- `GET /v1/bhoovalay/mappings` once; cached in route segment for 1h.
- `GET /v1/bhoovalay/paths?chakra=N&kind=canonical` for the picker.
- `POST /v1/bhoovalay/paths` on Save (auth).

### Tests (Playwright, in `ui/tests/e2e/bhoovalay.spec.ts`)

1. Selecting chakra 1 renders 729 cells.
2. Selecting "horizontal_row_major" highlights cell (0,0) first.
3. Toggling mapping from Kn→Sa updates `DecodedPanel` text.
4. Draw mode: clicking 5 cells builds a 5-syllable string.
5. Unauthenticated user cannot click "Save Path" (button disabled with tooltip).

## Phase C — LLM helper backend

### Files

```
services/bhoovalay_service/routers/llm.py       # new in this phase
services/bhoovalay_service/llm/
├── __init__.py
├── score.py        call model-serving for Sa/Pr perplexity
└── cross_ref.py    call cataloguesearch for semantic similarity

services/bhoovalay_service/tests/
├── test_score_path.py
└── test_cross_reference.py
```

### Endpoints

```
POST /v1/bhoovalay/score-path
  body:  { chakra_number: int,
           path_cells: list[[r,c]],
           mapping_name: str,
           language_guess: 'sa'|'pr' }
  returns: { decoded_text: str,
             perplexity: float,
             tokens: int,
             model_id: str,
             served_by: str }       // proxied from model-serving

POST /v1/bhoovalay/cross-reference
  body:  { decoded_text: str,
           top_k: int = 10,
           filter: { shastra_natural_keys?: list[str] } }
  returns: { hits: [ { gatha_natural_key, score, excerpt, shastra_natural_key } ] }
```

### `score-path` flow

1. Resolve chakra + mapping from Postgres.
2. Decode (server-side, reusing `path_engine.decode`).
3. Pick model from `model_registry` via the router from spec 23:
   - `language_guess='sa'` → `models.lookup(task='lm_score', lang='san', status='active')`
   - `language_guess='pr'` → `models.lookup(task='lm_score', lang='pra', status='active')`
4. Call `POST {MODEL_SERVING_URL}/v1/lm/score` with `{text, model_id}`; response includes `perplexity` and `tokens`.
5. If a stored path with the same `(chakra_id, path_cells, mapping_name)` exists for the caller, update its `score` + `language_guess` columns.
6. Return decoded text + perplexity + model attribution.

The Sa/Pr LM model interface contract (`/v1/lm/score` returning `perplexity`) is owned by spec 26. If model-serving returns 503 (model not yet promoted to `active`), bhoovalay-service surfaces a 503 with body `{"error": "sa_pr_model_unavailable"}` — the UI hides the score panel cleanly.

### `cross-reference` flow

1. Call cataloguesearch `POST /v1/search` (existing) with `{query: decoded_text, top_k}`.
2. For each chunk hit, look up `gatha_natural_key` via the `cataloguesearch_shastra_id` ↔ `teekas` join (read-only).
3. Return hits sorted by score.

### Tests

1. `test_score_path.py::test_decodes_then_calls_model_serving` — stub model-serving; assert request body has decoded text + correct `model_id`.
2. `test_score_path.py::test_persists_score_on_stored_user_path` — same path id sees updated `score`.
3. `test_score_path.py::test_model_unavailable_returns_503`.
4. `test_cross_reference.py::test_calls_cataloguesearch_with_decoded_text`.
5. `test_cross_reference.py::test_hits_mapped_to_gatha_natural_keys`.

## Manual verification

```bash
# 1. Run migration + seed
docker compose up -d postgres
alembic upgrade 0050

# 2. Boot service
uvicorn services.bhoovalay_service.main:app --port 8009

# 3. List chakras
curl http://localhost:8009/v1/bhoovalay/chakras | jq '.[0].chakra_number'

# 4. Read chakra 1 + the canonical row-major path
curl 'http://localhost:8009/v1/bhoovalay/paths?chakra=1&kind=canonical' \
  | jq '.[] | select(.name=="horizontal_row_major") | .path_cells[0:3]'

# 5. Score (requires sa_pr model active per spec 26)
curl -X POST http://localhost:8009/v1/bhoovalay/score-path \
  -H 'content-type: application/json' \
  -d '{"chakra_number":1,"path_cells":[[0,0],[0,1],[0,2]],
       "mapping_name":"sanskrit_default","language_guess":"sa"}'

# 6. UI smoke
open http://localhost:3000/research-tools/siri-bhoovalay
```

## Definition of done

- [ ] Migration `0050` applies cleanly; seed inserts ≥1 chakra + 3 mappings + ≥8 canonical paths per chakra.
- [ ] All Phase A tests pass.
- [ ] All Phase B Playwright tests pass against a seeded local stack.
- [ ] Phase C tests pass with model-serving stubbed; integration with spec 26's real Sa/Pr model verified once that spec ships (gate: `models.lookup(task='lm_score', lang='san', status='active')` returns a row).
- [ ] `bhoovalay_paths` round-trip: save → reload → identical `path_cells` order.
- [ ] Drawing a custom 10-cell path, switching mapping, and scoring it completes in a single page session with no full reload.

## Implementation notes

_(to be filled in after merge)_
