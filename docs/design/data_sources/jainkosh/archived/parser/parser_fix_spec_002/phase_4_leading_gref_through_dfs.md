# Phase 4 — Leading GRef siblings preserved through DFS

## Problem

Inside a heading `<li>` like:

```html
<li class="HindiText">
  <strong id="1.1">द्रव्य का निरुक्त्यर्थ</strong>
  <br/>
  <span class="GRef">पंचास्तिकाय/9   </span>
  <span class="PrakritGatha">दवियदि गच्छदि ...।9।</span>
  =
  <span class="HindiText">उन-उन सद्भाव पर्यायों को ... <span class="GRef">( राजवार्तिक/1/33/1/95/4 )</span> ।</span>
  ...
</li>
```

the leading `<span class="GRef">पंचास्तिकाय/9</span>` is dropped from
the parsed `prakrit_gatha` block — `references` ends up containing only
the inline `( राजवार्तिक/1/33/1/95/4 )`. The same bug drops the leading
`सर्वार्थसिद्धि/1/5/17/5` for the next `sanskrit_text` block, and several
others in `द्रव्य.json` and `पर्याय.json`.

Root cause: in `parse_subsections._dfs`, when walking direct children of
the `<li>`, `block_class_kind(span_with_class_GRef)` returns `None` (GRef
is not a block kind), and `<span>` is not in the structural tag list
(`ol`/`ul`/`li`/`div`/`tbody`/`tr`/`td`/`th`). The `else` branch does
`_dfs(list(_iter_direct_children(el)))` — which recurses into the GRef
span looking for children, but the GRef has none. So the GRef element is
silently lost. Once dropped from the event stream,
`parse_block_stream` never sees it as a `is_leading_reference_node`,
and the next emitted block has no leading reference.

## Failing tests (write first)

Create `workers/ingestion/jainkosh/tests/unit/test_leading_gref_preserved.py`:

```python
from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

FIXTURE = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"


def _result():
    return parse_keyword_html(
        FIXTURE.read_text(encoding="utf-8"),
        "https://example.org/wiki/द्रव्य",
        load_config(),
    )


def _walk_subs(subs):
    for s in subs:
        yield s
        yield from _walk_subs(s.children)


def _find_sub(res, heading):
    for sec in res.page_sections:
        for s in _walk_subs(sec.subsections):
            if s.heading_text == heading:
                return s
    raise AssertionError(heading)


def test_panchastikaya_leading_ref_attached_to_prakrit_gatha():
    sub = _find_sub(_result(), "द्रव्य का निरुक्त्यर्थ")
    blocks = sub.blocks
    gatha = next(b for b in blocks if b.kind == "prakrit_gatha")
    ref_texts = [r.text for r in gatha.references]
    assert any("पंचास्तिकाय/9" in t for t in ref_texts), ref_texts


def test_sarvarthasiddhi_leading_ref_attached_to_sanskrit_text():
    sub = _find_sub(_result(), "द्रव्य का निरुक्त्यर्थ")
    sanskrit_blocks = [b for b in sub.blocks if b.kind == "sanskrit_text"]
    first = next(b for b in sanskrit_blocks if "गुणैर्गुणान्वा" in (b.text_devanagari or ""))
    ref_texts = [r.text for r in first.references]
    assert any("सर्वार्थसिद्धि/1/5/17/5" in t for t in ref_texts), ref_texts
```

Run: must FAIL.

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
dfs:
  passthrough_leading_gref: true   # NEW, default true
```

`config.py`:

```python
class DfsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passthrough_leading_gref: bool = True


class JainkoshConfig(BaseModel):
    ...
    dfs: DfsConfig = Field(default_factory=DfsConfig)
```

## Implementation

### 4.1 Patch `_dfs` in `parse_subsections.py`

Inside the `_dfs` inner function, after the heading check and before the
"structural container" branch, add:

```python
# Phase 4: leading GRef passthrough
from .selectors import is_gref_node
if config.dfs.passthrough_leading_gref and is_gref_node(el, config):
    events.append(("block", el))
    continue
```

The `("block", el)` event is then forwarded to
`parse_block_stream(content_els, ...)`, which already calls
`is_leading_reference_node(el, config)` and routes it into
`pending_refs`. The next emitted block consumes the pending refs in
front-position.

### 4.2 Edge case: GRef sandwiched between two source-kind blocks

If the order is `GRef → SanskritText → GRef → SanskritText`, the first
GRef pends and attaches to the first `SanskritText`; the second GRef
pends and attaches to the second `SanskritText`. The existing
`pending_refs` clearing in `_emit` already handles this. No change
needed beyond passthrough.

### 4.3 Edge case: GRef inside a nested span that is not flattened

`flatten_for_blocks` already explodes nested SanskritText/HindiText
spans. The `_explode_nested_span` function preserves GRefs via
`is_gref_node(child) → results.append(child)`. The Phase 4 passthrough
is only relevant for top-level GRefs that are siblings of the heading
inside a `<li>` body — not for GRefs already living inside a span that
will be flattened.

### 4.4 Documentation

`docs/design/jainkosh/parsing_rules.md` §3.6 (NEW) — *Leading GRef
preservation*. Note the rule that GRefs encountered during the body DFS
are emitted as content events, even though they are not block-class
elements.

## Definition of Done

- [ ] `test_leading_gref_preserved.py` passes.
- [ ] `references[0].text` contains `पंचास्तिकाय/9` for the `prakrit_gatha`
      block of "द्रव्य का निरुक्त्यर्थ" in `द्रव्य.json`.
- [ ] `references[0].text` contains `सर्वार्थसिद्धि/1/5/17/5` for the
      `sanskrit_text` block "गुणैर्गुणान्वा द्रुतं गतं ..." in `द्रव्य.json`.
- [ ] Goldens regenerated and reviewed.
- [ ] No regression in fix-spec-001 phase 2 (sibling-`=` translation marker).
