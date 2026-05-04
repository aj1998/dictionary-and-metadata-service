# JainKosh Parser — Implementation Spec

> Implementation guide for the **standalone, parser-only** stage of the
> JainKosh ingestion pipeline. This stage reads pre-saved HTML files
> from `samples/sample_html_jainkosh_pages/` (no HTTP, no DB writes)
> and produces a structured `KeywordParseResult` JSON document per
> page, plus a "would-write" envelope showing exactly what each store
> (Postgres / Mongo / Neo4j) would receive on approval.
>
> Rules: see [`parsing_rules.md`](./parsing_rules.md). Schema changes:
> see [`schema_updates.md`](./schema_updates.md). Pipeline / fetch /
> alias mining: see [`../08_ingestion_jainkosh.md`](../08_ingestion_jainkosh.md).
>
> **Fixes applied in v1.1.0**: see
> [`parser_fix_spec_001/README.md`](./parser_fix_spec_001/README.md)
> for the full phased correction spec (configurable triggers, ref-strip,
> sibling-`=` marker, redlink prose-strip, label→topic seeds, table
> attachment, IndexRelation chain, idempotency contracts).
>
> **Fixes applied in v1.2.0**: see
> [`parser_fix_spec_002/README.md`](./parser_fix_spec_002/README.md)
> for the full phased correction spec (table outerHTML + raw_html whitespace
> collapse, idempotency contracts hoisted to envelope root, IndexRelation
> source chain resolution, DFS leading-GRef passthrough, paren-`देखें`
> cleanup, label-seed scope guard, see-also-only block drop, definition
> `(N)` numbering strip, redlink edge suppression).
>
> **Fixes applied in v1.3.0**: see
> [`parser_fix_spec_003/parser_fix_spec_003.md`](./parser_fix_spec_003/parser_fix_spec_003.md)
> for the full phased correction spec (row-style `see_also` relocation from
> parent blocks to child label-seed blocks; `RELATED_TO` edges now sourced
> from child seed natural key; redlink row detection at DOM level before
> text stripping).
>
> **Fixes applied in v1.5.0**: see
> [`parser_fix_spec_005/README.md`](./parser_fix_spec_005/README.md)
> for the full phased correction spec (GRef attribution across nested-span
> `<br/>` boundaries; parser version bump and golden regeneration).
>
> **Fixes applied in v1.6.0**: see
> [`parser_fix_spec_006/README.md`](./parser_fix_spec_006/README.md)
> for the full phased correction spec (label_seed `RELATED_TO` edges now
> sourced from child natural_key via see_also block relocation; `inline_reference`
> flag on `Reference`; nth-occurrence anchor dedup fixes duplicate `IndexRelation`
> and missing entry).
>
> Audience: any implementer (including small reasoning models) who has
> not been part of the design conversation. Every decision is named.

---

## 0. Scope

### In scope
- Pure HTML→JSON parsing for one keyword page.
- A YAML rule config so heading variants, block class mapping, etc.
  are data-driven and extensible without code changes.
- A CLI: `python -m workers.ingestion.jainkosh.cli parse <file.html> --out <out.json>`.
- Pydantic v2 models for every intermediate type.
- "Would-write" envelope: Postgres rows + Mongo doc + Neo4j fragments.
- Pytest suite with golden JSON for the three sample pages.

### Out of scope (later stages)
- Fetching, rate limiting, retries, snapshot writing.
- Real DB writes or Mongo upserts.
- Alias mining via the MediaWiki API.
- Orchestrator / Celery wiring.
- Admin review queue.

---

## 1. File layout

```
workers/ingestion/jainkosh/
├── __init__.py
├── cli.py                 # `python -m workers.ingestion.jainkosh.cli ...`
├── config.py              # Pydantic models for the YAML rules + loader
├── models.py              # Pydantic models for parser output (KeywordParseResult, ...)
├── normalize.py           # NFC, ZWJ/ZWNJ, whitespace, slug
├── selectors.py           # CSS selector + class constants (defaults)
├── parse_keyword.py       # public entry: parse_keyword_html(html, url, config) -> KeywordParseResult
├── parse_section.py       # one section (h2 → next h2)
├── parse_index.py         # leading <ol>/<ul> index → IndexRelation list
├── parse_subsections.py   # heading detection + tree assembly
├── parse_blocks.py        # block stream: refs, sanskrit, prakrit, hindi, table, see_also
├── parse_definitions.py   # pre-heading content → Definition list (siddhantkosh + puraankosh)
├── refs.py                # GRef extraction (leading vs trailing)
├── see_also.py            # देखें detection (index + inline)
├── topic_keys.py          # natural_key, slug, tree path math, parent inference
├── nav.py                 # पूर्व पृष्ठ / अगला पृष्ठ extraction & drop
├── tables.py              # table block extraction (raw_html)
├── envelope.py            # build the "would_write" envelope (pg/mongo/neo4j fragments)
└── tests/
    ├── __init__.py
    ├── fixtures/                                            # symlink or copy of samples/sample_html_jainkosh_pages/
    │   ├── आत्मा.html
    │   ├── द्रव्य.html
    │   └── पर्याय.html
    ├── golden/
    │   ├── आत्मा.json
    │   ├── द्रव्य.json
    │   └── पर्याय.json
    ├── unit/
    │   ├── test_normalize.py
    │   ├── test_topic_keys.py
    │   ├── test_heading_variants.py     # V1..V5 with inline HTML strings
    │   ├── test_refs.py
    │   ├── test_see_also.py
    │   ├── test_nested_span.py
    │   ├── test_translation_marker.py
    │   ├── test_index_relations.py
    │   └── test_definitions.py
    └── test_parse_keyword_golden.py     # snapshot tests against goldens

parser_configs/
├── jainkosh.yaml          # the parsing-rules config (schema-validated)
└── _schemas/
    └── jainkosh.schema.json
```

A `__main__.py` re-exporting `cli.main` is not required; tests invoke
the CLI via `python -m workers.ingestion.jainkosh.cli`.

---

## 2. Library choices

| Concern | Library | Why |
|---------|---------|-----|
| HTML parsing | **`selectolax`** (`HTMLParser`) | Already in `00_overview.md` stack; fast; CSS selectors; safer than BeautifulSoup for malformed wiki HTML. |
| YAML | `PyYAML` | Standard. |
| Pydantic | v2 | Stack default. |
| JSON schema | `jsonschema` (test-only) | Validate `parser_configs/jainkosh.yaml` in a unit test. |
| Slug | hand-rolled (Devanagari-aware) | No external slugger handles Devanagari. |
| NFC / ZWJ / ZWNJ | `unicodedata` (stdlib) | Sufficient. |

The parser is **synchronous, pure-Python**. No async, no I/O beyond
reading the input HTML file.

---

## 3. Configuration: `parser_configs/jainkosh.yaml`

