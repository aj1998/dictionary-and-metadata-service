# Phase 2 — Storage, Orchestrator, and CLI

Depends on [`phase_1_matcher_core_lib.md`](../phase_1_matcher_core_lib.md).
Adds the Mongo collection, the orchestrator that walks source blocks
through Neo4j to NJ Mongo targets, and the `scripts/match_extracts.py`
CLI.

## 1. Mongo collection — `extract_matches`

Database: `jain_kb`. One document per `(source_block, chosen_target)` —
see edge selection rules below.

```json
{
  "_id": "<sha1(natural_key)>",
  "natural_key": "match:keyword_definition:आत्मा:s0:d0:b2:target:pravachansaar:039:sanskrit",

  "source": {
    "kind": "keyword_definition" | "topic_extract",
    "parent_natural_key": "आत्मा" | "आत्मा:बहिरात्मादि-3-भेद",
    "section_index": 0,             // keyword_definition only
    "definition_index": 0,           // keyword_definition only
    "block_index": 2,
    "block_kind": "sanskrit_text",
    "text_devanagari": "आत्मा द्वादशांगम् आत्मपरिणामत्वात।",
    "reference_text": "धवला पुस्तक 13/5,5,50/282/9"
  },

  "target": {
    "collection": "gatha_teeka_sanskrit",
    "natural_key": "pravachansaar:amritchandra:गाथा:टीका:039:sanskrit",
    "stub_label": "GathaTeeka",
    "shastra_natural_key": "pravachansaar",
    "gatha_natural_key": "pravachansaar:039",
    "lang": "san"
  },

  "match": {
    "status": "matched" | "unmatched" | "target_missing",
    "method": "exact_normalized" | "shingle_fuzzy" | "none",
    "score": 0.97,
    "char_start": 1842,
    "char_end": 1891,
    "threshold": 0.80
  },

  "matcher_version": "1.0.0",
  "ingestion_run_id": "<uuid>",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

### Indexes (`ensure_indexes()`)

```python
{"natural_key": 1}                                            # UNIQUE
{"source.parent_natural_key": 1, "source.block_index": 1}
{"target.natural_key": 1}
{"target.shastra_natural_key": 1, "target.gatha_natural_key": 1}
{"match.status": 1}
{"ingestion_run_id": 1}
```

### Upsert key

`_id = stable_id(natural_key)` reusing the existing helper in
`packages/jain_kb_common/db/mongo/__init__.py`. Re-runs with the same
source/target overwrite the prior row in place — no duplicates.

### natural_key format

```
match:{source_kind}:{parent_natural_key}:s{section_index}:d{definition_index}:b{block_index}:target:{target_natural_key}
```

For `topic_extract` source: `s` and `d` segments are omitted
(`match:topic_extract:{parent_nk}:b{block_index}:target:{...}`).

## 2. Orchestrator

Location: `workers/matching/`.

```
workers/matching/
├── __init__.py
├── orchestrator.py         # main entry: match_all / match_for_keyword / match_for_shastra
├── source_iter.py          # yields source blocks from Mongo (keyword_definitions, topic_extracts)
├── target_resolver.py      # walks Neo4j edges → NJ Mongo doc(s); applies pick_refs_to_show
├── apply_match.py          # upserts extract_matches doc per (source_block, target)
└── tests/
    ├── test_target_resolver.py     # Neo4j mocked
    ├── test_orchestrator.py        # end-to-end on small fixture
    └── fixtures/
```

### 2.1 `source_iter.py`

```python
async def iter_keyword_blocks(mongo, *, keyword_natural_key: str | None = None):
    """Yields SourceBlock objects. If keyword_natural_key=None, scan all."""

async def iter_topic_extract_blocks(mongo, *, topic_natural_key: str | None = None):
    ...
```

Filters out `see_also` and `table` blocks; filters out blocks with no
references (per the user-confirmed scope — only blocks with GRef
references). A block whose `pick_refs_to_show` returns `[]` is also
skipped.

### 2.2 `target_resolver.py`

```python
async def resolve_targets(neo4j, mongo, source: SourceBlock) -> list[Target]:
    """
    1. Determine which references this block contributes via
       pick_refs_to_show (one or more).
    2. For each chosen reference, query Neo4j outgoing edges from the
       block's stub source node (Keyword/Topic) by the same identifying
       key the JainKosh parser used when emitting reference_edges
       (see docs/design/data_sources/jainkosh/parser.md §12 — extract
       common helpers from workers/ingestion/jainkosh/ if needed, but
       DO NOT add a Python→TS dependency).
    3. Map each stub node (Gatha / GathaTeeka / GathaTeekaBhaavarth /
       Kalash / KalashBhaavarth) to one or more NJ Mongo collections
       per the table below.
    4. Verify the NJ Mongo doc exists; if absent, return Target with
       status hint 'target_missing'.
    """
