# Phase 3 — `IndexRelation` source chain via ancestor `<strong>` text

## Problem

In `द्रव्य.json` every `IndexRelation` has:

```jsonc
"source_topic_path": null,
"source_topic_path_chain": [],
"source_topic_natural_key_chain": []
```

The `index_relations` like `"द्रव्य का लक्षण ‘अर्थक्रियाकारित्व’"`
should resolve to source topic `"द्रव्य के भेद व लक्षण"` (topic_path `1`),
i.e.

```jsonc
"source_topic_path_chain": ["1"],
"source_topic_natural_key_chain": ["द्रव्य:द्रव्य-के-भेद-व-लक्षण"]
```

Similarly `"परमाणु में कथंचित् सावयव निरवयवपना"` should resolve to
`"सत् व द्रव्य में कथंचित् भेदाभेद → क्षेत्र या प्रदेशों की अपेक्षा द्रव्य में कथंचित् भेदाभेद"`
i.e.

```jsonc
"source_topic_path_chain": ["4", "4.2"],
"source_topic_natural_key_chain": [
  "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद",
  "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद:क्षेत्र-या-प्रदेशों-की-अपेक्षा-द्रव्य-में-कथंचित्-भेदाभेद"
]
```

The current `parse_index._ancestor_li_ids` walks ancestor `<li>`
nodes and reads their `id` attribute. But the dictionary index uses
`<strong>HEADING</strong>` (no id) inside `<li class="HindiText">` — see
fixture lines 366–401. The actual numeric `id` (e.g. `id="1"`) lives
on the `<strong>` later in the **body**, on a different `<li>`.

So we cannot resolve via `li[id]` lookup. Resolution must instead:

1. Walk ancestor `<li>` containers (outermost → innermost, excluding
   footer-* and excluding the immediate `<li>` that contains the `देखें` anchor).
2. For each such ancestor `<li>`, read the inline heading text — either
   `<strong>HEADING</strong>` or `<strong><a href="#N.M">HEADING</a></strong>`
   (the immediate-child `<strong>` of the `<li>`, ignoring nested
   children inside any `<ol>`/`<ul>`).
3. Use that text to look up a topic in the body subsection tree, by
   matching against `Subsection.heading_text` (NFC-normalised, whitespace-collapsed).
4. The chain is the ordered list of resolved topics (outermost to innermost).

## Failing tests (write first)

Create `workers/ingestion/jainkosh/tests/unit/test_index_source_chain.py`:

```python
from workers.ingestion.jainkosh.cli import _parse_html
from workers.ingestion.jainkosh.config import load_config
from pathlib import Path

FIXTURE = Path(__file__).parents[1] / "fixtures" / "द्रव्य.html"


def _result():
    html = FIXTURE.read_text(encoding="utf-8")
    cfg = load_config()
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
    return parse_keyword_html(html, "https://example.org/wiki/द्रव्य", cfg)


def _by_label(rels, label):
    for r in rels:
        if r.label_text == label:
            return r
    raise AssertionError(f"label not found: {label}")


def test_top_level_index_relation_resolves_to_strong_heading():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "द्रव्य का लक्षण ‘अर्थक्रियाकारित्व’")
    assert rel.source_topic_path_chain == ["1"]
    assert rel.source_topic_natural_key_chain == ["द्रव्य:द्रव्य-के-भेद-व-लक्षण"]


def test_nested_index_relation_resolves_full_chain():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "परमाणु में कथंचित् सावयव निरवयवपना")
    assert rel.source_topic_path_chain == ["4", "4.2"]
    nks = rel.source_topic_natural_key_chain
    assert nks[0] == "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद"
    assert nks[-1].endswith(":क्षेत्र-या-प्रदेशों-की-अपेक्षा-द्रव्य-में-कथंचित्-भेदाभेद")


def test_unresolvable_label_falls_back_to_keyword():
    res = _result()
    rel = _by_label(res.page_sections[0].index_relations, "पंचास्तिकाय")
    assert rel.source_topic_path_chain == []
    assert rel.source_topic_natural_key_chain == []
```

Run: must FAIL.

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
index:
  source_chain:
    enabled: true
    li_strong_selector: "strong"           # immediate-child strong of <li>
    li_strong_a_selector: "strong > a"     # supports <strong><a>...</a></strong>
    skip_li_with_footer_id: true
    match_normalize: "nfc_collapsed_ws"    # how to normalize heading text for lookup
```

`config.py`:

```python
class IndexSourceChainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    li_strong_selector: str = "strong"
    li_strong_a_selector: str = "strong > a"
    skip_li_with_footer_id: bool = True
    match_normalize: Literal["nfc_collapsed_ws"] = "nfc_collapsed_ws"


class IndexConfig(BaseModel):
    ...
    source_chain: IndexSourceChainConfig = Field(default_factory=IndexSourceChainConfig)
```

## Implementation

### 3.1 New helper in `parse_index.py`

Replace `_ancestor_li_ids` with a richer helper that emits **heading-text
candidates**, leaving id-based emission as a fallback:

```python
def _ancestor_strong_chain(a: Node, config) -> list[str]:
    """
    Walk ancestor <li> nodes (outermost → innermost, excluding the immediate <li>
    containing the <a>). For each <li>, return its inline heading text from the
    immediate-child <strong> (or <strong><a>...</a></strong>). Skip <li> that has
    no such strong (e.g. plain see-also rows).
    """
    chain_inner_to_outer: list[str] = []
    cur = a.parent
    is_innermost = True
    while cur is not None:
        if cur.tag == "li":
            if is_innermost:
                # The <li> directly enclosing the see-also <a> is itself the row;
                # do not contribute it to the source chain.
                is_innermost = False
                cur = cur.parent
                continue
            li_id = (cur.attributes or {}).get("id") or ""
            if config.index.source_chain.skip_li_with_footer_id and li_id.startswith("footer-"):
                cur = cur.parent
                continue
            heading = _li_inline_heading_text(cur, config)
            if heading:
                chain_inner_to_outer.append(heading)
        cur = cur.parent
    return list(reversed(chain_inner_to_outer))


