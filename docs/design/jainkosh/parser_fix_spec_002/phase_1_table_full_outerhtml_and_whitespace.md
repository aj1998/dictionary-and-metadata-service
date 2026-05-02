# Phase 1 — Tables as full outerHTML; whitespace-cleaned `raw_html`

## Problem

In current goldens (e.g. `पर्याय.json`, `आत्मा.json`) blocks of
`kind="table"` carry only the opening `<table ...>` tag in
`raw_html`, without the table's child rows. Inline `Reference.raw_html`
strings keep multiple internal spaces (`<span class="GRef">सर्वार्थसिद्धि/5/2/266/10 </span>`,
`( सर्वार्थसिद्धि/5/38/30  पर उद्धृत गाथा)`) and stray newlines from the
source HTML, bloating the JSON.

We need:

1. Every `Block(kind="table").raw_html` is the **full** outer HTML of the
   `<table>` element — i.e. `<table ...>...</table>` with all `<tbody>`,
   `<tr>`, `<td>`, etc. preserved. (selectolax's `Node.html` is
   normally outerHTML, so we will assert this and write a regression test
   so the byte-for-byte snapshot is locked.)
2. `raw_html` strings — both for `Block(kind="table")` and for inline
   `Reference.raw_html` — are **whitespace-cleaned**: collapse consecutive
   ASCII whitespace (space, tab, newline, CR) inside text runs to a single
   space; strip leading/trailing whitespace inside tags (e.g. `>  X </span>`
   → `>X</span>`); preserve attribute values and tag structure verbatim.

The **NFC content** of the source must not change — only whitespace.

## Failing tests (write first)

Create `workers/ingestion/jainkosh/tests/unit/test_raw_html_outerhtml.py`:

```python
import pytest
from selectolax.parser import HTMLParser
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.tables import extract_table_block
from workers.ingestion.jainkosh.refs import extract_refs_from_node, _clean_raw_html


def _cfg():
    return load_config()


def test_table_raw_html_is_full_outerhtml():
    html = (
        '<table class="t1">'
        '<tbody><tr><th>A</th><th>B</th></tr>'
        '<tr><td>1</td><td>2</td></tr></tbody>'
        '</table>'
    )
    node = HTMLParser(html).css_first("table")
    block = extract_table_block(node, _cfg())
    assert block.raw_html.startswith("<table")
    assert "</table>" in block.raw_html
    assert "<tr>" in block.raw_html
    assert "<td>1</td>" in block.raw_html
    assert "<td>2</td>" in block.raw_html


def test_raw_html_collapses_runs_of_whitespace():
    src = '<span class="GRef">  सर्वार्थसिद्धि/5/2/266/10   </span>'
    out = _clean_raw_html(src, _cfg())
    assert out == '<span class="GRef">सर्वार्थसिद्धि/5/2/266/10</span>'


def test_raw_html_double_space_inside_text_collapsed():
    src = '<span class="GRef">( सर्वार्थसिद्धि/5/38/30  पर उद्धृत गाथा)</span>'
    out = _clean_raw_html(src, _cfg())
    assert out == '<span class="GRef">( सर्वार्थसिद्धि/5/38/30 पर उद्धृत गाथा)</span>'


def test_raw_html_attribute_values_preserved():
    src = '<a href="/wiki/X" title="X">link</a>'
    out = _clean_raw_html(src, _cfg())
    assert out == '<a href="/wiki/X" title="X">link</a>'


def test_reference_raw_html_is_cleaned_in_extract():
    html = '<p><span class="GRef">  abc   </span></p>'
    node = HTMLParser(html).css_first("p")
    refs = extract_refs_from_node(node, _cfg())
    assert refs[0].raw_html == '<span class="GRef">abc</span>'
```

Run: `pytest -x workers/ingestion/jainkosh/tests/unit/test_raw_html_outerhtml.py` →
must FAIL before implementation.

Add a golden-coverage assertion to
`workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py`:

```python
def test_no_truncated_table_raw_html_in_goldens(parsed_results):
    for result in parsed_results.values():
        for sec in result["keyword_parse_result"]["page_sections"]:
            for sub in _walk_subs(sec.get("subsections", [])):
                for b in sub.get("blocks", []):
                    if b.get("kind") != "table":
                        continue
                    assert b["raw_html"].startswith("<table")
                    assert b["raw_html"].rstrip().endswith("</table>")
```

