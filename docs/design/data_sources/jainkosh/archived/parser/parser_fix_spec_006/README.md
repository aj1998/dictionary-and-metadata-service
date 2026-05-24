# JainKosh Parser — Fix Spec 006

Addresses three classes of bugs found by analysing
`workers/ingestion/jainkosh/tests/golden/द्रव्य.json` and
`workers/ingestion/jainkosh/tests/golden/पर्याय.json`.

**Parser version bump**: `1.5.0` → `1.6.0` (bump both `version` and
`parser_rules_version` in `parser_configs/jainkosh.yaml` **after** all phases
pass, as the final step).

---

## Scope

- Parser output shape and semantics for three specific bugs.
- `would_write.neo4j` edge corrections driven by parser output.
- Golden updates for all three fixtures (`आत्मा`, `द्रव्य`, `पर्याय`).

Out of scope: orchestrator, DB writes, schema migrations.

---

## Root-cause summary

| # | File | Symptom | Root cause |
|---|------|---------|-----------|
| D1 | `parse_subsections.py`, `envelope.py` | In द्रव्य, `RELATED_TO` edge for a label_seed topic emits `from.key` = **parent** natural_key instead of **child** (label_seed) natural_key | `extract_label_topic_seeds` creates the child but leaves the `see_also` block in the parent's `blocks`; the Neo4j builder walks every block on every subsection, so it emits the edge from the parent |
| D2 | `models.py`, `refs.py`, `parse_blocks.py` | `Reference` objects carry no `inline_reference` flag distinguishing leading refs (ref first, then text) from inline/trailing refs (text first, then ref) | `Reference` model lacks the field; `extract_refs_from_node` never sets it |
| P1 | `see_also.py`, `parse_index.py` | In पर्याय, `index_relations` contains a **duplicate** entry for "परिणमन का अस्तित्व…" → उत्पाद#3, and the entry for "पर्याय का कथंचित् सत्पना…" → उत्पाद#3 is **missing** | When two `<a>` elements in the same parent have identical HTML (same href + same link text), `parent_html.find(a_html)` in `_extract_label_before_anchor` always returns the first occurrence's position; the second anchor's label is extracted from the wrong position |

---

## Files changed

| File | Phases |
|------|--------|
| `workers/ingestion/jainkosh/models.py` | 2 |
| `workers/ingestion/jainkosh/refs.py` | 2 |
| `workers/ingestion/jainkosh/parse_blocks.py` | 2 |
| `workers/ingestion/jainkosh/parse_subsections.py` | 1 |
| `workers/ingestion/jainkosh/see_also.py` | 3 |
| `workers/ingestion/jainkosh/parse_index.py` | 3 |
| `workers/ingestion/jainkosh/config.py` | 1, 2, 3 |
| `parser_configs/jainkosh.yaml` | 1, 2, 3, 4 |
| `parser_configs/_schemas/jainkosh.schema.json` | 1, 2, 3 |
| `workers/ingestion/jainkosh/tests/unit/test_refs.py` | 2 |
| `workers/ingestion/jainkosh/tests/unit/test_index_relations.py` | 3 |
| `workers/ingestion/jainkosh/tests/golden/द्रव्य.json` | 1, 2 |
| `workers/ingestion/jainkosh/tests/golden/पर्याय.json` | 3 |
| `workers/ingestion/jainkosh/tests/golden/आत्मा.json` | 2 (inline_reference field adds to all refs) |

---

## Phase 1 — label_seed `RELATED_TO` edge from child, not parent (Bug D1)

### 1.1 Background

When a `HindiText` block contains an **inline** `देखें` pattern (non-row-style,
no leading bullet), `parse_subsections.py` currently:

1. Creates the label_seed `Subsection` child (correct).
2. Leaves the `see_also` block **in the parent's `blocks`** list (wrong).

`envelope.py`'s `build_neo4j_fragment` then walks every subsection and emits a
`RELATED_TO` edge for every `see_also` block, using `sub.natural_key` as `from`.
Because the `see_also` sits in the parent, the edge uses the parent's key.

**Desired behaviour**: the `see_also` block must live in the child label_seed's
`blocks`. The parent subsection must **not** hold it. This mirrors the v1.3.0
row-style relocation already implemented for row-style entries.

### 1.2 Config change

**`config.py`** — add to `LabelToTopicConfig`:

```python
class LabelToTopicConfig(BaseModel):
    ...
    relocate_inline_see_also_to_child: bool = True   # ← NEW
```

**`parser_configs/jainkosh.yaml`** — under `label_to_topic:`:

```yaml
label_to_topic:
  ...
  relocate_inline_see_also_to_child: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside the
`"label_to_topic"` object's `"properties"`:

```json
"relocate_inline_see_also_to_child": { "type": "boolean" }
```

### 1.3 Code changes

#### 1.3.1 `parse_subsections.py` — `extract_label_topic_seeds`

**Current signature** (abbreviated):
```python
def extract_label_topic_seeds(
    blocks: list[Block],
    *,
    parent_subsection: Optional[Subsection],
    keyword: str,
    config: JainkoshConfig,
    label_seed_candidates: list[str],
    row_relations: Optional[dict[str, list[Block]]] = None,
) -> list[Subsection]:
```

**Change 1**: Change the return type to `tuple[list[Subsection], list[int]]`.
The second element is a list of **indices** into `blocks` that should be removed
from the parent because they have been relocated to a child. Call the new
variable `blocks_to_relocate_indices`.

**Change 2**: In the `for i, block in enumerate(blocks):` loop that processes
inline see_also blocks (the second loop in the function, starting at
`for i, block in enumerate(blocks):`), after creating the seed:

```python
seed = _make_label_seed_subsection(
    label=label,
    keyword=keyword,
    parent=parent_subsection,
    config=config,
    row_see_alsos=[block] if config.label_to_topic.relocate_inline_see_also_to_child else [],
)
seeds.append(seed)
emitted_labels.add(label)
emitted_in_block = True
if config.label_to_topic.relocate_inline_see_also_to_child:
    blocks_to_relocate_indices.append(i)
```

**Change 3**: Initialize `blocks_to_relocate_indices: list[int] = []` at the
top of the function. Return `seeds, blocks_to_relocate_indices` instead of just
`seeds`.

**Full updated function signature and return**:

```python
def extract_label_topic_seeds(
    blocks: list[Block],
    *,
    parent_subsection: Optional[Subsection],
    keyword: str,
    config: JainkoshConfig,
    label_seed_candidates: list[str],
    row_relations: Optional[dict[str, list[Block]]] = None,
) -> tuple[list[Subsection], list[int]]:   # ← return type changed
    if not config.label_to_topic.enabled:
        return [], []
    if row_relations is None:
        row_relations = {}
    seeds: list[Subsection] = []
    emitted_labels: set[str] = set()
    blocks_to_relocate_indices: list[int] = []   # ← NEW

    # --- first loop: label_seed_candidates from elements (row-style) ---
    for label in label_seed_candidates:
        if not label or label in emitted_labels:
            continue
        emitted_labels.add(label)
        seeds.append(
            _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=parent_subsection,
                config=config,
                row_see_alsos=row_relations.get(label, []),
            )
        )

    emitted_in_block = bool(seeds)

    # --- second loop: inline see_also blocks ---
    for i, block in enumerate(blocks):
        if block.kind != "see_also":
            continue
        if emitted_in_block:
            continue
        if not _should_emit_for_anchor(block, config):
            continue
        prose = _find_preceding_text_block(blocks, i)
        if prose is None:
            continue
        prose_text, prose_kind = _text_source_for_label_seed(prose, config)
        inside_brackets = _trigger_inside_brackets(prose_text, config)
        if (
            inside_brackets
            and prose_kind in config.label_to_topic.skip_in_source_kinds
            and not _is_row_like_label_context(prose_text, config)
        ):
            continue
        label = extract_label_before_trigger(prose_text, config)
        if not label or label in emitted_labels:
            continue
        emitted_labels.add(label)
        # Relocate the see_also block to the child when configured
        child_see_alsos = (
            [block] if config.label_to_topic.relocate_inline_see_also_to_child else []
        )
        seeds.append(
            _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=parent_subsection,
                config=config,
                row_see_alsos=child_see_alsos,   # ← pass see_also to child
            )
        )
        if config.label_to_topic.relocate_inline_see_also_to_child:
            blocks_to_relocate_indices.append(i)   # ← mark for removal from parent
        emitted_in_block = True

    return seeds, blocks_to_relocate_indices   # ← return both
```

#### 1.3.2 `parse_subsections.py` — `_append_label_seed_children`

**Current code** calls `extract_label_topic_seeds` and takes its return value
directly as a list. Update to unpack the tuple, and then remove the relocated
blocks from `node.blocks`:

```python
def _append_label_seed_children(
    node: Subsection,
    keyword: str,
    config: JainkoshConfig,
    *,
    label_seed_candidates: Optional[list[str]] = None,
    row_relations: Optional[dict[str, list[Block]]] = None,
) -> None:
    seeds, relocate_indices = extract_label_topic_seeds(   # ← unpack tuple
        node.blocks,
        parent_subsection=node,
        keyword=keyword,
        config=config,
        label_seed_candidates=label_seed_candidates or [],
        row_relations=row_relations or {},
    )
    # Remove relocated see_also blocks from parent (reverse order to preserve indices)
    for idx in sorted(relocate_indices, reverse=True):
        node.blocks.pop(idx)
    # Append child seeds
    for seed in seeds:
        if all(c.natural_key != seed.natural_key for c in node.children):
            node.children.append(seed)
    if seeds:
        node.is_leaf = False
