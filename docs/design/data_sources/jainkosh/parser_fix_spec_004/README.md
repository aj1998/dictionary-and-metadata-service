# JainKosh Parser — Fix Spec 004 (द्रव्य.html post-golden cleanup)

Addresses six classes of bugs found after analysing
`workers/ingestion/jainkosh/tests/golden/द्रव्य.json` and the source fixture
`workers/ingestion/jainkosh/tests/fixtures/द्रव्य.html`.

**Parser version bump**: `1.3.0` → `1.4.0` (bump both `version` and
`parser_rules_version` in `parser_configs/jainkosh.yaml` after all phases pass).

---

## Scope

- Parser output shape and semantics.
- `would_write.mongo` and `would_write.neo4j` corrections driven by parser output.
- Golden updates for all three fixtures (`आत्मा`, `द्रव्य`, `पर्याय`).

Out of scope: orchestrator, DB writes, schema migrations.

---

## Root-cause summary

| # | Symptom | Root cause |
|---|---------|-----------|
| 1A | `source_topic_path_chain=["4.2"]` for "नित्यानियत्व" (should be `["4","4.3"]`) | `_topic_path_from_li_heading_anchor` returns `None` for `<li>` whose `<strong>` has plain text (no `<a>` anchor); falls back to previous LI which has "4.2" |
| 1B | `source_topic_path_chain=[]` for "संसारी जीव…मूर्तत्व" and three others (should be `["3"]`) | `_nearest_previous_heading_path_in_same_list` exhausts siblings and never climbs to the enclosing top-level `<li>` whose `<strong><a href="#3">` would give path "3" |
| 1C | `source_topic_path_chain=["4"]` for "द्रव्य को गुण पर्याय…" (should be `["4","4.4"]`) | Same enclosing-LI gap but nested one level deeper (4.4's `<ul>` inside 4.4's `<li>`) |
| 2 | `blocks=[]` for topic 4.1.1 "एकांत अद्वैतपक्ष का निरास" | V2 heading span (`<span id="4.1.1" class="HindiText">`) holds content **inside** the same span after `<strong>`; DFS calls `continue` after the heading event and never processes that inline content |
| 3 | Single `hindi_text` block contains text from two logical paragraphs with misattributed references | When a `<p class="HindiText">` has inline `<span class="GRef">` interleaved with prose, all text and all refs are collapsed into one block; references lose their positional anchor in the prose |
| 4 | `index_relations` appear verbatim in `would_write.mongo`; no topic entities are created from them | `build_mongo_fragment` serialises raw `index_relations`; no path exists in `envelope.py` to promote them to Postgres topics, Mongo topic_extracts, or Neo4j nodes/edges |

---

## Files changed

| File | Phases |
|------|--------|
| `workers/ingestion/jainkosh/parse_index.py` | 1 |
| `workers/ingestion/jainkosh/parse_subsections.py` | 2 |
| `workers/ingestion/jainkosh/parse_blocks.py` | 3 |
| `workers/ingestion/jainkosh/envelope.py` | 4 |
| `workers/ingestion/jainkosh/config.py` | 1, 2, 3, 4 |
| `workers/ingestion/jainkosh/topic_keys.py` | 4 (new export) |
| `parser_configs/jainkosh.yaml` | 1, 2, 3, 4 |
| `parser_configs/_schemas/jainkosh.schema.json` | 1, 2, 3, 4 |
| `workers/ingestion/jainkosh/tests/unit/test_index_source_chain.py` | 1 |
| `workers/ingestion/jainkosh/tests/unit/test_heading_variants.py` | 2 |
| `workers/ingestion/jainkosh/tests/unit/test_reference_splitting.py` | 3 (new) |
| `workers/ingestion/jainkosh/tests/unit/test_envelope_index_relation_topics.py` | 4 (new) |
| `workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py` | 5 |
| `workers/ingestion/jainkosh/tests/golden/द्रव्य.json` | all |
| `workers/ingestion/jainkosh/tests/golden/आत्मा.json` | 3, 4 (regression check) |
| `workers/ingestion/jainkosh/tests/golden/पर्याय.json` | 4 (regression check) |
| `docs/design/jainkosh/parsing_rules.md` | sync §4.6, §6.3, new §6.8 |

---

## Phase 1 — Source-chain resolution fixes

### 1.1 Background: how source chains are built

`parse_index_relations` (in `parse_index.py`) finds every `देखें`-anchored `<a>` in the
index `<ol>`. For each anchor it calls:

- `_ancestor_li_ids(a, config)` → `source_topic_path_chain`
- `_ancestor_strong_chain(a, config)` → heading-text chain stored via
  `_attach_heading_chain`

Then `_resolve_index_relation_natural_keys` (in `parse_keyword.py`) merges both into the
final `source_topic_path_chain` + `source_topic_natural_key_chain`.

The two helper functions share a structural pattern: walk up ancestors collecting IDs /
heading texts, then call a "previous-heading" function for the immediate context.

### 1.2 Sub-fix 1A — inner-OL fallback for plain-`<strong>` headings

**Affected function**: `_topic_path_from_li_heading_anchor` (line 188 of `parse_index.py`)

**Current logic**: looks for a `<strong>` direct child of `<li>` that contains an `<a
href="#N">` anchor; returns `None` otherwise.

**Problem instances**:
- `<li>` for 4.3 ("काल या पर्याय…") has `<strong>plain text</strong>` → returns `None`
  → previous-sibling fallback finds 4.2's `<li>` (which DOES have `<a href="#4.2">`) →
  wrong path 4.2.
- `<li>` for 4.4 and for section 5 ("द्रव्य की स्वतंत्रता") have the same pattern.

**Fix**: When `<strong>` has no `<a>` anchor, scan the `<li>`'s direct `<ol>` children for
the first `<a href="#N.M">` and derive the parent path by removing the last dot-segment.

**New logic** — add after the existing `for child in li.iter(...)` loop body (after all
`<strong>` children are exhausted):

```python
# Fallback: derive path from first anchor in an inner <ol>
if config.index.source_chain.li_path_from_inner_ol_fallback:
    for child in li.iter(include_text=False):
        if child.tag != "ol":
            continue
        if child.parent is not None and child.parent != li:
            continue  # only direct <ol> children of this <li>
        for inner_li in child.iter(include_text=False):
            if inner_li.tag != "li":
                continue
            if inner_li.parent is not None and inner_li.parent != child:
                continue  # only direct <li> of the inner <ol>
            a = inner_li.css_first("a[href^='#']")
            if a:
                href = (a.attributes or {}).get("href") or ""
                if href.startswith("#"):
                    path = href[1:].strip()
                    parts = path.split(".")
                    if len(parts) > 1:
                        return ".".join(parts[:-1])
        break  # only check the first <ol>
return None
```

