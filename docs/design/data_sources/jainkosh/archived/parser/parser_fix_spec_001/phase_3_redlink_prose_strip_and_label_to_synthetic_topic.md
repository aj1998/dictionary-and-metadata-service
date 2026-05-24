# Phase 3 — Redlink prose-strip + label→synthetic-topic + idempotency contract

> **Goal A**: When a `देखें` (or `विशेष देखें`) anchor points to a
> "page does not exist" target (a MediaWiki redlink, marked
> `class="new"` and `title="X (page does not exist)"`), the entire
> `देखें <redlink>` substring (with its connector punctuation) is
> dropped from `text_devanagari`. The relation is **still emitted**
> with `target_exists=false` so the graph layer keeps the link.
>
> **Goal B**: When a HindiText prose block has the shape
> `• <label> - देखें <X>`, the `<label>` part (everything before the
> `देखें` trigger, minus the bullet) becomes a **new synthetic Topic
> seed** under the current open subsection (or under the keyword if
> at section root). Comma-separated labels are kept as a SINGLE
> topic — commas are NOT a delimiter anywhere in our code.
>
> **Goal C**: Each emitted entity (keyword, topic, synthetic topic)
> carries an `idempotency_contract` block describing the conflict key
> and the "merge / replace / append" policy per field, so the
> orchestrator can perform truly idempotent upserts in PG, Mongo,
> Neo4j without per-target reverse-engineering.

---

## 1. Failing tests (write first)

### 1.1 `tests/unit/test_see_also.py` — extend

```python
def test_redlink_prose_stripped_but_relation_emitted():
    html = ('<p class="HindiText">•\tबहिरात्मा, अंतरात्मा व परमात्मा - देखें '
            '<a href="/w/index.php?title=%E0%A4%B5%E0%A4%B9_%E0%A4%B5%E0%A4%B9_%E0%A4%A8%E0%A4%BE%E0%A4%AE&amp;action=edit&amp;redlink=1" '
            'class="new" title="वह वह नाम (page does not exist)">वह वह नाम</a></p>')
    blocks = parse_p_to_blocks(html, CFG)

    text_blocks = [b for b in blocks if b.kind == "hindi_text"]
    see_also_blocks = [b for b in blocks if b.kind == "see_also"]

    # Prose: redlink + connector dropped
    assert len(text_blocks) == 1
    assert "देखें" not in text_blocks[0].text_devanagari
    assert "वह वह नाम" not in text_blocks[0].text_devanagari
    assert text_blocks[0].text_devanagari.startswith("•")
    assert text_blocks[0].text_devanagari.endswith("परमात्मा")  # no trailing " - "

    # Relation: still emitted, target_exists=false
    assert len(see_also_blocks) == 1
    assert see_also_blocks[0].target_keyword == "वह वह नाम"
    assert see_also_blocks[0].target_exists is False
```

### 1.2 `tests/unit/test_definitions.py` — extend

```python
def test_label_before_dekhen_creates_synthetic_topic():
    """The label `बहिरात्मा, अंतरात्मा व परमात्मा` becomes one
    synthetic Topic (NOT three — commas are not delimiters)."""
    result = parse_keyword(load_fixture("आत्मा.html"))
    sk = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

    # Walk the whole subsection tree
    all_subs = list(walk_subsection_tree(sk.subsections))
    label_topics = [s for s in all_subs if s.label_topic_seed]

    matched = [s for s in label_topics
               if s.heading_text == "बहिरात्मा, अंतरात्मा व परमात्मा"]
    assert len(matched) == 1
    t = matched[0]
    assert t.is_synthetic is True
    assert t.is_leaf is True
    assert t.topic_path is None        # synthetic from prose, no numeric path
    assert t.label_topic_seed is True


def test_label_topic_natural_key_no_comma_split():
    """Commas in the label are kept verbatim in the slug; no splitting."""
    label = "बहिरात्मा, अंतरात्मा व परमात्मा"
    expected_slug = "बहिरात्मा-अंतरात्मा-व-परमात्मा"   # commas dropped via strip_chars, not split
    assert slug(label, CFG) == expected_slug
```

### 1.3 Idempotency contract test