(`_walk_subs` is a recursive helper over `children`; reuse the existing
one if present.)

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
table:
  raw_html:
    collapse_whitespace: true     # NEW

reference:
  raw_html:
    collapse_whitespace: true     # NEW
```

`parser_configs/_schemas/jainkosh.schema.json` — add the matching
sub-objects under `table` and `reference`.

`workers/ingestion/jainkosh/config.py`:

```python
class TableRawHtmlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collapse_whitespace: bool = True


class TableConfig(BaseModel):
    ...
    raw_html: TableRawHtmlConfig = Field(default_factory=TableRawHtmlConfig)


class ReferenceRawHtmlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collapse_whitespace: bool = True


class ReferenceConfig(BaseModel):
    ...
    raw_html: ReferenceRawHtmlConfig = Field(default_factory=ReferenceRawHtmlConfig)
```

## Implementation

### 1.1 Whitespace cleaner — `refs.py`

Add a private `_clean_raw_html(html: str, config) -> str`:

```python
def _clean_raw_html(html: str, config) -> str:
    if not html:
        return html
    enabled = (
        getattr(config.reference, "raw_html", None) is not None
        and config.reference.raw_html.collapse_whitespace
    )
    if not enabled:
        return html
    out = re.sub(r"(>)([^<]*)(<)", _collapse_run, html)
    return out


def _collapse_run(m: re.Match) -> str:
    before, run, after = m.group(1), m.group(2), m.group(3)
    if not run:
        return before + run + after
    cleaned = re.sub(r"[\s ]+", " ", run)
    cleaned = cleaned.strip()
    if not cleaned:
        return before + after
    head_space = " " if run[:1].isspace() and not run.lstrip().startswith(("(", "।", "॥")) else ""
    tail_space = ""
    if cleaned.startswith("(") or cleaned.endswith(")"):
        cleaned = cleaned
    return before + cleaned + after
```

(Implementation detail — the test fixtures dictate exact behaviour:
collapse internal runs, drop leading/trailing whitespace inside the tag.
Keep the function pure-string; no DOM round-trip.)

`extract_refs_from_node` change:

```python
def extract_refs_from_node(node, config):
    refs = []
    for gref in node.css("span.GRef"):
        text = extract_ref_text(gref, config)
        if text:
            raw = _clean_raw_html(gref.html or "", config)
            parsed = None
            if config.reference.parse_strategy != "text_only":
                parsed = parse_reference_text(text, config)
            refs.append(Reference(text=text, raw_html=raw, parsed=parsed))
    return refs
```

### 1.2 Table block — `tables.py`

```python
from .refs import _clean_raw_html


def extract_table_block(table: Node, config: JainkoshConfig) -> Block:
    raw = table.html or ""
    if config.table.raw_html.collapse_whitespace:
        raw = _clean_raw_html(raw, config)
    block = Block(kind="table", raw_html=raw)
    if config.table.extraction_strategy == "raw_html_plus_rows":
        block.table_rows = _extract_rows(table)
    return block
```

Defensively assert it really is full outerHTML; if `raw` does not contain
`</table>`, emit a `ParserWarning(code="truncated_table_html", ...)` (warning
only — selectolax always returns outerHTML, so this should never fire,
but the warning surfaces breakage early).

### 1.3 Selectors helper — `selectors.py`

`node_outer_html(node)` already exists; extend it to also accept a
`config` arg and run `_clean_raw_html` when called by callers that want
the cleaned form. Existing callers of `node_outer_html` that need the raw
shape (none currently — verify with `grep -n node_outer_html
workers/ingestion/jainkosh/*.py`) keep their behaviour.

### 1.4 Documentation

`docs/design/jainkosh/parsing_rules.md`:

- §3.5 (NEW) — *Raw HTML capture rules*. Tables: outerHTML. References:
  outerHTML of the `<span class="GRef">`. Whitespace collapse rule:
  internal runs of `[\s ]+` collapse to a single space; trim
  inside-tag whitespace.

## Definition of Done

- [ ] All tests in `test_raw_html_outerhtml.py` pass.
- [ ] Golden assertion in `test_parse_keyword_golden.py` passes.
- [ ] `parser_configs/jainkosh.yaml` validates against schema.
- [ ] Goldens regenerated under the candidate-and-review workflow described in the README.
- [ ] No new emojis or comments introduced (CLAUDE.md rules).
