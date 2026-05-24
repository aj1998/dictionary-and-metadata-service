# Phase 2 — Hoist `idempotency_contract` to envelope root

## Problem

Today every emitted row in `would_write` carries its own
`idempotency_contract` dict. The dict shape is identical for every row
of a given store/table (e.g. all `topics` rows share the same
`{conflict_key: ["natural_key"], on_conflict: "do_update", ...}` block),
so duplicating it per row inflates `would_write` JSON by hundreds of
KB on a typical keyword and clutters reviewer diffs.

Move it to a single `would_write.idempotency_contracts` map, keyed by
`<store>:<table_or_collection_or_label>`. Per-row dicts are removed.

## Failing tests (write first)

Create `workers/ingestion/jainkosh/tests/unit/test_envelope_idempotency.py`:

```python
import pytest
from datetime import datetime
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.models import (
    KeywordParseResult, Nav, PageSection, Subsection,
)


def _result_with_topics():
    sub = Subsection(
        topic_path="1",
        heading_text="t1",
        heading_path=["t1"],
        natural_key="k:t1",
        parent_natural_key=None,
        is_leaf=True,
        blocks=[],
        children=[],
    )
    sec = PageSection(
        section_kind="siddhantkosh",
        section_index=0,
        h2_text="सिद्धांतकोष से",
        definitions=[],
        index_relations=[],
        subsections=[sub],
    )
    return KeywordParseResult(
        keyword="k",
        source_url="https://example/",
        page_sections=[sec],
        nav=Nav(),
        parser_version="jainkosh.rules/1.2.0",
        parsed_at=datetime(2026, 5, 2),
    )


def test_idempotency_contracts_at_envelope_root():
    env = build_envelope(_result_with_topics()).would_write
    assert "idempotency_contracts" in env
    contracts = env["idempotency_contracts"]
    assert "postgres:keywords" in contracts
    assert contracts["postgres:keywords"]["conflict_key"] == ["natural_key"]
    assert "postgres:topics" in contracts
    assert "mongo:keyword_definitions" in contracts
    assert "mongo:topic_extracts" in contracts


def test_no_per_row_idempotency_contract_in_postgres_rows():
    env = build_envelope(_result_with_topics()).would_write
    for row in env["postgres"]["keywords"]:
        assert "idempotency_contract" not in row
    for row in env["postgres"]["topics"]:
        assert "idempotency_contract" not in row


def test_no_per_row_idempotency_contract_in_mongo_rows():
    env = build_envelope(_result_with_topics()).would_write
    for row in env["mongo"]["keyword_definitions"]:
        assert "idempotency_contract" not in row
    for row in env["mongo"]["topic_extracts"]:
        assert "idempotency_contract" not in row
```

Run: must FAIL.

Add a golden-coverage assertion in
`workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py`:

```python
def test_envelope_carries_root_idempotency_contracts(parsed_results):
    for env in (r["would_write"] for r in parsed_results.values()):
        assert "idempotency_contracts" in env
        for row in env["postgres"]["topics"]:
            assert "idempotency_contract" not in row
```

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
envelope:
  idempotency_mode: "envelope_root"   # "per_row" | "envelope_root"; default envelope_root
```

`config.py`:

```python
class EnvelopeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_mode: Literal["per_row", "envelope_root"] = "envelope_root"


class JainkoshConfig(BaseModel):
    ...
    envelope: EnvelopeConfig = Field(default_factory=EnvelopeConfig)
```

`per_row` is kept only as an emergency rollback knob; default and only
production mode is `envelope_root`.

## Implementation

### 2.1 Define the canonical contracts

In `envelope.py` add a private constant module-level dict:

```python
_DEFAULT_CONTRACTS: dict[str, dict] = {
    "postgres:keywords": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["display_text", "source_url"],
        "fields_append": ["definition_doc_ids"],
        "fields_skip_if_set": [],
        "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"],
    },
    "postgres:topics": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "topic_path", "display_text", "parent_topic_natural_key",
            "is_leaf", "is_synthetic", "source",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    "postgres:topics:label_seed": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "display_text", "is_leaf", "is_synthetic",
            "parent_topic_natural_key", "topic_path", "source", "source_subkind",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    "postgres:keyword_aliases": {
        "conflict_key": ["keyword_natural_key", "alias_text"],
        "on_conflict": "do_update",
        "fields_replace": ["alias_kind", "source"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:keyword_aliases"],
    },
    "mongo:keyword_definitions": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["page_sections", "redirect_aliases", "source_url"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:keyword_definitions"],
    },
    "mongo:topic_extracts": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": ["topic_path", "parent_natural_key", "is_leaf", "heading", "blocks", "source", "source_url"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["mongo:topic_extracts"],
    },
    "neo4j:Keyword": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["display_text", "source_url"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Keyword"],
    },
    "neo4j:Topic": {
        "conflict_key": ["key"],
        "on_conflict": "merge",
        "fields_replace": ["display_text_hi", "topic_path", "parent_keyword_natural_key", "source", "is_leaf"],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["neo4j:Topic"],
    },
}
```

### 2.2 Strip per-row contracts from emitters

In `envelope.py`:

- Remove the `idempotency_contract` key from every dict produced by
  `build_pg_fragment` (keyword row + each topic row) and from any future
  emitter.
- Remove the `or sub.idempotency_contract or {...}` fallback in the topic
  loop — the contract no longer lives on `Subsection`.

`build_envelope` becomes:

```python
def build_envelope(result: KeywordParseResult) -> WouldWriteEnvelope:
    pg = build_pg_fragment(result)
    mongo = build_mongo_fragment(result)
    neo = build_neo4j_fragment(result)
    return WouldWriteEnvelope(
        keyword_parse_result=result,
        would_write={
            "postgres": pg,
            "mongo": mongo,
            "neo4j": neo,
            "idempotency_contracts": _build_contracts(result),
        },
    )


def _build_contracts(result) -> dict:
    keys = {"postgres:keywords", "postgres:topics",
            "mongo:keyword_definitions", "mongo:topic_extracts",
            "neo4j:Keyword", "neo4j:Topic"}
    if any(_has_label_seed_topic(result)):
        keys.add("postgres:topics:label_seed")
    keys.add("postgres:keyword_aliases")
    return {k: _DEFAULT_CONTRACTS[k] for k in sorted(keys)}
```

`_has_label_seed_topic(result)` walks subsections and yields True for any
`Subsection` with `label_topic_seed=True`.

### 2.3 Remove `Subsection.idempotency_contract`

`models.py` — drop the field. Same for `parse_subsections.py`'s
`_make_label_seed_subsection` (delete the `idempotency_contract={...}`
kwarg). The label-seed-specific contract now lives in
`_DEFAULT_CONTRACTS["postgres:topics:label_seed"]` and the orchestrator
selects it by inspecting `is_synthetic + label_topic_seed` flags on each
topic row.

### 2.4 Documentation updates

- `docs/design/jainkosh/parsing_rules.md` §6.13 (NEW) — *Idempotency
  contract location*.
- `docs/design/jainkosh/parser_spec.md` §4 — remove
  `Subsection.idempotency_contract`; add `idempotency_contracts: dict`
  to `WouldWriteEnvelope.would_write`.

## Definition of Done

- [ ] `test_envelope_idempotency.py` passes.
- [ ] Golden assertion passes.
- [ ] Goldens regenerated and reviewed.
- [ ] `Subsection.idempotency_contract` removed from `models.py`.
- [ ] No row in any of the three goldens contains `idempotency_contract`.
- [ ] All five contracts in `_DEFAULT_CONTRACTS` are exercised by at least one fixture.
