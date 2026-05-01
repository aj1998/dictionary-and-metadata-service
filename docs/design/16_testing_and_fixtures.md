# 16 — Testing & Fixtures

A consistent fixture set so each module can be tested in isolation, and a single end-to-end happy path test that exercises the full stack.

## Test layout (per module)

```
<module>/tests/
├── conftest.py                # Pytest fixtures (DB sessions, fakes, factories)
├── fixtures/                  # JSON / HTML / YAML inputs
├── golden/                    # expected outputs (for parser modules)
└── test_*.py
```

## Stack-wide test infra

- **pytest-asyncio** for async tests.
- **testcontainers-python** for spinning Postgres + Mongo + Neo4j + Redis on demand.
- **respx** (httpx mock) for jainkosh fetch tests.
- **factory_boy** for SQLAlchemy fixtures.
- **freezegun** for time-sensitive logic.

```python
# packages/jain_kb_common/testing/containers.py
@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.fixture(scope="session")
def mongo_container():
    with MongoDbContainer("mongo:7") as m:
        yield m

@pytest.fixture(scope="session")
def neo4j_container():
    with Neo4jContainer("neo4j:5-community") as n:
        yield n
```

`make test` (or `pytest -q`) runs everything against ephemeral containers. `make test-fast` runs only unit tests that don't need containers (using SQLite in-memory + mongomock + a fake Neo4j driver).

## Canonical fixtures

### `fixtures/jainkosh/आत्मा.html`
Copy of `samples/sample_html_jainkosh_pages/आत्मा.html` (already in repo). The parser must produce `golden/आत्मा.json`:

```json
{
  "natural_key": "आत्मा",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा",
  "page_sections": [
    {
      "section_index": 0,
      "section_kind": "siddhantkosh",
      "heading": [{"lang": "hin", "script": "Deva", "text": "सिद्धांतकोष से"}],
      "subsections": [
        {
          "subsection_index": 1,
          "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा शब्द का अर्थ"}],
          "is_topic_seed": true,
          "topic_natural_key": "jainkosh:आत्मा:आत्मा-शब्द-का-अर्थ",
          "blocks": ["...elided in this doc, full file in repo..."]
        },
        {
          "subsection_index": 2,
          "heading": [{"lang": "hin", "script": "Deva", "text": "आत्मा के बहिरात्मादि 3 भेद"}],
          "is_topic_seed": true,
          "topic_natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
          ...
        }
      ]
    },
    {
      "section_index": 1,
      "section_kind": "puraankosh",
      ...
    }
  ],
  "redirect_aliases": []
}
```

### `fixtures/jainkosh/पर्याय.html`
Same approach. Golden: `golden/पर्याय.json`.

### `fixtures/nj/pravachansaar_index_partial.html`
A trimmed copy of `samples/sample_html_granths_nj/pravachansaar/html/index.html` containing the title block, adhikaar index, and gathas 037–040 (so we test multi-gatha extraction without bloating the fixture). Golden: `golden/pravachansaar_039.json`:

```json
{
  "natural_key": "pravachansaar:039",
  "shastra_natural_key": "pravachansaar",
  "gatha_number": "039",
  "adhikaar_hi": "ज्ञानतत्त्व-प्रज्ञापन-अधिकार",
  "heading_hi": "भूत-भावि पर्यायों की असद्भूत--अविद्यमान संज्ञा है",
  "prakrit_text": "जे णेव हि संजाया जे खलु णट्‌ठा भवीय पज्जया ।\nते होंति असब्भूदा पज्जाया णाणपच्चक्खा ॥39॥",
  "sanskrit_text": null,
  "chhands": [
    {"chhand_index": 1, "chhand_type": "harigeet",
     "text_hi": "पर्याय जो अनुत्पन्न हैं या नष्ट जो हो गई हैं\nअसद्भावी वे सभी पर्याय ज्ञानप्रत्यक्ष हैं ॥३९॥"}
  ],
  "anvayarthas": [
    {
      "teeka_natural_key": "pravachansaar:hindi-chhand",
      "raw_text_hi": "जो पर्यायें वास्तव में उत्पन्न नहीं हुई हैं ...",
      "tagged_terms": [
        {"source_word": "ये पर्याया:", "meaning": "जो पर्यायें"},
        {"source_word": "हि",            "meaning": "वास्तव में"},
        {"source_word": "न एव संजाता:", "meaning": "उत्पन्न नहीं हुई हैं"},
        {"source_word": "ये",            "meaning": "जो पर्यायें"},
        {"source_word": "खलु",          "meaning": "वास्तव में"}
      ],
      "is_alt": false
    }
  ],
  "extracted_keyword_natural_keys": []
}
```

### `fixtures/chat/topic_candidates_sample.json`
Mock rows for the chat puller test (FQ4):

```json
[
  {
    "source_chat_id": "cs-tc-887",
    "source_generated_at": "2026-04-30T10:15:00Z",
    "proposed_topic_text_hi": "द्रव्य गुण पर्याय भेद",
    "associated_keywords": ["पर्याय", "गुण", "द्रव्य"],
    "user_query": "द्रव्य और पर्याय में क्या अंतर है?",
    "llm_explanation": "...",
    "cataloguesearch_chunk_ids": ["cs-chunk-44231", "cs-chunk-12089"]
  },
  ...
]
```

### `fixtures/seed_graph/`
A YAML file describing a small graph used by `query_service` integration tests:

