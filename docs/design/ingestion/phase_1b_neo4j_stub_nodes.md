# Phase 1b — Neo4j stub (dummy) node ingestion

**Goal**: when `apply_approved_keyword_payload` writes a keyword envelope to
Neo4j, every node referenced by an edge must exist — even if its "real"
data hasn't been ingested yet. Currently the apply layer silently drops
cross-page edges (`resolve_by` targets) and the `MATCH` clauses in
`sync_part_of_edge` / `sync_related_to_edge` / `sync_has_topic_edge`
no-op when the target is missing. Reference-emitted lazy nodes (Gatha,
GathaTeeka, …) are collected into `would_write.neo4j.nodes` but never
written.

This phase introduces a **stub node** pattern: a minimal Neo4j node
(`is_stub: true`, `stub_source: "jainkosh_ingestion"`) created on demand
so edges always land. A later "real" ingestion (e.g. another JainKosh
page, the teeka-content pipeline, or a future shastra framework)
overwrites the stub fields with full data via the same idempotent
MERGE.

**Scope**: Neo4j only. Postgres and Mongo are unchanged — only the
JainKosh keyword being ingested ever produces rows/docs there.

---

## 1b.1 What triggers a stub

| Situation | Stub? |
|---|---|
| Edge target uses `resolve_by` (cross-page Topic — page exists on JainKosh, not yet ingested) | **yes** |
| Edge target is a Keyword `key` that isn't in this envelope's `nodes` (cross-page see-also / index-relation) | **yes** |
| Edge source is a `Gatha`/`GathaTeeka`/`GathaTeekaBhaavarth`/`Kalash`/`KalashBhaavarth`/`Page` (reference-emitted lazy node) | **yes** |
| Edge has `target_exists: false` (JainKosh redlink — page doesn't exist) | **no, skip edge** |
| `PART_OF` parent Topic missing (should never happen within a single envelope, but defensive) | **yes** |

Redlinks remain skipped because the target will never be ingested — a
stub would be permanent dead weight.

---

## 1b.2 Stub node shape

Every stub carries two reserved properties on top of the type-specific
fields:

```
is_stub      : true            // boolean; set to false by real syncs
stub_source  : "jainkosh_ingestion"  // free-form provenance string
```

Plus minimum identity props per label:

| Label | Required props on stub |
|---|---|
| `Keyword` | `natural_key`, `display_text` (= `natural_key`) |
| `Topic`   | `natural_key`, `display_text_hi` (last segment of `topic_path` with hyphens → spaces), `parent_keyword_natural_key`, `topic_path` |
| `Gatha`   | `natural_key`, `shastra_natural_key`, `gatha_number` (parsed from key) |
| `GathaTeeka` | `natural_key`, `shastra_natural_key`, `teeka_natural_key`, `gatha_number` |
| `GathaTeekaBhaavarth` | `natural_key`, `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `gatha_number` |
| `Kalash`  | `natural_key`, `teeka_natural_key`, `kalash_number` |
| `KalashBhaavarth` | `natural_key`, `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `kalash_number` |
| `Page` | `natural_key`, `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `page_number` |

For lazy-node labels the prop derivation is already implemented in
`envelope.py::_derive_props` — reuse it.

---

## 1b.3 Idempotency rule (Cypher pattern)

A stub is the *floor* of a node: real ingestion fills in the rest and
flips `is_stub`. We avoid `ON CREATE SET` to stay Cypher-25-compatible.

**Stub MERGE pattern:**

```cypher
MERGE (n:Topic {natural_key: $nk})
SET n.updated_at = datetime(),
    n.created_at = coalesce(n.created_at, datetime()),
    n.is_stub = coalesce(n.is_stub, true),
    n.stub_source = coalesce(n.stub_source, $stub_source),
    n.display_text_hi = coalesce(n.display_text_hi, $display),
    n.topic_path = coalesce(n.topic_path, $topic_path),
    n.parent_keyword_natural_key = coalesce(n.parent_keyword_natural_key, $parent_kw)
```

`coalesce(n.prop, $stub_val)` semantics:
- new node → prop is null → stub value wins
- existing real node → prop is set → existing value wins (no clobber)
- existing stub → `is_stub = true` → stays true

**Real-sync MERGE pattern** (existing `sync_keyword` / `sync_topic` /
etc.) must be updated to assert non-stub state:

```cypher
MERGE (n:Topic {natural_key: $nk})
SET n.is_stub = false,                  // hard-override the stub flag
    n.stub_source = null,
    n.display_text_hi = $display,       // unconditional set, not coalesce
    ...
```

When a stub gets upgraded to real, `is_stub` flips from `true` → `false`
in a single MERGE round-trip. Re-running real ingestion is still
idempotent.

---

## 1b.4 Where stubs get created — envelope vs apply

**Decision: derive stub keys at envelope-build time; create stub nodes
at apply time.**

Rationale:
- Envelope already knows how to slug/derive natural keys
  (`topic_keys.natural_key`, `envelope._derive_props`) — keep that logic
  in one place.
- Apply layer stays domain-agnostic: it sees `nodes` and `edges` with
  fully-resolved `key`s and `props`, applies them.
- Goldens stay readable: the envelope JSON shows every node that will
  be written, with `lazy: true` / `is_stub_seed: true` flags.

### 1b.4a Envelope changes (`workers/ingestion/jainkosh/envelope.py`)

1. **`resolve_by` → resolved `key` + stub seed node.**
   In `_see_also_edge`, `_see_also_kw_edge`, `_index_relation_edge`:
   when emitting a `to_node` with `resolve_by`, also compute the target
   `natural_key` via `topic_keys.slug` and:
   - Replace `to_node` with `{label, key}` (drop `resolve_by`, or keep
     it as a sibling for traceability).
   - Append a stub-seed node to `nodes`:
     ```python
     {"label": "Topic", "key": derived_nk, "is_stub_seed": True,
      "props": {
         "display_text_hi": _last_segment_unhyphen(topic_path),
         "topic_path": topic_path,
         "parent_keyword_natural_key": target_keyword,
      }}
     ```

2. **Cross-page Keyword refs.** When `to_node = {"label": "Keyword",
   "key": kw}` and `kw != result.keyword`, append a Keyword stub seed:
   ```python
   {"label": "Keyword", "key": kw, "is_stub_seed": True,
    "props": {"display_text": kw}}
   ```

3. **Lazy nodes (already collected by `_collect_lazy_nodes`).** Already
   tagged `lazy: true` with derived props — these are treated as stub
   seeds by the apply layer. No envelope change needed beyond making
   sure `_collect_lazy_nodes` runs for index-relation edges too if it
   doesn't already.

4. **`_dedupe`** must collapse duplicate stub seeds for the same
   `(label, key)`. If a node appears both as a real node and a stub
   seed, drop the stub-seed copy (the real one wins).

5. **New helper:**
   ```python
   def _last_segment_unhyphen(topic_path: str) -> str:
       seg = topic_path.split(".")[-1] if topic_path else ""
       return seg.replace("-", " ")
   ```

### 1b.4b Apply changes (`workers/ingestion/jainkosh/apply.py`)

1. **Stop skipping `resolve_by`.** After the envelope change above,
   edges no longer carry `resolve_by` — every edge has a concrete
   `key` on both endpoints. Remove the `if to_rb: continue` short-circuit
   at `apply.py:248-250`.

2. **Process stub-seed nodes before edges.** Insert a new step in the
   Neo4j section, after `sync_keyword` and the real-topic loop:

   ```python
   for node in neo4j_nodes:
       if node.get("is_stub_seed") or node.get("lazy"):
           await sync_stub_node(
               neo4j_driver,
               label=node["label"],
               natural_key=node["key"],
               props=node.get("props", {}),
               database=neo4j_database,
           )
   ```

3. **Defensive stub for MATCH-fail targets.** After all real + stub
   seeds are written, when iterating `neo4j_edges` and an edge type is
   `PART_OF` / `RELATED_TO` / `HAS_TOPIC` / `MENTIONS_TOPIC` /
   `CONTAINS_DEFINITION`, the existing `sync_*_edge` Cypher uses
   `MATCH`. Two options:
   - (a) leave `MATCH` and trust that stub seeds covered everything;
   - (b) change edge Cypher to use `MERGE` on endpoints with the stub
     pattern, so MATCH-fail can never happen.

   **Pick (b).** It's the more scalable invariant — apply never needs
   to know which side might be missing. See §1b.5.

### 1b.4c New module: `jain_kb_common/db/neo4j/stubs.py`

```python
STUB_SOURCE_DEFAULT = "jainkosh_ingestion"

# label → list of (prop_name, $param_name) used in coalesce-SET
_STUB_PROPS_BY_LABEL: dict[str, list[str]] = {
    "Keyword": ["display_text"],
    "Topic": ["display_text_hi", "topic_path", "parent_keyword_natural_key"],
    "Gatha": ["shastra_natural_key", "gatha_number"],
    "GathaTeeka": ["shastra_natural_key", "teeka_natural_key", "gatha_number"],
    "GathaTeekaBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "gatha_number"],
    "Kalash": ["teeka_natural_key", "kalash_number"],
    "KalashBhaavarth": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "kalash_number"],
    "Page": ["shastra_natural_key", "teeka_natural_key", "publisher_id", "page_number"],
}