```python
def test_envelope_idempotency_contract_present():
    result = parse_keyword(load_fixture("आत्मा.html"))
    env = build_envelope(result)
    pg_topics = env.would_write["postgres"]["topics"]
    assert all("idempotency_contract" in t for t in pg_topics)
    sample = pg_topics[0]["idempotency_contract"]
    assert sample["conflict_key"] == ["natural_key"]
    assert sample["on_conflict"] == "do_update"
    assert "fields_replace" in sample
    assert "fields_append" in sample
```

---

## 2. YAML / config additions

```yaml
redlink:
  enabled: true
  anchor_class: "new"
  title_marker_re: '^.+\(page does not exist\)\s*$'
  href_marker_substring: "redlink=1"
  prose_strip:
    enabled: true
    # Greedy back-strip: from the anchor's start, walk back over leading
    # punct + trigger word + connector punct + whitespace, removing them.
    connector_re: '\s*[\-–]\s*$'    # the stuff between label and trigger
    # The trigger itself is taken from index.see_also_triggers (phase 1)

label_to_topic:
  enabled: true
  # Trigger from which we infer "label is a topic seed":
  # only when the trigger anchor is a redlink OR a same-keyword self-link
  # OR a wiki link. (i.e., always — this knob lets us turn it off.)
  emit_for_redlink: true
  emit_for_wiki_link: true
  emit_for_self_link: true
  # If the prose has a leading bullet, strip it before slugging.
  bullet_prefixes: ["•", "·", "*", "-"]
  # Trim chars from the label after bullet-strip, before slugging.
  label_trim_chars: " \t।॥"
  # Where to attach the synthetic topic:
  attach_to: "current_subsection"   # | "section_root"
  # Resulting topic flags:
  is_synthetic: true
  is_leaf: true
  source_marker: "label_seed"       # written to topic.source_subkind
```

`config.py` adds matching Pydantic models with these defaults.

---

## 3. Pydantic model changes

### 3.1 `models.py` — `Subsection`

Add three fields, all optional with defaults to preserve existing
goldens shape during transition:

```python
class Subsection(BaseModel):
    ...
    # NEW — phase 3
    label_topic_seed: bool = False              # True when produced by Phase 3 §1.2
    source_subkind: Optional[str] = None        # "label_seed" | None
    idempotency_contract: dict = Field(default_factory=dict)
```

### 3.2 `models.py` — `Block` (already has see_also fields)

No new fields required for `Block`. The redlink-strip already works
through existing `target_exists=false`.

### 3.3 `topic_path` allowed to be None

`Subsection.topic_path` is currently `str` (required). For label
seeds, `topic_path` is `None` because there is no numeric path in the
HTML. Make it `Optional[str]`:

```python
class Subsection(BaseModel):
    topic_path: Optional[str] = None
```