```

Stub label → NJ collection routing:

| Stub label | Source block kind | Mongo collection |
|---|---|---|
| `Gatha` | `prakrit_gatha` / `prakrit_text` | `gatha_prakrit` |
| `Gatha` | `sanskrit_gatha` | `gatha_sanskrit` |
| `GathaTeeka` | `sanskrit_text` | `gatha_teeka_sanskrit` |
| `GathaTeekaBhaavarth` | `hindi_text` | `gatha_teeka_bhaavarth_hindi` |
| `Kalash` | `sanskrit_gatha` / `sanskrit_text` | `kalash_sanskrit` |
| `Kalash` | `hindi_gatha` / `hindi_text` | `kalash_hindi` |
| `KalashBhaavarth` | `hindi_text` | `kalash_bhaavarth_hindi` |
| `Page` | any | skipped in v1 (no body text yet) |

If the block kind / stub label pair is not in the table, log a WARNING
and skip — do not silently match against a mismatched language.

### 2.3 `orchestrator.py`

```python
async def match_all(mongo, neo4j, *, run_id: UUID) -> Stats: ...
async def match_for_jainkosh_keyword(mongo, neo4j, *, keyword_nk: str,
                                       run_id: UUID) -> Stats: ...
async def match_for_jainkosh_topic(mongo, neo4j, *, topic_nk: str,
                                     run_id: UUID) -> Stats: ...
async def match_for_nj_shastra(mongo, neo4j, *, shastra_nk: str,
                                  run_id: UUID) -> Stats: ...
```

For each `SourceBlock`:
1. `targets = await resolve_targets(...)`.
2. For each `target`:
   - fetch target text (extract the right field per collection — see
     [`data_model_mongo.md`](../../data_model/data_model_mongo.md):
     `text[0].text` for verse/translation collections, `anvayartha[0].text`
     for `teeka_gatha_mapping`).
   - `result = locate(normalize(source.text), normalize(target.text))`.
   - Compare `result.score` against
     `threshold_for(source.block_kind)`; record `matched|unmatched`.
   - `apply_match(mongo, source, target, result, run_id)`.

`match_for_nj_shastra`: reverse direction — iterate all source blocks
whose resolved target's `shastra_natural_key == shastra_nk`. Implement
by querying Neo4j for stub nodes belonging to the shastra and walking
incoming edges back to source blocks.

### Logging

`logging.getLogger("jain_kb.matching.orchestrator")`. INFO per
SourceBlock processed; structured fields `source_nk`, `target_nk`,
`status`, `score`. Final summary log at end of run.

### Stats

```python
@dataclass
class Stats:
    blocks_processed: int
    edges_attempted: int
    matched: int
    unmatched: int
    target_missing: int
    elapsed_seconds: float
```

## 3. CLI — `scripts/match_extracts.py`

```bash
# (1) full re-match
python scripts/match_extracts.py --mode all

# (2) newly-added JainKosh keyword or topic
python scripts/match_extracts.py --mode jainkosh-keyword --nk आत्मा
python scripts/match_extracts.py --mode jainkosh-topic --nk आत्मा:बहिरात्मादि-3-भेद

# (3) newly-added NJ shastra
python scripts/match_extracts.py --mode nj-shastra --nk samaysar

# dry-run: locate and score, but skip Mongo writes
python scripts/match_extracts.py --mode all --dry-run

