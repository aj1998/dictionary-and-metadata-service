# JainKosh Parser — Fix Spec 005

Addresses eight classes of bugs found by analysing
`workers/ingestion/jainkosh/tests/golden/द्रव्य.json` and
`workers/ingestion/jainkosh/tests/golden/पर्याय.json`.

**Parser version bump**: `1.4.0` → `1.5.0` (bump both `version` and
`parser_rules_version` in `parser_configs/jainkosh.yaml` **after** all phases
pass, as the final step).

---

## Scope

- Parser output shape and semantics.
- `would_write.neo4j` edge corrections driven by parser output.
- Golden updates for all three fixtures (`आत्मा`, `द्रव्य`, `पर्याय`).

Out of scope: orchestrator, DB writes, schema migrations.

---

## Root-cause summary

| # | File | Symptom | Root cause |
|---|------|---------|-----------|
| D1 | `models.py` | `IndexRelation` has no `is_top_level_reference` field | Field simply does not exist; cannot distinguish top-level (no source) from attributed relations |
| D2 | `refs.py` | `(ref1); (ref2)` in a single GRef span emits one `Reference` | `extract_refs_from_node` takes each `<span class="GRef">` as a unit; never splits on `); (` boundary |
| D3 | `parse_blocks.py` | `(विशेष देखें आकाश - 2)` — see_also block not populated for topic 4.2.2 | `make_block` discards `see_alsos` when `strip_paren_dekhen` empties the text (returns bare `None` instead of `(None, see_alsos)`) |
| D4 | `models.py` | `Block` has no `is_bullet_point` field | Field does not exist; callers cannot distinguish `<li>`-origin blocks from `<p>`-origin blocks |
| P1-a | `parse_index.py` | `source_topic_path_chain=[]` for "कर्म का अर्थ पर्याय" (should be `["1"]`) | The `<ul>` with this entry is **inside** LI[#1] (the heading LI itself); `_nearest_previous_heading_path_in_same_list(row_li=LI[#1])` starts at `LI[#1].prev`, never checking `LI[#1]` itself |
| P1-b | `parse_index.py` | `source_topic_path_chain=[]` for "ऊर्ध्व क्रम व ऊर्ध्व प्रचय" (should be `["1"]` or `["2"]`) | The `<ul>` is a **sibling** of LI[#1] and LI[#2] inside the outer OL; `row_li` is `None` (the anchor is not inside any LI); `_ancestor_li_ids` cannot find a contextual path |
| P3 | `parse_blocks.py` | `नयचक्र बृहद्/17` (GRef1) attributed to wrong block (`sanskrit_text` instead of `hindi_text`) | `_explode_nested_span` emits **all** pre-nested GRefs as standalone nodes → they become `pending_refs` attached to the **next** block; `<br/>` boundary between GRef1 and GRef2 is ignored |

---

## Files changed

| File | Phases |
|------|--------|
| `workers/ingestion/jainkosh/models.py` | 1, 4 |
| `workers/ingestion/jainkosh/refs.py` | 2 |
| `workers/ingestion/jainkosh/parse_blocks.py` | 3, 4, 7 |
| `workers/ingestion/jainkosh/parse_index.py` | 6 |
| `workers/ingestion/jainkosh/config.py` | 1, 2, 3, 4, 6, 7 |
| `parser_configs/jainkosh.yaml` | 1, 2, 3, 4, 6, 7, 8 |
| `parser_configs/_schemas/jainkosh.schema.json` | 1, 2, 3, 4, 6, 7 |
| `workers/ingestion/jainkosh/tests/unit/test_refs.py` | 2 |
| `workers/ingestion/jainkosh/tests/unit/test_see_also.py` | 3 |
| `workers/ingestion/jainkosh/tests/unit/test_index_source_chain.py` | 6 |
| `workers/ingestion/jainkosh/tests/unit/test_nested_span.py` | 7 |
| `workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py` | 8 |
| `workers/ingestion/jainkosh/tests/golden/द्रव्य.json` | 1, 2, 3, 4 |
| `workers/ingestion/jainkosh/tests/golden/पर्याय.json` | 1, 6, 7 |
| `workers/ingestion/jainkosh/tests/golden/आत्मा.json` | regression check |

---

## Phase 1 — `is_top_level_reference` on `IndexRelation`

### 1.1 Background

An `IndexRelation` is "top-level" when it has no attributed source topic — i.e.
`source_topic_path_chain == []`. Downstream consumers (Neo4j, Postgres) need to
distinguish this case explicitly rather than inferring it from the empty list.

### 1.2 Config change

**`config.py`** — add field to `IndexConfig`:

```python
class IndexConfig(BaseModel):
    ...
    top_level_reference_marking: bool = True
```

**`parser_configs/jainkosh.yaml`** — add under the `index:` key:

```yaml
index:
  ...
  top_level_reference_marking: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside the
`"index"` object's `"properties"`:

```json
"top_level_reference_marking": { "type": "boolean" }
```

### 1.3 Model change

**`models.py`** — add `is_top_level_reference` to `IndexRelation`:

```python
class IndexRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label_text: str
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: str
    is_self: bool = False
    target_exists: bool = True
    source_topic_path: Optional[str] = None
    source_topic_path_chain: list[str] = Field(default_factory=list)
    source_topic_natural_key_chain: list[str] = Field(default_factory=list)
    is_top_level_reference: bool = False          # ← NEW

    @model_validator(mode="after")
    def _legacy_source_topic_path(self):
        if self.source_topic_path is None and self.source_topic_path_chain:
            self.source_topic_path = self.source_topic_path_chain[-1]
        return self
```

### 1.4 Code change

**`parse_index.py`** — in `parse_index_relations`, after constructing `rel`,
set `is_top_level_reference` when config flag is on and chain is empty:

```python
# Inside the for-loop that builds IndexRelation objects:
rel = IndexRelation(
    label_text=label,
    source_topic_path_chain=source_path_chain,
    source_topic_natural_key_chain=[],
    **parsed,
)
_attach_heading_chain(rel, _ancestor_strong_chain(a, config))
if config.index.top_level_reference_marking and not rel.source_topic_path_chain:
    rel.is_top_level_reference = True  # ← NEW
out.append(rel)
```

### 1.5 Tests

**Existing**: `workers/ingestion/jainkosh/tests/unit/test_index_relations.py`

Add a test case:

```python
def test_top_level_reference_marking_true_when_no_chain():
    """IndexRelation with empty source_topic_path_chain gets is_top_level_reference=True."""
    html = """
    <ol>
      <li id="A"><strong><a href="#A">अ</a></strong>
        <ul><li class="HindiText"><a href="/wiki/ब">ब</a> — देखें <a href="/wiki/स">स</a></li></ul>
      </li>
    </ol>
    """
    # Parse with top_level_reference_marking=True (the default)
    # Expect: the see_also anchor whose source_path_chain=[] gets is_top_level_reference=True


def test_top_level_reference_marking_false_when_chain_present():
    """IndexRelation with a non-empty source_topic_path_chain gets is_top_level_reference=False."""
```

### 1.6 Golden delta

In `द्रव्य.json`, every `IndexRelation` whose `source_topic_path_chain` is `[]`
must have `"is_top_level_reference": true`.
All others must have `"is_top_level_reference": false`.

Run `python -m workers.ingestion.jainkosh.tests.regen_goldens` (or equivalent)
and approve the diff.

### 1.7 Definition of Done

- [ ] `IndexRelation.is_top_level_reference: bool = False` in `models.py`
- [ ] `IndexConfig.top_level_reference_marking: bool = True` in `config.py`
- [ ] YAML key `index.top_level_reference_marking: true`
- [ ] JSON schema updated
- [ ] `parse_index_relations` sets the field after building each `IndexRelation`
- [ ] Unit tests pass
- [ ] Goldens updated and approved

---

## Phase 2 — GRef semicolon splitting

### 2.1 Background

A single `<span class="GRef">` may contain a semicolon-delimited list of
independent references, e.g.:

```html
<span class="GRef">( नयचक्र बृहद्/17 ); ( द्रव्यसंग्रह/1 )</span>
```

Currently `extract_refs_from_node` treats the whole span as one `Reference`.
Each logical reference must become its own `Reference` object.

The split boundary is `); (` — a closing paren, optional whitespace, semicolon,
optional whitespace, opening paren. Split only at `)\s*;\s*(?=\()`, so
internal semicolons within a single reference (e.g. `(abc; 3-4)`) are
preserved.

### 2.2 Config change

**`config.py`** — add a new config class and field on `ReferenceConfig`:

```python
class ReferenceSemicolonSplitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    split_re: str = r'\)\s*;\s*(?=\()'
```

```python
class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    strip_inner_anchors: bool
    parse_strategy: Literal["text_only", "structured", "text_plus_structured"] = "text_only"
    raw_html: ReferenceRawHtmlConfig = Field(default_factory=ReferenceRawHtmlConfig)
    semicolon_split: ReferenceSemicolonSplitConfig = Field(   # ← NEW
        default_factory=ReferenceSemicolonSplitConfig
    )
```

**`parser_configs/jainkosh.yaml`** — add under the `reference:` key:

```yaml
reference:
  ...
  semicolon_split:
    enabled: true
    split_re: '\)\s*;\s*(?=\()'
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside the
`"reference"` object's `"properties"`:

```json
"semicolon_split": {
  "type": "object",
  "properties": {
    "enabled": { "type": "boolean" },
    "split_re": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 2.3 Code change

**`refs.py`** — add helper `_split_gref_text` and modify
`extract_refs_from_node`:

```python
def _split_gref_text(text: str, config: JainkoshConfig) -> list[str]:
    """Split a GRef text string at '); (' boundaries when configured."""
    if not config.reference.semicolon_split.enabled:
        return [text]
    parts = re.split(config.reference.semicolon_split.split_re, text)
    return [p.strip() for p in parts if p.strip()]


def extract_refs_from_node(node: Node, config: JainkoshConfig) -> list[Reference]:
    """Extract all GRef spans from a node, splitting at semicolons when configured."""
    refs = []
    for gref in node.css("span.GRef"):
        full_text = extract_ref_text(gref, config)
        if not full_text:
            continue
        parts = _split_gref_text(full_text, config)
        for part in parts:
            parsed = None
            if config.reference.parse_strategy != "text_only":
                parsed = parse_reference_text(part, config)
            # raw_html is only meaningful for single-part refs; multi-part gets None
            raw = _clean_raw_html(gref.html or "", config) if len(parts) == 1 else None
            refs.append(Reference(text=part, raw_html=raw, parsed=parsed))
    return refs
```

### 2.4 Tests

**`workers/ingestion/jainkosh/tests/unit/test_refs.py`** — add:

```python
def test_semicolon_split_basic():
    """A GRef containing '(ref1); (ref2)' produces two Reference objects."""
    html = '<p><span class="GRef">( नयचक्र बृहद्/17 ); ( द्रव्यसंग्रह/1 )</span></p>'
    # parse with default config (semicolon_split.enabled=True)
    # expect: refs == [Reference(text="( नयचक्र बृहद्/17 )"), Reference(text="( द्रव्यसंग्रह/1 )")]


def test_semicolon_split_disabled():
    """With semicolon_split.enabled=False, semicolon-delimited GRef stays as one Reference."""


def test_semicolon_split_preserves_internal_semicolons():
    """A GRef like '(abc; def)' (no paren at boundary) is NOT split."""
    html = '<p><span class="GRef">( abc; def )</span></p>'
    # expect: refs == [Reference(text="( abc; def )")]


def test_semicolon_split_three_parts():
    """Three-way split '(r1); (r2); (r3)' produces three Reference objects."""
```

### 2.5 Golden delta

In `पर्याय.json`, the block containing `नयचक्र बृहद्/17` currently has a
single reference. After this fix it should be split into two `Reference`
objects where the join was `); (`.

Check all three golden files for any GRef text containing `); (` and verify
the split is applied.

### 2.6 Definition of Done

- [ ] `ReferenceSemicolonSplitConfig` in `config.py`
- [ ] `ReferenceConfig.semicolon_split` field added
- [ ] YAML `reference.semicolon_split` section added
- [ ] JSON schema updated
- [ ] `_split_gref_text` helper in `refs.py`
- [ ] `extract_refs_from_node` uses `_split_gref_text`
- [ ] All unit tests pass
- [ ] Goldens updated and approved

---

## Phase 3 — Preserve `see_alsos` when block text empties after stripping

### 3.1 Background

In `द्रव्य.html`, topic 4.2.2's last `<li class="HindiText">` contains only:

```html
(विशेष  देखें <a href="/wiki/आकाश#2">आकाश - 2</a>)
```

The flow:
1. `find_see_alsos_in_element` correctly identifies this as a `see_also` block
   pointing to `आकाश - 2`.
2. `strip_paren_dekhen` removes the `(देखें …)` pattern, leaving an empty string.
3. `make_block` hits `if not text.strip(): return None` — discarding `see_alsos`
   entirely.
4. Result: topic 4.2.2 has zero `see_also` blocks in its output.

The fix: when text is empty but `see_alsos` is non-empty, return
`(None, see_alsos)` so the caller can still emit the see_also blocks.

### 3.2 Config change

**`config.py`** — add a new class `BlocksConfig` and a field on `JainkoshConfig`:

```python
class BlocksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preserve_see_alsos_on_empty_text: bool = True
    is_bullet_point_for_li: bool = True          # used in Phase 4
    nested_span_gref_reattach: bool = True        # used in Phase 7
    nested_span_gref_boundary_tags: list[str] = Field(
        default_factory=lambda: ["br"]
    )                                              # used in Phase 7
```

```python
class JainkoshConfig(BaseModel):
    ...
    blocks: BlocksConfig = Field(default_factory=BlocksConfig)  # ← NEW
```

**`parser_configs/jainkosh.yaml`** — add a new top-level section:

```yaml
blocks:
  preserve_see_alsos_on_empty_text: true
  is_bullet_point_for_li: true
  nested_span_gref_reattach: true
  nested_span_gref_boundary_tags: ["br"]
```

**`parser_configs/_schemas/jainkosh.schema.json`** — add at top level:

```json
"blocks": {
  "type": "object",
  "properties": {
    "preserve_see_alsos_on_empty_text": { "type": "boolean" },
    "is_bullet_point_for_li": { "type": "boolean" },
    "nested_span_gref_reattach": { "type": "boolean" },
    "nested_span_gref_boundary_tags": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "additionalProperties": false
}
```

### 3.3 Code change

**`parse_blocks.py`** — modify `make_block` to return `(None, see_alsos)` when
text is empty but see_alsos are present:

**Before** (lines 89–91):
```python
    text = strip_paren_dekhen(text, config)
    if not text.strip():
        return None
```

**After**:
```python
    text = strip_paren_dekhen(text, config)
    if not text.strip():
        if config.blocks.preserve_see_alsos_on_empty_text and see_alsos:
            return None, see_alsos   # caller must handle (None, [...]) tuple
        return None
```

**`parse_block_stream`** — the caller already handles the `(block, see_alsos)` tuple,
but it skips when `result is None`. The check must be extended:

**Before** (lines 186–194):
```python
        result = make_block(sub_el, config, current_keyword=current_keyword)
        if result is None:
            continue

        if isinstance(result, tuple):
            block, see_alsos = result
        else:
            block = result
            see_alsos = []
```

**After**:
```python
        result = make_block(sub_el, config, current_keyword=current_keyword)
        if result is None:
            continue

        if isinstance(result, tuple):
            block, see_alsos = result
            if block is None:
                # text was fully stripped but see_alsos survived
                for sa in see_alsos:
                    if isinstance(sa, Block):
                        out.append(sa)
                continue
        else:
            block = result
            see_alsos = []
```

### 3.4 Tests

**`workers/ingestion/jainkosh/tests/unit/test_see_also.py`** — add:

```python
def test_see_also_preserved_when_text_fully_stripped():
    """When block text is entirely a (देखें ...) pattern, the see_also block
    must still be emitted even though there is no prose block."""
    html = '<li class="HindiText">(विशेष देखें <a href="/wiki/आकाश#2">आकाश - 2</a>)</li>'
    # parse as block stream with default config
    # expect: one see_also block is emitted with target_keyword="आकाश - 2"
    # expect: NO hindi_text block is emitted


def test_see_also_not_preserved_when_flag_disabled():
    """With preserve_see_alsos_on_empty_text=False, the see_also is silently dropped."""
```

### 3.5 Golden delta

In `द्रव्य.json`, topic 4.2.2 (`natural_key` containing "4.2.2") currently has
`blocks: []` (no see_also). After this fix it should contain a `see_also` block
with `target_keyword: "आकाश - 2"` (or the resolved wiki path).

### 3.6 Definition of Done

- [ ] `BlocksConfig` class with `preserve_see_alsos_on_empty_text: bool = True`
  in `config.py`
- [ ] `JainkoshConfig.blocks: BlocksConfig` field added
- [ ] YAML `blocks:` section added
- [ ] JSON schema updated
- [ ] `make_block` returns `(None, see_alsos)` when text empty but see_alsos present
- [ ] `parse_block_stream` handles `(None, [...])` tuple
- [ ] Unit tests pass
- [ ] Goldens updated and approved

---

## Phase 4 — `is_bullet_point` field on `Block`

### 4.1 Background

Blocks produced from `<li>` elements (as opposed to `<p>` or `<span>`) represent
bullet-point entries in the source HTML. Downstream consumers need to know this
to render them correctly, but the current `Block` model has no such flag.

### 4.2 Config change

`BlocksConfig.is_bullet_point_for_li: bool = True` is already added in Phase 3.
No further config changes are needed here.

### 4.3 Model change

**`models.py`** — add `is_bullet_point` to `Block`:

```python
class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: BlockKind

    text_devanagari: Optional[str] = None
    hindi_translation: Optional[str] = None
    references: list[Reference] = Field(default_factory=list)
    is_orphan_translation: bool = False
    is_bullet_point: bool = False       # ← NEW

    # table
    raw_html: Optional[str] = None
    table_rows: Optional[list[list[str]]] = None

    # see_also
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: Optional[str] = None
    is_self: bool = False
    target_exists: bool = True
```

### 4.4 Code change

**`parse_blocks.py`** — in `make_block`, after constructing the `Block` object,
set `is_bullet_point` if the source node is an `<li>`:

```python
    block = Block(
        kind=kind,
        text_devanagari=text,
        references=refs,
    )
    if config.blocks.is_bullet_point_for_li and tag == "li":
        block.is_bullet_point = True    # ← NEW

    return block, see_alsos
```

### 4.5 Tests

**`workers/ingestion/jainkosh/tests/unit/test_refs.py`** or a new file:

```python
def test_is_bullet_point_set_for_li_element():
    """A block produced from an <li> node gets is_bullet_point=True."""
    html = '<li class="HindiText">कोई पाठ</li>'
    # parse as block stream with default config
    # expect: block.is_bullet_point == True


def test_is_bullet_point_false_for_p_element():
    """A block produced from a <p> node gets is_bullet_point=False."""
    html = '<p class="HindiText">कोई पाठ</p>'
    # expect: block.is_bullet_point == False


def test_is_bullet_point_flag_disabled():
    """With is_bullet_point_for_li=False, even <li>-origin blocks get is_bullet_point=False."""
```

### 4.6 Golden delta

In `द्रव्य.json` and `पर्याय.json`, all blocks whose source node is an `<li>`
must gain `"is_bullet_point": true`. Blocks from `<p>` or `<span>` keep
`"is_bullet_point": false`.

Since `Block` uses `extra="forbid"` and the field has a default, **existing**
golden snapshots that omit `is_bullet_point` will now include
`"is_bullet_point": false` for every block. Regenerate and approve.

### 4.7 Definition of Done

- [ ] `Block.is_bullet_point: bool = False` in `models.py`
- [ ] `BlocksConfig.is_bullet_point_for_li: bool = True` (already done in Phase 3)
- [ ] `make_block` sets `block.is_bullet_point = True` when `tag == "li"` and flag
  is on
- [ ] Unit tests pass
- [ ] Goldens updated and approved

---

## Phase 6 — Fix `source_topic_path_chain` for पर्याय index relations

### 6.1 Background

Two structural layouts in `पर्याय.html` produce wrong `source_topic_path_chain`
values:

**Bug P1-a — see_also inside the heading LI itself**

```html
<li id="1">
  <strong><a href="#1">पर्याय का स्वरूप</a></strong>
  <ul class="HindiText">
    <li class="HindiText">
      <a href="/wiki/...">कर्म का अर्थ पर्याय</a> — देखें <a href="...">...</a>
    </li>
  </ul>
</li>
```

The inner `<ul>` is **inside** LI[#1]. When `_ancestor_li_ids` walks up from the
see_also `<a>`, the `row_li` (the first `<li>` ancestor) is LI[#1] itself —
which **is** the heading LI. `_nearest_previous_heading_path_in_same_list` starts
from `row_li.prev` (the sibling before LI[#1]), never checking `row_li` itself,
so it returns `None`.

Expected: `source_topic_path_chain = ["1"]`

**Bug P1-b — see_also in a `<ul>` sibling to the heading LIs**

```html
<ol>
  <li id="1">...</li>
  <li id="2">...</li>
  <ul class="HindiText">      ← sibling of the heading LIs, inside the outer OL
    <li class="HindiText">
      <a href="...">ऊर्ध्व क्रम व ऊर्ध्व प्रचय</a> — देखें <a href="...">...</a>
    </li>
  </ul>
  <li id="3">...</li>
</ol>
```

The inner `<ul>` is not inside any `<li>`. When `_ancestor_li_ids` walks up from
the see_also `<a>`, it finds the inner `<ul>` element but `skip_innermost_li`
never gets a chance to assign `row_li` (there is no enclosing `<li>`). `row_li`
stays `None` and `_nearest_previous_heading_path_in_same_list(None)` returns
`None` immediately.

Expected: `source_topic_path_chain = ["1"]` (or `["2"]` depending on proximity)

### 6.2 Config change

**`config.py`** — add two fields to `IndexSourceChainConfig`:

```python
class IndexSourceChainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    li_strong_selector: str = "strong"
    li_strong_a_selector: str = "strong > a"
    skip_li_with_footer_id: bool = True
    match_normalize: Literal["nfc_collapsed_ws"] = "nfc_collapsed_ws"
    enclosing_li_fallback: bool = True
    li_path_from_inner_ol_fallback: bool = True
    row_li_self_path_check: bool = True           # ← NEW (fixes P1-a)
    sibling_container_fallback: bool = True        # ← NEW (fixes P1-b)
```

**`parser_configs/jainkosh.yaml`** — under `index.source_chain:`:

```yaml
index:
  source_chain:
    ...
    row_li_self_path_check: true
    sibling_container_fallback: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside
`"index"."source_chain"` properties:

```json
"row_li_self_path_check": { "type": "boolean" },
"sibling_container_fallback": { "type": "boolean" }
```

### 6.3 Code change — fix P1-a (`row_li_self_path_check`)

**`parse_index.py`** — modify `_nearest_previous_heading_path_in_same_list`:

**Current function signature and first check** (lines 161–164):
```python
def _nearest_previous_heading_path_in_same_list(li: Optional[Node], config: JainkoshConfig) -> Optional[str]:
    if li is None:
        return None
    prev = li.prev
```

**After** — add a self-check before scanning siblings:
```python
def _nearest_previous_heading_path_in_same_list(li: Optional[Node], config: JainkoshConfig) -> Optional[str]:
    if li is None:
        return None
    # P1-a fix: if `li` itself is a heading LI (has strong>a[href^="#"]),
    # return its own path before scanning backwards.
    if config.index.source_chain.row_li_self_path_check:
        self_path = _topic_path_from_li_heading_anchor(li, config)
        if self_path:
            return self_path
    prev = li.prev
    # ... rest of function unchanged ...
```

### 6.4 Code change — fix P1-b (`sibling_container_fallback`)

**`parse_index.py`** — modify `_ancestor_li_ids` to handle the case where
`row_li` is `None` (anchor is in a `<ul>` that is a direct child of an `<ol>`,
not inside any `<li>`).

Add a fallback block after the `while` loop that assigns `row_li` (currently at
line 68):

```python
def _ancestor_li_ids(a: Node, config: JainkoshConfig) -> list[str]:
    ids: list[str] = []
    row_li: Optional[Node] = None
    cur = a.parent
    skip_innermost_li = True
    while cur is not None:
        if cur.tag == "li":
            if skip_innermost_li:
                row_li = cur
                skip_innermost_li = False
            li_id = (cur.attributes or {}).get("id") or ""
            if not li_id:
                cur = cur.parent
                continue
            if config.index.source_chain.skip_li_with_footer_id and li_id.startswith("footer-"):
                cur = cur.parent
                continue
            if li_id:
                ids.append(li_id)
        cur = cur.parent
    ids.reverse()

    # P1-b fix: if row_li is None, the anchor is in a container (e.g. <ul>) that
    # is a direct sibling of heading LIs inside an outer <ol>/<ul>.
    # Walk the container's previous siblings to find a heading LI.
    if row_li is None and config.index.source_chain.sibling_container_fallback:
        container = a.parent
        # Walk up until we find the container that is a sibling of LIs
        while container is not None and container.tag not in ("ol", "ul", "li"):
            container = container.parent
        if container is not None and container.tag in ("ul", "ol"):
            # container itself is the non-li sibling; scan its prev siblings
            prev = container.prev
            while prev is not None:
                if prev.tag == "li":
                    path = _topic_path_from_li_heading_anchor(prev, config)
                    if path:
                        contextual_path = path
                        if not ids or ids[-1] != contextual_path:
                            ids.append(contextual_path)
                        return ids
                prev = prev.prev
        return ids

    contextual_path = _nearest_previous_heading_path_in_same_list(row_li, config)
    if contextual_path and (not ids or ids[-1] != contextual_path):
        ids.append(contextual_path)
    return ids
```

> **Implementation note**: the fallback walks **backwards** among sibling LIs
> to find the nearest heading LI before the container. It returns the first
> (closest) heading path found, which is the correct attribution.

### 6.5 Tests

**`workers/ingestion/jainkosh/tests/unit/test_index_source_chain.py`** — add:

```python
def test_row_li_self_path_check_inner_ul():
    """see_also inside a <ul> that is INSIDE the heading LI gets the heading LI's path."""
    html = """
    <ol>
      <li id="1">
        <strong><a href="#1">पर्याय का स्वरूप</a></strong>
        <ul>
          <li class="HindiText">
            <a href="/wiki/कर्म">कर्म</a> — देखें <a href="/wiki/कर्म">कर्म</a>
          </li>
        </ul>
      </li>
    </ol>
    """
    # expect: source_topic_path_chain == ["1"]


def test_sibling_container_fallback_ul_between_lis():
    """see_also in a <ul> that is a sibling of heading LIs gets the preceding heading LI's path."""
    html = """
    <ol>
      <li id="1"><strong><a href="#1">पर्याय का स्वरूप</a></strong></li>
      <li id="2"><strong><a href="#2">पर्याय के भेद</a></strong></li>
      <ul class="HindiText">
        <li class="HindiText">
          <a href="/wiki/कुछ">कुछ</a> — देखें <a href="/wiki/कुछ">कुछ</a>
        </li>
      </ul>
      <li id="3"><strong><a href="#3">तीसरा</a></strong></li>
    </ol>
    """
    # The <ul> is between LI[#2] and LI[#3], so the nearest heading LI is LI[#2]
    # expect: source_topic_path_chain == ["2"]


def test_sibling_container_fallback_disabled():
    """With sibling_container_fallback=False, source_topic_path_chain stays []."""
```

### 6.6 Golden delta

In `पर्याय.json`, the following `IndexRelation` objects must be updated:

| `label_text` | Before | After |
|---|---|---|
| कर्म का अर्थ पर्याय | `source_topic_path_chain: []` | `["1"]` |
| ऊर्ध्व क्रम व ऊर्ध्व प्रचय | `source_topic_path_chain: []` | `["1"]` or `["2"]` (whichever heading LI precedes the sibling `<ul>`) |

Additionally, verify that `पर्याय में परस्पर व्यतिरेक प्रदर्शन` which currently
has `["1"]` (possibly incorrect) is re-evaluated by the new self-check logic.

### 6.7 Definition of Done

- [ ] `IndexSourceChainConfig.row_li_self_path_check: bool = True`
- [ ] `IndexSourceChainConfig.sibling_container_fallback: bool = True`
- [ ] YAML keys added
- [ ] JSON schema updated
- [ ] `_nearest_previous_heading_path_in_same_list` performs self-check when flag
  is on
- [ ] `_ancestor_li_ids` has sibling-container fallback when `row_li is None`
- [ ] Unit tests pass
- [ ] Goldens updated and approved

---

## Phase 7 — Correct GRef attribution in `_explode_nested_span`

### 7.1 Background

`_explode_nested_span` handles a `<li class="HindiText">` (or similar outer span)
that contains nested block elements, e.g.:

```html
<li class="HindiText">
  प्रमाण नय... पाठ
  <span class="GRef">( नयचक्र बृहद्/17 )</span>
  ।<br/>
  <span class="GRef">( नयचक्र / श्रुतभवन दीपक/ पृष्ठ 57 )</span>
  <span class="SanskritText">संस्कृत पाठ यहाँ</span>
  = हिन्दी अनुवाद
</li>
```

Expected output:
- `hindi_text` block: prose + GRef1 (`नयचक्र बृहद्/17`) as trailing reference
- `sanskrit_text` block: संस्कृत पाठ + GRef2 (`नयचक्र / श्रुतभवन दीपक/ पृष्ठ 57`)
  as leading reference

Current bug: `_explode_nested_span` emits **all** pre-nested GRef children as
standalone nodes (lines 499–502 of `parse_blocks.py`):

```python
    for child in span.iter(include_text=False):
        child_kind = block_class_kind(child, config)
        if is_gref_node(child, config):
            results.append(child)    # ← becomes pending_refs for NEXT block
```

GRef1 (which follows `;<br/>`, a sentence-terminal boundary) is trailing for the
outer `hindi_text` block, but instead becomes a `pending_ref` that attaches to
the `sanskrit_text` block that follows.

**The `<br/>` is the attribution boundary**: GRefs **before** the last `<br/>`
before the first nested block are trailing for the outer block; GRefs **after**
the last `<br/>` before the first nested block (and before the nested block) are
leading for the first nested block.

### 7.2 Config change

`BlocksConfig.nested_span_gref_reattach: bool = True` and
`BlocksConfig.nested_span_gref_boundary_tags: list[str] = ["br"]` are already
added in Phase 3. No further config changes needed.

### 7.3 Code change

**`parse_blocks.py`** — rewrite `_explode_nested_span` to correctly partition
pre-nested GRefs across the `<br/>` boundary.

The algorithm:

1. Walk children of the outer span (direct children only) left-to-right.
2. Identify the index of the **first nested block** child (a child whose
   `block_class_kind` returns a kind different from `outer_kind`).
3. Among pre-nested children (indices 0 to `first_nested_idx - 1`), collect:
   - **trailing GRefs**: GRef children that come **before** the last
     `<br/>`-like boundary tag (any tag in `config.blocks.nested_span_gref_boundary_tags`).
   - **leading GRefs**: GRef children that come **after** the last `<br/>`-like
     boundary tag (i.e., between the `<br/>` and the first nested block).
4. Build the outer block synthetic node from: direct text + trailing GRefs.
5. Prepend leading GRefs as standalone nodes before the first nested block.

Full replacement for `_explode_nested_span`:

```python
def _explode_nested_span(span: Node, config: JainkoshConfig) -> list[Node]:
    """Flatten a nested-span element into a list of child blocks.

    Pre-nested GRefs are split across the last <br/> boundary:
    - GRefs before the last <br/> are appended to the outer block's HTML.
    - GRefs after the last <br/> (but before the first nested block) are emitted
      as standalone leading-reference nodes before the nested block.
    """
    from selectolax.parser import HTMLParser

    outer_kind = block_class_kind(span, config)
    children = [c for c in span.iter(include_text=False) if c != span]

    # Step 1: find index of first nested block child
    first_nested_idx = -1
    for i, child in enumerate(children):
        ck = block_class_kind(child, config)
        if ck is not None and ck != outer_kind:
            first_nested_idx = i
            break
        if ck == outer_kind and has_nested_block(child, config):
            first_nested_idx = i
            break

    if first_nested_idx < 0:
        # No nested block found; treat the whole span as a single block
        direct_text = _direct_text_of(span)
        if direct_text.strip():
            return [_make_synthetic_block(direct_text, outer_kind, config)]
        return [span]

    pre_nested = children[:first_nested_idx]
    post_nested = children[first_nested_idx:]

    # Step 2: split pre-nested children at the last <br/>-boundary tag
    boundary_tags = set(config.blocks.nested_span_gref_boundary_tags) if (
        config.blocks.nested_span_gref_reattach
    ) else set()

    last_boundary_idx = -1
    if boundary_tags:
        for i, child in enumerate(pre_nested):
            if child.tag in boundary_tags:
                last_boundary_idx = i

    # trailing_grefs: GRefs before (and including up to) last_boundary_idx
    # leading_grefs: GRefs after last_boundary_idx
    trailing_grefs = []
    leading_grefs = []
    for i, child in enumerate(pre_nested):
        if is_gref_node(child, config):
            if i <= last_boundary_idx or last_boundary_idx < 0:
                trailing_grefs.append(child)
            else:
                leading_grefs.append(child)

    # Step 3: build outer block with direct text + trailing_grefs
    direct_text = _direct_text_of(span)
    # Build synthetic outer HTML: direct text + trailing GRef HTML
    trailing_gref_html = "".join(c.html or "" for c in trailing_grefs)
    outer_html_content = (direct_text + " " + trailing_gref_html).strip()
    tag = span.tag or "p"
    css_class = None
    for cls_name, k in config.block_classes.items():
        if k == outer_kind:
            css_class = cls_name
            break
    if css_class is None:
        css_class = "HindiText"

    results = []
    if outer_html_content:
        synthetic_html = f'<{tag} class="{css_class}">{outer_html_content}</{tag}>'
        tree = HTMLParser(synthetic_html)
        outer_node = tree.css_first(f"{tag}.{css_class.split()[0]}")
        if outer_node is not None:
            results.append(outer_node)

    # Step 4: emit leading_grefs as standalone nodes (they become pending_refs for
    # the next block, which is correct since they precede the nested block)
    results.extend(leading_grefs)

    # Step 5: emit nested and post-nested children
    for child in post_nested:
        ck = block_class_kind(child, config)
        if ck is not None and ck != outer_kind:
            if ck in config.nested_span.outer_kinds and has_nested_block(child, config):
                results.extend(_explode_nested_span(child, config))
            else:
                results.append(child)
        elif is_gref_node(child, config):
            results.append(child)

    return results if results else [span]
```

> **Key invariant**: `trailing_grefs` end up inside the outer block's HTML so
> `extract_refs_from_node` picks them up naturally. `leading_grefs` are emitted
> as standalone nodes and become `pending_refs` attached to the **next** block
> (the nested `sanskrit_text`), which is the correct attribution.

### 7.4 Tests

**`workers/ingestion/jainkosh/tests/unit/test_nested_span.py`** — add:

```python
def test_gref_before_br_is_trailing_for_outer_block():
    """GRef before the <br/> boundary stays with the outer (hindi_text) block."""
    html = """
    <li class="HindiText">
      प्रमाण नय पाठ
      <span class="GRef">( नयचक्र बृहद्/17 )</span>
      ।<br/>
      <span class="GRef">( द्रव्यसंग्रह/1 )</span>
      <span class="SanskritText">संस्कृत पाठ</span>
    </li>
    """
    # parse with default config
    # expect:
    #   blocks[0].kind == "hindi_text"
    #   blocks[0].references[0].text == "( नयचक्र बृहद्/17 )"
    #   blocks[1].kind == "sanskrit_text"
    #   blocks[1].references[0].text == "( द्रव्यसंग्रह/1 )"


def test_gref_after_br_is_leading_for_nested_block():
    """GRef after the <br/> boundary becomes a leading ref for the nested block."""
    # same structure, verify GRef2 is in blocks[1].references, not blocks[0].references


def test_no_br_all_grefs_trailing():
    """When no <br/> boundary exists, all pre-nested GRefs are trailing for outer block."""
    html = """
    <li class="HindiText">
      पाठ
      <span class="GRef">( ref1 )</span>
      <span class="SanskritText">संस्कृत</span>
    </li>
    """
    # expect: blocks[0].references == [ref1], blocks[1].references == []


def test_reattach_disabled_old_behavior():
    """With nested_span_gref_reattach=False, all GRefs become standalone nodes (old behavior)."""
```

### 7.5 Golden delta

In `पर्याय.json`, the block containing `नयचक्र बृहद्/17` must move from the
`sanskrit_text` block to the preceding `hindi_text` block. The `sanskrit_text`
block should retain `नयचक्र / श्रुतभवन दीपक/ पृष्ठ 57` as its leading reference.

### 7.6 Definition of Done

- [ ] `BlocksConfig.nested_span_gref_reattach: bool = True` (already in Phase 3)
- [ ] `BlocksConfig.nested_span_gref_boundary_tags: list[str] = ["br"]` (already in Phase 3)
- [ ] `_explode_nested_span` rewritten with `<br/>`-boundary split logic
- [ ] Unit tests pass
- [ ] Goldens updated and approved

---

## Phase 8 — Version bump and golden regeneration

### 8.1 Version bump

**`parser_configs/jainkosh.yaml`** — after all phases pass:

```yaml
version: "1.5.0"
parser_rules_version: "jainkosh.rules/1.5.0"
```

### 8.2 Golden regeneration

Run the golden regeneration script (or equivalent) for all three fixtures:

```bash
python -m workers.ingestion.jainkosh.tests.regen_goldens
# or:
pytest workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py --regen
```

Review the diff carefully:
- Every `IndexRelation` with empty `source_topic_path_chain` gains
  `"is_top_level_reference": true`.
- Every `Block` gains `"is_bullet_point": false` (default) or `true` for
  `<li>`-origin blocks.
- Topic 4.2.2 in `द्रव्य` has a `see_also` block for `आकाश - 2`.
- Semicolon-delimited GRefs are split into separate `Reference` objects.
- `नयचक्र बृहद्/17` is attributed to the `hindi_text` block in `पर्याय`.
- Source chain values in `पर्याय` match the expected chains per §6.6.

### 8.3 Regression checks

Run the full test suite to confirm no regressions in `आत्मा.json`:

```bash
pytest workers/ingestion/jainkosh/tests/
```

### 8.4 Definition of Done

- [ ] `version: "1.5.0"` in `parser_configs/jainkosh.yaml`
- [ ] `parser_rules_version: "jainkosh.rules/1.5.0"` in `parser_configs/jainkosh.yaml`
- [ ] All three goldens regenerated and approved
- [ ] Full test suite passes (no regressions)
- [ ] Git commit: `parser_fix_spec_005 — bump to 1.5.0`

---

## Appendix A — Config key reference

All new config keys introduced in this spec, with their default values:

| Config path | Type | Default | Phase |
|---|---|---|---|
| `index.top_level_reference_marking` | `bool` | `true` | 1 |
| `reference.semicolon_split.enabled` | `bool` | `true` | 2 |
| `reference.semicolon_split.split_re` | `str` | `'\)\s*;\s*(?=\()'` | 2 |
| `blocks.preserve_see_alsos_on_empty_text` | `bool` | `true` | 3 |
| `blocks.is_bullet_point_for_li` | `bool` | `true` | 4 |
| `blocks.nested_span_gref_reattach` | `bool` | `true` | 7 |
| `blocks.nested_span_gref_boundary_tags` | `list[str]` | `["br"]` | 7 |
| `index.source_chain.row_li_self_path_check` | `bool` | `true` | 6 |
| `index.source_chain.sibling_container_fallback` | `bool` | `true` | 6 |

All flags default to the **corrected** behaviour so that existing configs
continue to work without changes. To revert to legacy behaviour, set the flag to
`false` in `parser_configs/jainkosh.yaml`.

---

## Appendix B — Implementation order and dependencies

Phases can be implemented independently **except**:

- Phase 3 must be done **before** Phase 4 (both modify `parse_blocks.py` and
  `BlocksConfig`; Phase 3 introduces `BlocksConfig`, Phase 4 adds a field to it).
- Phase 7 must be done **before** Phase 8 (golden regen incorporates all changes).
- Phase 8 (version bump) must be the **last** step.

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.

---

## Appendix C — Affected HTML structures (for test authoring)

### C.1 द्रव्य.html — topic 4.2.2 see_also (Bug D3)

```html
<!-- Line ~1604 in workers/ingestion/jainkosh/tests/fixtures/द्रव्य.html -->
<li class="HindiText">
  (विशेष  देखें <a href="/wiki/आकाश#2">आकाश - 2</a>)
</li>
```

After Phase 3: a `see_also` block with `target_keyword="आकाश - 2"` must appear
in topic 4.2.2's `blocks` list.

### C.2 पर्याय.html — "कर्म का अर्थ पर्याय" (Bug P1-a)

```html
<!-- Lines ~382-385 in workers/ingestion/jainkosh/tests/fixtures/पर्याय.html -->
<li id="1">
  <strong><a href="#1">पर्याय का स्वरूप</a></strong>
  <ul class="HindiText">
    <li class="HindiText">
      <a href="/wiki/...">कर्म का अर्थ पर्याय</a> — देखें <a href="...">...</a>
    </li>
  </ul>
</li>
```

After Phase 6: `source_topic_path_chain = ["1"]`.

### C.3 पर्याय.html — "ऊर्ध्व क्रम" (Bug P1-b)

```html
<!-- Lines ~413-416 in workers/ingestion/jainkosh/tests/fixtures/पर्याय.html -->
<ol>
  <li id="1">...</li>
  <li id="2">...</li>
  <ul class="HindiText">   <!-- NOT inside any <li> -->
    <li class="HindiText">ऊर्ध्व क्रम व ऊर्ध्व प्रचय — देखें ...</li>
  </ul>
</ol>
```

After Phase 6: `source_topic_path_chain = ["2"]` (nearest preceding heading LI
is LI[#2]).

### C.4 पर्याय.html — GRef misattribution (Bug P3)

```html
<!-- Lines ~598-613 in workers/ingestion/jainkosh/tests/fixtures/पर्याय.html -->
<li class="HindiText">
  प्रमाण नय ... पाठ
  <span class="GRef">( नयचक्र बृहद्/17 )</span>
  ।<br/>
  <span class="GRef">( नयचक्र / श्रुतभवन दीपक/ पृष्ठ 57 )</span>
  <span class="SanskritText">संस्कृत पाठ</span>
  = हिन्दी अनुवाद
</li>
```

After Phase 7:
- `hindi_text` block references: `[नयचक्र बृहद्/17]`
- `sanskrit_text` block references: `[नयचक्र / श्रुतभवन दीपक/ पृष्ठ 57]`