async def sync_stub_node(
    driver, *, label: str, natural_key: str, props: dict,
    stub_source: str = STUB_SOURCE_DEFAULT, database: str = "jainkb",
) -> None:
    """Idempotent MERGE: creates node if missing, leaves real data intact."""
    allowed = _STUB_PROPS_BY_LABEL.get(label, [])
    set_lines = ", ".join(
        f"n.{p} = coalesce(n.{p}, ${p})" for p in allowed if p in props
    )
    set_lines = (set_lines + ", ") if set_lines else ""
    cypher = f"""
    MERGE (n:{label} {{natural_key: $nk}})
    SET n.updated_at = datetime(),
        n.created_at = coalesce(n.created_at, datetime()),
        n.is_stub = coalesce(n.is_stub, true),
        n.stub_source = coalesce(n.stub_source, $stub_source),
        {set_lines.rstrip(', ')}
    """
    params = {"nk": natural_key, "stub_source": stub_source}
    params.update({k: v for k, v in props.items() if k in allowed})
    async with driver.session(database=database) as session:
        await session.run(cypher, **params)
```

Label allow-list is enforced in code (not Cypher) to avoid injection
since `label` is interpolated into the query string. Reject unknown
labels with `ValueError`.

---

## 1b.5 Edge-side MERGE upgrade

To eliminate MATCH-fail edges entirely, swap `MATCH` for `MERGE` on
both endpoints in the existing edge upserts. Endpoints created via
this path inherit the same stub semantics.

Updated `sync_part_of_edge`:
```cypher
MERGE (child:Topic {natural_key: $c})
  SET child.is_stub = coalesce(child.is_stub, true),
      child.stub_source = coalesce(child.stub_source, 'jainkosh_ingestion'),
      child.created_at = coalesce(child.created_at, datetime())