```

### 1.4 Golden changes — `द्रव्य.json`

After the fix:

1. **`keyword_parse_result.page_sections[0].subsections[1].children[0].blocks`**
   — the parent subsection for `topic_path="2.1"` ("एकांत पक्ष में..."):
   - The `see_also` block `{kind: "see_also", is_self: true, target_topic_path: "1.4", ...}`
     must be **removed** from this list.

2. **`keyword_parse_result.page_sections[0].subsections[1].children[0].children[0].blocks`**
   — the label_seed child (`source_subkind: "label_seed"`,
   `heading_text: "इसी प्रकार 'गुणपर्ययवद् द्रव्यं'..."`):
   - Must now contain the relocated `see_also` block:
     ```json
     {
       "kind": "see_also",
       "text_devanagari": null,
       "hindi_translation": null,
       "references": [],
       "is_orphan_translation": false,
       "is_bullet_point": false,
       "raw_html": null,
       "table_rows": null,
       "target_keyword": "द्रव्य",
       "target_topic_path": "1.4",
       "target_url": "#1.4",
       "is_self": true,
       "target_exists": true
     }
     ```

3. **`would_write.neo4j.edges`** — the `RELATED_TO` edge for this relation:
   - **Before** (wrong):
     ```json
     {
       "type": "RELATED_TO",
       "from": {
         "label": "Topic",
         "key": "द्रव्य:द्रव्य-निर्देश-व-शंका-समाधान:एकांत-पक-में-द्रव्य-का-लक्षण-संभव-नहीं"
       },
       "to": {
         "label": "Topic",
         "resolve_by": { "parent_keyword": "द्रव्य", "topic_path": "1.4" }
       },
       ...
     }
     ```
   - **After** (correct):
     ```json
     {
       "type": "RELATED_TO",
       "from": {
         "label": "Topic",
         "key": "द्रव्य:द्रव्य-निर्देश-व-शंका-समाधान:एकांत-पक्ष-में-द्रव्य-का-लक्षण-संभव-नहीं:इसी-प्रकार-'गुणपर्ययवद्-द्रव्यं'-या-'गुणसमुदायो-द्रव्यं'-भी-वे-नहीं-कह-सकते"
       },
       "to": {
         "label": "Topic",
         "resolve_by": { "parent_keyword": "द्रव्य", "topic_path": "1.4" }
       },
       "props": { "weight": 1.0, "source": "jainkosh" }
     }
     ```

4. Check all other `RELATED_TO` edges in द्रव्य — verify no other label_seed edges
   are affected. Specifically, check all subsections that have label_seed children
   and confirm their edges also move to the child key if they follow the same pattern.

5. Also check **`would_write.mongo.keyword_definitions.page_sections[0]`** and
   **`would_write.mongo.topic_extracts`** — the child label_seed topic_extract should
   now have the `see_also` block in its `blocks` array, and the parent topic_extract
   should have one fewer block.

### 1.5 Unit test

**`workers/ingestion/jainkosh/tests/unit/test_label_seed_relocation.py`** — new file
(or add to `test_index_relations.py`):

```python
"""Test that inline see_also blocks are relocated from parent to label_seed child."""

def test_inline_see_also_relocated_to_label_seed_child():
    """
    Given: a HindiText block with an inline देखें that creates a label_seed child,
    When: parse_subsections runs,
    Then: the parent subsection's blocks must NOT contain the see_also block,
          and the child label_seed's blocks MUST contain it.
    """
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
    from workers.ingestion.jainkosh.config import load_config

    html = """
    <html><body><div class="mw-parser-output">
    <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
    <li id="1"><span class="HindiText"><strong>अनुभव</strong></span></li>
    <p class="HindiText">
        यह लक्षण नहीं बनता (इसी प्रकार 'abc' भी वे नहीं कह सकते–देखें
        <a class="mw-selflink-fragment" href="#1.4">keyword - 1.4</a>)
        अनेकांतवादियों के मत में तो।
    </p>
    </div></body></html>
    """
    config = load_config()
    result = parse_keyword_html(html, "https://www.jainkosh.org/wiki/keyword", config)
    sec = result.page_sections[0]
    subsection = sec.subsections[0]  # topic_path="1"

    # Parent must have NO see_also in blocks
    parent_see_alsos = [b for b in subsection.blocks if b.kind == "see_also"]
    assert parent_see_alsos == [], "Parent must not hold the relocated see_also"

    # Child label_seed must have the see_also
    label_seeds = [c for c in subsection.children if c.label_topic_seed]
    assert len(label_seeds) == 1
    child_see_alsos = [b for b in label_seeds[0].blocks if b.kind == "see_also"]
    assert len(child_see_alsos) == 1
    assert child_see_alsos[0].target_topic_path == "1.4"
```

---

## Phase 2 — `inline_reference` field on `Reference` (Bug D2)

### 2.1 Background

`Reference` objects are emitted from two distinct positions:

- **Leading reference** (`inline_reference=False`): a `<p>` or bare
  `<span class="GRef">` that contains *only* GRef spans and appears *before*
  any Sanskrit/Prakrit/Hindi text block. Its refs are kept in a `pending_refs`
  buffer and attached to the *next* block.
- **Inline/trailing reference** (`inline_reference=True`): a `<span class="GRef">`
  embedded *inside* a text block (Sanskrit/Prakrit/Hindi `<p>` or `<span>`).
  Its refs are extracted by `extract_refs_from_node` within `make_block`.

The consumer needs to know which kind each reference is in order to render it
correctly (leading refs introduce a quotation; inline refs are footnotes).

### 2.2 Config change

**`config.py`** — add to `ReferenceConfig`:

```python
class ReferenceConfig(BaseModel):
    ...
    annotate_inline_position: bool = True   # ← NEW
```

**`parser_configs/jainkosh.yaml`** — under `reference:`:

```yaml
reference:
  ...
  annotate_inline_position: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside the
`"reference"` object's `"properties"`:

```json
"annotate_inline_position": { "type": "boolean" }
```

### 2.3 Model change

**`models.py`** — add `inline_reference` field to `Reference`:

```python
class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    raw_html: Optional[str] = None
    parsed: Optional["ParsedReference"] = None
    inline_reference: bool = False   # ← NEW: True = embedded in text; False = leading
```

`inline_reference=False` is the default, which is correct for leading refs
(they are the more common case in these pages).

### 2.4 Code changes

#### 2.4.1 `refs.py` — `extract_refs_from_node`

**Current signature**:
```python
def extract_refs_from_node(node: Node, config: JainkoshConfig) -> list[Reference]:
```

**Change**: Add `inline: bool = False` parameter. Pass it to each `Reference`
constructed inside the function when `config.reference.annotate_inline_position`
is `True`:

```python
def extract_refs_from_node(
    node: Node,
    config: JainkoshConfig,
    *,
    inline: bool = False,
) -> list[Reference]:
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
            raw = _clean_raw_html(gref.html or "", config) if len(parts) == 1 else None
            inline_ref_value = inline if config.reference.annotate_inline_position else False
            refs.append(Reference(
                text=part,
                raw_html=raw,
                parsed=parsed,
                inline_reference=inline_ref_value,   # ← NEW
            ))
    return refs
```

#### 2.4.2 `parse_blocks.py` — `make_block`

**Current call** (line ~71 in `make_block`):
```python
refs = extract_refs_from_node(node, config)
```

**Change**: Pass `inline=True` because this call extracts refs embedded *inside*
a text block (inline/trailing refs):

```python
refs = extract_refs_from_node(node, config, inline=True)   # ← inline=True
```

#### 2.4.3 `parse_blocks.py` — `parse_block_stream`

**Current call** in the leading-reference branch:
```python
if is_leading_reference_node(el, config):
    pending_refs.extend(extract_refs_from_node(el, config))
    continue
```

**Change**: Pass `inline=False` (explicitly; default is already `False`, but
make it explicit for clarity):

```python
if is_leading_reference_node(el, config):
    pending_refs.extend(extract_refs_from_node(el, config, inline=False))   # inline=False
    continue
```

#### 2.4.4 `parse_definitions.py` — leading refs

Search for any call to `extract_refs_from_node` inside
`parse_siddhantkosh_definitions` or `parse_puraankosh_definitions` that
processes leading reference nodes. Those should use `inline=False`. Any call
that processes inline content should use `inline=True`.

*Note: Check the actual code — if there are additional call sites in
`parse_definitions.py` or elsewhere, apply the same `inline=True/False`
distinction based on context.*

### 2.5 Golden changes — all three files

Every `Reference` object in the goldens gains `"inline_reference": true` or
`"inline_reference": false` depending on context.

**Rules for manual verification**:

1. Any `Reference` that was in `pending_refs` at the time it was attached →
   `inline_reference: false` (it was a leading ref).
2. Any `Reference` extracted by `extract_refs_from_node` inside `make_block`
   (i.e., `inline=True` call) → `inline_reference: true`.

**Practical verification**: run the parser on all three fixtures and compare
JSON diffs. The only field changing on `Reference` is the new
`inline_reference` boolean.

**Example from द्रव्य.json** — a leading ref becomes:
```json
{
  "text": "राजवार्तिक/1/33/1/95/6",
  "raw_html": "<span class=\"GRef\">राजवार्तिक/1/33/1/95/6</span>",
  "parsed": null,
  "inline_reference": false
}
```

An inline ref (e.g. `( धवला 1/1,1,1/84/1 )` embedded in HindiText) becomes:
```json
{
  "text": "धवला 1/1,1,1/84/1",
  "raw_html": "<span class=\"GRef\">( धवला 1/1,1,1/84/1 )</span>",
  "parsed": null,
  "inline_reference": true
}
```

### 2.6 Unit tests

**`workers/ingestion/jainkosh/tests/unit/test_refs.py`** — add two cases:

```python
def test_extract_refs_leading_sets_inline_false():
    """Leading refs (extracted from pending_refs buffer) have inline_reference=False."""
    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    from workers.ingestion.jainkosh.config import load_config
    from selectolax.parser import HTMLParser
    config = load_config()
    node = HTMLParser('<p><span class="GRef">सर्वार्थसिद्धि/1/5/17/5</span></p>').css_first("p")
    refs = extract_refs_from_node(node, config, inline=False)
    assert len(refs) == 1
    assert refs[0].inline_reference is False


def test_extract_refs_inline_sets_inline_true():
    """Inline/trailing refs (embedded in text blocks) have inline_reference=True."""
    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    from workers.ingestion.jainkosh.config import load_config
    from selectolax.parser import HTMLParser
    config = load_config()
    # Simulate a HindiText block with an embedded GRef
    node = HTMLParser(
        '<p class="HindiText">some text <span class="GRef">( धवला 1/1,1,1/84/1 )</span></p>'
    ).css_first("p")
    refs = extract_refs_from_node(node, config, inline=True)
    assert len(refs) == 1
    assert refs[0].inline_reference is True


def test_annotate_inline_position_false_always_returns_false():
    """When annotate_inline_position=False, inline_reference is always False."""
    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    from workers.ingestion.jainkosh.config import load_config
    from selectolax.parser import HTMLParser
    config = load_config()
    config.reference.annotate_inline_position = False
    node = HTMLParser('<p><span class="GRef">ref text</span></p>').css_first("p")
    refs = extract_refs_from_node(node, config, inline=True)
    assert refs[0].inline_reference is False
```