The config is the single source of truth for *which DOM patterns map
to which logical concept*. Adding a heading variant or a block class
must not require code changes.

### 3.1 Top-level shape

```yaml
version: "1.2.0"
parser_rules_version: "jainkosh.rules/1.2.0"        # mirrored into output

normalization:
  nfc: true
  strip_zwj: true
  strip_zwnj: true
  collapse_whitespace: true
  br_to_newline: true

sections:
  selector: "div.mw-parser-output"
  h2_headline_selector: "h2 span.mw-headline"
  kinds:
    - id: "सिद्धांतकोष_से"
      kind: "siddhantkosh"
    - id: "पुराणकोष_से"
      kind: "puraankosh"
  default_kind: "misc"

definitions:
  siddhantkosh:
    # Each [GRef] starts a new Definition. A leading <p class="HindiText">
    # without a preceding GRef is also one Definition (intro paragraph).
    boundary: "leading_reference_or_intro"
  puraankosh:
    # If the inner <div class="HindiText"> contains <p id="N">, treat each
    # as a separate Definition; else, the whole inner block is one Definition.
    boundary: "p_with_id_or_whole_block"

index:
  enabled_for: ["siddhantkosh"]   # PuranKosh has no index
  outer_list_selector: "ol"
  inner_anchor_ignore_selector: "ol li a[href^='#']"
  see_also_list_selector: "ul"
  self_link_class: "mw-selflink-fragment"
  # v1.1.0 — configurable trigger list (phase 1)
  see_also_triggers:
    - "देखें"
    - "विशेष देखें"
  see_also_window_chars: 40
  see_also_leading_punct_re: '[(–\-।\s]*'
  # deprecated; auto-built from above if absent
  see_also_text_pattern: '(?:[(–\-]\s*)?(?:विशेष\s+)?देखें\s*'

block_classes:
  # CSS class on a <p> or <span> → block kind
  SanskritText: "sanskrit_text"
  SanskritGatha: "sanskrit_gatha"
  PrakritText: "prakrit_text"
  PrakritGatha: "prakrit_gatha"
  HindiText: "hindi_text"
  HindiGatha: "hindi_gatha"

reference:
  selector: "span.GRef"
  strip_inner_anchors: true     # <a href> inside GRef → keep visible text only

translation_marker:
  prefix: "="                   # leading "=" in a HindiText block = translation of preceding source-block
  source_kinds: ["sanskrit_text", "sanskrit_gatha", "prakrit_text", "prakrit_gatha"]
  hindi_kinds:   ["hindi_text", "hindi_gatha"]

nested_span:
  flatten: true                 # see parsing_rules.md §6.4
  outer_kinds: ["sanskrit_text", "prakrit_text", "hindi_text"]

table:
  selector: "table"
  store_raw_html: true
  extraction_strategy: "raw_html_only"      # | "raw_html_plus_rows" (future)
  attach_to: "current_subsection"           # v1.1.0 changed from "section_extra_blocks"
  fallback_when_no_subsection: "section_root"

navigation:
  drop: true
  prev_text: "पूर्व पृष्ठ"
  next_text: "अगला पृष्ठ"
  containing_tag: "p"

emphasis:
  bold_to_markdown: true        # <b>/<strong> inline → **x**
  italic_to_markdown: true      # <i>/<em> inline → *x*

headings:
  variants:
    - name: V1
      selector: "strong[id]"
      id_from: "self.attribute(id)"
      heading_text: "self.text"
    - name: V2
      selector: "span.HindiText[id] > strong"
      id_from: "parent.attribute(id)"
      heading_text: "self.text"
    - name: V3
      selector: "li[id] > span.HindiText > strong"
      id_from: "ancestor::li[1].attribute(id)"
      heading_text: "self.text"
    - name: V4
      selector: "p.HindiText > b:only-child"
      id_from: "regex_group(self.text, 'topic_path')"
      heading_text: "regex_group(self.text, 'heading')"
      regex: '^\s*(?P<topic_path>\d+(?:\.\d+)*)[.\s]+(?P<heading>.+?)\s*$'

slug:
  preserve_devanagari: true
  strip_chars: "।॥.,;:!?()[]{}'\"`-"
  whitespace_to: "-"
  collapse_dashes: true
  strip_v4_numeric_prefix: true

bullet_strip:
  prefixes: ["•", "·", "*", "-"]
  trailing_punct: ["।", "॥"]

blocks_to_drop_when_empty:
  - "p"        # <p><br/></p> after stripping
  - "div"

# v1.1.0 additions (parser_fix_spec_001)
ref_strip:
  enabled: true
  collapse_double_spaces: true
  collapse_orphan_parens: true
  collapse_orphan_brackets: true
  trim_trailing_chars: " ।॥;,"

translation_marker:
  # (prefix, source_kinds, hindi_kinds already existed above)
  sibling_marker_enabled: true
  sibling_marker_text_node_re: '^\s*=\s*$'
  reference_ordering: "leading_then_inline"

redlink:
  enabled: true
  anchor_class: "new"
  title_marker_re: '^.+\(page does not exist\)\s*$'
  href_marker_substring: "redlink=1"
  prose_strip:
    enabled: true
    connector_re: '\s*[\-–]\s*$'

label_to_topic:
  enabled: true
  emit_for_redlink: true
  emit_for_wiki_link: true
  emit_for_self_link: true
  bullet_prefixes: ["•", "·", "*", "-"]
  label_trim_chars: " \t।॥"
  attach_to: "current_subsection"
  is_synthetic: true
  is_leaf: true
  source_marker: "label_seed"

reference:
  selector: "span.GRef"
  strip_inner_anchors: true
  parse_strategy: "text_only"    # | "structured" | "text_plus_structured" (future)
