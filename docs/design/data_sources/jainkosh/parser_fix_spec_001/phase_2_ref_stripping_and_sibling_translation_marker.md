# Phase 2 — Reference stripping & sibling-`=` translation marker

> **Goal A**: Inline `<span class="GRef">…</span>` text must not appear
> inside `text_devanagari` of any block. Refs live exclusively in
> `references[]`.
>
> **Goal B**: When a `<span class="HindiText">` is the next sibling of
> a source-language block (`SanskritText`/`PrakritGatha`/…) **and the
> intervening sibling text contains only `=`**, the HindiText is the
> translation of that source block. This is the द्रव्य L724–759 case.
>
> **Goal C**: Stable reference ordering when a block has both a
> leading reference and trailing/inline references — leading first,
> then inline in document order.

---

## 1. Failing tests (write first)

### 1.1 `tests/unit/test_refs.py` — extend

```python
def test_inline_gref_stripped_from_text_devanagari():
    html = ('<p class="HindiText">उन-उन सद्भाव पर्यायों को... '
            '<span class="GRef">( राजवार्तिक/1/33/1/95/4 )</span>।</p>')
    block = parse_p_to_block(html, CFG)
    assert block.kind == "hindi_text"
    assert "राजवार्तिक" not in block.text_devanagari
    assert block.text_devanagari.rstrip("। ").endswith("प्राप्त होता है")
    assert any(r.text == "( राजवार्तिक/1/33/1/95/4 )" for r in block.references)


def test_inline_gref_brackets_collapsed():
    """The bracket pair surrounding the inline GRef is also removed
    when it would leave an orphan '( )' in prose."""
    html = ('<p class="HindiText">… द्रव्य कहते हैं। '
            '<span class="GRef">( राजवार्तिक/1/33 )</span> ।</p>')
    block = parse_p_to_block(html, CFG)
    # Trailing punctuation collapsed: should not have stray '( )'
    assert "( )" not in block.text_devanagari
    assert "  " not in block.text_devanagari   # no double spaces
```

### 1.2 `tests/unit/test_translation_marker.py` — extend

```python
def test_sibling_eq_translation_marker():
    """=  between sibling spans inside a parent (e.g. <li>) should
    pair the HindiText sibling as hindi_translation of the preceding
    source-language sibling."""
    html = """
    <li>
      <span class="GRef">पंचास्तिकाय/9</span>
      <span class="PrakritGatha">दवियदि गच्छदि …।9।</span>
      =
      <span class="HindiText">उन-उन सद्भाव पर्यायों को …।</span>
    </li>
    """
    blocks = parse_li_to_blocks(html, CFG)
    src = next(b for b in blocks if b.kind == "prakrit_gatha")
    assert src.text_devanagari.startswith("दवियदि")
    assert src.hindi_translation is not None
    assert src.hindi_translation.startswith("उन-उन")
    # No standalone hindi_text block was emitted
    assert not any(b.kind == "hindi_text" for b in blocks)


def test_sibling_eq_with_inline_gref_in_translation():
    """Inline GRef inside the HindiText sibling becomes a reference
    on the merged source block (after the leading reference)."""
    html = """
    <li>
      <span class="GRef">पंचास्तिकाय/9</span>
      <span class="PrakritGatha">दवियदि गच्छदि …।9।</span>
      =
      <span class="HindiText">उन-उन सद्भाव …।
        <span class="GRef">( राजवार्तिक/1/33/1/95/4 )</span>।
      </span>
    </li>
    """
    blocks = parse_li_to_blocks(html, CFG)
    src = next(b for b in blocks if b.kind == "prakrit_gatha")
    assert [r.text for r in src.references] == [
        "पंचास्तिकाय/9",
        "( राजवार्तिक/1/33/1/95/4 )",
    ]
    # No GRef text in hindi_translation
    assert "राजवार्तिक" not in src.hindi_translation


def test_eq_inside_hindi_text_still_works():
    """The existing leading-= case still works."""
    html = '<p class="HindiText">= द्रव्य का लक्षण।</p>'
    block = parse_p_to_block_with_prev_source(html, CFG)
    assert block.hindi_translation is not None
```