---

## Phase 3 — Fix duplicate `IndexRelation` and missing entry (Bug P1)

### 3.1 Background

The पर्याय HTML has a `<ul class="HindiText">` (not wrapped in `<li>`) containing
four entries separated by text nodes and `<br>`:

```
पर्याय  पर्यायी में कथंचित् भेदाभेद - देखें <a href="...द्रव्य#4">...</a>
। <br>
पर्यायों  को द्रव्यगुण... - देखें <a href="...उपचार#3">...</a>
। <br>
परिणमन  का अस्तित्व... - देखें <a href="...उत्पाद#3">उत्पाद - 3</a>  ← anchor A
। <br>
पर्याय  का कथंचित्... देखें <a href="...उत्पाद#3">उत्पाद - 3</a>   ← anchor B
। <br>
```

Anchor A and anchor B have **identical** `a.html` strings (same `href`, same
`title` attribute, same link text). In `_extract_label_before_anchor(a)`:

```python
idx = parent_html.find(a_html)  # always finds anchor A's position
```

For anchor B, this returns anchor A's position → label text extracted is
anchor A's label ("परिणमन...") rather than anchor B's ("पर्याय का कथंचित्...").
Result: two identical `IndexRelation` objects, and the "पर्याय का कथंचित्..." entry
is lost.

### 3.2 Config change

**`config.py`** — add a new nested config class and field to `IndexConfig`:

```python
class AnchorDedupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nth_occurrence_tracking: bool = True   # track nth-occurrence for identical anchors


class IndexConfig(BaseModel):
    ...
    anchor_dedup: AnchorDedupConfig = Field(default_factory=AnchorDedupConfig)
```

**`parser_configs/jainkosh.yaml`** — under `index:`:

```yaml
index:
  ...
  anchor_dedup:
    nth_occurrence_tracking: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — inside the
`"index"` object's `"properties"`:

```json
"anchor_dedup": {
  "type": "object",
  "properties": {
    "nth_occurrence_tracking": { "type": "boolean" }
  },
  "additionalProperties": false
}
```

### 3.3 Code changes

#### 3.3.1 `see_also.py` — `_extract_label_before_anchor` and `_preceding_inline_text`

**Change `_extract_label_before_anchor`**: add `nth_occurrence: int = 0` parameter.
Instead of `parent_html.find(a_html)`, use a loop to find the Nth occurrence:

```python
def _extract_label_before_anchor(a: Node, nth_occurrence: int = 0) -> str:
    """Extract the label text immediately before the देखें trigger in the parent element.

    nth_occurrence: 0-based index of this anchor among all anchors with the same HTML
    in the same parent. Used when two anchors have identical href and link text.
    """
    parent = a.parent
    if parent is None:
        return ""
    parent_html = parent.html or ""
    a_html = a.html or ""

    # Find the nth_occurrence-th match of a_html in parent_html
    idx = -1
    for _ in range(nth_occurrence + 1):
        new_idx = parent_html.find(a_html, idx + 1)
        if new_idx < 0:
            # Fewer occurrences than expected; fall back to first
            idx = parent_html.find(a_html)
            break
        idx = new_idx

    if idx < 0:
        return ""

    before_html = parent_html[:idx]
    # Split on the rightmost separator to isolate the current item's text
    best_pos = -1
    best_sep_len = 0
    for sep in ("</a>", "<br/>", "<br >", "<br>", "</li>"):
        pos = before_html.rfind(sep)
        if pos > best_pos:
            best_pos = pos
            best_sep_len = len(sep)
    if best_pos >= 0:
        before_html = before_html[best_pos + best_sep_len:]
    label = re.sub(r"<[^>]+>", "", before_html)
    label = re.sub(r"[(–\-।\s]*(?:विशेष\s+)?देखें\s*$", "", label).strip()
    return normalize_text(label)
```

**Change `_preceding_inline_text`**: add `nth_occurrence: int = 0` parameter.
Apply the same N-th occurrence logic for the innermost level (where `cur == a`):

```python
def _preceding_inline_text(a: Node, max_chars: int = 40, nth_occurrence: int = 0) -> str:
    """Walk up ancestors concatenating text before <a> until max_chars is reached.

    nth_occurrence: 0-based index of this anchor among all anchors with the same HTML
    in the same parent. Ensures we measure text before the correct occurrence.
    """
    pieces: list[str] = []
    cur = a
    is_first_level = True
    while cur.parent is not None and sum(len(p) for p in pieces) < max_chars:
        parent = cur.parent
        parent_html = parent.html or ""
        cur_html = cur.html or ""

        if is_first_level and nth_occurrence > 0:
            # Find the nth_occurrence-th occurrence instead of the first
            idx = -1
            for _ in range(nth_occurrence + 1):
                new_idx = parent_html.find(cur_html, idx + 1)
                if new_idx < 0:
                    idx = parent_html.find(cur_html)
                    break
                idx = new_idx
        else:
            idx = parent_html.find(cur_html) if cur_html else -1

        is_first_level = False

        if idx > 0:
            before = parent_html[:idx]
            pieces.append(re.sub(r"<[^>]+>", "", before))
        cur = parent

    text = "".join(reversed(pieces))
    return text[-max_chars:] if len(text) > max_chars else text