```

Variant **V5** is intentionally **not** in `headings.variants` — V5
is a definition pattern, not a heading. It's handled by
`definitions.puraankosh.boundary: p_with_id_or_whole_block`.

### 3.2 Selector DSL semantics

`id_from` and `heading_text` use a tiny path expression:

| Expression                      | Meaning                                       |
|--------------------------------|-----------------------------------------------|
| `self.text`                    | Current node's text content (post-normalize)  |
| `self.attribute(X)`            | Current node's attribute X                    |
| `parent.attribute(X)`          | Direct parent's attribute X                   |
| `ancestor::tag[N].attribute(X)` | Nth-nearest ancestor `<tag>`'s attribute X    |
| `regex_group(text, name)`      | Apply `regex:` to `text`, return named group  |

If multiple variants match the same DOM node, the first match (by
order in the YAML) wins. Implementation: try variants in order; on
first hit, record (`topic_path`, `heading_text`) and stop.

### 3.3 Schema validation

`parser_configs/_schemas/jainkosh.schema.json` defines the JSON Schema
for §3.1. The parser loads `jainkosh.yaml`, runs it through
`jsonschema.validate(...)`, and fails fast if invalid. A unit test
asserts the bundled YAML validates.

---

## 4. Pydantic models (`workers/ingestion/jainkosh/models.py`)

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional
from datetime import datetime

# ----------------------- atomic types -----------------------

class Multilingual(BaseModel):
    lang: str       # ISO-639-3 ("hin", "san", "pra")
    script: str     # ISO-15924 ("Deva")
    text: str

class ParsedReference(BaseModel):
    """Reserved for future structured extraction (v1.1.0: always None)."""
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
    raw_html: Optional[str] = None     # for debug
    parsed: Optional[ParsedReference] = None   # v1.1.0 template; always None until future phase

# ----------------------- block -----------------------

BlockKind = Literal[
    "sanskrit_text", "sanskrit_gatha",
    "prakrit_text",  "prakrit_gatha",
    "hindi_text",    "hindi_gatha",
    "table", "see_also",
]

class Block(BaseModel):
    kind: BlockKind

    # body text (Devanagari, NFC) — present for sanskrit/prakrit/hindi *_text/*_gatha
    text_devanagari: Optional[str] = None

    # for source-language blocks: the "= …" Hindi translation following them
    hindi_translation: Optional[str] = None

    # GRef(s) cited by this block (leading or trailing)
    references: list[Reference] = Field(default_factory=list)

    # for source-language blocks where the leading "=" was orphan (no source block to attach to)
    is_orphan_translation: bool = False

    # for kind == "table"
    raw_html: Optional[str] = None
    table_rows: Optional[list[list[str]]] = None   # v1.1.0 template; populated when extraction_strategy="raw_html_plus_rows"

    # for kind == "see_also"
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None     # e.g. "1.2", "II.3.3"
    target_url: Optional[str] = None
    is_self: bool = False
    target_exists: bool = True                  # false if href is a redlink

# ----------------------- definition (no heading) -----------------------

class Definition(BaseModel):
    definition_index: int                       # 1-based, per section
    blocks: list[Block]
    raw_html: Optional[str] = None              # debug

# ----------------------- subsection (topic seed) -----------------------

class Subsection(BaseModel):
    topic_path: Optional[str] = None            # "1.1.3"; None for label-seed topics (v1.1.0)
    heading_text: str                           # plain Devanagari, post-normalize
    heading_path: list[str]                     # e.g. ["द्रव्य के भेद व लक्षण", "द्रव्य का निरुक्त्यर्थ"]
    natural_key: str                            # "द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ"
    parent_natural_key: Optional[str]           # None for top-level (path "1", "2", …)
    is_leaf: bool
    is_synthetic: bool = False                  # parent inferred but not declared in HTML
    blocks: list[Block]
    children: list["Subsection"]                # nested
    # v1.1.0 — label-seed fields
    label_topic_seed: bool = False              # True when synthesised from prose label before देखें
    source_subkind: Optional[str] = None        # "label_seed" | None
    # idempotency_contract removed in v1.2.0 — contracts are now at envelope root (parsing_rules §3.4)

Subsection.model_rebuild()

# ----------------------- index relation -----------------------

class IndexRelation(BaseModel):
    label_text: str                             # the descriptive text in the <li>, before the link
    target_keyword: Optional[str]               # NFC-decoded keyword name
    target_topic_path: Optional[str]            # parsed from URL fragment "#…"
    target_url: str                             # the original href
    is_self: bool = False                       # via class="mw-selflink-fragment"
    target_exists: bool = True                  # false for redlinks

    # source of relation: None = keyword-level, "1" = top-level section 1, "1.1" = subsection
    # source_topic_path removed in v1.2.0 (was deprecated in v1.1.0)
    # v1.1.0 — full ancestor chain (resolution improved in v1.2.0 via ancestor <strong> text lookup)
    source_topic_path_chain: list[str] = Field(default_factory=list)           # e.g. ["1", "1.2"]
    source_topic_natural_key_chain: list[str] = Field(default_factory=list)    # resolved natural keys

# ----------------------- section -----------------------

SectionKind = Literal["siddhantkosh", "puraankosh", "misc"]

class PageSection(BaseModel):
    section_kind: SectionKind
    section_index: int                          # 0-based document order
    h2_text: str                                # raw heading ("सिद्धांतकोष से")
    definitions: list[Definition]               # see parsing_rules §3
    index_relations: list[IndexRelation]        # see parsing_rules §4
    subsections: list[Subsection]               # tree, top-level only
    extra_blocks: list[Block] = Field(default_factory=list)   # orphan tables before first heading (parsing_rules §6.5)
    # v1.1.0 — label-seed topics at section root (outside any numeric subsection)
    label_topic_seeds: list[Subsection] = Field(default_factory=list)

# ----------------------- top-level result -----------------------

class Nav(BaseModel):
    prev: Optional[str] = None                  # /wiki/X
    next: Optional[str] = None                  # /wiki/Y

class KeywordParseResult(BaseModel):
    keyword: str                                # NFC, e.g. "द्रव्य"
    source_url: str
    page_sections: list[PageSection]
    nav: Nav
    parser_version: str                         # "jainkosh.rules/1.0.0"
    parsed_at: datetime

# ----------------------- envelope (would_write) -----------------------

class WouldWriteEnvelope(BaseModel):
    """What each store would receive on approval. No DB writes happen."""
    keyword_parse_result: KeywordParseResult
    would_write: dict                           # see envelope.py §6
```

`KeywordParseResult` and `WouldWriteEnvelope` are the JSON shapes
written to `--out`. Goldens compare against `WouldWriteEnvelope`.

---

## 5. Algorithms

### 5.1 `parse_keyword_html(html, url, config) -> KeywordParseResult`

```python
def parse_keyword_html(html: str, url: str, config: JainkoshConfig) -> KeywordParseResult:
    tree = HTMLParser(html)
    main = tree.css_first(config.sections.selector)        # div.mw-parser-output
    if main is None:
        raise ParseError("no mw-parser-output found")

    keyword = nfc(decode_keyword_from_url(url))            # url-decode + NFC + ZWJ/ZWNJ strip
    nav = extract_nav(main, config)                         # remove पूर्व/अगला from main beforehand
    drop_nav_nodes(main, nav, config)

    h2_nodes = main.css(config.sections.h2_headline_selector)
    page_sections = []

    for i, h2 in enumerate(h2_nodes):
        section_kind = classify_section(h2, config)
        section_dom = collect_siblings_until_next_h2(h2)    # list of top-level elements
        section = parse_section(section_dom,
                                section_kind=section_kind,
                                section_index=i,
                                h2_text=clean_text(h2.text()),
                                keyword=keyword,
                                config=config)
        page_sections.append(section)

    return KeywordParseResult(
        keyword=keyword,
        source_url=url,
        page_sections=page_sections,
        nav=nav,
        parser_version=config.parser_rules_version,
        parsed_at=datetime.utcnow(),
    )
```

### 5.2 `parse_section(elements, ...) -> PageSection`