# limit (for smoke tests)
python scripts/match_extracts.py --mode all --limit 50
```

Reads env vars: `MONGO_URL`, `MONGO_DB_NAME`, `NEO4J_URL`,
`NEO4J_USER`, `NEO4J_PASSWORD` (same as `clear_dbs.py`). Generates a
fresh `ingestion_run_id` (UUID4) per invocation and stamps every
written `extract_matches` doc.

Exit code: 0 if no `target_missing` and `unmatched_pct < 50%`,
otherwise 1 (so CI can flag regressions). Print final Stats JSON.

## 4. Tests

Location: `tests/workers/matching/` and
`tests/db/mongo/test_extract_matches.py`.

- `test_extract_matches.py` — upsert idempotency on the new
  collection; index presence; stable `_id` round-trip.
- `test_target_resolver.py` — mocked Neo4j; assert correct stub→
  collection routing; assert `pick_refs_to_show` rule applied.
- `test_orchestrator.py` — small fixture (1 keyword_definition with 3
  blocks, 1 corresponding NJ gatha with all 3 body collections);
  expect 3 `matched` rows.
- Regression: re-running orchestrator on same fixture leaves row
  count unchanged.

## 5. Acceptance / DoD

- [ ] `pytest tests/workers/matching/ -v` — all green.
- [ ] `pytest tests/db/mongo/test_extract_matches.py -v` — all green.
- [ ] `clear_dbs.py` updated to also drop the `extract_matches`
      collection (one-line change; reflect in README scripts section).
- [ ] `scripts/match_extracts.py` runs end-to-end against the bundled
      goldens (आत्मा + पर्याय + द्रव्य + वस्तु) after first running
      `ingest_goldens_apply.py` and `ingest_nj_apply.py --config
      samaysar.yaml` — produces non-zero matched count and persists
      rows.
- [ ] `ensure_indexes()` extended with the six indexes above.

## 6. Manual verification

```bash
# Fresh stack
python scripts/clear_dbs.py
python scripts/ingest_goldens_apply.py
python scripts/ingest_nj_apply.py --config parser_configs/nj/samaysar.yaml

# Run matcher
python scripts/match_extracts.py --mode all

# Sanity-check from Mongo shell
mongosh jain_kb --eval 'db.extract_matches.countDocuments({"match.status": "matched"})'
mongosh jain_kb --eval 'db.extract_matches.findOne({"match.status": "matched"})'
```

## Implementation Notes / Diversions

### Files created
- `workers/matching/__init__.py` — module init
- `workers/matching/source_iter.py` — `SourceBlock` dataclass + `iter_keyword_blocks` / `iter_topic_extract_blocks` async generators
- `workers/matching/target_resolver.py` — `Target` dataclass, `_ROUTING` table, `resolve_targets`, `resolve_targets_for_shastra`
- `workers/matching/apply_match.py` — `apply_match` upsert helper
- `workers/matching/orchestrator.py` — `Stats` dataclass, `match_all` / `match_for_jainkosh_keyword` / `match_for_jainkosh_topic` / `match_for_nj_shastra`
- `workers/matching/tests/__init__.py`, `tests/workers/matching/__init__.py` — empty inits
- `tests/workers/matching/test_target_resolver.py` — 6 mocked-Neo4j unit tests
- `tests/workers/matching/test_orchestrator.py` — 2 integration tests (requires MONGO_URL)
- `tests/db/mongo/test_extract_matches.py` — 6 tests: stable_id, idempotency, index presence
- `scripts/match_extracts.py` — CLI with `--mode`, `--nk`, `--dry-run`, `--limit`

### Files modified
- `packages/jain_kb_common/jain_kb_common/db/mongo/collections.py` — added `EXTRACT_MATCHES`
- `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py` — added 6 `extract_matches` indexes
- `packages/jain_kb_common/jain_kb_common/db/mongo/upserts.py` — added `upsert_extract_match`
- `scripts/clear_dbs.py` — added `"extract_matches"` to `_MONGO_COLLECTIONS`

### Key design decisions
- **Mongo natural_key derivation**: Derived directly from Neo4j stub properties rather than re-parsing. `Gatha` stub nk is identical to the `gatha_natural_key` field stored in `gatha_prakrit`/`gatha_sanskrit` docs, so Mongo nk = `{stub_nk}:prakrit` / `{stub_nk}:sanskrit`. For `GathaTeeka`, `gatha_teeka_sanskrit` nk = `{teeka_natural_key}:{gnum}:टीका:san` where `gnum` comes from `gatha_natural_key.split(":")[-1]`.
- **Edge type disambiguation**: `keyword_definition` blocks → `CONTAINS_DEFINITION`; `topic_extract` blocks → `MENTIONS_TOPIC` (as emitted by the JainKosh envelope).
- **`_ALL_STUB_LABELS`** frozenset guards against unknown labels reaching the routing lookup (the `in _ROUTING` check on tuples was a bug caught in test run and fixed).
- **`kalash_bhaavarth_hindi`**: routing is implemented but the NJ ingestor does not yet write these docs; results in `target_missing` in practice.
- **`match_for_nj_shastra`**: queries Neo4j for stubs by shastra, then does per-block Mongo lookups. May be slow for large shastras; acceptable for Phase 2 (manual CLI, no Celery).
