# Phase 1 — Configurable `देखें` triggers + nested-DFS scan

> **Goal**: Detect `देखें` *and* `विशेष देखें` (and any future trigger
> we add) anywhere in the page DOM (including deeply nested `<ul>` /
> `<li>` / `<p>` / `<span>` structures), as a configurable list. Today
> we miss e.g. `परमाणु में कथंचित् सावयव निरवयवपना।।–देखें …` because
> the index walker only descends two levels into the outer `<ol>`.

> **Symptoms in golden द्रव्य.json** (search "परमाणु में कथंचित्",
> "द्रव्य में कथंचित् नित्यानियत्व") — these `देखें` relations are
> absent from `index_relations`.

---

## 1. Failing tests (write first)

### 1.1 `tests/unit/test_see_also.py` — extend

Add the following parametrised cases. They MUST fail on `main`.

```python
import pytest
from selectolax.parser import HTMLParser
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.see_also import find_see_alsos_in_element

CFG = load_config("parser_configs/jainkosh.yaml")

@pytest.mark.parametrize("html, expected_trigger_count", [
    # Existing trigger
    ('<p class="HindiText">देखें <a href="/wiki/X">X</a></p>', 1),
    # NEW: विशेष देखें trigger
    ('<p class="HindiText">विशेष देखें <a href="/wiki/X">X</a></p>', 1),
    # NEW: deeply nested case (mirrors the द्रव्य nested <ul>)
    ('<ol><li><strong id="1">A</strong>'
     '<ol><li><ul><li>परमाणु में कथंचित् सावयव निरवयवपना।।–देखें '
     '<a href="/wiki/परमाणु">परमाणु</a></li></ul></li></ol>'
     '</li></ol>', 1),
    # Multiple triggers in one element
    ('<p class="HindiText">A देखें <a href="/wiki/A">A</a> '
     'और विशेष देखें <a href="/wiki/B">B</a></p>', 2),
])
def test_see_also_triggers(html, expected_trigger_count):
    tree = HTMLParser(html)
    root = tree.css_first("p, ol")
    results = find_see_alsos_in_element(root, CFG, current_keyword="X")
    assert len(results) == expected_trigger_count
```

### 1.2 `tests/unit/test_index_relations.py` — extend

```python
def test_index_relations_full_dfs(load_fixture):
    """The द्रव्य fixture has nested <ul> देखें relations multiple
    levels deep inside the leading <ol>. All must be captured."""
    result = parse_keyword(load_fixture("द्रव्य.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    targets = [r.label_text for r in sk.index_relations]
    assert any("परमाणु में कथंचित् सावयव" in t for t in targets)
    assert any("द्रव्य में कथंचित् नित्यानियत्व" in t for t in targets)
```

### 1.3 `tests/unit/test_config_schema.py` — extend

Assert that `parser_configs/jainkosh.yaml` validates with the new
`index.see_also_triggers` array and `index.see_also_window_chars` int.

---

## 2. YAML / config changes

### 2.1 `parser_configs/jainkosh.yaml`

Add **inside the existing `index:` block**, replacing the single
`see_also_text_pattern` regex:

```yaml
index:
  enabled_for: ["siddhantkosh"]
  outer_list_selector: "ol"
  inner_anchor_ignore_selector: "ol li a[href^='#']"
  see_also_list_selector: "ul"
  self_link_class: "mw-selflink-fragment"

  # NEW — phase 1
  see_also_triggers:
    - "देखें"
    - "विशेष देखें"
  see_also_window_chars: 40
  see_also_leading_punct_re: '[(–\-।\s]*'   # punctuation allowed between trigger and anchor (preceding side)

  # DEPRECATED — keep for one version for back-compat; built from the new fields if absent.
  see_also_text_pattern: '(?:[(–\-]\s*)?(?:विशेष\s+)?देखें\s*'
```

### 2.2 `parser_configs/_schemas/jainkosh.schema.json`

Add the matching schema entries:

```json
"see_also_triggers": {
  "type": "array",
  "items": {"type": "string"},
  "minItems": 1
},
"see_also_window_chars": {"type": "integer", "minimum": 1, "maximum": 200},
"see_also_leading_punct_re": {"type": "string"}
```

`see_also_text_pattern` remains in the schema as `"deprecated": true`
but still validated as `string`.

### 2.3 `workers/ingestion/jainkosh/config.py`

In the `IndexConfig` Pydantic model:

```python
class IndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled_for: list[str]
    outer_list_selector: str
    inner_anchor_ignore_selector: str
    see_also_list_selector: str
    self_link_class: str

    # NEW
    see_also_triggers: list[str] = Field(default_factory=lambda: ["देखें"])
    see_also_window_chars: int = 40
    see_also_leading_punct_re: str = r'[(–\-।\s]*'

    # deprecated; auto-derived if not provided
    see_also_text_pattern: Optional[str] = None

    @model_validator(mode="after")
    def _build_pattern(self):
        if not self.see_also_text_pattern:
            triggers = "|".join(re.escape(t) for t in sorted(
                self.see_also_triggers, key=len, reverse=True))
            self.see_also_text_pattern = f"(?:{self.see_also_leading_punct_re})(?:{triggers})\\s*$"
        return self
```

`sorted(..., key=len, reverse=True)` ensures `विशेष देखें` matches
before `देखें` (longest-trigger-first).

`\s*$` — anchors to **end of preceding text** so a trigger only fires
when the next thing is the anchor.

