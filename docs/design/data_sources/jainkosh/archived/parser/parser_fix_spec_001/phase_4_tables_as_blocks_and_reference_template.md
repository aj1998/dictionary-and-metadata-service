# Phase 4 — Tables as regular blocks + reference-parsing template

> **Goal A**: A `<table>` becomes a regular `Block(kind="table",
> raw_html=...)` attached to the **current open subsection**, not to
> a section-level `extra_blocks` bucket. `extra_blocks` is **kept on
> `PageSection`** for backwards compatibility / future use, but the
> default attachment for in-flow tables is the current subsection.
>
> **Goal B**: `raw_html` for tables stays as **raw HTML** for now (no
> structural parsing), but the code path is **extensible** so we can
> later add a `rows: list[list[str]]` representation under a YAML
> `table.extraction_strategy` toggle.
>
> **Goal C**: Add a **template-only** structured-reference field on
> `Reference` (`parsed: Optional[ParsedReference]`) and a
> `parse_reference_text()` stub that returns `None` in 1.1.0. Future
> phases (out of scope for this spec) will fill in shastra/teeka/gatha
> extraction without further model changes.

---

## 1. Failing tests (write first)

### 1.1 `tests/unit/test_tables.py` — new file

```python
def test_table_attaches_to_current_subsection(load_fixture):
    """The big د्रव्य table previously emitted under section.extra_blocks
    must now be attached to the current open subsection."""
    result = parse_keyword(load_fixture("द्रव्य.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

    # Find the table by walking the subsection tree
    found = []
    for sub in walk_subsection_tree(sk.subsections):
        for b in sub.blocks:
            if b.kind == "table":
                found.append((sub, b))
    assert len(found) >= 1
    parent, tbl = found[0]
    assert tbl.raw_html and tbl.raw_html.lstrip().startswith("<table")

    # PageSection.extra_blocks no longer holds this table
    assert all(b.kind != "table" or b.raw_html != tbl.raw_html
               for b in sk.extra_blocks)


def test_table_extra_blocks_preserved_for_orphan_tables():
    """A truly orphan table (no preceding heading in the section)
    still lands in section.extra_blocks. Synthesise a minimal fixture."""
    html = """
    <div class="mw-parser-output">
      <h2><span class="mw-headline" id="सिद्धांतकोष_से">…</span></h2>
      <table><tbody><tr><td>x</td></tr></tbody></table>
    </div>
    """
    result = parse_keyword_html(html, "https://example/d", CFG)
    sec = result.page_sections[0]
    assert len(sec.extra_blocks) == 1 and sec.extra_blocks[0].kind == "table"
    # No subsections in this fixture
    assert sec.subsections == []
```

### 1.2 `tests/unit/test_refs.py` — extend (template only)

```python
def test_parsed_reference_stub_returns_none_in_v1_1_0():
    """The Reference.parsed field exists and is None until a future
    phase plugs in a real shastra/teeka/gatha parser."""
    refs = extract_refs_from_node(make_p('<p><span class="GRef">पंचास्तिकाय/9</span></p>'), CFG)
    assert len(refs) == 1
    assert refs[0].text == "पंचास्तिकाय/9"
    assert refs[0].parsed is None      # template field
```

---

## 2. YAML / config additions

```yaml
table:
  selector: "table"
  store_raw_html: true
  # NEW — phase 4
  extraction_strategy: "raw_html_only"     # | "raw_html_plus_rows"
  attach_to: "current_subsection"          # | "section_root"
  # When attach_to == "current_subsection" but no subsection is open
  # at the table's position, fall back to section_root (extra_blocks).
  fallback_when_no_subsection: "section_root"

reference:
  selector: "span.GRef"
  strip_inner_anchors: true
  # NEW — phase 4 (template only; no parser yet)
  parse_strategy: "text_only"              # | "structured" | "text_plus_structured"
  # When parse_strategy != "text_only", call parse_reference_text(text, config)
  # which is a stub in 1.1.0 and always returns None. Future phases
  # implement structured extraction.
```

---

## 3. Pydantic model changes

### 3.1 `models.py`

```python
class ParsedReference(BaseModel):
    """Structured reference fields. Reserved for future phases.
    All fields optional; presence indicates successful parsing."""
    model_config = ConfigDict(extra="forbid")
    shastra: Optional[str] = None
    teeka: Optional[str] = None
    gatha: Optional[str] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    page: Optional[str] = None
    line: Optional[str] = None
    raw_components: list[str] = Field(default_factory=list)


class Reference(BaseModel):
    text: str
    raw_html: Optional[str] = None
    parsed: Optional[ParsedReference] = None     # NEW — template, None until future phase


class Block(BaseModel):
    ...
    # NEW — phase 4 (template, populated when extraction_strategy == "raw_html_plus_rows")
    table_rows: Optional[list[list[str]]] = None
```

