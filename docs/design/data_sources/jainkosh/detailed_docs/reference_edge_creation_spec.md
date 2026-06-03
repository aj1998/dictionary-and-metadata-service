# JainKosh Reference → Neo4j Edge Creation — Implementation Spec

> Specification for emitting Neo4j edges from resolved `Reference` objects
> inside `would_write.neo4j.edges`. No new node creation — edges only.
> Companion to `reference_parser_spec.md`.

---

## 0. Scope

### In scope
- Augment `build_neo4j_fragment` (`workers/ingestion/jainkosh/envelope.py`) to
  emit reference-derived edges (`MENTIONS_TOPIC`, `CONTAINS_DEFINITION`).
- Load `parser_configs/_manual_configs/publishers.json` once at config-load
  time (similar to `ShastraRegistry`); attach to `JainkoshConfig`.
- Use the existing `ShastraRegistry` (already attached to config) to look up
  the `type` of the matched shastra (`shastra` | `teeka` | `publication`) and
  its publisher (for `type=publication`).
- Tests for the new edge-emission logic.

### Out of scope
- Creating any new Neo4j nodes (no `Gatha`, `GathaTeeka`, `GathaTeekaBhaavarth`,
  `Kalash`, `KalashBhaavarth`, `Page`, `Publication` node objects in `nodes`).
- Schema changes to `shastra.json` or `Reference` model.
- Range/list expansion (already handled in parser §14A.4).
- Edges originating from `puraankosh` sections (parser already skips them).

---

## 1. Inputs

### 1.1 Per-block reference selection (v1.11.18)

References in a block are split by `inline_reference` flag:

- **Non-inline refs** (`inline_reference=False`): the **first** non-inline ref
  is the "main" reference, processed with full block-kind-aware rules (§4.1–§4.3).
  Remaining non-inline refs use the simplified rules (§4.5).
- **Inline refs** (`inline_reference=True`): **all** inline refs are processed
  with the simplified inline-only rules (§4.5b), regardless of whether any
  non-inline ref is present. No block-kind check.

If there are no non-inline refs, the main path (§4.1–§4.3) is skipped
entirely — all refs use §4.5b. Non-inline refs with `shastra_name is None`
are skipped silently.

### 1.2 Block-context classification

Each block is classified by **where it lives** in the parse result:

| Context | Source | Target node | Edge type |
|---------|--------|-------------|-----------|
| **subsection** | `Subsection.blocks[i]` (innermost subsection that directly contains the block) | `Topic` keyed by `subsection.natural_key` | `MENTIONS_TOPIC` |
| **definition** | `Definition.blocks[i]` (any depth in `PageSection.definitions`) | `Keyword` keyed by `result.keyword` | `CONTAINS_DEFINITION` |

`extra_blocks` and `label_topic_seeds[*].blocks` are ignored for v1 (no edges
emitted from them). If a future need arises, treat them as definition-context.

### 1.3 Shastra-type lookup

Use `config.shastra_registry` (already loaded). Add a helper on `ShastraRegistry`:

```python
def get_type(self, shastra_name: str) -> Optional[str]:
    """Return raw 'type' field of registry entry; None if missing."""
```

The lookup uses **canonical `shastra_name`** (already canonical on the
`Reference`, since the parser stores the registry's `shastra_name`, not the
raw text). No `_normalise` call needed here.

### 1.4 Publishers registry

New `parser_configs/_manual_configs/publishers.json` (already exists in repo):

```json
[{"publisher_id": "1", "publisher": "अनन्तकीर्ति ग्रन्थमाला"}, …]
```

Add to `parse_reference.py` (or new `publishers.py`):

```python
class PublisherRegistry:
    _by_name: dict[str, str]  # publisher (NFC) -> publisher_id

    @classmethod
    def load(cls, path: Path) -> "PublisherRegistry": ...

    def get_id(self, publisher_name: str) -> str:
        return self._by_name.get(unicodedata.normalize("NFC", publisher_name),
                                 "publisher_to_be_added")
```

Attach to `JainkoshConfig.publisher_registry: Optional[Any]` (exclude from
dump). Load alongside `shastra_registry` in `load_config()`.