**Config key**: `index.source_chain.li_path_from_inner_ol_fallback: bool` (default `true`).

### 1.3 Sub-fix 1B — enclosing-`<li>` fallback in `_nearest_previous_heading_path_in_same_list`

**Affected function**: `_nearest_previous_heading_path_in_same_list` (line 153)

**Problem**: When `container` (the `<ul>` holding the row) is a direct child of a
section-level `<li>` (e.g. LI[2] = "षट् द्रव्य विभाजन") and all `container.prev`
siblings yield no path, the function returns `None`. The enclosing LI's own
`<strong><a href="#3">` would give path "3".

**Fix**: After the `while prev is not None` loop over `container.prev`, add:

```python
# Climb to enclosing <li> if container is inside one
if config.index.source_chain.enclosing_li_fallback:
    enclosing_li = container.parent if container is not None else None
    if enclosing_li is not None and enclosing_li.tag == "li":
        path = _topic_path_from_li_heading_anchor(enclosing_li, config)
        if path:
            return path
```

**This fixes these relations** (all in LI[2] "षट् द्रव्य विभाजन"):
- संसारी जीव का कथंचित् मूर्तत्व → `["3"]`
- द्रव्यों के भेदादि जानने का प्रयोजन → `["3"]`
- जीव का असर्वगतपना → `["3"]`
- कारण अकारण विभाग → `["3"]`

**And also** the 4.4-level relations (enclosing LI = 4.4's `<li>`, which after Fix 1A
will return "4.4" via the inner-OL fallback):
- द्रव्य को गुण पर्याय… → `["4","4.4"]`
- अनेक अपेक्षाओं से द्रव्य में भेदाभेद… → `["4","4.4"]`
- द्रव्य में परस्पर षट्कारकी भेद व अभेद → `["4","4.4"]`

**Config key**: `index.source_chain.enclosing_li_fallback: bool` (default `true`).

### 1.4 Sub-fix 1C — enclosing-`<li>` fallback in `_nearest_previous_heading_in_same_list`

**Affected function**: `_nearest_previous_heading_in_same_list` (line 117)

Same structural gap as 1B but for the heading-text chain used by
`_ancestor_strong_chain`. The function must also try the enclosing LI's heading text
when `container.prev` is exhausted.

**Fix**: After the `while prev is not None` loop over `container.prev`, add:

```python
if config.index.source_chain.enclosing_li_fallback:
    enclosing_li = container.parent if container is not None else None
    if enclosing_li is not None and enclosing_li.tag == "li":
        heading = _li_inline_heading_text(enclosing_li, config)
        if heading:
            return heading
```

### 1.5 Config changes

**`config.py` — `IndexSourceChainConfig`**: add two fields:

```python
class IndexSourceChainConfig(BaseModel):
    ...
    enclosing_li_fallback: bool = True          # new
    li_path_from_inner_ol_fallback: bool = True # new
```

**`parser_configs/jainkosh.yaml`**:

```yaml
index:
  source_chain:
    enabled: true
    li_strong_selector: "strong"
    li_strong_a_selector: "strong > a"
    skip_li_with_footer_id: true
    match_normalize: "nfc_collapsed_ws"
    enclosing_li_fallback: true              # NEW
    li_path_from_inner_ol_fallback: true     # NEW
```

**`parser_configs/_schemas/jainkosh.schema.json`** — update `source_chain` object:

```json
"enclosing_li_fallback": { "type": "boolean" },
"li_path_from_inner_ol_fallback": { "type": "boolean" }
```

### 1.6 Failing tests (write before code changes)

File: `workers/ingestion/jainkosh/tests/unit/test_index_source_chain.py`

**Existing test that must change** — `test_unresolvable_label_falls_back_to_keyword` was
asserting `source_topic_path_chain == []`. Replace with the corrected expectation:

```python
def test_link_wrapped_heading_li_resolves_source_path():
    """षट् द्रव्य विभाजन index LI has <strong><a href="#3">; relations under
    its <ul> must resolve to source_topic_path_chain=["3"]."""
    res = _result()
    rels = res.page_sections[0].index_relations
    for label in [
        "संसारी जीव का कथंचित् मूर्तत्व",
        "द्रव्यों के भेदादि जानने का प्रयोजन",
        "जीव का असर्वगतपना",
        "कारण अकारण विभाग",
    ]:
        rel = _by_label(rels, label)
        assert rel.source_topic_path_chain == ["3"], f"failed for {label}"
        assert rel.source_topic_natural_key_chain == ["द्रव्य:षट्द्रव्य-विभाजन"], \
            f"failed for {label}"
```

```python
def test_plain_strong_heading_derives_path_from_inner_ol():
    """4.3 and 4.4 LIs have plain-text <strong> (no anchor); path must be
    derived from their inner <ol>'s first anchor and cross-checked."""
    res = _result()
    rels = res.page_sections[0].index_relations

    rel_nitya = _by_label(rels, "द्रव्य में कथंचित् नित्यानियत्व")
    assert rel_nitya.source_topic_path_chain == ["4", "4.3"]

    rel_guna = _by_label(rels, "द्रव्य को गुण पर्याय और गुण पर्याय को द्रव्य रूप से लक्षित करना")
    assert rel_guna.source_topic_path_chain == ["4", "4.4"]

    rel_anek = _by_label(rels, "अनेक अपेक्षाओं से द्रव्य में भेदाभेद व विधि-निषेध")
    assert rel_anek.source_topic_path_chain == ["4", "4.4"]
```

**Existing test that must remain green**: `test_nested_index_relation_resolves_full_chain`
for "परमाणु में कथंचित् सावयव निरवयवपना" → `["4","4.2"]` (already correct, must not
regress).

### 1.7 Expected golden delta for `द्रव्य.json`

In `keyword_parse_result.page_sections[0].index_relations`:

| label | old `source_topic_path_chain` | new |
|-------|------------------------------|-----|
| संसारी जीव का कथंचित् मूर्तत्व | `[]` | `["3"]` |
| द्रव्यों के भेदादि जानने का प्रयोजन | `[]` | `["3"]` |
| जीव का असर्वगतपना | `[]` | `["3"]` |
| कारण अकारण विभाग | `[]` | `["3"]` |
| द्रव्य में कथंचित् नित्यानियत्व | `["4","4.2"]` | `["4","4.3"]` |
| द्रव्य को गुण पर्याय… | `["4"]` | `["4","4.4"]` |
| अनेक अपेक्षाओं से द्रव्य में भेदाभेद… | `["4"]` | `["4","4.4"]` |
| द्रव्य में परस्पर षट्कारकी भेद व अभेद | `["4"]` | `["4","4.4"]` |