---

## 2. YAML / config changes

### 2.1 `parser_configs/jainkosh.yaml`

Add a new top-level block:

```yaml
ref_strip:
  enabled: true
  # When stripping a GRef from text, also collapse:
  collapse_double_spaces: true
  collapse_orphan_parens: true   # "( )" -> ""  and  "()" -> ""
  collapse_orphan_brackets: true # "[ ]" -> ""
  # Trailing-punct cleanup applied after the strip pass:
  trim_trailing_chars: " ।॥;,"

translation_marker:
  prefix: "="                    # already exists
  source_kinds: ["sanskrit_text", "sanskrit_gatha", "prakrit_text", "prakrit_gatha"]
  hindi_kinds:   ["hindi_text", "hindi_gatha"]
  # NEW — phase 2
  sibling_marker_enabled: true
  sibling_marker_text_node_re: '^\s*=\s*$'
  # When sibling-marker fires, the merged source block's references
  # are ordered as [leading, ...inline].
  reference_ordering: "leading_then_inline"
```

### 2.2 `workers/ingestion/jainkosh/config.py`

```python
class RefStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    collapse_double_spaces: bool = True
    collapse_orphan_parens: bool = True
    collapse_orphan_brackets: bool = True
    trim_trailing_chars: str = " ।॥;,"

class TranslationMarkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str = "="
    source_kinds: list[str]
    hindi_kinds: list[str]
    sibling_marker_enabled: bool = True
    sibling_marker_text_node_re: str = r'^\s*=\s*$'
    reference_ordering: Literal["leading_then_inline", "document_order"] = "leading_then_inline"

class JainkoshConfig(BaseModel):
    ...
    ref_strip: RefStripConfig = Field(default_factory=RefStripConfig)
    translation_marker: TranslationMarkerConfig
```

---

## 3. Code changes

### 3.1 `refs.py` — add `strip_refs_from_text`

```python
def strip_refs_from_text(text: str, refs: list[Reference], config: JainkoshConfig) -> str:
    """Remove every ref's literal text occurrence from the input text,
    then collapse orphan brackets/parens and double whitespace per config.
    Idempotent: stripping a ref that doesn't exist is a no-op."""
    if not config.ref_strip.enabled:
        return text
    out = text
    for r in refs:
        if not r.text:
            continue
        out = out.replace(r.text, " ")
    if config.ref_strip.collapse_orphan_parens:
        out = re.sub(r"\(\s*\)", "", out)
    if config.ref_strip.collapse_orphan_brackets:
        out = re.sub(r"\[\s*\]", "", out)
    if config.ref_strip.collapse_double_spaces:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\s*\n\s*", "\n", out)
    out = re.sub(r"^[" + re.escape(config.ref_strip.trim_trailing_chars) + r"]+", "", out)
    out = re.sub(r"[ \t]+([।॥;,])", r"\1", out)   # no space before danda
    return out.strip()
```

### 3.2 `parse_blocks.py` — apply ref-strip in `make_block`

After collecting `refs` (existing code), but before constructing the
`Block`:

```python
text = strip_refs_from_text(text, refs, config)
```

This applies to ALL block kinds that have `text_devanagari`
(sanskrit_text/_gatha, prakrit_text/_gatha, hindi_text/_gatha).

### 3.3 Sibling-`=` translation marker in `flatten_for_blocks` / `parse_block_stream`

The current `_emit` only fires when `block.text_devanagari` itself
**starts** with `=`. The fix detects `=` as a **standalone sibling
text-node** between two element siblings, and consumes it.

#### 3.3.1 New helper `_collect_siblings_with_text_nodes`

`selectolax.Node.iter(include_text=False)` skips text nodes — that's
why the parser never sees the bare `=`. We need a custom iterator
that returns BOTH element children **and** their direct sibling text
nodes (in document order), so we can detect a `=` text node between
two elements.