For a given `Reference`, the publisher is fetched as:

```python
entry = config.shastra_registry._by_primary.get(reference.shastra_name) \
        or … # canonical entry
publisher_name = entry.publisher if entry else ""   # add `publisher` to ShastraEntry
publisher_id = config.publisher_registry.get_id(publisher_name)
```

> **`ShastraEntry` change**: add `publisher: str = ""` (loaded from JSON).
> Non-breaking; existing tests unaffected.

---

## 2. Keyword classification (configurable)

In `config.py`, add a new config block:

```python
class ReferenceEntityKeywordsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gatha: list[str] = Field(default_factory=lambda: [
        "गाथा", "श्लोक", "सूत्र", "दोहक", "वार्तिक",
    ])
    kalash: list[str] = Field(default_factory=lambda: ["कलश"])
    page: list[str] = Field(default_factory=lambda: ["पृष्ठ"])
    pankti: list[str] = Field(default_factory=lambda: ["पंक्ति"])
```

Add to `ReferenceConfig`:

```python
entity_keywords: ReferenceEntityKeywordsConfig = Field(
    default_factory=ReferenceEntityKeywordsConfig
)
```

And to `jainkosh.yaml` under `reference:` (with the same defaults).

### 2.1 Field extraction helpers

```python
def _first_value(rfields: list[ResolvedField], names: list[str]) -> Optional[int]:
    """Return the int value of the first matching field name; None if absent
    or non-int (range/list strings should already have been expanded)."""
    by = {f.field: f.value for f in rfields}
    for n in names:
        if n in by and isinstance(by[n], int):
            return by[n]
    return None
```

Used to extract gatha-value, kalash-value, page-value, pankti-value.

---

## 3. Node-key formats

The literal segments **in keys** are always the canonical Devanagari strings
below (regardless of which keyword variant matched in `resolved_fields`).

| Source label | Format | Used by |
|--------------|--------|---------|
| `Gatha` | `<shastra>:गाथा:<n>` | shastra-type rules |
| `GathaTeeka` | `<shastra>:<teeka>:गाथा:टीका:<n>` | teeka/publication rules |
| `GathaTeekaBhaavarth` | `<shastra>:<teeka>:<publisher_id>:गाथा:टीका:भावार्थ:<n>` | publication hindi_text |
| `Kalash` | `<shastra>:<teeka>:कलश:<n>` | teeka/publication rules (kalash) |
| `KalashBhaavarth` | `<shastra>:<teeka>:<publisher_id>:कलश:भावार्थ:<n>` | publication hindi_text (kalash) |
| `Page` | `<shastra>:<teeka>:<publisher_id>:पृष्ठ:<n>` | publication page rule |

`<shastra>` = `Reference.shastra_name`.
`<teeka>` = `Reference.teeka_name` (may be empty string — caller MUST guard,
see §5.4).
`<n>` = int value extracted via `_first_value`.

> Per Q10: branching is determined by `registry.get_type(shastra_name)`; the
> teeka segment in keys is always taken from `Reference.teeka_name`.

---

## 4. Edge-emission rules

All edges have shape:

```python
{
    "type": <edge_type>,           # MENTIONS_TOPIC | CONTAINS_DEFINITION
    "from": {"label": <src_label>, "key": <src_key>},
    "to":   <topic_or_keyword_node>,
    "props": {
        "weight": 1.0,
        "source": "jainkosh",
        "block_index": <int>,           # 0-based index of block in parent list
        "mention_path": <str>,          # see below
        "source_natural_key": <str>,    # natural_key of the Mongo doc being referenced
        # CONTAINS_DEFINITION only:
        "section_index": <int>,         # index of PageSection
        "definition_index": <int>,      # Definition.definition_index within that section
        **optional_pankti,
    },
}
```

`optional_pankti = {"pankti": <int>}` when `पंक्ति` resolved (§2.1), else absent.

**`block_index`**: 0-based index of the block (within `Subsection.blocks[]` or `Definition.blocks[]`) that produced the edge. Passed from the `enumerate()` loop in `envelope.py`.