`source_topic_path` (scalar) is set automatically by the model validator
(`_legacy_source_topic_path`) as `chain[-1]`; the regenerated golden will show
the correct value after code changes.

`source_topic_natural_key_chain` will also update because
`_resolve_index_relation_natural_keys` maps each corrected path to a natural key.

---

## Phase 2 — V2 heading inline content extraction

### 2.1 Root cause

`walk_and_collect_headings` in `parse_subsections.py` DFS detects a V2 heading:

```
<span class="HindiText" id="4.1.1">
    <strong>एकांत अद्वैतपक्ष का निरास</strong>
    <br>
    जगत् में एक ब्रह्म के अतिरिक्त … <span class="GRef">आप्तमीमांसा/26</span>
    दूसरी बात … <span class="GRef">आप्तमीमांसा/27</span>
    ।
</span>
```

After emitting `("heading", span)`, the DFS calls `continue` and moves to the next
sibling. The content (prose + GRefs) inside the span is **never processed**.

This only affects V2 headings where the HTML author placed body text inside the heading
span rather than as subsequent siblings.

### 2.2 Fix — `_dfs_after_v2_heading` and a synthetic content block

**New function** in `parse_subsections.py` (place after `_dfs_after_v3_heading`):

```python
def _make_v2_content_block(span: Node, config: JainkoshConfig) -> Optional[Node]:
    """
    Create a synthetic <p class="HindiText"> from the content inside a V2 heading span,
    stripping the leading <strong> heading element.

    Returns None if no meaningful content remains.
    """
    from selectolax.parser import HTMLParser
    import re

    html = span.html or ""
    # Extract inner HTML
    start = html.find(">")
    end = html.rfind("<")
    if start < 0 or end <= start:
        return None
    inner = html[start + 1:end]

    # Remove the leading <strong>...</strong> (only the first occurrence)
    inner = re.sub(r"^\s*<strong[^>]*>.*?</strong>\s*", "", inner, count=1, flags=re.DOTALL)

    # Strip leading <br> / whitespace
    inner = re.sub(r"^\s*(<br\s*/?>)?\s*", "", inner)

    if not re.sub(r"<[^>]+>", "", inner).strip():
        return None

    # Find the CSS class for "hindi_text" kind (reverse-lookup from block_classes)
    css_class = next(
        (cls for cls, kind in config.block_classes.items() if kind == "hindi_text"),
        "HindiText",
    )
    synthetic_html = f'<p class="{css_class}">{inner}</p>'
    tree = HTMLParser(synthetic_html)
    return tree.css_first(f"p.{css_class}")
```

**Update `_dfs`** inside `walk_and_collect_headings` (after the existing V3 branch):

```python
if match is not None:
    events.append(("heading", el))
    if el.tag == "li":
        _dfs_after_v3_heading(el)
    elif el.tag == "span" and config.dfs.process_v2_inline_content:
        # NEW: extract inline content from V2 heading spans
        synthetic = _make_v2_content_block(el, config)
        if synthetic is not None:
            events.append(("block", synthetic))
    continue
```

### 2.3 Config changes

**`config.py` — `DfsConfig`**: add one field:

```python
class DfsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passthrough_leading_gref: bool = True
    process_v2_inline_content: bool = True  # NEW
```

**`parser_configs/jainkosh.yaml`**:

```yaml
dfs:
  passthrough_leading_gref: true
  process_v2_inline_content: true   # NEW
```

**`parser_configs/_schemas/jainkosh.schema.json`** — update `dfs` object:

```json
"process_v2_inline_content": { "type": "boolean" }
```

### 2.4 Failing tests (write before code changes)

File: `workers/ingestion/jainkosh/tests/unit/test_heading_variants.py`

```python
def test_v2_heading_inline_content_is_captured():
    """Topic 4.1.1 is a V2 heading whose body content lives inside the heading span.
    After the fix it must have non-empty blocks."""
    from pathlib import Path
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    fixture = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
    html = fixture.read_text(encoding="utf-8")
    cfg = load_config()
    res = parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)

    section = res.page_sections[0]

    def find_by_path(subs, path):
        for s in subs:
            if s.topic_path == path:
                return s
            found = find_by_path(s.children, path)
            if found:
                return found
        return None

    sub_411 = find_by_path(section.subsections, "4.1.1")
    assert sub_411 is not None, "topic 4.1.1 not found"
    assert len(sub_411.blocks) > 0, "4.1.1 must have blocks"
    assert sub_411.blocks[0].kind == "hindi_text"
    assert "ब्रह्माद्वैत" in (sub_411.blocks[0].text_devanagari or "")
```

Note: after Phase 3 (reference splitting) is also applied, 4.1.1 will have **two** blocks
(split at the first inline GRef). The test above only checks `len > 0` and the first block
kind, so it remains valid after Phase 3.

### 2.5 Expected golden delta for `द्रव्य.json`

In `keyword_parse_result.page_sections[0].subsections` (nested at path 4 → 4.1 → 4.1.1):

Before:
```json
{
  "topic_path": "4.1.1",
  "heading_text": "एकांत अद्वैतपक्ष का निरास",
  ...
  "blocks": []
}
```

After (before Phase 3 also runs; see Phase 3 for final shape):
```json
{
  "topic_path": "4.1.1",
  "heading_text": "एकांत अद्वैतपक्ष का निरास",
  ...
  "blocks": [
    {
      "kind": "hindi_text",
      "text_devanagari": "जगत् में एक ब्रह्म के अतिरिक्त … प्रकार के द्वैतों का सर्वथा अभाव ठहरे।",
      "references": [{ "text": "आप्तमीमांसा/26", ... }],
      ...
    },
    {
      "kind": "hindi_text",
      "text_devanagari": "दूसरी बात यह भी तो है … अद्वैत की प्रतिपत्ति कैसे होगी।",
      "references": [{ "text": "आप्तमीमांसा/27", ... }],
      ...
    }
  ]
}
```

(Two blocks because Phase 3 splits at the inline GRef between the two prose passages.)

---

## Phase 3 — Reference splitting at inline GRefs

### 3.1 Root cause

`make_block` in `parse_blocks.py` calls:

1. `_render_inline(node, config)` — strips all tags and collapses text; loses GRef
   positions.
2. `extract_refs_from_node(node, config)` — collects **all** `<span class="GRef">` from
   the node regardless of position.

When a `<p class="HindiText">` looks like:

```
TEXT_A
<span class="GRef">REF_1</span>
TEXT_B
<span class="GRef">REF_2</span>
<span class="GRef">REF_3</span>
```

all text and all refs end up in one `Block`, losing the fact that `REF_1` terminates `TEXT_A`
and `REF_2 + REF_3` terminate `TEXT_B`.

### 3.2 Fix — `split_element_at_inline_refs`