The trickiest function. Pseudocode:

```python
def parse_section(elements, *, section_kind, section_index, h2_text, keyword, config) -> PageSection:
    # Phase 1: split elements into [pre_heading, index, body, extra_tables].
    # An element belongs to "index" if it is a top-level <ol> AND no <strong[id]> heading
    # has been seen yet AND the <ol> contains no headings at any depth.
    # Once we see the first heading-bearing element, "body" begins.
    pre_heading: list[el] = []
    index_ols:   list[el] = []
    body:        list[el] = []
    tables:      list[el] = []

    seen_first_heading = False
    for el in elements:
        if el.tag == "table":
            tables.append(el); continue
        if not seen_first_heading and el.tag == "ol" and not contains_heading(el, config):
            index_ols.append(el); continue
        if not seen_first_heading and not contains_heading(el, config):
            pre_heading.append(el); continue
        # We've reached body.
        seen_first_heading = True
        body.append(el)

    # Phase 2: definitions (parsing_rules §3)
    if section_kind == "siddhantkosh":
        definitions = parse_siddhantkosh_definitions(pre_heading, config)
    elif section_kind == "puraankosh":
        definitions = parse_puraankosh_definitions(pre_heading, config)
    else:
        definitions = parse_siddhantkosh_definitions(pre_heading, config)  # default

    # Phase 3: index relations (parsing_rules §4)
    index_relations = parse_index_relations(index_ols, keyword, config) if section_kind == "siddhantkosh" else []

    # Phase 4: subsections tree (parsing_rules §5)
    subsections = parse_subsections(body, keyword, config)

    # Phase 5: section-level tables (parsing_rules §6.5)
    extra_blocks = [Block(kind="table", raw_html=html_of(t)) for t in tables]

    return PageSection(
        section_kind=section_kind,
        section_index=section_index,
        h2_text=h2_text,
        definitions=definitions,
        index_relations=index_relations,
        subsections=subsections,
        extra_blocks=extra_blocks,
    )
```

`contains_heading(el, config)` returns True iff any `<strong[id]>`,
`<span class="HindiText"[id]>`, `<li[id]>` with the right shape, or
`<p class="HindiText"><b>` matching V4 regex appears as a descendant.
This single function is what differentiates "the leading `<ol>` is an
index" from "the leading `<ol>` is the body".

### 5.3 Definition parsing

```python
def parse_siddhantkosh_definitions(pre_heading_elements, config) -> list[Definition]:
    # A "leading reference" is a <p> whose only meaningful children are <span class="GRef">,
    # OR a bare <span class="GRef"> at the top level.
    # A new GRef starts a new Definition; intervening blocks are appended to the current.
    defs: list[Definition] = []
    cur: list[Block] = []
    pending_refs: list[Reference] = []

    for el in pre_heading_elements:
        if is_leading_reference(el, config):
            # Close current def if it has any blocks; start new.
            if cur:
                defs.append(Definition(definition_index=len(defs)+1, blocks=cur))
                cur = []
            pending_refs.extend(extract_refs(el, config))
            continue
        # Otherwise, it's a body block — emit it.
        block = make_block(el, config)
        if block is None:
            continue
        # Apply translation-marker logic (§5.5)
        cur, pending_refs = apply_translation_marker(cur, block, pending_refs, config)

    # Flush final def.
    if cur:
        defs.append(Definition(definition_index=len(defs)+1, blocks=cur))
    elif pending_refs:
        # orphan reference — make a definition with just the reference attached to nothing
        # This is rare; emit an empty hindi_text block carrying the refs.
        defs.append(Definition(
            definition_index=len(defs)+1,
            blocks=[Block(kind="hindi_text", text_devanagari="", references=pending_refs)],
        ))

    return defs

def parse_puraankosh_definitions(pre_heading_elements, config) -> list[Definition]:
    # PuranKosh content is wrapped in <div class="HindiText">. Two patterns:
    #   (a) Multiple <p id="N" class="HindiText">(N) …</p> → N definitions.
    #   (b) One <p class="HindiText">…</p> → one definition.
    inner = first_child_div(pre_heading_elements, "HindiText")
    if inner is None:
        # fallback: treat each pre_heading <p> as its own block, one definition
        return [make_definition_from_blocks(make_blocks(pre_heading_elements, config))]

    p_with_id = inner.css("p[id]")
    if len(p_with_id) >= 2 or (len(p_with_id) == 1 and starts_with_paren_number(p_with_id[0])):
        defs = []
        for p in p_with_id:
            block = make_block(p, config)
            defs.append(Definition(definition_index=len(defs)+1, blocks=[block]))
        return defs

    # Single-paragraph case
    block = make_block(inner.css_first("p.HindiText") or inner, config)
    return [Definition(definition_index=1, blocks=[block])]
```

### 5.4 Subsection tree assembly (`parse_subsections.py`)

```python
def parse_subsections(body_elements, keyword: str, config) -> list[Subsection]:
    flat: list[tuple[str, str, list[el]]] = walk_and_collect_headings(body_elements, config)
    # Each tuple: (topic_path, heading_text, content_elements_until_next_heading_at_any_level)

    # Build tree by topic_path.
    nodes: dict[str, Subsection] = {}      # path → node
    roots: list[Subsection] = []

    for path, heading_text, content_els in flat:
        parent_path = parent_of(path)      # "1.1.3" → "1.1"; "1" → None
        ensure_ancestors_exist(path, nodes, roots, keyword)
        blocks = parse_block_stream(content_els, config)
        node = build_subsection_node(path, heading_text, blocks,
                                     parent_path, keyword, nodes)
        nodes[path] = node
        attach_to_parent(node, parent_path, nodes, roots)

    # Mark is_leaf bottom-up.
    for n in nodes.values():
        n.is_leaf = (len(n.children) == 0)

    return roots

def parent_of(path: str) -> Optional[str]:
    if "." not in path:
        return None
    return path.rsplit(".", 1)[0]

def ensure_ancestors_exist(path, nodes, roots, keyword):
    # If "1.1.3" appears but "1.1" doesn't, synthesise "1.1" with empty heading.
    parts = path.split(".")
    for i in range(1, len(parts)):
        p = ".".join(parts[:i])
        if p not in nodes:
            synth = Subsection(
                topic_path=p,
                heading_text="",
                heading_path=[],          # will be filled when (or if) declared later — see §5.4.1
                natural_key=f"{keyword}:" + ":".join(["__synthetic_{}".format(p)]),  # placeholder
                parent_natural_key=None,  # filled later
                is_leaf=False,
                is_synthetic=True,
                blocks=[],
                children=[],
            )
            nodes[p] = synth
            attach_to_parent(synth, parent_of(p), nodes, roots)
```

#### 5.4.1 Synthetic-then-declared resolution