```

#### 3.3.2 `parse_index.py` — `parse_index_relations`

Track per-parent occurrence counts for each anchor's HTML. Pass `nth_occurrence`
to both `_preceding_inline_text` and `_extract_label_before_anchor`:

```python
def parse_index_relations(
    index_ols: list[Node],
    keyword: str,
    config: JainkoshConfig,
) -> list[IndexRelation]:
    """Full-DFS scan of index <ol> elements; emits one IndexRelation per देखें-anchored <a>."""
    out: list[IndexRelation] = []
    see_also_re = re.compile(config.index.see_also_text_pattern)
    nth_tracking = config.index.anchor_dedup.nth_occurrence_tracking

    # Track per-parent occurrence counts: (parent_html_prefix, a_html) → count
    anchor_occurrence_count: dict[tuple[str, str], int] = {}

    for outer_ol in index_ols:
        for a in outer_ol.css("a"):
            a_html = a.html or ""
            parent_html_prefix = (a.parent.html or "")[:100] if a.parent else ""
            count_key = (parent_html_prefix, a_html)

            nth = 0
            if nth_tracking:
                nth = anchor_occurrence_count.get(count_key, 0)
                anchor_occurrence_count[count_key] = nth + 1

            prev_text = _preceding_inline_text(
                a,
                config.index.see_also_window_chars,
                nth_occurrence=nth,
            )
            if not see_also_re.search(prev_text):
                continue
            parsed = parse_anchor(a, config, current_keyword=keyword)
            label = _extract_label_before_anchor(a, nth_occurrence=nth)
            source_path_chain = _ancestor_li_ids(a, config)
            rel = IndexRelation(
                label_text=label,
                source_topic_path_chain=source_path_chain,
                source_topic_natural_key_chain=[],
                **parsed,
            )
            _attach_heading_chain(rel, _ancestor_strong_chain(a, config))
            if config.index.top_level_reference_marking and not rel.source_topic_path_chain:
                rel.is_top_level_reference = True
            out.append(rel)

    return out
```

**Important**: `anchor_occurrence_count` must be reset per outer_ol if the same
`<a>` HTML could appear in two different `<ol>` elements that are unrelated.
Since the key includes the first 100 chars of the parent's HTML (which differs
per `<ul>` parent), this is already correct — anchors in different `<ul>` parents
produce different keys.

#### 3.3.3 `see_also.py` — `find_see_alsos_in_element` and `find_see_also_candidates_in_element`

These functions also call `_preceding_inline_text` and `_extract_label_before_anchor`.
Apply the same nth-occurrence tracking:

```python
def find_see_alsos_in_element(
    el: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
    source_topic_path: Optional[str] = None,
    as_index_relation: bool = False,
) -> list[Block | IndexRelation]:
    see_also_re = _build_see_also_re(config)
    nth_tracking = config.index.anchor_dedup.nth_occurrence_tracking
    anchor_occurrence_count: dict[tuple[str, str], int] = {}
    results = []

    for a in el.css("a"):
        a_html = a.html or ""
        parent_html_prefix = (a.parent.html or "")[:100] if a.parent else ""
        count_key = (parent_html_prefix, a_html)

        nth = 0
        if nth_tracking:
            nth = anchor_occurrence_count.get(count_key, 0)
            anchor_occurrence_count[count_key] = nth + 1

        prev_text = _preceding_inline_text(
            a,
            max_chars=config.index.see_also_window_chars,
            nth_occurrence=nth,
        )
        if not see_also_re.search(prev_text):
            continue

        parsed = parse_anchor(a, config, current_keyword=current_keyword)
        label_text = _extract_label_before_anchor(a, nth_occurrence=nth)

        if as_index_relation:
            results.append(IndexRelation(
                label_text=label_text,
                source_topic_path=source_topic_path,
                **parsed,
            ))
        else:
            results.append(Block(
                kind="see_also",
                **{k: v for k, v in parsed.items()},
            ))

    return results