**New function** in `parse_blocks.py` (place before `flatten_for_blocks`):

```python
import re as _re

def _split_at_inline_grefs(inner_html: str, gref_selector: str = 'span.GRef') -> list[str]:
    """
    Tokenise inner_html into text + GRef tokens.
    Start a new segment whenever non-trivial text follows accumulated GRefs.
    Returns a list of HTML strings (one per output block).
    """
    # Match <span class="GRef"...>...</span>  (non-nested, which is the standard pattern)
    gref_re = _re.compile(
        r'<span\b[^>]*\bclass=["\']GRef["\'][^>]*>.*?</span>',
        _re.DOTALL,
    )

    tokens: list[tuple[str, str]] = []  # ("text"|"gref", html_fragment)
    pos = 0
    for m in gref_re.finditer(inner_html):
        if m.start() > pos:
            tokens.append(("text", inner_html[pos:m.start()]))
        tokens.append(("gref", m.group(0)))
        pos = m.end()
    if pos < len(inner_html):
        tokens.append(("text", inner_html[pos:]))

    segments: list[str] = []
    current_html = ""
    pending_grefs: list[str] = []

    for kind, fragment in tokens:
        if kind == "text":
            # Strip tags to detect meaningful prose
            prose = _re.sub(r"<[^>]+>", "", fragment).strip()
            if prose and pending_grefs:
                # Meaningful prose follows pending GRefs → close current segment
                segments.append(current_html + "".join(pending_grefs))
                current_html = fragment
                pending_grefs = []
            else:
                current_html += fragment
        else:  # gref
            pending_grefs.append(fragment)

    # Final segment
    current_html += "".join(pending_grefs)
    if _re.sub(r"<[^>]+>", "", current_html).strip():
        segments.append(current_html)

    return segments


def split_element_at_inline_refs(
    el: Node,
    config: "JainkoshConfig",
) -> list[Node]:
    """
    If `el` is a text-block element of an applicable kind and has inline GRefs
    with prose after them, split into multiple synthetic nodes.
    Returns [el] unchanged when no split is needed or the feature is disabled.
    """
    from selectolax.parser import HTMLParser

    if not config.reference_splitting.enabled:
        return [el]

    kind = block_class_kind(el, config)
    if kind not in config.reference_splitting.applicable_block_kinds:
        return [el]

    # Get inner HTML
    html = el.html or ""
    start = html.find(">")
    end = html.rfind("<")
    if start < 0 or end <= start:
        return [el]
    inner = html[start + 1:end]

    segments = _split_at_inline_grefs(inner, config.reference_splitting.gref_selector)
    if len(segments) <= 1:
        return [el]

    # Build synthetic nodes
    # Find tag + class for this block kind
    tag = el.tag or "p"
    cls = (el.attributes or {}).get("class", "HindiText")

    result: list[Node] = []
    for seg_html in segments:
        synthetic = f'<{tag} class="{cls}">{seg_html}</{tag}>'
        tree = HTMLParser(synthetic)
        node = tree.css_first(f"{tag}.{cls.split()[0]}")
        if node is not None:
            result.append(node)
    return result if result else [el]
```

**Update `flatten_for_blocks`** (line 334 of `parse_blocks.py`):

```python
def flatten_for_blocks(
    elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[Node]:
    """Flatten nested spans into a sequential list of blocks."""
    if not config.nested_span.flatten:
        result = elements
    else:
        result = []
        for el in elements:
            kind = block_class_kind(el, config)
            if kind in config.nested_span.outer_kinds and has_nested_block(el, config):
                result.extend(_explode_nested_span(el, config))
            else:
                result.append(el)

    # NEW: split at inline GRefs when text follows a reference
    if config.reference_splitting.enabled:
        split_result: list[Node] = []
        for el in result:
            split_result.extend(split_element_at_inline_refs(el, config))
        return split_result

    return result
```

### 3.3 Config changes

**`config.py`** — new class and field:

```python
class ReferenceSplittingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    applicable_block_kinds: list[str] = Field(
        default_factory=lambda: [
            "hindi_text", "sanskrit_text", "prakrit_text", "hindi_gatha"
        ]
    )
    gref_selector: str = "span.GRef"


class JainkoshConfig(BaseModel):
    ...
    reference_splitting: ReferenceSplittingConfig = Field(
        default_factory=ReferenceSplittingConfig
    )
```

**`parser_configs/jainkosh.yaml`** — add after `ref_strip`:

```yaml
reference_splitting:
  enabled: true
  applicable_block_kinds:
    - hindi_text
    - sanskrit_text
    - prakrit_text
    - hindi_gatha
  gref_selector: "span.GRef"
```

**`parser_configs/_schemas/jainkosh.schema.json`** — add new top-level property:

```json
"reference_splitting": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "enabled": { "type": "boolean" },
    "applicable_block_kinds": { "type": "array", "items": { "type": "string" } },
    "gref_selector": { "type": "string" }
  }
}
```

### 3.4 Failing tests (write before code changes)

New file: `workers/ingestion/jainkosh/tests/unit/test_reference_splitting.py`