**`mention_path`**: compact string locating the block in its Mongo document.
- For `CONTAINS_DEFINITION`: `"<section_index>/<definition_index>/<block_index>"` — matches the path in `keyword_definitions.page_sections[*].definitions[*].blocks[*]`.
- For `MENTIONS_TOPIC`: `"<topic_natural_key>/<block_index>"`.

**`source_natural_key`**: the `natural_key` of the Mongo document containing the block.
- For `MENTIONS_TOPIC` (subsection context): equals the subsection's `topic_natural_key` (the `topic_extracts` doc).
- For `CONTAINS_DEFINITION` (definition context): equals `result.keyword` (the `keyword_definitions` doc).

**`section_index` / `definition_index`** (`CONTAINS_DEFINITION` only): together with `block_index`, these three form a triplet that uniquely locates any block in `keyword_definitions`. `section_index` is the loop index over `result.page_sections`; `definition_index` is `Definition.definition_index`.

The `from` / `to` ordering is fixed: source = the `Gatha`/`Kalash`/etc. node;
target = the Topic (subsection context) or Keyword (definition context).

### 4.1 Gatha edges

Let `g = _first_value(rf, cfg.entity_keywords.gatha)`. If `g is None`, no
gatha edges. The block-kind constraints below MUST hold.

**`type == "shastra"`** (any block kind):
- emit one edge: src = `Gatha("<shastra>:गाथा:<g>")`.

**`type == "teeka"`**:
- block_kind ∈ {sanskrit_gatha, prakrit_gatha, hindi_gatha}: src = `Gatha("<shastra>:गाथा:<g>")`.
- block_kind ∈ {sanskrit_text, prakrit_text, hindi_text}: src = `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")`.

**`type == "publication"`**:
- block_kind ∈ {sanskrit_gatha, prakrit_gatha, hindi_gatha, **prakrit_text**}: src = `Gatha("<shastra>:गाथा:<g>")`.
  (`prakrit_text` is original Prakrit source content, treated the same as `prakrit_gatha`.)
- block_kind == **sanskrit_text**: src = `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")`.
  When `teeka_name` is absent, `<teeka>` defaults to `"टीका"` (e.g. `"तत्त्वानुशासन:टीका:गाथा:टीका:53"`).
- block_kind == hindi_text: emit **two edges**:
  - src1 = `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")`
  - src2 = `GathaTeekaBhaavarth("<shastra>:<teeka>:<publisher_id>:गाथा:टीका:भावार्थ:<g>")`

For other block kinds (`table`, `see_also`), emit nothing.

### 4.2 Kalash edges

Let `k = _first_value(rf, cfg.entity_keywords.kalash)`. If `k is None`, none.

**`type == "teeka"`**, block_kind ∈ {sanskrit_gatha, prakrit_gatha, hindi_gatha}:
- src = `Kalash("<shastra>:<teeka>:कलश:<k>")`.

**`type == "publication"`**:
- block_kind ∈ {sanskrit_gatha, prakrit_gatha, hindi_gatha}:
  - src = `Kalash("<shastra>:<teeka>:कलश:<k>")`.
- block_kind == hindi_text:
  - src = `KalashBhaavarth("<shastra>:<teeka>:<publisher_id>:कलश:भावार्थ:<k>")`.

`type == "shastra"`: no kalash edges.

### 4.3 Page edges

Let `p = _first_value(rf, cfg.entity_keywords.page)`. If `p is None`, none.

**`type == "publication"` only** (any block kind):
- src = `Page("<shastra>:<teeka>:<publisher_id>:पृष्ठ:<p>")`.

> Note: per Q8 the original spec text "Gatha" was a typo — Page edges use
> label `Page`.

### 4.4 Composability

A single block can emit multiple edges (gatha + kalash + page). Each edge is
independent; all use the same target (Topic-or-Keyword) and the same `pankti`
prop if present.

### 4.5 Inline (non-main) reference edges

After emitting edges for the main non-inline reference, every remaining
**non-inline** reference is processed with **simplified rules that ignore block
kind** (same as the old §4.5 for the main path). The target and edge type are
the same as for the main reference.