def find_see_also_candidates_in_element(
    el: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[dict]:
    see_also_re = _build_see_also_re(config)
    nth_tracking = config.index.anchor_dedup.nth_occurrence_tracking
    anchor_occurrence_count: dict[tuple[str, str], int] = {}
    results: list[dict] = []

    for a in el.css("a"):
        a_html = a.html or ""
        parent_html_prefix = (a.parent.html or "")[:100] if a.parent else ""
        count_key = (parent_html_prefix, a_html)

        nth = 0
        if nth_tracking:
            nth = anchor_occurrence_count.get(count_key, 0)
            anchor_occurrence_count[count_key] = nth + 1

        prev_text = _preceding_inline_text(
            a,
            max_chars=config.index.see_also_window_chars,
            nth_occurrence=nth,
        )
        if not see_also_re.search(prev_text):
            continue
        parsed = parse_anchor(a, config, current_keyword=current_keyword)
        results.append({
            "label_text": _extract_label_before_anchor(a, nth_occurrence=nth),
            **parsed,
        })
    return results
```

### 3.4 Golden changes — `पर्याय.json`

**Before** (8 `index_relations`, entries 5 and 6 are duplicates, "पर्याय का
कथंचित्..." is missing):

```
index 5: परिणमन का अस्तित्व... → उत्पाद#3
index 6: परिणमन का अस्तित्व... → उत्पाद#3   ← duplicate
```

**After** (8 `index_relations`, no duplicates, all four entries from the `<ul>`
are present):

```
index 5: परिणमन का अस्तित्व... → उत्पाद#3
index 6: पर्याय का कथंचित् सत्पना या नित्यानित्यपना → उत्पाद#3   ← NEW (was missing)
```

The complete corrected entry at index 6 should be:

```json
{
  "label_text": "पर्याय का कथंचित् सत्पना या नित्यानित्यपना",
  "target_keyword": "उत्पाद",
  "target_topic_path": "3",
  "target_url": "/wiki/%E0%A4%89%E0%A4%A4%E0%A5%8D%E0%A4%AA%E0%A4%BE%E0%A4%A6#3",
  "is_self": false,
  "target_exists": true,
  "source_topic_path": "2",
  "source_topic_path_chain": ["2"],
  "source_topic_natural_key_chain": ["पर्याय:पर्याय-सामान्य-निर्देश"],
  "is_top_level_reference": false
}
```

*(The exact `source_topic_path_chain` and `source_topic_natural_key_chain` values
mirror those of the other entries in the same `<ul>`, since this anchor is in the
same `<ul>` under the section-2 heading.)*

Also verify that the `would_write.neo4j.edges` now has a `RELATED_TO` edge for
"पर्याय का कथंचित् सत्पना..." → `उत्पाद#3` (emitted via
`_build_index_relation_neo4j`).

### 3.5 Unit tests

**`workers/ingestion/jainkosh/tests/unit/test_index_relations.py`** — add:

```python
def test_duplicate_anchor_html_produces_distinct_labels():
    """
    Two <a> elements in the same parent with identical HTML (same href + text)
    must produce two distinct IndexRelations with different label_text values.
    """
    from workers.ingestion.jainkosh.parse_index import parse_index_relations
    from workers.ingestion.jainkosh.config import load_config
    from selectolax.parser import HTMLParser

    html = """
    <ol>
      <li class="HindiText">
        <strong><a href="#2">Section 2</a></strong>
        <ul class="HindiText">
          Entry A - देखें <a href="/wiki/X#3" title="X">X - 3</a>
          । <br>
          Entry B देखें <a href="/wiki/X#3" title="X">X - 3</a>
          。<br>
        </ul>
      </li>
    </ol>
    """
    tree = HTMLParser(html)
    outer_ol = tree.css_first("ol")
    config = load_config()
    config.index.anchor_dedup.nth_occurrence_tracking = True

    rels = parse_index_relations([outer_ol], "keyword", config)
    # Must have exactly 2 relations (not 1 or 3)
    assert len(rels) == 2
    labels = {r.label_text for r in rels}
    assert "Entry A" in labels, f"Expected 'Entry A' in {labels}"
    assert "Entry B" in labels, f"Expected 'Entry B' in {labels}"
    # Both target the same keyword/path
    for r in rels:
        assert r.target_keyword == "X"
        assert r.target_topic_path == "3"


def test_nth_occurrence_tracking_disabled_produces_duplicates():
    """
    With nth_occurrence_tracking=False (legacy), duplicate anchors produce
    duplicate labels. This test documents the pre-fix behaviour.
    """
    from workers.ingestion.jainkosh.parse_index import parse_index_relations
    from workers.ingestion.jainkosh.config import load_config
    from selectolax.parser import HTMLParser

    html = """
    <ol>
      <li class="HindiText">
        <strong><a href="#2">Section 2</a></strong>
        <ul class="HindiText">
          Entry A - देखें <a href="/wiki/X#3" title="X">X - 3</a>
          । <br>
          Entry B देखें <a href="/wiki/X#3" title="X">X - 3</a>
          。<br>
        </ul>
      </li>
    </ol>
    """
    tree = HTMLParser(html)
    outer_ol = tree.css_first("ol")
    config = load_config()
    config.index.anchor_dedup.nth_occurrence_tracking = False

    rels = parse_index_relations([outer_ol], "keyword", config)
    # Legacy: both produce same label → duplicate
    assert len(rels) == 2
    assert rels[0].label_text == rels[1].label_text  # both "Entry A" (buggy behaviour)
```

---

## Phase 4 — Version bump and golden regeneration

### 4.1 Version bump

**`parser_configs/jainkosh.yaml`** — update both version fields:

```yaml
version: "1.6.0"
parser_rules_version: "jainkosh.rules/1.6.0"
```

**`parsing_rules.md`** — append to the changelog table:

```markdown
| `1.6.0` | fix-spec-006: label_seed `RELATED_TO` edges now emitted from child's natural_key via see_also relocation to child blocks (§5.6, §6.13); `inline_reference` flag on `Reference` distinguishes leading from inline refs (§6.3); nth-occurrence anchor tracking fixes duplicate `IndexRelation` and missing entry when two `<a>` elements share identical HTML (§4.5). See `parser_fix_spec_006/README.md`. |
```

**`parser_spec.md`** — update the version reference in the "Fixes applied" list:

```markdown
> **Fixes applied in v1.6.0**: see
> [`parser_fix_spec_006/README.md`](./parser_fix_spec_006/README.md)
> for the full phased correction spec (label_seed RELATED_TO edge from child
> natural_key; inline_reference on Reference; nth-occurrence anchor dedup).
```