```python
"""Tests for reference splitting at inline GRefs."""
from selectolax.parser import HTMLParser

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import split_element_at_inline_refs


def _cfg():
    return load_config()


def test_no_split_when_refs_only_trail():
    """If all GRefs come after the prose (no text after any GRef), no split occurs."""
    html = (
        '<p class="HindiText">यह एक वाक्य है।'
        '<span class="GRef">ग्रंथ 1.2</span>'
        '<span class="GRef">ग्रंथ 3.4</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1, "trailing GRefs must not cause a split"


def test_split_when_text_follows_gref():
    """Prose → GRef → more prose produces two blocks."""
    html = (
        '<p class="HindiText">'
        'यह पहला वाक्य है।'
        '<span class="GRef">हरिवंशपुराण - 1.1</span>'
        'यह दूसरा वाक्य है।'
        '<span class="GRef">महापुराण 3.5</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 2

    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    refs0 = extract_refs_from_node(result[0], cfg)
    refs1 = extract_refs_from_node(result[1], cfg)
    assert len(refs0) == 1
    assert "हरिवंशपुराण" in refs0[0].text
    assert len(refs1) == 1
    assert "महापुराण" in refs1[0].text


def test_split_multiple_trailing_grefs_stay_in_last_block():
    """GRef1 splits; GRef2 and GRef3 both trail the second segment."""
    html = (
        '<p class="HindiText">'
        'पहला।'
        '<span class="GRef">REF_A</span>'
        'दूसरा।'
        '<span class="GRef">REF_B</span>'
        '<span class="GRef">REF_C</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 2
    from workers.ingestion.jainkosh.refs import extract_refs_from_node
    refs1 = extract_refs_from_node(result[1], cfg)
    ref_texts = [r.text for r in refs1]
    assert "REF_B" in ref_texts
    assert "REF_C" in ref_texts


def test_split_disabled_returns_original():
    """When reference_splitting.enabled=false no split occurs."""
    html = (
        '<p class="HindiText">'
        'पहला।<span class="GRef">REF_A</span>दूसरा।<span class="GRef">REF_B</span>'
        '</p>'
    )
    tree = HTMLParser(html)
    el = tree.css_first("p.HindiText")
    cfg = _cfg()
    # Temporarily disable
    cfg.reference_splitting.enabled = False
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1


def test_split_only_for_applicable_kinds():
    """kind=table or see_also blocks are not split."""
    # A table element will have kind=None, so split_element returns [el] unchanged
    html = '<p class="SomeUnknownClass">TEXT<span class="GRef">REF</span>MORE</p>'
    tree = HTMLParser(html)
    el = tree.css_first("p.SomeUnknownClass")
    cfg = _cfg()
    result = split_element_at_inline_refs(el, cfg)
    assert len(result) == 1


def test_puranakosh_block_from_dravya_fixture_splits():
    """
    Integration: the large PuranKosh block in द्रव्य.html that currently produces
    a single hindi_text block must produce two blocks after the fix.
    """
    from pathlib import Path
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    fixture = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
    html = fixture.read_text(encoding="utf-8")
    cfg = load_config()
    res = parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)

    # Find the puraankosh section
    puraankosh_sec = next(
        (s for s in res.page_sections if s.section_kind == "puraankosh"), None
    )
    assert puraankosh_sec is not None

    # The definition that contains हरिवंशपुराण must NOT have महापुराण in the same block
    hariv_block = None
    mahap_block = None
    for defn in puraankosh_sec.definitions:
        for b in defn.blocks:
            if b.references:
                ref_texts = [r.text for r in b.references]
                if any("हरिवंशपुराण" in t for t in ref_texts):
                    hariv_block = b
                if any("महापुराण" in t for t in ref_texts):
                    mahap_block = b

    assert hariv_block is not None, "block with हरिवंशपुराण not found"
    assert mahap_block is not None, "block with महापुराण not found"
    # They must be different block objects (different segments)
    assert hariv_block is not mahap_block, (
        "हरिवंशपुराण and महापुराण must be in separate blocks"
    )
    # हरिवंशपुराण block must not include महापुराण text
    assert "महापुराण" not in (hariv_block.text_devanagari or "")
    # महापुराण block text must not start with the first sentence
    assert "आठ अनुयोग" not in (mahap_block.text_devanagari or "")
```

### 3.5 Expected golden delta for `द्रव्य.json`

**PuranKosh definition block** (currently one `hindi_text` block with all three refs):

Before:
```json
{
  "kind": "hindi_text",
  "text_devanagari": "यह सत्, संध्या, ... से ज्ञेय होता है।\nजीव, पुद्गल, ... ये सब स्वतंत्र हैं।",
  "references": [
    { "text": "हरिवंशपुराण - 1.1\n , 2.108, 17.135", ... },
    { "text": "महापुराण 3.5-9", ... },
    { "text": "वीरवर्द्धमान चरित्र 16.137-138", ... }
  ]
}
```

After (two separate blocks):
```json
{
  "kind": "hindi_text",
  "text_devanagari": "यह सत्, संध्या, ... से ज्ञेय होता है।",
  "references": [
    { "text": "हरिवंशपुराण - 1.1\n , 2.108, 17.135", ... }
  ],
  ...
},
{
  "kind": "hindi_text",
  "text_devanagari": "जीव, पुद्गल, ... ये सब स्वतंत्र हैं।",
  "references": [
    { "text": "महापुराण 3.5-9", ... },
    { "text": "वीरवर्द्धमान चरित्र 16.137-138", ... }
  ],
  ...
}
```

**Topic 4.1.1** (combined effect of Phase 2 + Phase 3): the synthetic V2 block will
also be split at its inline GRef into two `hindi_text` blocks. See Phase 2 § 2.5 for
the expected shape.

**Globally**: any topic or definition block that previously contained mid-text GRefs
will be split. Review all three goldens carefully after regeneration (see Phase 5).

---

## Phase 4 — Index relations materialised as topics

### 4.1 Target behaviour

Currently `build_mongo_fragment` includes:

```python
"index_relations": [r.model_dump() for r in s.index_relations],
```

This dumps raw relation objects into the Mongo keyword_definitions document and no
topics/nodes/edges are emitted.

**After this phase**:

1. `index_relations` key is **absent** from `would_write.mongo.keyword_definitions[*].page_sections[*]`.

2. For each `IndexRelation` in every `PageSection`:
   - A new **Topic** is created:
     - `natural_key = <parent_nk>:<slug(label_text)>` where `parent_nk = source_topic_natural_key_chain[-1]`
       or `keyword` if the chain is empty.
     - `topic_path = None` (no numeric path from the index)
     - `is_synthetic = True`, `label_topic_seed = True`
     - `source_subkind = "index_relation_seed"`
     - `is_leaf = True`
     - `parent_topic_natural_key = source_topic_natural_key_chain[-1]` or `None`
   - Added to `would_write.postgres.topics`
   - Added to `would_write.mongo.topic_extracts` with `blocks = []`
   - Neo4j **Topic node** added to `would_write.neo4j.nodes`
   - Neo4j **structural edge** added:
     - If `parent_topic_natural_key` is not None → `PART_OF` (from label-topic to parent-topic)
     - If `parent_topic_natural_key` is None → `HAS_TOPIC` (from keyword to label-topic)
   - Neo4j **`RELATED_TO` edge** from the label-topic to the relation's existing target (keyword or topic),
     using the same logic as the existing `_index_relation_edge` helper. The existing
     `_index_relation_edge` calls in `build_neo4j_fragment` are **replaced** by this new path.

### 4.2 Natural-key computation

**Add to `topic_keys.py`** (or inline in `envelope.py`):

```python
def index_relation_natural_key(label_text: str, parent_nk: str, config) -> str:
    """Compute natural_key for an index-relation-derived topic."""
    from .topic_keys import slug as _slug
    sl = _slug(label_text, config)
    return f"{parent_nk}:{sl}"
```

The `slug()` function is already in `topic_keys.py`. Use it directly.

### 4.3 New helpers in `envelope.py`

Add the following private helpers. Insert before `build_envelope`.