These additions are forwards-compatible: existing goldens still parse
because all new fields default to `None` / unset.

---

## 4. Algorithms

### 4.1 Table attachment

In `parse_subsections.walk_and_collect_headings._dfs`, today a
`<table>` is treated as a content "block" event. Keep that — but mark
it as a table-event that flows to whichever heading is currently open:

```python
if el.tag == "table":
    events.append(("block", el))   # already done; fine
    continue
```

In `parse_section.parse_section`, today `<table>` siblings are
collected into `tables: list[el]` and emitted as `extra_blocks`.
Change Phase 1 (split into `pre_heading`/`index`/`body`/`tables`) to
NOT extract tables anymore — instead, leave them in `body`. Tables
inside `body` will end up under whichever subsection owns the slice
they fall into.

```python
def parse_section(elements, ...) -> PageSection:
    pre_heading, index_ols, body, orphan_tables = [], [], [], []
    seen_first_heading = False
    for el in elements:
        if el.tag == "table" and not seen_first_heading:
            # Truly orphan: no heading exists yet in this section.
            orphan_tables.append(el)
            continue
        if not seen_first_heading and el.tag == "ol" and not contains_heading(el, config):
            index_ols.append(el); continue
        if not seen_first_heading and not contains_heading(el, config):
            pre_heading.append(el); continue
        seen_first_heading = True
        body.append(el)

    ...
    extra_blocks = [extract_table_block(t, config) for t in orphan_tables]
    return PageSection(..., extra_blocks=extra_blocks)
```

The `body` list goes to `parse_subsections`, where tables get
naturally attached to the current subsection by the existing
slice-between-headings logic.

### 4.2 `extract_table_block` extensibility

`tables.py`:

```python
def extract_table_block(table: Node, config: JainkoshConfig) -> Block:
    block = Block(kind="table", raw_html=table.html or "")
    if config.table.extraction_strategy == "raw_html_only":
        return block
    if config.table.extraction_strategy == "raw_html_plus_rows":
        block.table_rows = _extract_rows(table)
    return block


def _extract_rows(table: Node) -> list[list[str]]:
    """Future implementation. Stub returns []."""
    return []
```

In 1.1.0 the default is `raw_html_only`, so `_extract_rows` is never
reached. The function exists only to make future enabling a single
config flip.

### 4.3 Reference parsing template

`refs.py`:

```python
def parse_reference_text(text: str, config: JainkoshConfig) -> Optional[ParsedReference]:
    """Stub. Returns None until a future phase ships structured extraction.
    The stub IS called from extract_ref_text when reference.parse_strategy
    is not 'text_only', so behaviour wiring is in place."""
    return None


def extract_refs_from_node(node: Node, config: JainkoshConfig) -> list[Reference]:
    refs = []
    for gref in node.css("span.GRef"):
        text = extract_ref_text(gref, config)
        if not text:
            continue
        parsed = None
        if config.reference.parse_strategy != "text_only":
            parsed = parse_reference_text(text, config)
        refs.append(Reference(text=text, raw_html=gref.html, parsed=parsed))
    return refs
```

---

## 5. Edge cases

| Case | Expected |
|------|----------|
| Table inside a deeply nested subsection (`1.2.3`) | Attaches to that subsection's `blocks`. |
| Table directly between two top-level subsections (after `1` closes, before `2` opens) | Attaches to subsection `1` (the most recent open subsection). The current emit-event ordering already places it inside the `1`-segment of the heading walker. Verify in tests. |
| Two consecutive tables in the same subsection | Both attached, order preserved. |
| Table with malformed HTML (unclosed `<tr>`) | `extract_table_block` returns whatever `node.html` is — no validation. (Out of scope.) |
| `attach_to: "section_root"` config override | All tables go to `extra_blocks` regardless of position. Test by flipping the config in a unit test. |
| `reference.parse_strategy: "structured"` config override | Stub returns `None`, `Reference.parsed` is `None`, no crash. |

---

## 6. Verification

```bash
pytest workers/ingestion/jainkosh/tests/unit/test_tables.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_refs.py -x
pytest workers/ingestion/jainkosh/tests/unit/ -x
```

Regenerate goldens. Expected diff highlights:

- `द्रव्य` SiddhantKosh `extra_blocks` becomes empty (or close to —
  only truly orphan tables remain).
- The big d→table now lives under the appropriate subsection (e.g.
  `1.2` per the source structure — verify by hand).
- Every `Reference` object has `"parsed": null` added.
- Every `Block` object has `"table_rows": null` added (only
  meaningful for `kind == "table"`, but Pydantic emits the field
  uniformly).

If the new fields cause a lot of noise in the diff, review the
README "R2" rule — the new fields are deliberate, optional, and
default-`None`, and goldens are expected to grow accordingly.

Manually review and accept the diff per the README process.