### 4.2 Golden regeneration

Run the CLI on each fixture with `--frozen-time 2026-05-04T00:00:00Z`:

```bash
python -m workers.ingestion.jainkosh.cli parse \
  workers/ingestion/jainkosh/tests/fixtures/आत्मा.html \
  --out workers/ingestion/jainkosh/tests/golden/आत्मा.json \
  --frozen-time 2026-05-04T00:00:00Z

python -m workers.ingestion.jainkosh.cli parse \
  workers/ingestion/jainkosh/tests/fixtures/द्रव्य.html \
  --out workers/ingestion/jainkosh/tests/golden/द्रव्य.json \
  --frozen-time 2026-05-04T00:00:00Z

python -m workers.ingestion.jainkosh.cli parse \
  workers/ingestion/jainkosh/tests/fixtures/पर्याय.html \
  --out workers/ingestion/jainkosh/tests/golden/पर्याय.json \
  --frozen-time 2026-05-04T00:00:00Z
```

**After** regeneration, manually verify the following invariants:

| Check | File | Expected |
|-------|------|---------|
| `parser_version` | all 3 | `"jainkosh.rules/1.6.0"` |
| label_seed see_also not in parent | द्रव्य | `subsections[1].children[0].blocks` has no `see_also` kind |
| label_seed see_also in child | द्रव्य | `subsections[1].children[0].children[0].blocks` has one `see_also` with `target_topic_path="1.4"` |
| RELATED_TO edge from child | द्रव्य | RELATED_TO `from.key` ends with `इसी-प्रकार-...` (child nk) |
| No RELATED_TO from parent for this relation | द्रव्य | No RELATED_TO `from.key` = `...एकांत-पक्ष-में-द्रव्य-का-लक्षण-संभव-नहीं` (without child suffix) for target `1.4` |
| All refs have `inline_reference` | all 3 | Every `Reference` object has `"inline_reference": true` or `false` |
| Leading refs are `false` | all 3 | Refs that were in `pending_refs` buffer → `false` |
| Inline refs are `true` | all 3 | Refs inside HindiText/SanskritText blocks → `true` |
| पर्याय index_relations[6] correct | पर्याय | `label_text` = "पर्याय का कथंचित् सत्पना या नित्यानित्यपना", `target_keyword` = "उत्पाद", `target_topic_path` = "3" |
| No duplicate in पर्याय | पर्याय | No two `index_relations` with the same `label_text` + `target_keyword` + `target_topic_path` |

### 4.3 Update golden test timestamps

**`workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py`** — if the
frozen timestamp is hardcoded, update it to `"2026-05-04T00:00:00Z"`.

---

## Implementation order (for a lower-reasoning model)

Implement phases strictly in order. Run the golden test after each phase to
verify no regression before proceeding.

1. **Phase 1 first**: config + code changes in `config.py`, `parse_subsections.py`.
   Verify द्रव्य golden shape (see_also in child, not parent; edge from child key).

2. **Phase 2 second**: config + model + code changes in `config.py`, `models.py`,
   `refs.py`, `parse_blocks.py`. Verify all three goldens gain `inline_reference`.
   Run `test_refs.py` unit tests.

3. **Phase 3 third**: config + code changes in `config.py`, `see_also.py`,
   `parse_index.py`. Verify पर्याय golden has correct entry 6 and no duplicate.
   Run `test_index_relations.py` unit tests.

4. **Phase 4 last**: bump version in YAML, regenerate all three goldens, update
   golden test frozen-time if needed, update `parsing_rules.md` and `parser_spec.md`.

**Do not skip the unit test additions** — they lock in the fixed behaviour and
prevent regressions in future specs.

---

## Appendix: Key HTML evidence

### D1 — label_seed HTML (द्रव्य L989–996)

```html
<span class="HindiText">
  एकांत अभेद वादियों ... 'द्रव्यं भव्ये' यह लक्षण भी नहीं बनता (इसी
  प्रकार 'गुणपर्ययवद् द्रव्यं' या 'गुणसमुदायो द्रव्यं' भी वे नहीं कह सकते–देखें
  <a class="mw-selflink-fragment" href="#1.4">द्रव्य - 1.4</a>
  ) अनेकांतवादियों के मत में तो ...
</span>
```

The `देखें` is inside `(…)` but the label "इसी प्रकार 'गुणपर्ययवद् द्रव्यं' या
'गुणसमुदायो द्रव्यं' भी वे नहीं कह सकते" is what seeds the child label_seed topic.

### P1 — duplicate anchor HTML (पर्याय L460–463)

```html
<ul class="HindiText">
  ...
  परिणमन  का अस्तित्व ... - देखें
  <a href="/wiki/%E0%A4%89%E0%A4%A4%E0%A5%8D%E0%A4%AA%E0%A4%BE%E0%A4%A6#3"
     title="उत्पाद">उत्पाद - 3</a>
  । <br>
  पर्याय  का कथंचित् सत्पना या नित्यानित्यपना। देखें
  <a href="/wiki/%E0%A4%89%E0%A4%A4%E0%A5%8D%E0%A4%AA%E0%A4%BE%E0%A4%A6#3"
     title="उत्पाद">उत्पाद - 3</a>
  । <br>
</ul>
```

Both `<a>` elements produce the same HTML string; only their preceding text differs.