```python
def _index_relation_topic_natural_key(
    rel: IndexRelation, keyword: str, config: JainkoshConfig
) -> str:
    from .topic_keys import slug as _slug
    sl = _slug(rel.label_text, config)
    parent_nk = (
        rel.source_topic_natural_key_chain[-1]
        if rel.source_topic_natural_key_chain
        else keyword
    )
    return f"{parent_nk}:{sl}"


def _index_relation_parent_nk(rel: IndexRelation, keyword: str) -> Optional[str]:
    if rel.source_topic_natural_key_chain:
        return rel.source_topic_natural_key_chain[-1]
    return None  # parent is the keyword itself


def _build_index_relation_pg_rows(
    result: KeywordParseResult, config: JainkoshConfig
) -> list[dict]:
    if not config.envelope.index_relations_as_topics.enabled:
        return []
    rows = []
    seen: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk in seen:
                continue
            seen.add(nk)
            parent_nk = _index_relation_parent_nk(rel, result.keyword)
            rows.append({
                "table": "topics",
                "natural_key": nk,
                "topic_path": None,
                "parent_topic_natural_key": parent_nk,
                "display_text": [{"lang": "hin", "script": "Deva", "text": rel.label_text}],
                "source": "jainkosh",
                "parent_keyword_natural_key": result.keyword,
                "is_leaf": True,
                "is_synthetic": True,
                "source_subkind": "index_relation_seed",
                "label_topic_seed": True,
            })
    return rows


def _build_index_relation_mongo_extracts(
    result: KeywordParseResult, config: JainkoshConfig
) -> list[dict]:
    if not config.envelope.index_relations_as_topics.enabled:
        return []
    extracts = []
    seen: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk in seen:
                continue
            seen.add(nk)
            parent_nk = _index_relation_parent_nk(rel, result.keyword)
            extracts.append({
                "collection": "topic_extracts",
                "natural_key": nk,
                "topic_path": None,
                "parent_natural_key": parent_nk,
                "is_leaf": True,
                "heading": [{"lang": "hin", "script": "Deva", "text": rel.label_text}],
                "blocks": [],
                "source": "jainkosh",
                "source_url": result.source_url,
            })
    return extracts


def _build_index_relation_neo4j(
    result: KeywordParseResult, config: JainkoshConfig
) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) for index-relation topics."""
    if not config.envelope.index_relations_as_topics.enabled:
        return [], []
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nk: set[str] = set()
    for sec in result.page_sections:
        for rel in sec.index_relations:
            nk = _index_relation_topic_natural_key(rel, result.keyword, config)
            if nk not in seen_nk:
                seen_nk.add(nk)
                nodes.append({
                    "label": "Topic",
                    "key": nk,
                    "props": {
                        "display_text_hi": rel.label_text,
                        "topic_path": None,
                        "parent_keyword_natural_key": result.keyword,
                        "source": "jainkosh",
                        "is_leaf": True,
                    },
                })
                parent_nk = _index_relation_parent_nk(rel, result.keyword)
                if parent_nk is not None:
                    edges.append({
                        "type": "PART_OF",
                        "from": {"label": "Topic", "key": nk},
                        "to": {"label": "Topic", "key": parent_nk},
                        "props": {"weight": 1.0, "source": "jainkosh"},
                    })
                else:
                    edges.append({
                        "type": "HAS_TOPIC",
                        "from": {"label": "Keyword", "key": result.keyword},
                        "to": {"label": "Topic", "key": nk},
                        "props": {"weight": 1.0, "source": "jainkosh"},
                    })

            # RELATED_TO edge from label-topic to target (reusing existing helper)
            edge = _index_relation_edge(rel, ("Topic", nk), keyword=result.keyword, config=config)
            if edge:
                edges.append(edge)

    return nodes, edges
```

### 4.4 Update `build_pg_fragment`

In the existing function (line 109 of `envelope.py`), append index-relation topic rows:

```python
def build_pg_fragment(result: KeywordParseResult, config: Optional[JainkoshConfig] = None) -> dict:
    if config is None:
        config = load_config()
    ...
    # existing logic
    pg = {"keywords": [keyword_row], "topics": topic_rows, "keyword_aliases": []}

    # NEW: add index-relation topics
    if config.envelope.index_relations_as_topics.enabled:
        pg["topics"].extend(_build_index_relation_pg_rows(result, config))

    return pg
```

**Important**: `build_pg_fragment` currently does not accept `config`. Add `config:
Optional[JainkoshConfig] = None` parameter and add a `load_config()` fallback. Update
the call in `build_envelope` accordingly.

### 4.5 Update `build_mongo_fragment`

```python
def build_mongo_fragment(result: KeywordParseResult, config: Optional[JainkoshConfig] = None) -> dict:
    if config is None:
        config = load_config()
    kdef = {
        ...
        "page_sections": [
            {
                "section_index": s.section_index,
                "section_kind": s.section_kind,
                "h2_text": s.h2_text,
                "definitions": [d.model_dump() for d in s.definitions],
                "label_topic_seeds": [t.model_dump() for t in s.label_topic_seeds],
                "extra_blocks": [b.model_dump() for b in s.extra_blocks],
                # REMOVED: "index_relations": [r.model_dump() for r in s.index_relations],
            }
            for s in result.page_sections
        ],
        ...
    }
    topic_extracts = [...]  # existing

    # NEW
    topic_extracts.extend(_build_index_relation_mongo_extracts(result, config))

    return {"keyword_definitions": [kdef], "topic_extracts": topic_extracts}
```

### 4.6 Update `build_neo4j_fragment`

```python
def build_neo4j_fragment(result: KeywordParseResult, config: JainkoshConfig) -> dict:
    nodes = [...]  # existing keyword node
    edges = []

    # ... existing subsection loop ...

    # REPLACE old "Index relations" block (lines 323-332) with:
    ir_nodes, ir_edges = _build_index_relation_neo4j(result, config)
    nodes.extend(ir_nodes)
    edges.extend(ir_edges)

    return {"nodes": _dedupe(nodes), "edges": _dedupe(edges)}
```

The old block that called `_index_relation_edge` with the last-chain-entry as source is
**deleted**. `_build_index_relation_neo4j` handles that logic correctly.

### 4.7 Config changes

**`config.py`** — new classes:

```python
class IndexRelationsAsTopicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True


class EnvelopeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_mode: Literal["per_row", "envelope_root"] = "envelope_root"
    index_relations_as_topics: IndexRelationsAsTopicsConfig = Field(
        default_factory=IndexRelationsAsTopicsConfig
    )  # NEW
```

**`parser_configs/jainkosh.yaml`**:

```yaml
envelope:
  idempotency_mode: "envelope_root"
  index_relations_as_topics:       # NEW
    enabled: true
```

**`parser_configs/_schemas/jainkosh.schema.json`** — update `envelope` object:

```json
"envelope": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "idempotency_mode": { "type": "string", "enum": ["per_row", "envelope_root"] },
    "index_relations_as_topics": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "enabled": { "type": "boolean" }
      }
    }
  }
}
```