Selectolax exposes raw HTML; the cheapest fix is to **parse the
parent's inner HTML manually**, walking top-level segments. Implement
in `parse_blocks.py`:

```python
def iter_children_with_text(parent: Node) -> Iterator[Union[Node, str]]:
    """Yield direct element children and direct text nodes of `parent`,
    in document order. Text nodes are yielded as plain str (post-NFC)."""
    inner = _get_inner_html(parent)   # already exists
    # Walk inner HTML; for each top-level child element, yield Node;
    # for each gap of text between elements, yield the text string.
    pos = 0
    depth = 0
    text_buf: list[str] = []
    seg_start = 0
    elements = list(parent.iter(include_text=False))
    elements = [e for e in elements if e is not parent]
    elem_idx = 0
    for ch in iter_top_level_segments(inner):
        if isinstance(ch, str):
            t = normalize_text(ch)
            if t:
                yield t
        else:
            if elem_idx < len(elements):
                yield elements[elem_idx]
                elem_idx += 1
```

`iter_top_level_segments` is a small state machine that splits inner
HTML into top-level `<tag>...</tag>` element strings and the text
between them. This is already 80% of what `_get_inner_html` /
`_direct_text_of` are doing — refactor those to call into the new
iterator.

#### 3.3.2 Updated emit logic

```python
# When we are about to emit a block from a parent context (e.g. inside an <li>):
last_block: Optional[Block] = None
pending_refs: list[Reference] = []
seen_eq_marker: bool = False     # NEW

for child in iter_children_with_text(parent):
    if isinstance(child, str):
        if config.translation_marker.sibling_marker_enabled and \
           re.match(config.translation_marker.sibling_marker_text_node_re, child):
            seen_eq_marker = True
            continue
        # other text — currently ignored
        continue

    # element
    if is_leading_reference_node(child, config):
        pending_refs.extend(extract_refs_from_node(child, config))
        continue

    block = make_block(child, config, current_keyword=keyword)
    if block is None:
        continue
    if isinstance(block, tuple):
        block, see_alsos = block
    else:
        see_alsos = []

    if seen_eq_marker and last_block is not None \
       and last_block.kind in config.translation_marker.source_kinds \
       and block.kind in config.translation_marker.hindi_kinds:
        # Merge as hindi_translation of last_block
        last_block.hindi_translation = block.text_devanagari
        # references: leading first, then block's own (already deduped)
        if config.translation_marker.reference_ordering == "leading_then_inline":
            last_block.references = list(last_block.references) + \
                                    list(pending_refs) + list(block.references)
        else:
            last_block.references = list(last_block.references) + \
                                    list(block.references) + list(pending_refs)
        # Strip GRef text from the merged hindi_translation
        last_block.hindi_translation = strip_refs_from_text(
            last_block.hindi_translation, last_block.references, config)
        pending_refs.clear()
        seen_eq_marker = False
        for sa in see_alsos:
            out.append(sa)
        continue

    seen_eq_marker = False  # reset if not consumed
    last_block, pending_refs, out = _emit(block, last_block, pending_refs, out, config)
    out.extend(see_alsos)
```

This logic supersedes the current `_emit` translation-marker branch
**only when the parent context provides text-node visibility**
(i.e. when iterating via `iter_children_with_text`). The existing
"`text_devanagari` starts with `=`" branch in `_emit` stays — it
covers the case where `=` is fused into the HindiText body itself.

### 3.4 Reference order on a block

Establish an invariant in `Block`:

```
references = [leading_refs..., inline_refs_in_doc_order...]
```

Update `_emit` so when leading refs are flushed onto a block:

```python
block.references = list(pending_refs) + list(block.references)
pending_refs.clear()
```

(Currently it does `block.references.extend(pending_refs)` — that's
`[inline..., leading...]`, the wrong order. Fix.)

---