Update all readers (`envelope.py`, `parse_subsections.py`) to handle
`None`. Postgres schema (`schema_updates.md`) already allows `NULL`
on `topic_path` (it's `TEXT`, no NOT NULL).

---

## 4. Algorithms

### 4.1 Redlink detection (`see_also.py`)

```python
def is_redlink_anchor(a: Node, config: JainkoshConfig) -> bool:
    if not config.redlink.enabled:
        return False
    href = a.attributes.get("href", "") or ""
    if config.redlink.href_marker_substring in href:
        return True
    cls = (a.attributes.get("class", "") or "").split()
    if config.redlink.anchor_class in cls:
        title = a.attributes.get("title", "") or ""
        if re.match(config.redlink.title_marker_re, title):
            return True
    return False
```

`parse_anchor` already handles `redlink=1` → `target_exists=false`,
so no behaviour change needed there.

### 4.2 Prose-strip (`parse_blocks.py` / `see_also.py`)

When `make_block` finds see_also anchors via
`find_see_alsos_in_element`, after building the `Block(..., text_devanagari=text)`:

```python
for sa in see_alsos:
    if not config.redlink.prose_strip.enabled:
        continue
    if not sa.target_exists:
        # Drop the trigger + anchor + connector from text_devanagari.
        text = strip_dekhen_redlink_substring(
            text=text,
            anchor_text=anchor_visible_text(sa),
            triggers=config.index.see_also_triggers,
            connector_re=config.redlink.prose_strip.connector_re,
        )
block.text_devanagari = text
```

`strip_dekhen_redlink_substring` (new helper in `see_also.py`):

```python
def strip_dekhen_redlink_substring(text: str, anchor_text: str,
                                   triggers: list[str], connector_re: str) -> str:
    triggers_alt = "|".join(re.escape(t) for t in sorted(triggers, key=len, reverse=True))
    pattern = (
        r"(?P<connector>" + connector_re.rstrip("$") + r")"
        r"(?P<trigger>" + triggers_alt + r")"
        r"\s*" + re.escape(anchor_text) + r"\s*"
    )
    return re.sub(pattern, "", text, count=1).rstrip(" -–\t")
```

Also handle the case where the *whole `<li>` or `<p>` becomes empty*
after stripping: drop the empty block (existing
`blocks_to_drop_when_empty` rule already covers this once
`text.strip()` is empty).

### 4.3 Label → synthetic topic emission

Where: `parse_subsections.py`, after `parse_block_stream_with_text`
returns the body block list for a subsection. Walk the blocks; for
each `Block(kind="see_also")` whose paired prose contains a "label"
prefix, emit a child `Subsection` on the current node (or on the
section root if outside any subsection).

#### 4.3.1 Pairing prose ↔ see_also block

In phase 2 we changed block emission to call
`parse_block_stream_with_text`. After that returns, walk the result:

```python
def extract_label_topic_seeds(
    blocks: list[Block],
    *,
    parent_subsection: Optional[Subsection],
    keyword: str,
    config: JainkoshConfig,
) -> list[Subsection]:
    if not config.label_to_topic.enabled:
        return []
    seeds: list[Subsection] = []
    for i, b in enumerate(blocks):
        if b.kind != "see_also":
            continue
        if not _should_emit_for_anchor(b, config):
            continue
        # The prose block immediately before the see_also (in document order)
        # is the label-bearer.
        prose = _find_preceding_text_block(blocks, i)
        if prose is None:
            continue
        label = _extract_label_before_trigger(prose.text_devanagari, config)
        if not label:
            continue
        seeds.append(_make_label_seed_subsection(
            label=label, keyword=keyword,
            parent=parent_subsection, config=config))
    return seeds
```

`_extract_label_before_trigger`:

```python
def _extract_label_before_trigger(text: str, config) -> str:
    triggers = sorted(config.index.see_also_triggers, key=len, reverse=True)
    for t in triggers:
        idx = text.rfind(t)
        if idx > 0:
            label = text[:idx]
            for bullet in config.label_to_topic.bullet_prefixes:
                label = label.lstrip(bullet)
            label = re.sub(r"[\-–]\s*$", "", label)
            label = label.strip(config.label_to_topic.label_trim_chars + " \t\n")
            return label
    return ""
```

`_should_emit_for_anchor` honours
`emit_for_redlink/wiki_link/self_link` knobs.

`_make_label_seed_subsection` constructs the `Subsection`:

```python
def _make_label_seed_subsection(*, label, keyword, parent, config) -> Subsection:
    sl = slug(label, config)
    parts = [keyword]
    if parent is not None:
        parts = [parent.natural_key]
    nk = ":".join(parts + [sl])
    return Subsection(
        topic_path=None,
        heading_text=label,
        heading_path=(parent.heading_path if parent else []) + [label],
        natural_key=nk,
        parent_natural_key=(parent.natural_key if parent else None),
        is_leaf=True,
        is_synthetic=True,
        label_topic_seed=True,
        source_subkind=config.label_to_topic.source_marker,
        blocks=[],
        children=[],
        idempotency_contract={
            "conflict_key": ["natural_key"],
            "on_conflict": "do_update",
            "fields_replace": ["display_text", "is_leaf", "is_synthetic", "parent_topic_natural_key", "topic_path", "source", "source_subkind"],
            "fields_append": [],
            "fields_skip_if_set": [],
            "stores": ["postgres", "mongo:topic_extracts", "neo4j:Topic"],
        },
    )
```

The orchestrator (out of scope here) reads `idempotency_contract` to
decide whether to overwrite or append a particular field on a
re-ingest.

#### 4.3.2 Attachment

In `parse_subsections.parse_subsections`, after `parse_block_stream`
returns blocks for a subsection node, call
`extract_label_topic_seeds` and append the seeds to `node.children`.
Re-mark `node.is_leaf = False` if seeds were appended.

For label seeds emitted **outside** any subsection (at section root —
e.g. when a HindiText with `देखें` appears before the first numeric
heading), attach to the `PageSection` directly. Add a new field on
`PageSection`:

```python
class PageSection(BaseModel):
    ...
    label_topic_seeds: list[Subsection] = Field(default_factory=list)
```

(Keep separate from `subsections` so the numeric-tree topology stays
unambiguous.)

---

## 5. Idempotency contract — emission for **all** envelope rows

### 5.1 Keyword

```python
keyword_row["idempotency_contract"] = {
    "conflict_key": ["natural_key"],
    "on_conflict": "do_update",
    "fields_replace": ["display_text", "source_url"],
    "fields_append": ["definition_doc_ids"],
    "fields_skip_if_set": [],
    "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"],
}
```

### 5.2 Topic (numeric-tree)

```python
topic_row["idempotency_contract"] = {
    "conflict_key": ["natural_key"],
    "on_conflict": "do_update",
    "fields_replace": ["topic_path", "display_text", "parent_topic_natural_key", "is_leaf", "is_synthetic", "source"],
    "fields_append": [],
    "fields_skip_if_set": [],
    "stores": ["postgres:topics", "mongo:topic_extracts", "neo4j:Topic"],
}
```

### 5.3 Topic (label seed)

(See §4.3.1.)

### 5.4 Keyword aliases (placeholder for Phase ≥ orchestrator)

```python
"keyword_aliases": []   # reserved; orchestrator fills with idempotency_contract
```

---

## 6. Edge cases

| Case | Expected |
|------|----------|
| Redlink anchor with no preceding `देखें` | Treat as a regular link (parser doesn't drop prose; no see_also emitted). |
| Redlink anchor preceded by `विशेष देखें` | Same handling — both triggers honoured. |
| Multiple redlinks in same paragraph | Each independently stripped + each gets its own see_also block + (if label can be extracted) its own label seed. Labels for adjacent redlinks share the same prose only when the prose actually contains multiple labelled segments. **Default**: only emit a label seed for the FIRST trigger in a block; subsequent triggers in the same block emit see_also only. (Configurable later if needed.) |
| Label is empty after bullet/connector strip | Don't emit a label seed (still emit the see_also relation). |
| Label seed slug collides with an existing numeric-tree topic | Conflict key (`natural_key`) wins: orchestrator's `ON CONFLICT DO UPDATE` overwrites. The `is_synthetic`/`label_topic_seed` flags MAY change on re-ingest if the human later declares it as a numeric subsection. |
| `topic_path = None` in PG | Allowed (column is nullable). The `idx_topics_keyword_path` index is non-unique; multiple `(parent_keyword_id, NULL)` rows are permitted. |
| Re-ingestion (idempotency check) | Re-running the parser produces **byte-identical** envelope (frozen-time). Re-running orchestrator with the same envelope produces **zero** net DB changes (the contract makes this the orchestrator's guarantee — outside parser-only scope, but documented). |

---

## 7. Verification

```bash
pytest workers/ingestion/jainkosh/tests/unit/test_see_also.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_definitions.py -x
pytest workers/ingestion/jainkosh/tests/unit/test_topic_keys.py -x
pytest workers/ingestion/jainkosh/tests/unit/ -x
```

Then regenerate goldens. Expected diff highlights:

- `आत्मा` SiddhantKosh: a new `label_topic_seeds` entry under one of
  the subsections, with heading `बहिरात्मा, अंतरात्मा व परमात्मा`.
- `text_devanagari` of the prose block lost the ` - देखें वह वह नाम` suffix.
- All `topic_rows` in `would_write.postgres.topics` carry an
  `idempotency_contract` dict.

Manually review the diff and accept per the README "Goldens" process.