MERGE (parent:Topic {natural_key: $p})
  SET parent.is_stub = coalesce(parent.is_stub, true),
      parent.stub_source = coalesce(parent.stub_source, 'jainkosh_ingestion'),
      parent.created_at = coalesce(parent.created_at, datetime())
MERGE (child)-[r:PART_OF]->(parent)
SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
```

Same treatment for `sync_has_topic_edge` (Keyword→Topic),
`sync_related_to_edge` (label-parameterised), and the
`MENTIONS_KEYWORD` / `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` blocks
inside `sync_topic` and `build_reference_edges`-driven runs.

If we keep §1b.4b step 2 (explicit stub seeding before edges), this
edge-side MERGE is a **belt-and-braces safety net** — for normal
envelopes it never creates anything new. Worth keeping because it
prevents silent edge loss if a future code path forgets to seed.

---

## 1b.6 Real-sync overrides

Every "real" sync function flips the stub flag off:

- `sync_keyword`: add `SET k.is_stub = false, k.stub_source = null`
- `sync_topic`: add `SET t.is_stub = false, t.stub_source = null`
- `sync_shastra`, `sync_teeka`, `sync_publication`, `sync_kalash`,
  `sync_gatha`: same
- `ensure_lazy_node`: leave as-is (it *is* the stub creator for lazy
  labels in graph-only flows) — but in apply.py we'll route lazy-node
  writes through `sync_stub_node` instead, for uniform semantics.

These edits are one-line additions to the existing `SET` clauses.

---

## 1b.7 Constraints / indexes

No new uniqueness constraints. Add one optional index for
investigation:

```cypher
CREATE INDEX stub_nodes IF NOT EXISTS FOR (n) ON (n.is_stub)
```

Add to `constraints.py::ensure_constraints`. Cheap and lets us audit
"how many stubs are still un-filled?" with one query:
```cypher
MATCH (n {is_stub: true}) RETURN labels(n)[0] AS label, count(*) ORDER BY count(*) DESC
```

---

## 1b.8 Tests

`tests/ingestion/test_apply_stubs.py` (new):

1. **`test_resolve_by_creates_topic_stub`** — parse a keyword whose
   index relations point to a topic in another keyword's page
   (e.g. द्रव्य has a `देखें` to a topic under पर्याय). Apply. Assert:
   - Target Topic node exists with `is_stub = true`.
   - `RELATED_TO` edge from source Topic to stub target exists.
   - `display_text_hi` equals the last `topic_path` segment with
     hyphens replaced by spaces.

2. **`test_real_ingestion_upgrades_stub`** — apply keyword A which
   creates a stub Topic X (referenced cross-page); then apply keyword B
   whose envelope *is* the real ingestion of X. Assert:
   - `is_stub` is now `false`.
   - `stub_source` is null.
   - `display_text_hi` is the real heading, not the slugged fallback.
   - `created_at` is unchanged from the stub creation.

3. **`test_stub_idempotent`** — apply keyword A twice; stub count and
   props unchanged on second run.

4. **`test_lazy_nodes_get_written`** — load an envelope that includes
   `GathaTeeka` lazy nodes from references. Assert these nodes exist in
   Neo4j with `is_stub = true` after apply, and that the
   `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` edges from them land.

5. **`test_redlink_still_skipped`** — an envelope with
   `target_exists: false` edges produces no stub and no edge.

6. **`test_part_of_parent_present`** — sanity: in-envelope `PART_OF`
   edges still land with `is_stub = false` on both endpoints (real
   topic-row writes precede edge writes).

Each test uses golden HTML from
`workers/ingestion/jainkosh/tests/fixtures/`.

---

## 1b.9 Definition of done

- [ ] `jain_kb_common/db/neo4j/stubs.py` exists with `sync_stub_node`
      and a per-label prop allow-list.
- [ ] `envelope.py` resolves `resolve_by` to a concrete `key` at
      build time and emits stub-seed nodes for cross-page Topic and
      Keyword references; existing lazy-node collection unchanged.
- [ ] `_dedupe` collapses (real, stub-seed) duplicates so the real
      copy wins.
- [ ] `apply.py` no longer skips `resolve_by` edges; iterates
      `neo4j.nodes` writing stub-seeds via `sync_stub_node`; edges then
      apply cleanly.
- [ ] All `sync_*` real-data functions set `is_stub = false` and
      `stub_source = null` on their writes.
- [ ] All edge `sync_*_edge` helpers use `MERGE` (not `MATCH`) on both
      endpoints with the stub-coalesce safety net.
- [ ] `target_exists: false` edges are still dropped at envelope time
      (no behaviour change for redlinks).
- [ ] `edge_types.yaml` unchanged (no new edge types).
- [ ] 6 new tests in `tests/ingestion/test_apply_stubs.py` pass; the
      existing 12 phase-1 tests still pass.
- [ ] `ensure_constraints` creates `stub_nodes` index.

---

## 1b.10 Open questions / future

- Should a periodic reconciliation job report long-lived stubs (e.g.
  `is_stub = true` for > N days) so the team can prioritise filling
  pages? Out of scope here; trivial Cypher query once the flag exists.
- Cross-source stubs: when the teeka-content pipeline starts writing
  Gatha nodes, those writes must also flip `is_stub = false`. Document
  this contract in `phase_1_schema_and_apply.md §1.5b` when that stage
  lands.
- Postgres/Mongo equivalent: explicitly out of scope per this spec.
  Cross-keyword Topic references in Postgres remain unresolved
  (`parent_topic_id = NULL`) until the parent's own page is ingested —
  acceptable because Postgres isn't doing graph traversal.
