# JainKosh Parser — Fix Spec 003 (Post-golden cleanup)

This spec addresses the `आत्मा.html` golden issues found after parser-only fixes 001/002.
It is implementation-ready for lower-reasoning models and is intentionally explicit about file edits and tests.

## Scope

- Parser-only output shape/semantics corrections.
- `would_write.mongo.topic_extracts` and `would_write.neo4j.edges` corrections driven by parser output.
- Golden updates for `workers/ingestion/jainkosh/tests/golden/*.json`.

Out of scope:
- Orchestrator, DB writes, schema migrations.

## Root Cause Summary

1. `• ... - देखें <redlink>` prose survives in parent `subsection.blocks` because:
- `parse_blocks.make_block()` strips redlink substring first (`strip_dekhen_redlink_substring`), so text becomes plain bullet prose.
- `_drop_see_also_only()` matches only rows still containing `देखें`, so this stripped row is no longer dropped.

2. `see_also` blocks are currently kept in parent `subsection.blocks` by design (`_drop_see_also_only()` drops prose row but retains pending `see_also` blocks), which causes:
- unwanted parent-level `blocks` pollution in parsed output,
- unwanted embedding inside parent `mongo.topic_extracts[*].blocks`,
- wrong `RELATED_TO` source node (edge emitted from parent instead of seed child topic).

## Target Behavior

For row-style `देखें` items (`• label - देखें target`), including redlink targets:

1. Parent subsection:
- must not keep row prose block,
- must not keep corresponding `see_also` block.

2. Child synthetic topic seed (label-topic):
- must contain the corresponding `see_also` block in its own `blocks`.
- may be redlink or non-redlink target.

3. `mongo.topic_extracts`:
- parent topic extract must not contain these row-derived `see_also` blocks,
- child synthetic extract must carry them in its own `blocks`.

4. Neo4j edges:
- `RELATED_TO` must be emitted from the child label-seed topic natural key when relation is row-derived from that label.
- existing redlink edge suppression policy remains unchanged.

## Files To Change

1. `workers/ingestion/jainkosh/parse_blocks.py`
2. `workers/ingestion/jainkosh/parse_subsections.py`
3. `workers/ingestion/jainkosh/models.py` (only if helper fields are needed; keep backward-compatible defaults)
4. `workers/ingestion/jainkosh/envelope.py` (no algorithm rewrite expected; verify it naturally follows moved blocks)
5. `workers/ingestion/jainkosh/tests/unit/test_see_also_only_block_drop.py`
6. `workers/ingestion/jainkosh/tests/unit/test_definitions.py` (or a new unit test file for seed-block assignment)
7. `workers/ingestion/jainkosh/tests/unit/test_redlink_edge_suppression.py`
8. `workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py`
9. `workers/ingestion/jainkosh/tests/golden/आत्मा.json` (and any other changed goldens)
10. Optional docs sync:
- `docs/design/jainkosh/parsing_rules.md`
- `docs/design/jainkosh/parser_spec.md`

## Implementation Plan (TDD-first)

## Phase 1: Stop retaining row-level `see_also` in parent block stream

### Failing tests first

Update `test_see_also_only_block_drop.py`:

1. Change expectation for row-style prose:
- input: `• जीवको आत्मा कहनेकी विवक्षा - देखें जीव`
- expected: neither `hindi_text` nor `see_also` remains in `parse_block_stream()` output.

2. Add redlink variant:
- input: `• बहिरात्मा... - देखें <redlink>`
- expected: neither cleaned bullet prose nor `see_also` remains in returned block stream.

Keep existing test that inline prose with contextual sentence + `देखें` is preserved as prose (non-row style).

### Code changes

In `parse_blocks.py`:

1. Replace `_drop_see_also_only()` behavior:
- detect row-style relation candidates using element-level analysis before destructive text stripping.
- when a row-style mapping is detected, drop both prose and its row-derived `see_also` from parent stream.

2. Important ordering rule:
- row-detection must execute before `strip_dekhen_redlink_substring()` so redlink rows are still classifiable as row-style.

3. Keep non-row `see_also` behavior unchanged (inline narrative `देखें` still allowed in parent where applicable).

## Phase 2: Attach row-style relations to label-seed child topics

### Failing tests first

Add/extend unit tests (preferred: new file `test_label_seed_relation_assignment.py`):

1. Given row-style entries:
- child seed `heading_text` is created from label (already true),
- child seed `blocks` contains exactly one `see_also` pointing to that row target.

2. Redlink row-style entry:
- child seed exists,
- child seed contains redlink `see_also` block (`target_exists=false`),
- parent subsection `blocks` does not contain either row prose or this `see_also`.

3. Multi-row subsection case:
- each row label maps to correct child seed and correct target, not cross-assigned.

### Code changes

In `parse_subsections.py`:

1. Introduce a row extraction pass from `content_els` (element-level, not post-cleaned text) that yields:
- normalized row label,
- parsed anchor target payload (same fields as `Block(kind="see_also")`),
- source order.

2. Keep existing label-seed generation flow, but extend it to accept optional row-relations map:
- key by normalized label text,
- value list of `see_also` blocks for that seed.

3. During `_make_label_seed_subsection` creation (or immediately after):
- inject mapped `see_also` blocks into `seed.blocks`,
- dedupe by `(target_keyword, target_topic_path, target_url, is_self, target_exists)`.

4. Ensure no coupling to parent `blocks` list for this mapping; child assignment should rely on element-derived rows.

## Phase 3: Validate downstream envelope behavior (mongo + neo4j)

### Failing tests first

1. Add a focused unit test (new file `test_envelope_label_seed_related_to_source.py`):
- parse `आत्मा.html`, build envelope,
- assert no `RELATED_TO` from parent topic `आत्मा:एक-आत्मा-...-प्रयोजन` to `जीव` for row-derived relation,
- assert `RELATED_TO` exists from child topic `...:जीवको-आत्मा-कहनेकी-विवक्षा` to `जीव`.

2. Extend `test_redlink_edge_suppression.py`:
- ensure redlink `see_also` can still exist in parse result (now likely under child seeds),
- ensure redlink-related edges are still suppressed in envelope.

3. Add mongo-fragment assertion test (new file `test_mongo_topic_extracts_seed_blocks.py`):
- parent extract for target subsection has no row-derived `see_also` blocks,
- child label-seed extract carries those `see_also` blocks.

### Code changes

`envelope.py` likely needs no structural changes because it already traverses all subsection nodes and their own `blocks`.
Only patch if any assumptions break due to moved location.

## Phase 4: Golden regeneration and review

### Expected golden deltas (`आत्मा.json`)

1. In `page_sections[0].subsections[...]` for:
- `गुण स्थानों की अपेक्षा बहिरात्मा आदि भेद` section:
  - remove parent `hindi_text` bullet `• बहिरात्मा, अंतरात्मा व परमात्मा।`
  - remove parent redlink `see_also` block.
  - add corresponding `see_also` block to child seed `बहिरात्मा, अंतरात्मा व परमात्मा`.

- `एक आत्मा के तीन भेद करने का प्रयोजन` section:
  - remove parent `see_also` blocks (`जीव`, `प्रमाण#3.3`, `मोक्षमार्ग#2.5`),
  - place each inside the matching child seed (`जीवको आत्मा कहनेकी विवक्षा`, `आत्मा ही कथंचित प्रमाण है`, `शुद्धात्माके अपर नाम`).

2. In `would_write.mongo.topic_extracts`:
- parent extracts above no longer contain these `see_also` blocks,
- child seed extracts now contain them.

3. In `would_write.neo4j.edges`:
- `RELATED_TO` source changes from parent topic key to corresponding child seed topic key for row-derived relations.

### Regeneration flow

Run:

```bash
pytest -x workers/ingestion/jainkosh/tests/unit
pytest -x workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py
```

Then regenerate candidates:

```bash
for f in आत्मा द्रव्य पर्याय; do
  python -m workers.ingestion.jainkosh.cli parse \
    workers/ingestion/jainkosh/tests/fixtures/$f.html \
    --out workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
    --frozen-time 2026-05-02T00:00:00Z
done
```

Review diffs, then replace approved candidates:

```bash
for f in आत्मा द्रव्य पर्याय; do
  mv workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
     workers/ingestion/jainkosh/tests/golden/$f.json
done
```

Re-run:

```bash
pytest workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py
```

## Guardrails / Non-regression checks

1. Keep inline narrative `देखें` in genuine prose blocks unchanged.
2. Do not break translation-marker handling (`=` logic).
3. Preserve redlink parsing semantics (`target_exists=false`).
4. Keep `label_topic_seed` creation idempotent and deduplicated.
5. Ensure no duplicate `RELATED_TO` edges after moving relation location.

## Suggested Commit Breakdown

1. `test: add failing tests for row-style see_also relocation`
2. `parser: drop row-style prose+see_also from parent blocks`
3. `parser: assign row-derived see_also blocks to label-seed children`
4. `envelope/tests: verify mongo and neo4j source correction`
5. `tests: regenerate approved goldens`
6. `docs: sync parsing_rules/parser_spec for row-relocation rule`

## Definition of Done

- All new/updated unit tests pass.
- Golden tests pass with approved updated goldens.
- `आत्मा` output satisfies all reported issues:
  - redlink bullet not present in parent blocks,
  - row `see_also` not present in parent blocks,
  - row relations present under child seed nodes,
  - parent `topic_extracts.blocks` clean,
  - `RELATED_TO` edge source points to child seed topic key.