If `1.1` is synthesised (because `1.1.3` appeared first) and `1.1`
is later declared in the HTML, the parser must *replace the synthetic
heading_text and natural_key in place*, preserving children. In
practice this never happens in the three sample pages (parents always
declared first), but the parser implements it defensively.

#### 5.4.2 `walk_and_collect_headings`

This walker tries every heading variant (V1..V4) on every node in
document order. As soon as a node matches a variant, it emits a
`(topic_path, heading_text, content_elements)` tuple where
`content_elements` is everything **after** that heading in document
order until the next heading at *any* level. Because headings can be
deeply nested (V3 puts the heading inside an `<li>`'s `<span>`), the
walker is recursive but yields a flat sequence.

A pragmatic implementation:

1. Recursively traverse the body DOM in pre-order.
2. At each node, try each heading variant in YAML order; first hit
   wins.
3. When a heading is detected, record its position (a global index)
   and `(topic_path, heading_text)`.
4. After full traversal, emit
   `(topic_path, heading_text, dom_slice_between(this_pos, next_pos))`
   for each detected heading, using positions to slice DOM siblings.
5. The "DOM slice" is implemented as a list of nodes that are
   *descendants* of the section root and are document-order between
   the heading and the next heading, **excluding the heading nodes
   themselves and excluding anything that is *inside* a child heading
   under this heading** (the latter is naturally handled because we
   slice up to the next heading's position).

### 5.5 Block stream + translation marker (`parse_blocks.py`)

```python
def parse_block_stream(elements: list[el], config) -> list[Block]:
    out: list[Block] = []
    last_block: Optional[Block] = None
    pending_refs: list[Reference] = []

    for el in flatten_for_blocks(elements, config):
        if is_leading_reference(el, config):
            pending_refs.extend(extract_refs(el, config))
            continue
        if el.tag == "table":
            out.append(Block(kind="table", raw_html=html_of(el)))
            last_block = out[-1]
            continue
        # see_also is detected at the inline level, not the element level — it's emitted
        # as part of make_block when a HindiText paragraph contains a देखें pattern.
        block = make_block(el, config)
        if block is None:
            continue
        if isinstance(block, list):
            # nested-span flatten produced multiple blocks
            for sub in block:
                last_block, pending_refs, out = _emit(sub, last_block, pending_refs, out, config)
        else:
            last_block, pending_refs, out = _emit(block, last_block, pending_refs, out, config)

    if pending_refs and last_block is not None:
        last_block.references.extend(pending_refs)

    return out

def _emit(block, last_block, pending_refs, out, config):
    if (block.kind in config.translation_marker.hindi_kinds
        and block.text_devanagari is not None
        and block.text_devanagari.lstrip().startswith(config.translation_marker.prefix)):
        if last_block is not None and last_block.kind in config.translation_marker.source_kinds:
            last_block.hindi_translation = strip_eq_prefix(block.text_devanagari)
            last_block.references.extend(pending_refs)
            pending_refs.clear()
            return last_block, pending_refs, out
        block.is_orphan_translation = True
        block.text_devanagari = strip_eq_prefix(block.text_devanagari)
    block.references.extend(pending_refs)
    pending_refs.clear()
    out.append(block)
    return out[-1], pending_refs, out
```

### 5.6 Nested-span flatten (`flatten_for_blocks`)

When a `<span class="SanskritText">` contains nested elements that
would be blocks at the top level, we flatten:

```python
def flatten_for_blocks(elements, config):
    if not config.nested_span.flatten:
        yield from elements; return
    for el in elements:
        kind = block_class_kind(el, config)        # None if not a recognised block class
        if kind in config.nested_span.outer_kinds and has_nested_block(el, config):
            yield from explode_nested_span(el, config)
        else:
            yield el

def explode_nested_span(span, config):
    # 1. Emit the outer span's "direct text" as a synthetic <p> of the outer kind.
    #    Direct text = text nodes that are NOT inside any nested element.
    direct = direct_text_of(span)
    if direct.strip():
        yield make_synthetic_node(direct, kind=block_class_kind(span, config))
    # 2. Iterate children left-to-right.
    for child in span.iter():
        if is_leading_reference(child, config) or block_class_kind(child, config) is not None:
            yield child
```

Tests must verify the द्रव्य L734–759 case ends up with the
top-level `गुणैर्गुणान्वा …` as one Sanskrit block, then the nested
`यथास्वं पर्यायैर्…` Sanskrit block + its `=` Hindi translation as
the next block, and so on.

### 5.7 `see_also` extraction (`see_also.py`)

The same function is used by both `parse_index_relations` and
`make_block` (when a HindiText contains a `देखें` link).

```python
SEE_ALSO_TEXT_RE = re.compile(config.index.see_also_text_pattern)

def find_see_alsos_in_element(el, *, source_topic_path: Optional[str] = None) -> list[IndexRelation | Block]:
    # Walk the element's children. For each <a>, check whether the text
    # immediately preceding it (within ~20 chars on the same parent) ends
    # with "देखें" (per the regex). If yes, it's a see_also.
    out = []
    for a in el.css("a"):
        prev_text = preceding_inline_text(a, max_chars=20)
        if not SEE_ALSO_TEXT_RE.search(prev_text):
            continue
        rel = parse_anchor(a, config)            # → (target_keyword, target_topic_path, is_self, target_exists, target_url)
        out.append(rel)
    return out

def parse_anchor(a, config) -> dict:
    href = a.attributes.get("href", "")
    cls  = a.attributes.get("class", "")
    if "redlink=1" in href:
        title = href_query(href, "title") or a.text()
        return dict(target_keyword=nfc(url_decode(title)), target_topic_path=None,
                    target_url=href, is_self=False, target_exists=False)
    if config.index.self_link_class in cls.split():
        # href like "#3" or "#1.2"
        return dict(target_keyword=None, target_topic_path=href.lstrip("#"),
                    target_url=href, is_self=True, target_exists=True)
    if href.startswith("/wiki/"):
        path, _, frag = href[len("/wiki/"):].partition("#")
        return dict(target_keyword=nfc(url_decode(path)),
                    target_topic_path=frag or None,
                    target_url=href, is_self=False, target_exists=True)
    # other shapes — keep as-is
    return dict(target_keyword=None, target_topic_path=None,
                target_url=href, is_self=False, target_exists=True)
```

When the parent context is the index (i.e., we're inside
`parse_index_relations`), we wrap each parsed anchor in
`IndexRelation`. When the parent is a body block, we instead emit a
`Block(kind="see_also", …)` *additionally* alongside the
`hindi_text` block (the surrounding text is preserved unchanged).

### 5.8 Slugging (`topic_keys.py`)

```python
def slug(s: str, config) -> str:
    s = nfc(s)
    if config.slug.strip_v4_numeric_prefix:
        s = re.sub(r'^\s*\d+(?:\.\d+)*[.\s]+', '', s)
    for ch in config.slug.strip_chars:
        s = s.replace(ch, "")
    if config.slug.preserve_devanagari:
        # Replace whitespace runs with the configured separator
        s = re.sub(r'\s+', config.slug.whitespace_to, s)
    if config.slug.collapse_dashes:
        s = re.sub(r'-+', '-', s)
    return s.strip('-').strip()

def natural_key(keyword: str, heading_path: list[str], config) -> str:
    return ":".join([keyword] + [slug(h, config) for h in heading_path])
```

`heading_path` is the list of ancestor headings + this heading, in
order. For a top-level subsection it's `[heading]`; for a child
`[parent_heading, heading]`; etc.

### 5.9 Topic display_text

Always produce a `[Multilingual]` array with one entry:

```python
display_text = [Multilingual(lang="hin", script="Deva", text=heading_text)]
```

(other languages are added later by enrichment).

---

## 6. The "would_write" envelope (`envelope.py`)

Goal: at parse time, produce a single JSON document that shows
*exactly* what each store would receive on approval. This is what
goldens compare against.

```python
def build_envelope(result: KeywordParseResult) -> WouldWriteEnvelope:
    return WouldWriteEnvelope(
        keyword_parse_result=result,
        would_write={
            "postgres": build_pg_fragment(result),
            "mongo":    build_mongo_fragment(result),
            "neo4j":    build_neo4j_fragment(result),
        },
    )
```

### 6.1 Postgres fragment

```python
def build_pg_fragment(result):
    keyword_row = {
        "table": "keywords",
        "natural_key": result.keyword,
        "display_text": result.keyword,
        "source_url": result.source_url,
        # definition_doc_ids is not known until Mongo upsert runs — leave [] in envelope.
        "definition_doc_ids": [],
    }
    topic_rows = []
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            topic_rows.append({
                "table": "topics",
                "natural_key": sub.natural_key,
                "topic_path": sub.topic_path,
                "parent_topic_natural_key": sub.parent_natural_key,
                "display_text": [{"lang":"hin","script":"Deva","text":sub.heading_text}],
                "source": "jainkosh",
                "parent_keyword_natural_key": result.keyword,
                "is_leaf": sub.is_leaf,
                "is_synthetic": sub.is_synthetic,
            })
    return {"keywords": [keyword_row], "topics": topic_rows, "keyword_aliases": []}
```

`keyword_aliases` is empty in the parser-only stage (alias mining is
the orchestrator's job). The envelope reserves the field so future
stages can fill it.

### 6.2 Mongo fragment

```python
def build_mongo_fragment(result):
    kdef = {
        "collection": "keyword_definitions",
        "natural_key": result.keyword,
        "source_url": result.source_url,
        "page_sections": [
            {
                "section_index": s.section_index,
                "section_kind": s.section_kind,
                "h2_text": s.h2_text,
                "definitions": [d.model_dump() for d in s.definitions],
                # subsection_tree removed in v1.1.0 (phase 5); full tree lives in topic_extracts
                "extra_blocks": [b.model_dump() for b in s.extra_blocks],
                "index_relations": [r.model_dump() for r in s.index_relations],
            }
            for s in result.page_sections
        ],
        "redirect_aliases": [],     # filled by orchestrator post-parse
    }
    topic_extracts = []
    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            topic_extracts.append({
                "collection": "topic_extracts",
                "natural_key": sub.natural_key,
                "topic_path": sub.topic_path,
                "parent_natural_key": sub.parent_natural_key,
                "is_leaf": sub.is_leaf,
                "heading": [{"lang":"hin","script":"Deva","text":sub.heading_text}],
                "blocks": [b.model_dump() for b in sub.blocks],
                "source": "jainkosh",
                "source_url": f"{result.source_url}#{sub.topic_path}" if sub.topic_path else result.source_url,
            })
    return {"keyword_definitions": [kdef], "topic_extracts": topic_extracts}
```

### 6.3 Neo4j fragment

Edges follow `04_data_model_graph.md`:

```python
def build_neo4j_fragment(result):
    nodes = [{"label":"Keyword","key":result.keyword,
              "props":{"display_text":result.keyword, "source_url":result.source_url}}]
    edges = []

    for sec in result.page_sections:
        for sub in walk_subsection_tree(sec.subsections):
            nodes.append({"label":"Topic","key":sub.natural_key,
                          "props":{"display_text_hi":sub.heading_text,
                                   "topic_path":sub.topic_path,
                                   "parent_keyword_natural_key": result.keyword,
                                   "source":"jainkosh",
                                   "is_leaf": sub.is_leaf}})
            # Keyword → Topic
            if sub.parent_natural_key is None:
                edges.append({"type":"HAS_TOPIC",
                              "from":{"label":"Keyword","key":result.keyword},
                              "to":{"label":"Topic","key":sub.natural_key},
                              "props":{"weight":1.0,"source":"jainkosh"}})
            else:
                # Topic → Topic (PART_OF, child → parent)
                edges.append({"type":"PART_OF",
                              "from":{"label":"Topic","key":sub.natural_key},
                              "to":{"label":"Topic","key":sub.parent_natural_key},
                              "props":{"weight":1.0,"source":"jainkosh"}})
            # see_also blocks become MENTIONS_KEYWORD edges or RELATED_TO if the target is a topic
            for b in sub.blocks:
                if b.kind != "see_also": continue
                edges.append(_see_also_edge(b, source_topic_key=sub.natural_key, keyword_node=result.keyword))

    # Index relations
    for sec in result.page_sections:
        for rel in sec.index_relations:
            if rel.source_topic_natural_key_chain:
                src = ("Topic", rel.source_topic_natural_key_chain[-1])
            else:
                src = ("Keyword", result.keyword)
            edges.append(_index_relation_edge(rel, src, keyword=result.keyword))

    return {"nodes": dedupe(nodes), "edges": dedupe(edges)}
```

`_see_also_edge`:

- Target has `target_topic_path` and `target_keyword`: edge type
  `RELATED_TO`, target = `Topic{ key: "<target_keyword>:<topic_path-resolved>" }`. **At parse time**
  we don't know the target's slug-based natural_key (we only have its
  `topic_path`), so we emit a *placeholder* edge with target shape
  `{"label":"Topic","resolve_by":{"parent_keyword":"X","topic_path":"1.2"}}`.
  The orchestrator resolves this at apply time using Postgres.
- Target has only `target_keyword`: `RELATED_TO` to
  `{"label":"Keyword","key":"<target_keyword>"}`.
- Self link (`is_self`): edge stays within the current keyword.

### 6.4 Output JSON schema

The envelope is serialised with `model_dump_json(indent=2,
ensure_ascii=False)`. Devanagari is preserved verbatim in the JSON.

---

## 7. Public CLI

`workers/ingestion/jainkosh/cli.py`:

```
usage: python -m workers.ingestion.jainkosh.cli parse <html_path> [options]

options:
  --url URL              Source URL to record. If omitted, derive from filename:
                         "samples/sample_html_jainkosh_pages/<name>.html" → "https://www.jainkosh.org/wiki/<name>"
  --config PATH          Path to jainkosh.yaml (default: parser_configs/jainkosh.yaml)
  --out PATH             Output JSON path. If omitted, write to "<input>.parsed.json"
  --pretty               Pretty-print JSON (default true)
  --validate-only        Run the parser but don't write; print summary stats only
  --rules-version STR    Override parser_rules_version (for testing migrations)

exit codes:
  0  success
  1  parse error (selectolax couldn't find mw-parser-output, etc.)
  2  config validation error
  3  IO error
```

### 7.1 Filename → URL convention

When `--url` is omitted, the CLI URL-encodes the filename stem:

```
"samples/sample_html_jainkosh_pages/द्रव्य.html" → "https://www.jainkosh.org/wiki/द्रव्य"
```

This is intentional: the URL is the canonical keyword identity, and
the test fixtures are named after the keyword.

### 7.2 Reproducibility

The CLI accepts a `--frozen-time TIMESTAMP` flag for tests, which
overrides `parsed_at`. This makes goldens byte-identical across runs.
Tests pass `--frozen-time 2026-05-02T00:00:00Z`.

---

## 8. Tests

### 8.1 Test categories

| Category | Files | What it does |
|----------|-------|--------------|
| **Golden** | `tests/test_parse_keyword_golden.py` | Run the parser on each of the 3 sample HTMLs; diff against `tests/golden/<keyword>.json`. Re-run produces zero diff (idempotency). |
| **Heading variants** | `tests/unit/test_heading_variants.py` | Parametrised: V1, V2, V3, V4 with minimal HTML strings. V5 must be detected as a *non-heading*. |
| **Translation marker** | `tests/unit/test_translation_marker.py` | Sanskrit + Hindi pair, leading `=`, leading `=` with `<b>` markers, no preceding source block (orphan), `=` in middle (not consumed). |
| **References** | `tests/unit/test_refs.py` | Leading `<p><span class="GRef">…</span></p>` → next block; trailing inline `<span class="GRef">` → same block; multiple GRefs in one `<p>`; redlink GRef with `<a>` inside (anchor stripped). |
| **`see_also`** | `tests/unit/test_see_also.py` | All `देखें` formats from parsing_rules.md §4.3; self-link; redlink. Inline and index variants. |
| **Nested-span** | `tests/unit/test_nested_span.py` | द्रव्य L734-759 reduced to a fixture; verify number and order of emitted blocks. |
| **Definitions** | `tests/unit/test_definitions.py` | (a) आत्मा SiddhantKosh → 5 definitions (b) द्रव्य SiddhantKosh → 1 (c) आत्मा PuranKosh → 2 (`(1)` and `(2)`) (d) द्रव्य PuranKosh → 1. |
| **Index relations** | `tests/unit/test_index_relations.py` | The three target formats; keyword-level `<ul>` vs section-level `<ul>`; redlink. |
| **Slugging** | `tests/unit/test_topic_keys.py` | Devanagari preservation, V4 prefix strip, danda strip, dash collapse, NBSP. |
| **Config schema** | `tests/unit/test_config_schema.py` | `parser_configs/jainkosh.yaml` validates against `_schemas/jainkosh.schema.json`. Missing required key → fail. Invalid heading variant → fail. |
| **CLI** | `tests/unit/test_cli.py` | `python -m workers.ingestion.jainkosh.cli parse <fixture> --out <tmp>`; verify output is valid `WouldWriteEnvelope`. |

### 8.2 Golden generation

Goldens are **hand-reviewed** the first time:

1. Run `python -m workers.ingestion.jainkosh.cli parse samples/sample_html_jainkosh_pages/आत्मा.html --out tests/golden/आत्मा.json --frozen-time 2026-05-02T00:00:00Z`.
2. Manually inspect the JSON.
3. Commit to git only after a human approves it.

Subsequent runs must produce byte-identical output. The golden test
diffs character-by-character.

### 8.3 What the golden MUST contain (sanity checks)

For **आत्मा.json**:
- `keyword == "आत्मा"`.
- 2 page_sections: `siddhantkosh`, `puraankosh`.
- SiddhantKosh has 5 `Definition`s and ~5 top-level subsections
  (`<b>2. …</b>` through `<b>6. …</b>`).
- The first SiddhantKosh subsection is `topic_path == "2"`.
  *Note*: the `<b>1. …</b>` heading **doesn't exist** in this page —
  the first heading in the body is `<b>2. आत्मा के बहिरात्मादि 3 भेद</b>`.
  This is explicitly allowed; the parser MUST NOT synthesise a
  missing `1`. (This is a real quirk of the source page.)
- PuranKosh has 2 `Definition`s (one per `<p id="1">`, `<p id="2">`).
- 0 `index_relations` (no leading `<ol>` index).
- Inline `देखें` blocks appear within **child label-seed subsections**
  (v1.3.0): the seeds `जीवको आत्मा कहनेकी विवक्षा`,
  `आत्मा ही कथंचित प्रमाण है`, and `शुद्धात्माके अपर नाम` each carry
  their respective `see_also` blocks (`जीव`, `प्रमाण#3.3`,
  `मोक्षमार्ग#2.5`). The parent subsection
  `एक आत्मा के तीन भेद करने का प्रयोजन` has **no** `see_also` blocks.
- `RELATED_TO` edges in `would_write.neo4j.edges` originate from the
  child seed natural keys, e.g.
  `आत्मा:एक-आत्मा-के-तीन-भेद-करने-का-प्रयोजन:जीवको-आत्मा-कहनेकी-विवक्षा`,
  **not** from the parent topic key.

For **द्रव्य.json**:
- 2 page_sections.
- SiddhantKosh has 1 `Definition` (the intro `<p class="HindiText">`),
  many index_relations (the leading `<ol>` is an index), and a
  multi-level subsection tree (1 → 1.1..1.11; 2 → 2.1..2.4; 3 →
  3.1..3.10; 4 → 4.1.1..4.1.3, 4.2.1..4.2.3, etc.).
- 1 `extra_block` of kind=`table` at section-level (the table between
  sections 3 and 4).
- PuranKosh has 1 `Definition`.

For **पर्याय.json**:
- SiddhantKosh has subsection paths up to 3 levels deep (`1.1.1`,
  `1.1.2`, `1.1.3`, `1.1.4`, `1.2`, `2.1`, …, `3.8.1`, …).
- All synthetic flag values are false (no missing intermediates in
  this page — verify).
- Many index_relations including a few `mw-selflink-fragment`
  self-links.

Any deviation from these sanity invariants is a parser bug.

### 8.4 Idempotency test

```python
def test_parser_is_byte_identical_on_rerun(tmp_path):
    out1 = tmp_path / "out1.json"
    out2 = tmp_path / "out2.json"
    run_cli(["parse", FIXTURE, "--out", str(out1), "--frozen-time", FROZEN])
    run_cli(["parse", FIXTURE, "--out", str(out2), "--frozen-time", FROZEN])
    assert out1.read_bytes() == out2.read_bytes()
```

### 8.5 Performance budget (advisory, not blocking)

- `आत्मा.html` (58 KB) → < 200 ms on a developer laptop.
- `द्रव्य.html` (290 KB) → < 1.5 s.
- `पर्याय.html` (192 KB) → < 1.0 s.

If we exceed this by 2× during development, profile but don't block.

---

## 9. Error model

Single exception class:

```python
class ParseError(Exception):
    """Raised when the HTML cannot be parsed per the configured rules."""
    def __init__(self, message: str, *, file: Optional[str] = None,
                 location: Optional[str] = None):
        ...
```

Failures that should raise `ParseError`:
- `mw-parser-output` div not found.
- Heading regex matches but extracted `topic_path` is empty.
- Topic tree assembly creates a cycle (defensive).
- Config doesn't validate against the schema.

Failures that should **NOT** raise:
- Unknown CSS class on a `<p>` or `<span>` — silently dropped, with
  one entry in `KeywordParseResult.warnings: list[str]` (added field;
  see §10).
- Empty `<p>` after whitespace-strip — silently dropped.
- Image, comment, script tags — silently dropped.
- Trailing GRef with no preceding/following block — attached to last
  block as fallback; warning recorded.

### 9.1 Warnings field

Add to `KeywordParseResult`:

```python
class Warning(BaseModel):
    code: str               # "unknown_block_class" | "orphan_gref" | "synthetic_parent" | ...
    message: str
    where: Optional[str]    # path/topic locator

class KeywordParseResult(BaseModel):
    ...
    warnings: list[Warning] = Field(default_factory=list)
```

Goldens include the warnings list, so unexpected new warnings cause
the golden test to fail (intentional). Empty list is the goal.

---

## 10. Definition of Done (parser-only stage)

- [ ] `parser_configs/jainkosh.yaml` and its JSON Schema exist; YAML validates.
- [ ] All Pydantic models in `models.py` have `ConfigDict(extra='forbid')` and round-trip valid JSON.
- [ ] `parse_keyword_html` works end-to-end on all three samples.
- [ ] `tests/golden/आत्मा.json`, `द्रव्य.json`, `पर्याय.json` are committed and human-reviewed.
- [ ] Golden tests are byte-identical idempotent.
- [ ] All unit-test files pass (including `test_tables.py`, `test_see_also.py` phase-1/3 cases, `test_translation_marker.py` sibling-`=` cases, `test_refs.py` ref-strip cases).
- [ ] CLI works: `python -m workers.ingestion.jainkosh.cli parse <html> --out <json> --frozen-time <ts>` produces the envelope.
- [ ] Each emitted topic in the envelope has BOTH `natural_key` (slug path) AND `topic_path` (numeric or `null` for label seeds).
- [ ] Tables attach to the current open subsection's `blocks`; only truly orphan tables land in `extra_blocks`.
- [ ] Inline `देखें` and `विशेष देखें` both produce a `Block(kind='see_also', …)` via the configurable trigger list.
- [ ] Redlink anchors: prose stripped from `text_devanagari`; `see_also` block emitted with `target_exists=false`.
- [ ] Label-before-`देखें` produces a `Subsection` with `label_topic_seed=true`, `is_synthetic=true`, `topic_path=null`.
- [ ] `<b>`/`<strong>` inside body text becomes `**…**` markdown.
- [ ] `=` translation marker: both leading-`=` (HindiText body) and sibling-`=` (text node) cases correctly absorb Hindi into the preceding source block.
- [ ] GRef text absent from every `text_devanagari` field.
- [ ] `IndexRelation.source_topic_path_chain` and `source_topic_natural_key_chain` populated on all relations.
- [ ] `mongo.keyword_definitions.page_sections[*]` has no `subsection_tree` key; `extra_blocks` is present.
- [ ] `would_write.idempotency_contracts` is a top-level map keyed by `"<store>:<table>"`; no per-row `idempotency_contract` field.
- [ ] `Block(kind="table").raw_html` contains full outerHTML with collapsed whitespace.
- [ ] `IndexRelation.source_topic_path_chain` and `source_topic_natural_key_chain` are non-null for all relations with a section-level source.
- [ ] Parenthesised `(देखें X)` fragments absent from every `text_devanagari` and `hindi_translation` field.
- [ ] See-also-only blocks (`• X – देखें Y`) absent from `Subsection.blocks`; present only in `see_alsos`.
- [ ] Definition `(N)` numbering prefix absent from every definition's prose text.
- [ ] `RELATED_TO` edges with `target_exists=false` absent from `would_write.neo4j.edges`.
- [ ] `parser_rules_version: "jainkosh.rules/1.2.0"` in YAML and in every golden's `parser_version` field.
- [ ] `KeywordParseResult.warnings` is empty for all three fixtures.
- [ ] No part of the parser performs HTTP, DB writes, or filesystem writes beyond `--out`.

---

## 11. Implementation order (recommended)

This sequence keeps each commit testable:

1. `config.py` + `parser_configs/jainkosh.yaml` + JSON Schema + schema test.
2. `models.py` + a smoke test (`KeywordParseResult().model_dump_json()`).
3. `normalize.py` + `topic_keys.py` + their unit tests.
4. `selectors.py` + `parse_blocks.make_block` for the simple cases (Sanskrit/Prakrit/Hindi text & gatha) + `refs.py` + `test_refs.py`.
5. Translation marker logic + `test_translation_marker.py`.
6. `parse_subsections.py` (heading variant detection + tree assembly) + `test_heading_variants.py`.
7. `parse_definitions.py` + `test_definitions.py`.
8. `parse_index.py` + `see_also.py` + `test_index_relations.py` + `test_see_also.py`.
9. `nested_span` flatten + `test_nested_span.py`.
10. `tables.py` + `nav.py`.
11. `parse_section.py` + `parse_keyword.py` (wire all pieces together).
12. `envelope.py`.
13. `cli.py`.
14. Generate goldens, hand-review, commit.
15. `test_parse_keyword_golden.py` + idempotency test.

Each step ends with all prior tests still green.

---

## 12. Future-proofing notes

- **More heading variants**: add a row to
  `parser_configs/jainkosh.yaml > headings.variants` with selector and
  id_from. No code change. Add a fixture-based unit test for the new
  variant.
- **More block classes**: add a row to `block_classes`. No code change.
- **Roman-numeral topic paths** (`II.3.3`): already opaque-string by
  design. No change needed.
- **Different source language tags**: add to a future
  `block_classes_to_lang_script` map keyed by block kind.
- **Embedding deferred to v2** (per `00_overview.md`): the parser does
  not produce embeddings; topic_extracts are stored in Mongo and
  v1-traversed in Neo4j only.