```yaml
keywords:
  - natural_key: पर्याय
  - natural_key: गुण
  - natural_key: द्रव्य
  - natural_key: ज्ञान
aliases:
  - alias: पर्यायें       -> पर्याय
  - alias: आतम            -> आत्मा   # for alias-resolution test
keywords_extra:
  - natural_key: आत्मा
topics:
  - natural_key: jainkosh:द्रव्य:द्रव्य-गुण-पर्याय-भेद
    parent_keyword: द्रव्य
    mentions_keywords: [द्रव्य, गुण, पर्याय]
  - natural_key: jainkosh:पर्याय:पर्याय-भेद
    parent_keyword: पर्याय
    mentions_keywords: [पर्याय]
edges:
  - {from: jainkosh:पर्याय:पर्याय-भेद, to: jainkosh:द्रव्य:द्रव्य-गुण-पर्याय-भेद, type: PART_OF}
```

A loader `tests/seed_graph_loader.py` materializes this into Postgres + Mongo + Neo4j before the tests run.

## Per-module test plans

### `02_data_model_postgres`
- `test_idempotent_upsert.py`: upsert keyword twice → 1 row, fields match second payload.
- `test_natural_key_uniqueness.py`: violating `UNIQUE (natural_key)` raises `IntegrityError`.
- `test_topic_mention_check.py`: topic_mentions row with multiple non-null FK columns rejected by CHECK.

### `03_data_model_mongo`
- `test_stable_id.py`: `stable_id(nk)` deterministic across processes.
- `test_upsert.py`: upsert by natural_key updates fields, preserves `created_at`.

### `04_data_model_graph`
- `test_constraints.py`: duplicate `natural_key` rejected.
- `test_sync_idempotent.py`: `sync_keyword` twice produces 1 node, 1 alias edge.
- `test_edge_types.py`: writing an unknown edge type raises (schema_check).

### `05/06/07 service APIs`
- Per-route happy path + 404 + auth-required + validation error.
- `query_service`: zero-match, partial-match, full-match, alias-match, depth-2 traversal.

### `08 ingestion_jainkosh`
- `test_parse_keyword.py`: `parse_keyword_html(आत्मा.html)` matches `golden/आत्मा.json`.
- `test_alias_mining.py`: `देखें` link produces an alias entry; respx mocks the redirect API.
- `test_orchestrator_idempotent.py`: ingest → approve → ingest again → 0 net DB changes.

### `09 ingestion_gatha_parser`
- `test_parse_index.py`: title, author, ≥ 270 gatha anchors detected on full sample.
- `test_parse_gatha.py`: gatha 039 matches golden.
- `test_heading_topic.py`: heading topic node created with correct `natural_key`.

### `10 ingestion_vyakaran_ocr`
- `test_engine_protocol.py`: `TesseractEngine.ocr_page(...)` returns `status="not_implemented"` (intentional).

### `11 chat_enrichment_loop`
- `test_pull_idempotent.py`: pull twice, 0 net inserts.
- `test_approve_new.py`: approve as new → topic + mentions + edges + sync.
- `test_approve_merge.py`: approve as merge → no new topic, only mentions added.
- `test_schema_drift.py`: missing column → clean error, `last_run_status` set.

### `12 query_engine`
- `test_normalize.py`: NFC + ZWJ stripping + suffix-strip table.
- `test_resolve.py`: exact, alias, suffix-strip; fuzzy disabled by default.
- `test_traverse.py`: in-memory Neo4j fixture, depth-1 + depth-2 + edge-type restriction.
- `test_ranking.py`: overlap dominates, weight tiebreaks, deterministic order.

### `13 admin_ui` / `14 public_ui`
- Playwright e2e covering: ingest → review-queue → approve → public detail page reflects change.
- Lighthouse SEO ≥ 95 on `/dictionary/[nk]` and `/topics/[nk]`.

## End-to-end happy path (single test)

```
@pytest.mark.e2e
async def test_full_path():
    # 1. trigger jainkosh ingest for letter 'आ' (mocked HTTP, two pages: आत्मा, आचार्य)
    # 2. assert 2 review_queue rows
    # 3. approve both
    # 4. assert 2 keywords + 2-3 topics in Postgres, equivalent nodes in Neo4j
    # 5. trigger nikkyjain ingest for pravachansaar (sliced fixture, gathas 1-5)
    # 6. approve
    # 7. assert 5 gathas in Postgres + Mongo
    # 8. POST /v1/graphrag/topics with tokens=['पर्याय','गुण'] (after seed_graph load)
    # 9. assert response.topics[0].natural_key == 'jainkosh:द्रव्य:द्रव्य-गुण-पर्याय-भेद'
    # 10. seed a chat candidate, run puller, approve as new, assert topic + edges
    # 11. /v1/graphrag/topics again — new topic now appears in results
```

## CI

- GitHub Actions workflow `.github/workflows/test.yml`:
  - matrix: `unit`, `integration`, `e2e`
  - `unit`: `pytest -q -m "not integration and not e2e"` ~ 1 min
  - `integration`: testcontainers, ~ 5 min
  - `e2e`: full stack via docker-compose; runs only on `main`
- Linting: `ruff check`, `mypy --strict` for `packages/jain_kb_common/`, `prettier` + `eslint` for UI.

## Definition of Done

- [ ] All fixtures committed under `tests/fixtures/`.
- [ ] All goldens committed and re-generated only via `pytest --update-goldens`.
- [ ] `make test` (or CI) runs unit + integration suites green.
- [ ] e2e test passes against `docker compose up` stack.
- [ ] Coverage ≥ 80% on `packages/jain_kb_common/` and each `services/*/`.
- [ ] README at repo root has a "Running tests" section pointing here.