Per-entity rules (remaining non-inline refs):

#### Gatha — remaining non-inline

| Shastra type | Emits |
|---|---|
| `shastra` | `Gatha("<shastra>:गाथा:<g>")` |
| `teeka` | `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")` (guard: teeka_name non-empty) |
| `publication` | `GathaTeekaBhaavarth("<shastra>:<teeka>:<publisher_id>:गाथा:टीका:भावार्थ:<g>")` (guard: teeka_name non-empty) |

#### Kalash — remaining non-inline

| Shastra type | Emits |
|---|---|
| `shastra` | nothing |
| `teeka` | `Kalash("<shastra>:<teeka>:कलश:<k>")` (guard: teeka_name non-empty) |
| `publication` | `KalashBhaavarth("<shastra>:<teeka>:<publisher_id>:कलश:भावार्थ:<k>")` (guard: teeka_name non-empty) |

#### Page — remaining non-inline

Same rule as main (§4.3): `publication` only, any block kind, emits
`Page("<shastra>:<teeka>:<publisher_id>:पृष्ठ:<p>")`.

Guard rules (§5.4) apply identically.

---

## 4.5b Inline reference rules (v1.11.18)

All `inline_reference=True` refs use a **further-simplified path** that always
emits plain `Gatha`/`Kalash`/`Page` — no `GathaTeeka`, `GathaTeekaBhaavarth`,
or `KalashBhaavarth`.

#### Gatha — inline

| Condition | Emits |
|---|---|
| gatha field present, any shastra type | `Gatha("<shastra>:गाथा:<g>")` |

Gatha field names: `गाथा`, `श्लोक`, `सूत्र`, `दोहक`, `वार्तिक` (same matcher list as §2.1).

#### Kalash — inline

| Shastra type | Emits |
|---|---|
| `shastra` | nothing |
| `teeka` or `publication` | `Kalash("<shastra>:<teeka>:कलश:<k>")` |

#### Page — inline

| Shastra type | Emits |
|---|---|
| `publication` only | `Page("<shastra>:<teeka>:<publisher_id>:पृष्ठ:<p>")` |

Guards: `shastra_name=None` or `type=None` → skip (same as §5.4).

Implemented in `_emit_inline_only_edges`.

---

## 5. Implementation outline

### 5.1 New module: `workers/ingestion/jainkosh/reference_edges.py`

Pure functions, no I/O. Public entry:

```python
def build_reference_edges(
    block: Block,
    *,
    block_index: int,       # 0-based index of block in its parent list
    target: dict,           # {"label": "Topic"|"Keyword", "key": ...}
    edge_type: str,         # "MENTIONS_TOPIC" | "CONTAINS_DEFINITION"
    config: JainkoshConfig,
    # CONTAINS_DEFINITION only:
    section_index: int = 0,
    definition_index: int = 0,
    source_natural_key: str = "",
) -> list[dict]:
    """Return edge dicts for this block. May return [] if no eligible ref or
    the ref doesn't carry the required keyword fields."""
```

Internal helpers:

- `_pick_reference(refs)` — (internal, kept for reference; no longer drives `build_reference_edges`)
- `_first_value(rf, names)` — §2.1
- `_pankti_props(rf, cfg)` — returns `{"pankti": int}` or `{}`
- `_resolve_publisher_id(ref, config)` — §1.4
- `_make_edge(edge_type, src_label, src_key, target, pankti_props, *, block_index, mention_path, source_natural_key, section_index=None, definition_index=None)` — assembles dict
- `_emit_gatha(...)`, `_emit_kalash(...)`, `_emit_page(...)` — implement §4.1–§4.3 (main non-inline ref, block-kind-aware)
- `_emit_gatha_inline(...)`, `_emit_kalash_inline(...)` — implement §4.5 for remaining non-inline refs
- `_emit_inline_ref_edges(ref, block_kind, ...)` — dispatches §4.5 for a single remaining non-inline ref
- `_emit_inline_only_edges(ref, ...)` — dispatches §4.5b for inline refs (Gatha/Kalash/Page only, no block-kind check)
- Top-level `build_reference_edges` separates non-inline and inline refs, dispatches each to the appropriate path.

