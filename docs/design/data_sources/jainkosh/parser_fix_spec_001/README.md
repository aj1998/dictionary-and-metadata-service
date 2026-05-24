# JainKosh Parser — Fix Spec 001

> Phased correction spec for the parser-only stage. Findings come from
> hand-review of the goldens at
> `workers/ingestion/jainkosh/tests/golden/{आत्मा,द्रव्य,पर्याय}.json`.
>
> **Audience: a small reasoning model (Sonnet) implementing the fixes
> step by step.** Every change names exact files, exact functions,
> exact Pydantic field additions, exact YAML keys, and exact failing
> tests to write first.
>
> **TDD is mandatory** (per `CLAUDE.md` Operating Instructions): each
> phase below opens with the failing tests to author, then the
> implementation. Run the relevant pytest before and after.

---

## Version bump

After all phases land:

```yaml
# parser_configs/jainkosh.yaml
parser_rules_version: "jainkosh.rules/1.1.0"     # was 1.0.0
```

Reflect in `KeywordParseResult.parser_version` (already wired) and in
`docs/design/jainkosh/parsing_rules.md` §10 ("Versioning").

---

## Phases

| # | File | Theme | Touches |
|---|------|-------|---------|
| 1 | [`phase_1_configurable_triggers_and_nested_DFS.md`](./phase_1_configurable_triggers_and_nested_DFS.md) | Configurable `देखें` trigger list (`देखें`, `विशेष देखें`, …) + full-DFS scan inside index `<ol>` and inline body | `parser_configs/jainkosh.yaml`, `see_also.py`, `parse_index.py`, `config.py` |
| 2 | [`phase_2_ref_stripping_and_sibling_translation_marker.md`](./phase_2_ref_stripping_and_sibling_translation_marker.md) | Strip inline GRef text from `text_devanagari` everywhere; treat sibling text-node `=` (between source-block and HindiText siblings) as the translation marker; ordering of leading vs. trailing references | `parse_blocks.py`, `parse_definitions.py`, `refs.py`, `models.py` (no shape change), `selectors.py` |
| 3 | [`phase_3_redlink_prose_strip_and_label_to_synthetic_topic.md`](./phase_3_redlink_prose_strip_and_label_to_synthetic_topic.md) | Drop `देखें <redlink>` from prose; emit a synthetic Topic for the label-before-`देखें`; add idempotency contract for the orchestrator-level upsert | `see_also.py`, `parse_blocks.py`, `parse_subsections.py`, `models.py`, `envelope.py`, `topic_keys.py` |
| 4 | [`phase_4_tables_as_blocks_and_reference_template.md`](./phase_4_tables_as_blocks_and_reference_template.md) | Tables become regular `Block(kind="table")` attached to the current open subsection; section-level `extra_blocks` stays as a placeholder list (kept for future); add an extensibility template for future reference parsing (shastra/teeka/gatha extraction) | `parse_subsections.py`, `parse_blocks.py`, `tables.py`, `refs.py`, `models.py` |
| 5 | [`phase_5_would_write_cleanup_and_index_relation_chain.md`](./phase_5_would_write_cleanup_and_index_relation_chain.md) | Drop `subsection_tree` from `mongo.keyword_definitions.page_sections[]` (keep `extra_blocks`); replace `IndexRelation.source_topic_path: str` with both `source_topic_path_chain: list[str]` and `source_topic_natural_key_chain: list[str]` | `envelope.py`, `models.py`, `parse_index.py`, `parse_subsections.py` |

Phases are ordered by dependency. Each phase ends green (all prior
tests still pass + new tests pass) before the next begins.

---

## Goldens

Goldens **WILL** change in every phase. Process per phase:

1. Implement the phase.
2. Run the unit tests added by the phase — they must pass.
3. **Do NOT auto-overwrite goldens.** Run the parser CLI against each fixture and write to a side-by-side `*.candidate.json`:

   ```bash
   for f in आत्मा द्रव्य पर्याय; do
     python -m workers.ingestion.jainkosh.cli parse \
       workers/ingestion/jainkosh/tests/fixtures/$f.html \
       --out workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
       --frozen-time 2026-05-02T00:00:00Z
   done
   ```

4. Diff `*.candidate.json` vs `*.json` and post the diff in the PR description for human review.
5. After the human approves, `mv $f.candidate.json $f.json` and re-run `pytest workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py` for byte-identical idempotency.

This regen-and-review step must be repeated **at the end of every phase**, not just at the end of phase 5. The goldens must remain a hand-reviewed source of truth.

---

## Cross-cutting design rules

Read these before starting any phase.

### R1. Everything user-facing in parsing logic is configurable in YAML

The user instruction is explicit:

> VIMP: Make this parsing logic as manually configurable as possible in our parsing-design itself.

For every new heuristic introduced by these phases, expose a YAML knob in `parser_configs/jainkosh.yaml`. Hard-coded constants are forbidden unless they are pure invariants (e.g. NFC normalisation form). Specifically:

- `देखें` triggers → list (Phase 1)
- preceding-text window length → int (Phase 1)
- redlink class names → list (Phase 3)
- "page does not exist" detection: anchor `class` + `title` regex → string (Phase 3)
- ref-strip behaviour → bool toggle (Phase 2)
- sibling-`=` translation detection → bool toggle (Phase 2)
- table extraction strategy (`raw_html_only` | `raw_html_plus_rows`) → enum, default `raw_html_only` (Phase 4)
- reference parsing strategy (`text_only` | `structured` | `text_plus_structured`) → enum, default `text_only` (Phase 4 — template only, no implementation)

`config.py` adds the corresponding Pydantic fields with sensible defaults so existing callers are unaffected.

### R2. No shape-breaking changes to `KeywordParseResult` mid-phase

Any new Pydantic field added to a model in `models.py` must be **Optional with a default** (`Optional[X] = None`, `list[X] = Field(default_factory=list)`, etc.) so older goldens parse cleanly during the transition. We *do* let goldens change content; we don't break the shape unilaterally.

After phase 5 lands, fields that were transitional may be removed in a follow-up cleanup commit.

### R3. TDD: failing test first

Each phase doc lists the test files to create (or extend) and what they assert. Implement the test, run it (`pytest -x <test_file>`), confirm it fails, then implement the code change.

### R4. Idempotent DB upserts (orchestrator stage — referenced from Phase 3)

Phase 3 introduces synthetic topics (label-before-`देखें`). The orchestrator that consumes the envelope (out of scope for parser-only) must upsert these idempotently:

- **Postgres**: `INSERT ... ON CONFLICT (natural_key) DO UPDATE SET ...` — see `02_data_model_postgres.md` `upsert_topic` example.
- **Mongo `topic_extracts`**: `update_one({"natural_key": nk}, {"$set": doc}, upsert=True)`.
- **Neo4j**: `MERGE (t:Topic {natural_key: $nk}) SET t.<...>` then `MERGE` edges.

The parser-only stage does not perform these writes; it produces the envelope and adds an `idempotency_contract` block per emitted entity (see Phase 3 §3.4) describing the conflict key.

### R5. Comments policy (per repo CLAUDE.md)

When the new code is written, default to **no comments**. Do not narrate what the code does. Comments are only for non-obvious WHY.

### R6. No new comments in goldens

Goldens are pure data; no comments anywhere.

---

## File-by-file change index (for reviewer convenience)

After all five phases:

| File | Net change |
|------|-----------|
| `parser_configs/jainkosh.yaml` | +`see_also_triggers`, +`see_also_window_chars`, +`redlink`, +`page_does_not_exist`, +`ref_strip`, +`sibling_translation_marker`, +`table.extraction_strategy`, +`reference.parse_strategy`, version bump |
| `parser_configs/_schemas/jainkosh.schema.json` | matching schema additions |
| `workers/ingestion/jainkosh/config.py` | matching Pydantic models |
| `workers/ingestion/jainkosh/models.py` | `Block.label_topic_seed`, `Reference.parsed: Optional[ParsedReference]`, `IndexRelation.source_topic_path_chain`, `IndexRelation.source_topic_natural_key_chain`, `Subsection.idempotency_contract: dict` (advisory), `Topic` synthetic-from-label, `Block.table_rows: Optional[list[list[str]]]` (added but unused in 1.1.0) |
| `workers/ingestion/jainkosh/see_also.py` | trigger list, full DFS walk, redlink prose-strip, label-extraction-as-topic-seed |
| `workers/ingestion/jainkosh/parse_index.py` | full DFS instead of two-tier `<ol>/<ul>` walk; chain population |
| `workers/ingestion/jainkosh/parse_blocks.py` | sibling-`=` detection; ref-stripping in `text_devanagari`; redlink prose stripping when emitting blocks; emit label-as-topic |
| `workers/ingestion/jainkosh/parse_definitions.py` | use shared ref-strip helpers (no logic dup) |
| `workers/ingestion/jainkosh/parse_subsections.py` | tables attach to current subsection; capture inline `देखें` topic seeds as synthetic children |
| `workers/ingestion/jainkosh/refs.py` | `strip_refs_from_text(text, refs) -> str`; `parse_reference_text(text, config) -> ParsedReference \| None` (template only — returns `None` in 1.1.0) |
| `workers/ingestion/jainkosh/tables.py` | extraction-strategy switch (raw_html only for 1.1.0) |
| `workers/ingestion/jainkosh/envelope.py` | drop `subsection_tree` from `keyword_definitions`; keep `extra_blocks`; add `idempotency_contract` per row |
| `docs/design/jainkosh/parsing_rules.md` | rule additions §3.4, §4.5, §5.6, §6.11, §6.12, version bump |
| `docs/design/jainkosh/parser_spec.md` | minor cross-references to this spec |

The schema_updates.md doc is unchanged (no DB schema changes are part
of this fix; only parser output and `would_write` envelope shape).

---

## Out of scope for fix-spec-001

- Real DB writes / orchestrator wiring (still parser-only stage).
- Alias mining (still owned by `08_ingestion_jainkosh.md`).
- Parsing reference text into structured shastra/teeka/gatha — phase 4
  adds the **template** only; the actual parser is tracked separately.
- Any UI / API surface changes.