## 4. Where to wire `iter_children_with_text`

The sibling-marker logic must be invoked wherever block streams are
assembled from a parent that may contain `=` text nodes:

- `parse_block_stream(elements, ...)` — outermost. The `elements`
  list **already** flattens away parent context, so we lose text
  nodes. **Refactor** so `parse_block_stream` accepts an *element
  with children* (the `<li>` or `<div>`) and iterates its children
  with text-node visibility — OR — we pre-scan the original parent in
  `parse_subsections.walk_and_collect_headings` and emit text-node
  events alongside element events.

  **Pragmatic implementation**: change
  `walk_and_collect_headings._dfs` to also append `("text", str)`
  events when it encounters a top-level text node `=`. Then in
  `parse_subsections.parse_subsections`, when calling
  `parse_block_stream(content_els)`, build a `content_els_with_text`
  list of `Union[Node, str]` and pass it to a new
  `parse_block_stream_with_text(items, config, ...)` that uses the
  emit logic in §3.3.2.

  This is the minimally invasive change: `walk_and_collect_headings`
  is the single chokepoint for content collection, and it already
  knows where text nodes live.

- `parse_definitions.parse_siddhantkosh_definitions` and
  `parse_puraankosh_definitions` — same: switch their
  `parse_block_stream` calls to `parse_block_stream_with_text` when
  the parent (`<li>`, `<div>`) may host text nodes.

- `_explode_nested_span` — the L734–759 case where a single
  `<span class="SanskritText">` contains nested `<span>`s separated by
  `=` text nodes — this iterator must also yield text nodes. Replace
  the body with a call to `iter_children_with_text(span)`.

### 4.1 Detail for nested-span flatten

Today `_explode_nested_span` does:

```python
for child in span.iter(include_text=False):
    ...
```

After phase 2:

```python
for ch in iter_children_with_text(span):
    if isinstance(ch, str):
        if matches_sibling_marker(ch, config):
            yield ("text_eq",)   # sentinel
        continue
    yield ch
```

The consumer (`parse_block_stream_with_text`) handles the sentinel
identically to a top-level `=` text node.

---

## 5. Edge cases (must be in tests)

| Case | Expected |
|------|----------|
| Source block followed by HindiText whose own text starts with `=` | Existing behaviour: merged as translation. Keep working. |
| Source block, sibling text `=`, then HindiText | NEW: merged as translation. |
| Two source blocks in a row, then `=`, then HindiText | The HindiText pairs with the **most recent** source block. |
| `=` text node with no preceding source block | The marker is **dropped silently** (no orphan block emitted), warning recorded with code `orphan_eq_marker`. |
| HindiText starts with `=` but no preceding source block | Existing fallback: `is_orphan_translation=true`, leading `=` stripped. Keep. |
| `=` appearing in the middle of HindiText prose (`x = y`) | NOT a marker; only `^\s*=\s*$` text nodes match. |
| Inline GRef inside a SanskritText that has no following HindiText | GRef stripped from `text_devanagari`, attached to `references[]`. |
| Multiple inline GRefs in one block | All stripped, all attached to `references[]` in document order. |
| Ref text contains regex metacharacters | `strip_refs_from_text` uses literal `.replace`, not regex — safe. |

---

## 6. Verification

```bash
pytest workers/ingestion/jainkosh/tests/unit/test_refs.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_translation_marker.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_nested_span.py -x
pytest workers/ingestion/jainkosh/tests/unit/ -x
```

Then regenerate goldens. Expected diff highlights:

- The first SiddhantKosh definition of द्रव्य (1.1) should now show:
  - `prakrit_gatha` block with `hindi_translation` populated.
  - References `["पंचास्तिकाय/9", "( राजवार्तिक/1/33/1/95/4 )"]` on the gatha.
  - **No** standalone `hindi_text` block carrying the translation.
- All `text_devanagari` strings should have GRef text stripped.

Manually review and accept the diff per the README "Goldens" process.