### 4.8 Update `_DEFAULT_CONTRACTS` and `_build_contracts` in `envelope.py`

Add a new contract for `postgres:topics:index_relation_seed`:

```python
_DEFAULT_CONTRACTS: dict[str, dict] = {
    ...
    "postgres:topics:index_relation_seed": {
        "conflict_key": ["natural_key"],
        "on_conflict": "do_update",
        "fields_replace": [
            "display_text", "is_leaf", "is_synthetic",
            "parent_topic_natural_key", "topic_path",
            "source", "source_subkind",
        ],
        "fields_append": [],
        "fields_skip_if_set": [],
        "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
    },
    ...
}
```

Update `_build_contracts`:

```python
def _has_index_relation_topic(result: KeywordParseResult) -> bool:
    for sec in result.page_sections:
        if sec.index_relations:
            return True
    return False


def _build_contracts(result: KeywordParseResult) -> dict[str, dict]:
    keys = { ... }  # existing keys
    if _has_label_seed_topic(result):
        keys.add("postgres:topics:label_seed")
    if _has_index_relation_topic(result):              # NEW
        keys.add("postgres:topics:index_relation_seed")
    return {k: deepcopy(_DEFAULT_CONTRACTS[k]) for k in sorted(keys)}
```

### 4.9 Failing tests (write before code changes)

New file: `workers/ingestion/jainkosh/tests/unit/test_envelope_index_relation_topics.py`

```python
"""Tests: index relations are materialised as topics in the would_write envelope."""
from pathlib import Path
from datetime import datetime

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope


_DRAVYA = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"
_URL = "https://www.jainkosh.org/wiki/%E0%A4%A6%E0%A5%8D%E0%A4%B0%E0%A4%B5%E0%A5%8D%E0%A4%AF"
_FROZEN = datetime(2026, 5, 2)


def _envelope():
    cfg = load_config()
    html = _DRAVYA.read_text(encoding="utf-8")
    result = parse_keyword_html(html, _URL, cfg, frozen_time=_FROZEN)
    return build_envelope(result, cfg)


def test_index_relations_absent_from_mongo_page_sections():
    env = _envelope()
    kdef_list = env.would_write["mongo"]["keyword_definitions"]
    assert kdef_list, "keyword_definitions must be present"
    for page_sec in kdef_list[0]["page_sections"]:
        assert "index_relations" not in page_sec, (
            "index_relations must not appear in would_write.mongo page_sections"
        )


def test_index_relation_topics_in_postgres():
    env = _envelope()
    topic_rows = env.would_write["postgres"]["topics"]
    nks = {r["natural_key"] for r in topic_rows}

    # "द्रव्य का लक्षण 'अर्थक्रियाकारित्व'" is under topic "द्रव्य:द्रव्य-के-भेद-व-लक्षण"
    # its nk = "द्रव्य:द्रव्य-के-भेद-व-लक्षण:<slug(label)>"
    matching = [r for r in topic_rows if "अर्थक्रियाकारित्व" in r["natural_key"]]
    assert matching, "index-relation topic for अर्थक्रियाकारित्व must exist in postgres topics"
    row = matching[0]
    assert row["is_synthetic"] is True
    assert row["label_topic_seed"] is True
    assert row["source_subkind"] == "index_relation_seed"
    assert row["topic_path"] is None


def test_index_relation_topics_in_mongo_topic_extracts():
    env = _envelope()
    extracts = env.would_write["mongo"]["topic_extracts"]
    nks = {e["natural_key"] for e in extracts}
    matching = [e for e in extracts if "अर्थक्रियाकारित्व" in e["natural_key"]]
    assert matching, "mongo topic_extract for अर्थक्रियाकारित्व must exist"
    ext = matching[0]
    assert ext["blocks"] == []


def test_index_relation_topics_in_neo4j_nodes():
    env = _envelope()
    nodes = env.would_write["neo4j"]["nodes"]
    topic_nks = {n["key"] for n in nodes if n.get("label") == "Topic"}
    matching = [k for k in topic_nks if "अर्थक्रियाकारित्व" in k]
    assert matching, "neo4j Topic node for अर्थक्रियाकारित्व must exist"


def test_index_relation_related_to_edge_from_label_topic():
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    # "द्रव्य का लक्षण 'अर्थक्रियाकारित्व'" targets keyword "वस्तु"
    related_to_edges = [e for e in edges if e.get("type") == "RELATED_TO"]
    label_topic_to_vastu = [
        e for e in related_to_edges
        if "अर्थक्रियाकारित्व" in e.get("from", {}).get("key", "")
        and e.get("to", {}).get("key") == "वस्तु"
    ]
    assert label_topic_to_vastu, (
        "RELATED_TO edge from label-topic for अर्थक्रियाकारित्व to keyword वस्तु must exist"
    )


def test_index_relation_part_of_edge_to_parent_topic():
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    part_of_edges = [e for e in edges if e.get("type") == "PART_OF"]
    # अर्थक्रियाकारित्व topic is PART_OF "द्रव्य:द्रव्य-के-भेद-व-लक्षण"
    matching = [
        e for e in part_of_edges
        if "अर्थक्रियाकारित्व" in e.get("from", {}).get("key", "")
        and "द्रव्य-के-भेद-व-लक्षण" in e.get("to", {}).get("key", "")
    ]
    assert matching, "PART_OF edge from label-topic to parent topic must exist"


def test_no_old_index_relation_edge_from_parent_topic():
    """The old code emitted RELATED_TO from the parent topic (chain[-1]).
    After the fix, no RELATED_TO should come from the parent directly for index relations."""
    env = _envelope()
    edges = env.would_write["neo4j"]["edges"]
    # Old behaviour: RELATED_TO from "द्रव्य:द्रव्य-के-भेद-व-लक्षण" to "वस्तु"
    old_style = [
        e for e in edges
        if e.get("type") == "RELATED_TO"
        and e.get("from", {}).get("key") == "द्रव्य:द्रव्य-के-भेद-व-लक्षण"
        and e.get("to", {}).get("key") == "वस्तु"
    ]
    assert not old_style, (
        "RELATED_TO must NOT be emitted from the parent topic directly; "
        "it must come from the label-topic node"
    )


def test_idempotency_contract_includes_index_relation_seed():
    env = _envelope()
    contracts = env.would_write.get("idempotency_contracts", {})
    assert "postgres:topics:index_relation_seed" in contracts
```

### 4.10 Expected golden delta for `द्रव्य.json`

1. **`would_write.mongo.keyword_definitions[0].page_sections[*]`**: each section object
   loses the `index_relations` key entirely.

