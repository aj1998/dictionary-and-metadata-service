# Phase 5 — `would_write` cleanup + IndexRelation parent chain

> **Goal A**: Drop `subsection_tree` from
> `mongo.keyword_definitions.page_sections[]` in the envelope. Keep
> `extra_blocks` (per user decision: reserved for future use). Keep
> `definitions[]` and `index_relations[]`. The would_write payload is
> now strictly the entities that the orchestrator will write to a
> store on approval.
>
> **Goal B**: Replace `IndexRelation.source_topic_path: Optional[str]`
> with **two** new fields, **keeping the old one** for one version
> for back-compat:
>
> - `source_topic_path_chain: list[str]` — full numeric ancestor
>   chain (e.g. `["1", "1.2"]`); empty list `[]` for keyword-level
>   (outer-`<ol>`) `<ul>` relations.
> - `source_topic_natural_key_chain: list[str]` — same ancestors but
>   resolved to natural keys (e.g.
>   `["द्रव्य:द्रव्य-के-भेद-व-लक्षण",
>    "द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-लक्षण-सत्-तथा-उत्पादव्ययध्रौव्य"]`);
>   `[]` for keyword-level.
>
> The Neo4j edge builder uses `source_topic_natural_key_chain[-1]`
> when present (innermost ancestor) as the source node; otherwise
> falls back to the keyword node.

---

## 1. Failing tests (write first)

### 1.1 `tests/unit/test_index_relations.py` — extend

```python
def test_index_relation_chain_for_nested_relation(load_fixture):
    """The 'पंचास्तिकाय।–देखें अस्तिकाय' relation lives under <li id='1'>;
    inside <li id='1'> there is no further numbered ancestor for this
    particular <ul>, so the chain is ['1']."""
    result = parse_keyword(load_fixture("द्रव्य.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    matches = [r for r in sk.index_relations if r.target_keyword == "अस्तिकाय"]
    assert matches, "अस्तिकाय relation not found"
    rel = matches[0]
    assert rel.source_topic_path_chain == ["1"]
    assert len(rel.source_topic_natural_key_chain) == 1
    assert rel.source_topic_natural_key_chain[0].startswith("द्रव्य:")


def test_index_relation_chain_for_keyword_level_ul(load_fixture):
    """A <ul> at the outer-<ol> level (keyword-level) has empty chain."""
    result = parse_keyword(load_fixture("पर्याय.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    keyword_level = [r for r in sk.index_relations if r.source_topic_path_chain == []]
    assert len(keyword_level) >= 1
    assert all(r.source_topic_natural_key_chain == [] for r in keyword_level)


def test_index_relation_chain_for_deeply_nested_dekhen(load_fixture):
    """A देखें found inside a <ul> inside a sub-<ol> inside <li id='1'>
    in turn inside another <li id='1.4'> should produce a chain of
    ['1', '1.4'] (or whatever the actual ancestor sequence is in the
    fixture)."""
    result = parse_keyword(load_fixture("द्रव्य.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")
    deep = [r for r in sk.index_relations if "इसी प्रकार" in r.label_text or "गुणसमुदायो" in r.label_text]
    if deep:
        rel = deep[0]
        assert len(rel.source_topic_path_chain) >= 2
```

### 1.2 `tests/test_parse_keyword_golden.py` — extend

```python
def test_keyword_definitions_has_no_subsection_tree(load_fixture):
    result = parse_keyword(load_fixture("आत्मा.html"))
    env = build_envelope(result)
    kdef = env.would_write["mongo"]["keyword_definitions"][0]
    for ps in kdef["page_sections"]:
        assert "subsection_tree" not in ps
        assert "extra_blocks" in ps                  # still present
        assert "definitions" in ps
        assert "index_relations" in ps
```

---

## 2. Pydantic model changes

### 2.1 `models.py` — `IndexRelation`

```python
class IndexRelation(BaseModel):
    label_text: str
    target_keyword: Optional[str]
    target_topic_path: Optional[str]
    target_url: str
    is_self: bool = False
    target_exists: bool = True

    # DEPRECATED — kept for one version. Equal to source_topic_path_chain[-1]
    # if non-empty, else None. Removable in 1.2.0.
    source_topic_path: Optional[str] = None

    # NEW — phase 5
    source_topic_path_chain: list[str] = Field(default_factory=list)
    source_topic_natural_key_chain: list[str] = Field(default_factory=list)
```

A `model_validator(mode="after")` derives `source_topic_path` from
the chain if not set:

```python
    @model_validator(mode="after")
    def _legacy_source_topic_path(self):
        if self.source_topic_path is None and self.source_topic_path_chain:
            self.source_topic_path = self.source_topic_path_chain[-1]
        return self
```

---

## 3. Algorithm — chain construction

### 3.1 In `parse_index.parse_index_relations`

After phase 1's full-DFS walker, when a `देखें` anchor is captured,
compute the chain by walking up the DOM looking at every `<li id="…">`
ancestor:

```python
def _ancestor_li_ids(a: Node) -> list[str]:
    """Return the list of <li> ancestor ids in document order
    (outermost first)."""
    ids = []
    cur = a.parent
    while cur is not None:
        if cur.tag == "li":
            li_id = (cur.attributes or {}).get("id") or ""
            if li_id and not li_id.startswith("footer-"):
                ids.append(li_id)
        cur = cur.parent
    ids.reverse()
    return ids
```

Then the new `IndexRelation` construction:

```python
chain = _ancestor_li_ids(a)
out.append(IndexRelation(
    label_text=label,
    source_topic_path_chain=chain,
    source_topic_natural_key_chain=[],   # filled in §3.2
    **parsed,
))
```

### 3.2 Resolving `source_topic_natural_key_chain`

The natural keys depend on the headings that own each `<li id="X">`.
After `parse_section` finishes building both `subsections` and
`index_relations` (subsections first, since the body has the actual
heading text), back-fill the chain by topic_path lookup:

```python
def resolve_index_relation_natural_keys(
    section: PageSection,
    keyword: str,
) -> None:
    path_to_nk: dict[str, str] = {}
    for sub in walk_subsection_tree(section.subsections):
        if sub.topic_path is not None:
            path_to_nk[sub.topic_path] = sub.natural_key
    for rel in section.index_relations:
        rel.source_topic_natural_key_chain = [
            path_to_nk[p] for p in rel.source_topic_path_chain if p in path_to_nk
        ]
```

If `rel.source_topic_path_chain[i]` has no matching subsection (e.g.
a stale id like a footer or a redlink-bound id), it is skipped — the
chain may be shorter than `source_topic_path_chain` in pathological
cases. Tests assert this is rare.

Call this from `parse_keyword.parse_keyword_html` right after the
section loop.

---

## 4. Envelope cleanup (`envelope.py`)

### 4.1 Drop `subsection_tree`

In `build_mongo_fragment.kdef.page_sections[*]`:

```python
# REMOVE these two lines:
# "subsection_tree": [_sub_to_summary(t) for t in s.subsections],
# Keep:
# "extra_blocks": [b.model_dump() for b in s.extra_blocks],
# "definitions": [d.model_dump() for d in s.definitions],
# "index_relations": [r.model_dump() for r in s.index_relations],
```

### 4.2 Drop `_sub_to_summary` if unused

If no other call site uses `_sub_to_summary`, delete it (keep the
module clean). If the `Subsection.children` summary is still needed
for some Postgres consumer, leave it.

### 4.3 Neo4j edge: pick innermost natural key

In `build_neo4j_fragment`, replace the source-topic lookup loop:

```python
for rel in sec.index_relations:
    if rel.source_topic_natural_key_chain:
        src = ("Topic", rel.source_topic_natural_key_chain[-1])
    else:
        src = ("Keyword", result.keyword)
    edge = _index_relation_edge(rel, src, keyword=result.keyword)
    if edge:
        edges.append(edge)
```

This drops the slow inner subscription loop.

---

## 5. Edge cases

| Case | Expected |
|------|----------|
| Relation under `<li id="1">` with no inner `<li id="1.X">` | chain = `["1"]`, nk_chain has 1 entry. |
| Relation under `<li id="1.4">` nested in `<li id="1">` | chain = `["1", "1.4"]`, nk_chain has 2 entries. |
| Relation inside an inner `<ul>` whose nearest `<li>` ancestor has no `id` | Skip that `<li>`; pick the next ancestor with id. (Tests cover.) |
| All `<li>` ancestors lack `id` | chain = `[]`, treated as keyword-level. |
| `id` is `footer-…` | Excluded from the chain (filter in `_ancestor_li_ids`). |
| `topic_path` of a label-seed topic is None (Phase 3) | The label-seed Subsection is never an ancestor of an index_relation, so this doesn't intersect. |

---

## 6. Verification

```bash
pytest workers/ingestion/jainkosh/tests/unit/test_index_relations.py -x
pytest workers/ingestion/jainkosh/tests/test_parse_keyword_golden.py -x
pytest workers/ingestion/jainkosh/tests/ -x
```

Regenerate goldens. Expected diff highlights:

- Every `IndexRelation` has `source_topic_path_chain` (array) and
  `source_topic_natural_key_chain` (array) populated.
- `mongo.keyword_definitions.page_sections[*]` no longer contains
  `subsection_tree`.
- `mongo.keyword_definitions.page_sections[*]` still contains
  `extra_blocks` (preserved).

Manually review and accept the diff per the README process.

---

## 7. After phase 5

After phase 5 ships green and goldens are accepted:

1. Bump `parser_configs/jainkosh.yaml` `parser_rules_version` from
   `1.0.0` to `1.1.0` (per README "Version bump").
2. Update `docs/design/jainkosh/parsing_rules.md` §10 with the new
   version and a one-line changelog pointing to this spec folder.
3. Add a deprecation note in `models.py` for
   `IndexRelation.source_topic_path` — schedule removal in `1.2.0`.

---

## 8. Definition of Done (fix-spec-001 overall)

When all five phases are merged and goldens are committed:

- [ ] All five phase docs implemented; their failing-tests-first
      checkpoints pass.
- [ ] Full test suite green:
      `pytest workers/ingestion/jainkosh/tests/`.
- [ ] Three goldens regenerated, hand-reviewed, and committed.
- [ ] `parser_rules_version: jainkosh.rules/1.1.0` in YAML and in
      every golden's `parser_version` field.
- [ ] `parser_configs/jainkosh.yaml` validates against
      `_schemas/jainkosh.schema.json`.
- [ ] `idempotency_contract` present on every emitted entity row in
      `would_write` (verify by golden grep).
- [ ] No regression in `KeywordParseResult.warnings` — empty for the
      three sample fixtures (or new `code` values are explicitly
      added to the goldens).
- [ ] CHANGELOG / commit message references this spec folder.