def _li_inline_heading_text(li: Node, config) -> Optional[str]:
    for strong in li.iter(include_text=False):
        if strong.tag != "strong":
            continue
        anchor = strong.css_first("a")
        text = anchor.text(strip=True) if anchor is not None else strong.text(strip=True)
        if text:
            return _normalize_heading_for_match(text, config)
    return None


def _normalize_heading_for_match(text: str, config) -> str:
    text = nfc(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

The function emits **heading texts** (not topic_paths). Resolution to
topic_path / natural_key happens in `parse_keyword.py` after the body
subsection tree is built.

### 3.2 Update `parse_index_relations`

```python
def parse_index_relations(index_ols, keyword, config) -> list[IndexRelation]:
    out = []
    see_also_re = re.compile(config.index.see_also_text_pattern)
    for outer_ol in index_ols:
        for a in outer_ol.css("a"):
            prev_text = _preceding_inline_text(a, config.index.see_also_window_chars)
            if not see_also_re.search(prev_text):
                continue
            parsed = parse_anchor(a, config, current_keyword=keyword)
            label = _extract_label_before_anchor(a)
            heading_chain = _ancestor_strong_chain(a, config)
            out.append(IndexRelation(
                label_text=label,
                source_topic_path_chain=[],                  # filled in resolver
                source_topic_natural_key_chain=[],           # filled in resolver
                _temp_heading_chain=heading_chain,           # private; see below
                **parsed,
            ))
    return out
```

`_temp_heading_chain` is **not** a model field. Instead, attach it via a
side-channel dict in `parse_index.py`:

```python
_HEADING_CHAINS_BY_REL: "WeakValueDictionary[int, list[str]]" = {}

def _attach_heading_chain(rel: IndexRelation, chain: list[str]):
    _HEADING_CHAINS_BY_REL[id(rel)] = chain

def get_heading_chain(rel: IndexRelation) -> list[str]:
    return _HEADING_CHAINS_BY_REL.get(id(rel), [])
```

(Since `IndexRelation.model_config = ConfigDict(extra="forbid")`, we
cannot stash arbitrary fields on the model itself. The side-channel keeps
the model schema unchanged. The dict is purged after each `parse_keyword_html`
call by `_resolve_index_relation_natural_keys`.)

### 3.3 Resolve in `parse_keyword.py`

Extend `_resolve_index_relation_natural_keys`:

```python
def _resolve_index_relation_natural_keys(section: PageSection) -> None:
    path_to_nk: dict[str, str] = {}
    heading_to_topic: dict[str, tuple[str, str]] = {}
    for sub in _walk_subsection_tree(section.subsections):
        if sub.topic_path is not None:
            path_to_nk[sub.topic_path] = sub.natural_key
            norm = _normalize_heading_for_match(sub.heading_text, _CFG)
            heading_to_topic.setdefault(norm, (sub.topic_path, sub.natural_key))

    for rel in section.index_relations:
        # Topic_path-keyed (existing path: id-based ancestors)
        if rel.source_topic_path_chain:
            rel.source_topic_natural_key_chain = [
                path_to_nk[p] for p in rel.source_topic_path_chain if p in path_to_nk
            ]
            continue
        # Heading-text-keyed (Phase 3 new path)
        from .parse_index import get_heading_chain
        chain_texts = get_heading_chain(rel)
        if not chain_texts:
            continue
        path_chain, nk_chain = [], []
        for h in chain_texts:
            hit = heading_to_topic.get(h)
            if hit is None:
                # The label is unresolvable (e.g. only-redlink-target list); skip the chain.
                path_chain, nk_chain = [], []
                break
            path_chain.append(hit[0]); nk_chain.append(hit[1])
        rel.source_topic_path_chain = path_chain
        rel.source_topic_natural_key_chain = nk_chain
```

`_CFG` here means the same `JainkoshConfig` that was passed into
`parse_keyword_html`. Thread it through the function signature
(`_resolve_index_relation_natural_keys(section, config)`).

### 3.4 Edge case: ancestor `<li>` without `<strong>` (i.e. it is itself a see-also row)

If the ancestor `<li>` has no immediate-child `<strong>`, it is a
non-titled wrapper (e.g. an `<ul>` of see-also entries nested inside a
titled `<li>`). Skip it — do not contribute. Tests in Phase 5 cover the
case where multiple `<ul>` siblings of titled `<li>` exist.

### 3.5 Documentation

`docs/design/jainkosh/parsing_rules.md` §7.3 (NEW) — *Index source chain
resolution*. Document the lookup order: `li[id]` → `li > strong` text →
`li > strong > a` text → unresolved.

## Definition of Done

- [ ] `test_index_source_chain.py` passes.
- [ ] Goldens regenerated and reviewed; every `IndexRelation` whose
      ancestor `<li>` carries a `<strong>` heading now has a non-empty
      chain.
- [ ] Unresolvable labels (no matching subsection — e.g. labels whose
      ancestor `<li>` has no `<strong>`) keep empty chains; no crash.
- [ ] No regression in fix-spec-001 phase 1 (configurable triggers / DFS).