### 5.2 `envelope.py` changes

In `build_neo4j_fragment`, after the existing subsection loop body:

```python
for sub in walk_subsection_tree(sec.subsections):
    # ... existing node + HAS_TOPIC/PART_OF + see_also ...
    target = {"label": "Topic", "key": sub.natural_key}
    for i, b in enumerate(sub.blocks):
        edges.extend(build_reference_edges(
            b,
            block_index=i,
            target=target,
            edge_type="MENTIONS_TOPIC",
            config=config,
            source_natural_key=sub.natural_key,
        ))
```

And new loop for definitions:

```python
for sec_idx, sec in enumerate(result.page_sections):
    if sec.section_kind == "puraankosh":
        continue                         # parser already strips refs, but be safe
    target = {"label": "Keyword", "key": result.keyword}
    for d in sec.definitions:
        for i, b in enumerate(d.blocks):
            edges.extend(build_reference_edges(
                b,
                block_index=i,
                target=target,
                edge_type="CONTAINS_DEFINITION",
                config=config,
                section_index=sec_idx,
                definition_index=d.definition_index,
                source_natural_key=result.keyword,
            ))
```

`_dedupe(edges)` keys on `(type, from, to, mention_path)` so that distinct citation contexts (same gatha cited in two different definitions) are preserved as distinct edges:

```python
def _dedupe(edges: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for e in edges:
        key = (
            e["type"],
            e["from"]["label"], e["from"]["key"],
            e["to"]["label"], e["to"]["key"],
            e["props"].get("mention_path", ""),
        )
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out
```

### 5.3 `config.py` changes

```python
class JainkoshConfig(BaseModel):
    # ... existing ...
    publisher_registry: Optional[Any] = Field(default=None, exclude=True)
```

In `load_config()`:

```python
if cfg.reference.parse_strategy != "text_only":
    pub_path = Path(__file__).parents[3] / \
        "parser_configs/_manual_configs/publishers.json"
    if pub_path.exists():
        cfg.publisher_registry = PublisherRegistry.load(pub_path)
```

### 5.4 Edge cases / guards

Skip emission silently (return `[]`) when:
- `ref.shastra_name is None`
- `registry.get_type(ref.shastra_name)` is None (entry vanished / mismatch)
- The rule requires `<teeka>` but `ref.teeka_name == ""` (i.e., `type=teeka`
  text-block rule, or any `type=publication` rule that uses
  `GathaTeeka`/`Kalash`/`Page`/etc. keys). Log a single
  `parser_warning` (`code="missing_teeka_for_edge"`) per occurrence.
- The rule requires `publisher_id` but the matched shastra entry has
  `publisher == ""` → `publisher_id = "publisher_to_be_added"` (still emit;
  warn once).
- `_first_value(...)` returns `None` for the keyword group the rule needs.

### 5.5 Devanagari-canonical guarantee

All segments inserted into keys (`shastra_name`, `teeka_name`) are stored on
the `Reference` post-resolution and have already been NFC-normalised by the
parser. Edge emission must NOT re-normalise — keys are byte-for-byte stable.

---

## 6. Test plan

New file: `workers/ingestion/jainkosh/tests/unit/test_reference_edges.py`.

### 6.1 Unit cases (parametric, table-driven)

Build a tiny stub registry with three entries — one per type:

| shastra | type | teeka | publisher |
|---------|------|-------|-----------|
| `समयसार` | shastra | — | — |
| `नियमसार` | teeka | — | — |
| `धवला` | publication | — | `अनन्तकीर्ति ग्रन्थमाला` |

For each, fabricate `Block` objects across all 6 text/gatha kinds and
assert the emitted edge list matches the expected set. Cover:

- shastra/sanskrit_gatha + गाथा=6 → `Gatha("समयसार:गाथा:6")` →
  Topic.
