# JainKosh Parser — Fix Spec 002

> Second phased correction spec for the parser-only stage. Findings come
> from hand-review of the goldens at
> `workers/ingestion/jainkosh/tests/golden/{आत्मा,द्रव्य,पर्याय}.json`
> after fix-spec-001 landed.
>
> **Audience: a small reasoning model (Sonnet) implementing the fixes
> step by step.** Every change names exact files, exact functions,
> exact Pydantic field additions, exact YAML keys, and exact failing
> tests to write first.
>
> **TDD is mandatory** (per repo `CLAUDE.md`): each phase below opens
> with the failing tests to author, then the implementation. Run the
> relevant pytest before and after.
>
> Prerequisite: fix-spec-001 fully landed (see
> [`../parser_fix_spec_001/README.md`](../parser_fix_spec_001/README.md)).
> All five phases of 001 must be green; this spec rebases on top of
> them.

---

## Version bump

After all phases land:

```yaml
# parser_configs/jainkosh.yaml
parser_rules_version: "jainkosh.rules/1.2.0"     # was 1.1.0
```

Reflect in `KeywordParseResult.parser_version` (already wired) and in
`docs/design/jainkosh/parsing_rules.md` §10 ("Versioning").

---

## Phases

| # | File | Theme | Touches |
|---|------|-------|---------|
| 1 | [`phase_1_table_full_outerhtml_and_whitespace.md`](./phase_1_table_full_outerhtml_and_whitespace.md) | `Block(kind="table")` and inline-block `raw_html` always carry full outerHTML; whitespace inside `raw_html` strings collapsed. | `tables.py`, `parse_blocks.py`, `refs.py`, `selectors.py`, `models.py` (no shape change), tests |
| 2 | [`phase_2_envelope_idempotency_hoist.md`](./phase_2_envelope_idempotency_hoist.md) | Lift `idempotency_contract` out of every row into a single `would_write.idempotency_contracts` map keyed by `(store, table)`; remove the duplicated per-row dict. | `envelope.py`, `models.py`, `parse_subsections.py`, `parser_spec.md`, `parsing_rules.md`, tests |
| 3 | [`phase_3_index_relation_source_chain.md`](./phase_3_index_relation_source_chain.md) | Resolve `IndexRelation.source_topic_path_chain` and `source_topic_natural_key_chain` correctly by following ancestor `<li>` containers and matching their inline `<strong>` (or `<strong><a>`) heading text against the subsection tree. Eliminates `null` chains. | `parse_index.py`, `parse_keyword.py`, `topic_keys.py`, tests |
| 4 | [`phase_4_leading_gref_through_dfs.md`](./phase_4_leading_gref_through_dfs.md) | Preserve top-level GRef siblings inside `<li>` heading bodies as content events in `walk_and_collect_headings` so the leading `<span class="GRef">` reaches `parse_block_stream` and attaches to the next emitted block. Fixes the missing topmost reference (e.g. `पंचास्तिकाय/9`). | `parse_subsections.py`, `selectors.py`, tests |
| 5 | [`phase_5_inline_dekhen_paren_cleanup_and_label_scope.md`](./phase_5_inline_dekhen_paren_cleanup_and_label_scope.md) | Strip parenthesised `(... देखें X ...)` fragments from prose `text_devanagari` / `hindi_translation`; preserve un-parenthesised `देखें` text. Tighten `label_to_topic` so embedded `(देखें)` does NOT spawn a synthetic label-seed Topic. When a label IS emitted, trim it to just the segment between bullet/sentence-end and the trigger. | `see_also.py`, `parse_blocks.py`, `parse_subsections.py`, `config.py`, `parser_configs/jainkosh.yaml`, tests |
| 6 | [`phase_6_dekhen_only_blocks_and_definition_numbering.md`](./phase_6_dekhen_only_blocks_and_definition_numbering.md) | A block whose entire content is `• X – देखें Y` (i.e. a "see-also row") is dropped from `Subsection.blocks` and emitted only via `see_alsos`/`label_topic_seeds`. Strip leading `(1) `, `(2) `, ... numbering from PuranKosh/SiddhantKosh definition prose so `definition_index` is the only signal. | `parse_blocks.py`, `parse_subsections.py`, `parse_definitions.py`, `config.py`, `parser_configs/jainkosh.yaml`, tests |
| 7 | [`phase_7_redlink_edges_suppression.md`](./phase_7_redlink_edges_suppression.md) | A `RELATED_TO` edge (in `would_write.neo4j.edges`) is **not** emitted whenever the target node is a redlink (`target_exists=False`). Applies to both `IndexRelation`-derived and `Block(kind="see_also")`-derived edges. | `envelope.py`, `config.py`, `parser_configs/jainkosh.yaml`, tests |

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

This regen-and-review step must be repeated **at the end of every phase**, not just at the end of phase 7.

---

## Cross-cutting design rules

Read these before starting any phase. They mirror fix-spec-001's rules
(R1–R6) and add 002-specific guidance.

### R1. Everything user-facing in parsing logic stays configurable in YAML

Every new heuristic introduced by these phases gets a YAML knob in
`parser_configs/jainkosh.yaml` and a matching Pydantic field in
`config.py`. Hard-coded constants are forbidden unless they are pure
invariants. Specifically:

- Whitespace-collapse policy for `raw_html` → bool toggle (Phase 1)
- Idempotency-contract emission mode (`per_row` | `envelope_root`) → enum, default `envelope_root` (Phase 2)
- Index source-resolution: ancestor strong CSS, fallback selectors → list (Phase 3)
- DFS leading-GRef passthrough → bool toggle (Phase 4)
- Paren-`देखें` stripping pattern + bracket pairs → list of `(open, close)` pairs (Phase 5)
- Label-seed parent-context blocklist (e.g. don't seed inside translation prose) → list of source kinds (Phase 5)
- "See-also-only block" drop-toggle and matcher → bool + regex (Phase 6)
- Definition prose numbering-strip pattern → regex (Phase 6)
- Redlink edge emission policy → enum (`always` | `never` | `only_if_topic`) (Phase 7)

### R2. No shape-breaking changes to `KeywordParseResult` mid-phase

Any new Pydantic field added to a model in `models.py` must be **Optional with a default**
(`Optional[X] = None`, `list[X] = Field(default_factory=list)`, etc.) so older goldens parse
cleanly during the transition. We *do* let goldens change content; we don't break the shape
unilaterally.

After Phase 2 lands, the per-row `idempotency_contract` field on `Subsection` is **removed**
from `models.py` (it was internal-only to the parser; envelope is the public contract). This
is the only shape-breaking change in 002, and it ships in its own commit so reviewers can
isolate it.

### R3. TDD: failing test first

Each phase doc lists the test files to create (or extend) and what they assert. Implement the
test, run it (`pytest -x <test_file>`), confirm it fails, then implement the code change.

### R4. Idempotency contract semantics (Phase 2 follow-up)

After Phase 2 the orchestrator reads `would_write.idempotency_contracts` as a top-level dict:

```jsonc
"idempotency_contracts": {
  "postgres:keywords": {
    "conflict_key": ["natural_key"],
    "on_conflict": "do_update",
    "fields_replace": ["display_text", "source_url"],
    "fields_append":  ["definition_doc_ids"],
    "fields_skip_if_set": [],
    "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"]
  },
  "postgres:topics": { ... },
  "postgres:keyword_aliases": { ... },
  "mongo:keyword_definitions": { ... },
  "mongo:topic_extracts": { ... },
  "neo4j:Keyword": { ... },
  "neo4j:Topic": { ... }
}
```

Per-row behaviour is identical (still natural-key driven). Only the *transport* shape changes.
Phase 2 details the orchestrator-side migration (it's documentation only — the orchestrator
reads `idempotency_contracts[<store:table>]` instead of `row.idempotency_contract`).

### R5. Comments policy (per repo CLAUDE.md)

When the new code is written, default to **no comments**. Do not narrate what the code does.
Comments are only for non-obvious WHY.

### R6. No new comments in goldens

Goldens are pure data; no comments anywhere.

### R7. Stay parser-only

This spec changes parser output and `would_write` envelope shape only. No DB writes,
no orchestrator wiring, no schema_updates.md changes (DB schemas are unaffected — Phase 7
removes some edges from the envelope, but the Neo4j schema in
`docs/design/04_data_model_graph.md` already says `target_exists=false` edges are optional
and admin-only).

---

## File-by-file change index (for reviewer convenience)

After all seven phases:

| File | Net change |
|------|-----------|
| `parser_configs/jainkosh.yaml` | +`raw_html.collapse_whitespace`, +`envelope.idempotency_mode`, +`index.source_chain`, +`dfs.passthrough_leading_gref`, +`paren_dekhen_strip`, +`label_to_topic.skip_in_source_kinds`, +`see_also_only_block`, +`definitions.numbering_strip_re`, +`neo4j.redlink_edges`, version bump to `1.2.0` |
| `parser_configs/_schemas/jainkosh.schema.json` | matching schema additions |
| `workers/ingestion/jainkosh/config.py` | matching Pydantic models |
| `workers/ingestion/jainkosh/models.py` | remove `Subsection.idempotency_contract` after Phase 2; no other shape changes |
| `workers/ingestion/jainkosh/tables.py` | full-outerHTML guarantee + whitespace collapse |
| `workers/ingestion/jainkosh/parse_blocks.py` | drop pure-`देखें` blocks; strip paren-`देखें`; preserve raw_html for see-also blocks via `node_outer_html` cleanup; collapse whitespace in stored `raw_html` |
| `workers/ingestion/jainkosh/parse_index.py` | source-chain resolution via ancestor `<li>` strong-text lookup |
| `workers/ingestion/jainkosh/parse_keyword.py` | `_resolve_index_relation_natural_keys` extended to handle text-keyed chains in addition to topic_path-keyed |
| `workers/ingestion/jainkosh/parse_subsections.py` | leading-GRef passthrough in `_dfs`; label-seed scope guard; label trimming |
| `workers/ingestion/jainkosh/parse_definitions.py` | strip `(N)` numbering prefix from leading prose of each definition |
| `workers/ingestion/jainkosh/refs.py` | `node_outer_html` whitespace collapse helper; reused for `Reference.raw_html` |
| `workers/ingestion/jainkosh/see_also.py` | paren-`देखें` matcher + label-trim; redlink-edge suppression hook |
| `workers/ingestion/jainkosh/envelope.py` | hoist `idempotency_contract` to `idempotency_contracts` root; suppress redlink edges per `neo4j.redlink_edges` |
| `docs/design/jainkosh/parsing_rules.md` | rule additions §3.5 (raw_html), §4.6 (see-also-only block drop), §5.7 (paren-`देखें`), §6.13 (idempotency root), §6.14 (redlink edges), §7.3 (index source chain), version bump |
| `docs/design/jainkosh/parser_spec.md` | minor cross-references to this spec; remove `Subsection.idempotency_contract` from §4 |

`schema_updates.md` is unchanged.

---

## Out of scope for fix-spec-002

- Real DB writes / orchestrator wiring (still parser-only stage).
- Alias mining (still owned by `08_ingestion_jainkosh.md`).
- Parsing reference text into structured shastra/teeka/gatha (deferred from fix-spec-001 phase 4).
- Any UI / API surface changes.
- Re-architecting how the DFS walks; we only patch the leading-GRef gap.