2. **`would_write.postgres.topics`**: gains `N` new rows (one per unique `IndexRelation`
   label across all sections), each with `is_synthetic=true`, `label_topic_seed=true`,
   `source_subkind="index_relation_seed"`, `topic_path=null`.

3. **`would_write.mongo.topic_extracts`**: gains corresponding entries with `blocks=[]`.

4. **`would_write.neo4j.nodes`**: gains `N` new Topic nodes.

5. **`would_write.neo4j.edges`**: gains `N` `PART_OF` (or `HAS_TOPIC`) edges plus
   `N` `RELATED_TO` edges (from label-topic to target). Old `RELATED_TO` edges from
   the parent-topic directly are **removed**.

6. **`would_write.idempotency_contracts`**: gains
   `"postgres:topics:index_relation_seed"` entry.

---

## Phase 5 — Golden regeneration and review

### 5.1 Test run order

```bash
# Unit tests first (all four phases)
pytest -x workers/ingestion/jainkosh/tests/unit/

# Then golden test (expected to fail until goldens are regenerated)
pytest -x workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py
```

### 5.2 Regenerate candidates

```bash
for f in आत्मा द्रव्य पर्याय; do
  python -m workers.ingestion.jainkosh.cli parse \
    workers/ingestion/jainkosh/tests/fixtures/$f.html \
    --out workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
    --frozen-time 2026-05-02T00:00:00Z
done
```

### 5.3 Review diffs

```bash
for f in आत्मा द्रव्य पर्याय; do
  echo "=== $f ==="
  diff workers/ingestion/jainkosh/tests/golden/$f.json \
       workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
    | head -120
done
```

**Expected meaningful changes in `द्रव्य.json`** (confirm all of these before accepting):

- `index_relations[*].source_topic_path_chain` corrections (Phase 1).
- `source_topic_path` scalar now equals `chain[-1]` on all relations.
- `source_topic_natural_key_chain` updated to match new path chains.
- Topic 4.1.1 `blocks` is now non-empty (Phase 2).
- PuranKosh definition block split into two `hindi_text` blocks with correct ref attribution (Phase 3).
- V2 inline content in any other topics that were previously empty gains blocks (Phase 2+3).
- `would_write.mongo.keyword_definitions[*].page_sections[*]` no longer has `index_relations` (Phase 4).
- `would_write.postgres.topics` and `would_write.mongo.topic_extracts` contain index-relation topics (Phase 4).
- `would_write.neo4j` contains new Topic nodes + PART_OF/HAS_TOPIC + RELATED_TO edges from label-topics (Phase 4).

**`आत्मा.json`** — check for reference-splitting changes in any PuranKosh blocks that had
inline GRefs; check Phase-4 index-relation-topic changes. Fix-spec-003 changes must
remain intact.

**`पर्याय.json`** — check for reference-splitting changes; check Phase-4 changes.

### 5.4 Accept and lock goldens

```bash
for f in आत्मा द्रव्य पर्याय; do
  mv workers/ingestion/jainkosh/tests/golden/$f.candidate.json \
     workers/ingestion/jainkosh/tests/golden/$f.json
done
pytest workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py
```

---

## Guardrails / non-regression checklist

1. `test_nested_index_relation_resolves_full_chain` ("परमाणु में कथंचित् सावयव
   निरवयवपना" → `["4","4.2"]`) must remain green — it was already correct and must
   not be disturbed by the inner-OL fallback.
2. `test_top_level_index_relation_resolves_to_strong_heading` ("द्रव्य का लक्षण
   'अर्थक्रियाकारित्व'" → `["1"]`) must remain green.
3. Reference splitting must not affect `see_also` blocks, tables, or `sanskrit_gatha`.
4. Translation-marker (`=`) absorption must still work after reference splitting.
5. V2 heading content that is empty (only `<strong>` + `<br>`) must not produce empty
   blocks (the `_make_v2_content_block` function must return `None` in that case).
6. Label-seed subsection assignment (spec 003) must remain intact; reference splitting
   of a block does not affect label-seed extraction from subsection content elements.
7. Existing `RELATED_TO` edges from `see_also` blocks inside subsections are unaffected.
8. `देखें` trigger detection in `_is_row_style_element` is unaffected by splitting.

---

## Suggested commit sequence

1. `test: failing tests for source-chain enclosing-LI and inner-OL fallbacks`
2. `parser(index): enclosing-LI and inner-OL fallbacks for source-chain resolution`
3. `test: failing test for V2 heading inline content`
4. `parser(subsections): extract inline content from V2 heading spans`
5. `test: failing tests for reference splitting at inline GRefs`
6. `parser(blocks): split text blocks at inline GRef boundaries`
7. `test: failing tests for index-relation materialisation as topics`
8. `envelope: materialise index relations as topics; remove from mongo page_sections`
9. `tests: regenerate approved goldens (v1.4.0)`
10. `docs: sync parsing_rules.md §4.6, §6.3, new §6.8`

---

## Documentation sync (`docs/design/jainkosh/parsing_rules.md`)

After all phases pass, update:

- **§4.6**: Add note that `_nearest_previous_heading_path_in_same_list` now climbs to
  the enclosing LI when siblings are exhausted
  (`index.source_chain.enclosing_li_fallback`), and that paths can be derived from a
  LI's inner `<ol>` anchors when `<strong>` has no anchor
  (`index.source_chain.li_path_from_inner_ol_fallback`).

- **§6.3** (References): Add a new sub-section: when a text block element contains
  inline GRef spans interleaved with prose (not just trailing), the parser splits the
  element into multiple blocks at each split point (`reference_splitting.enabled`). Each
  block gets the references that immediately follow its text.

- **New §6.8 — Index-relation topics**: Each `IndexRelation` is materialised as a
  `Topic` entity (`is_synthetic=true`, `label_topic_seed=true`,
  `source_subkind="index_relation_seed"`). Its `natural_key` is
  `source_topic_natural_key_chain[-1]:<slug(label_text)>`, or
  `<keyword>:<slug(label_text)>` when the chain is empty. Enabled via
  `envelope.index_relations_as_topics.enabled`. The relation's target edge (`RELATED_TO`)
  is emitted from this label-topic node, not from the parent topic.

---

## Definition of Done

- All new and updated unit tests pass.
- All three golden tests pass with approved updated goldens.
- `द्रव्य.json` satisfies every reported issue:
  - `source_topic_path_chain` correct for all 26 index relations.
  - Topic 4.1.1 has non-empty `blocks`.
  - PuranKosh definition block split into two blocks with correct ref attribution.
  - `would_write.mongo` page_sections have no `index_relations` key.
  - Index-relation label-topics present in postgres, mongo, neo4j.
  - `RELATED_TO` edges emitted from label-topic nodes, not parent topics.
- No regressions in `आत्मा.json` or `पर्याय.json`.