---

## 3. Code changes

### 3.1 `workers/ingestion/jainkosh/see_also.py`

Replace `_build_see_also_re` to consume the new pattern (already
auto-built by config validator):

```python
def _build_see_also_re(config: JainkoshConfig) -> re.Pattern:
    return re.compile(config.index.see_also_text_pattern)
```

`find_see_alsos_in_element(...)` already does `for a in el.css("a")`,
which is a deep CSS scan. Verify by adding a unit-test fixture with
3-deep nesting (1.1 above). If the existing scan misses cases, the
likely root cause is the `_preceding_inline_text` helper that only
looks at `a.parent.html` — fix:

```python
def _preceding_inline_text(a: Node, max_chars: int = 40) -> str:
    """Walk *up* the ancestor chain, concatenating text that appears
    in document order before <a> within each ancestor, until we have
    >= max_chars characters or we hit the section root."""
    pieces = []
    cur = a
    while cur.parent is not None and sum(len(p) for p in pieces) < max_chars:
        parent = cur.parent
        parent_html = parent.html or ""
        cur_html = cur.html or ""
        idx = parent_html.find(cur_html)
        if idx > 0:
            before = parent_html[:idx]
            pieces.append(re.sub(r"<[^>]+>", "", before))
        cur = parent
    text = "".join(reversed(pieces))
    return text[-max_chars:] if len(text) > max_chars else text
```

The window is `config.index.see_also_window_chars` instead of the
hard-coded 40 — replace the call sites.

### 3.2 `workers/ingestion/jainkosh/parse_index.py`

Replace the two-tier `<ol> → <li> → <ul>` walker with a full DFS that
emits one `IndexRelation` per `देखें`-anchored `<a>` regardless of
ancestor structure:

```python
def parse_index_relations(index_ols, keyword, config) -> list[IndexRelation]:
    out: list[IndexRelation] = []
    see_also_re = re.compile(config.index.see_also_text_pattern)

    for outer_ol in index_ols:
        for a in outer_ol.css("a"):
            prev_text = _preceding_inline_text(a, config.index.see_also_window_chars)
            if not see_also_re.search(prev_text):
                continue
            parsed = parse_anchor(a, config, current_keyword=keyword)
            label = _extract_label_before_anchor(a, config)
            source_path = _nearest_ancestor_li_id(a)   # may be None for outer-<ol>-level <ul>
            out.append(IndexRelation(
                label_text=label,
                source_topic_path=source_path,         # legacy; phase 5 swaps this for chain
                **parsed,
            ))
    return out


def _nearest_ancestor_li_id(a: Node) -> Optional[str]:
    """Walk up parents; return the @id of the first <li> with one (excluding 'footer-*')."""
    cur = a.parent
    while cur is not None:
        if cur.tag == "li":
            li_id = (cur.attributes or {}).get("id") or ""
            if li_id and not li_id.startswith("footer-"):
                return li_id
        cur = cur.parent
    return None
```

Drop the old `_parse_ul_relations` / `_direct_children_of` /
`_preceding_text_in_li` helpers — superseded.

### 3.3 `workers/ingestion/jainkosh/see_also.py` — inline path uses same trigger list

`make_block` in `parse_blocks.py` already calls
`find_see_alsos_in_element(node, config, …)`. After phase 1's regex
upgrade, `विशेष देखें` is automatically picked up there too.

Add a unit test:

```python
def test_inline_visesh_dekhen_in_hindi_block():
    html = '<p class="HindiText">पर्याय का स्वरूप (विशेष देखें '
           '<a href="/wiki/अस्तिकाय">अस्तिकाय</a>)</p>'
    blocks, _ = parse_p_to_blocks(html, CFG)
    see_alsos = [b for b in blocks if b.kind == "see_also"]
    assert len(see_alsos) == 1
    assert see_alsos[0].target_keyword == "अस्तिकाय"
```

---

## 4. Edge cases (must be in tests)

| Case | Expected |
|------|----------|
| `देखें` followed by **no** `<a>` (just plain text) | No relation emitted, no warning. |
| Two anchors after one `देखें` (`देखें <a>X</a>, <a>Y</a>`) | Only the first anchor (immediate next) is the see_also target; the second is unrelated unless it also has its own preceding `देखें`. The regex anchored to `\s*$` of preceding text already enforces this. |
| `विशेष देखें` and `देखें` in same paragraph, both with anchors | Two separate relations, in document order. |
| Trigger inside an anchor's own text (e.g. `<a>देखें</a>`) | No relation (preceding text outside the anchor must contain the trigger). |
| `–देखें` with en-dash, no space | Match (existing `see_also_leading_punct_re` covers it). |
| Whitespace-only / NBSP between trigger and anchor | Match (`\s*$` plus normalization in `_preceding_inline_text`). |

Add at least one test per row.

---

## 5. Verification

```bash
pytest workers/ingestion/jainkosh/tests/unit/test_see_also.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_index_relations.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_config_schema.py -x
pytest workers/ingestion/jainkosh/tests/unit/ -x
```

All must pass. Then regenerate goldens (`*.candidate.json`) and post
the diff for human review per `README.md` "Goldens" section.

---

## 6. Rollback

If phase 1 ships and we need to revert: set `see_also_triggers:
["देखें"]` (single-trigger) in YAML — code path is identical. No code
revert needed for behaviour parity with `1.0.0`.