- shastra/sanskrit_text + गाथा=6 → same as above (any block kind).
- teeka/sanskrit_gatha + गाथा=6 + teeka="आत्मख्याती" → `Gatha`.
- teeka/sanskrit_text + गाथा=6 + teeka="आत्मख्याती" → `GathaTeeka(":आत्मख्याती:गाथा:टीका:6")`.
- publication/hindi_text + गाथा=6 + teeka + publisher → 2 edges (`GathaTeeka` + `GathaTeekaBhaavarth`).
- publication + पृष्ठ=98 → `Page` edge with publisher_id resolved.
- teeka/prakrit_gatha + कलश=3 → `Kalash` edge.
- publication/hindi_text + कलश=3 → `KalashBhaavarth` edge.
- गाथा-keyword aliasing: `श्लोक=29` resolves to `Gatha(...:गाथा:29)`.
- पंक्ति=5 + गाथा=6 → edge has `props.pankti == 5`.
- Block with multiple non-inline references — first picks full path, rest simplified.
- Block with all-inline references — all use §4.5b (plain Gatha/Kalash/Page only).
- Block with non-inline + inline: non-inline uses §4.1–§4.3; all inline use §4.5b.
- `shastra_name=None` → no edges.
- `type=teeka` text block missing teeka_name → no edge + warning.
- Inline teeka ref with गाथा field → `Gatha` (not `GathaTeeka`).

### 6.2 Integration

Update `test_envelope_*.py` and `test_parse_keyword_golden.py`:

- Build a fixture `KeywordParseResult` carrying realistic references for each
  type/block-kind combo.
- Assert `would_write.neo4j.edges` contains the expected edge set
  (ordering-insensitive subset assertion).

### 6.3 Golden regeneration

After implementation:

1. Regenerate the three goldens (`आत्मा.json`, `द्रव्य.json`, `गुण.json`).
2. Manually inspect new `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` edges.
3. Confirm: no new node objects appear in `would_write.neo4j.nodes`.

---

## 7. `jainkosh.yaml` additions

```yaml
reference:
  # ... existing keys ...
  entity_keywords:
    gatha: [गाथा, श्लोक, सूत्र, दोहक, वार्तिक]
    kalash: [कलश]
    page: [पृष्ठ]
    pankti: [पंक्ति]
```

Update `jainkosh.schema.json` to permit the new `entity_keywords` block.

---

## 8. Definition of Done

- [ ] `PublisherRegistry` exists and is loaded into `JainkoshConfig.publisher_registry`.
- [ ] `ShastraEntry.publisher: str` field present; loader populates it.
- [ ] `ShastraRegistry.get_type(shastra_name)` helper returns `'shastra'|'teeka'|'publication'|None`.
- [ ] `ReferenceEntityKeywordsConfig` added; `jainkosh.yaml` + JSON schema updated.
- [ ] `reference_edges.py` exists with `build_reference_edges` and helpers.
- [ ] `build_neo4j_fragment` invokes edge builder for every block in
      `Subsection.blocks` (target=Topic) and `Definition.blocks` (target=Keyword).
- [ ] No new node objects added to `would_write.neo4j.nodes`.
- [ ] Reference selection: first non-inline; else first inline (main ref).
- [ ] Remaining refs processed with inline rules (§4.5): shastra→Gatha; teeka→GathaTeeka only; publication→GathaTeekaBhaavarth/KalashBhaavarth/Page only.
- [ ] Skip rules respected (no-shastra, no-type, no-teeka where required, no-value).
- [ ] All node keys use **canonical literals** `गाथा`, `कलश`, `पृष्ठ`, `टीका`, `भावार्थ`.
- [ ] पंक्ति surfaces as `props.pankti: int` on edges when present.
- [ ] Range/list values are not re-expanded here (parser §14A.4 already handled).
- [ ] Edge props include `block_index`, `mention_path`, `source_natural_key`; `CONTAINS_DEFINITION` also includes `section_index` and `definition_index`.
- [ ] `_dedupe(edges)` keys on `(type, from, to, mention_path)` to preserve distinct citation contexts.
- [ ] All new unit + integration tests pass.
- [ ] Goldens regenerated and human-reviewed.
- [ ] `parser_rules_version` bumped (`jainkosh.rules/1.10.0`).
