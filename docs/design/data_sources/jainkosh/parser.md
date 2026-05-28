# JainKosh Parser — Complete Reference

> Single authoritative doc for anyone working with the JainKosh parser.
> Covers HTML structure rules, parser implementation, configuration, models,
> algorithms, CLI, tests, and edge-emission specs.
>
> **Current version**: `jainkosh.rules/1.11.0`
>
> Source docs that fed this file:
> - `parser/parsing_rules.md` — canonical HTML rules
> - `parser/parser_spec.md` — implementation spec
> - `parser/reference_parser_spec.md` — structured reference resolution
> - `parser/reference_edge_creation_spec.md` — Neo4j edge emission from references

---

## Table of Contents

1. [Overview](#1-overview)
2. [Page Anatomy & HTML Rules](#2-page-anatomy--html-rules)
3. [Definitions](#3-definitions)
4. [Topic Index Parsing](#4-topic-index-parsing)
5. [Subsections (Topic Seeds)](#5-subsections-topic-seeds)
6. [Block Kinds & Processing Rules](#6-block-kinds--processing-rules)
7. [File Layout](#7-file-layout)
8. [Configuration (`jainkosh.yaml`)](#8-configuration-jainkoshyaml)
9. [Pydantic Models](#9-pydantic-models)
10. [Algorithms](#10-algorithms)
11. [Reference Parser](#11-reference-parser)
12. [Neo4j Edge Emission from References](#12-neo4j-edge-emission-from-references)
13. [Would-Write Envelope](#13-would-write-envelope)
14. [CLI](#14-cli)
15. [Tests](#15-tests)
16. [Error Model](#16-error-model)
17. [Versioning & Changelog](#17-versioning--changelog)

---

## 1. Overview

The JainKosh parser is a **pure HTML → JSON** pipeline. It reads pre-saved
MediaWiki HTML pages from `samples/sample_html_jainkosh_pages/` and produces a
structured `KeywordParseResult` JSON document per page, plus a "would-write"
envelope showing exactly what each store (Postgres / Mongo / Neo4j) would
receive on approval.

**Constraints:**
- No HTTP, no DB writes, no async I/O.
- Fully synchronous Python.
- Rule-driven: all DOM patterns are configured in `parser_configs/jainkosh.yaml`.
  Adding a heading variant or block class must not require code changes.

**Entry point:**
```
python -m workers.ingestion.jainkosh.cli parse <file.html> --out <out.json>
```

---

## 2. Page Anatomy & HTML Rules

A keyword page is a MediaWiki-rendered article. The parsable region is
`div.mw-parser-output` (one per page).

### 2.1 Identifying the keyword

The keyword comes from the source URL, **not** from page text:
```
https://www.jainkosh.org/wiki/<keyword>
```

Steps:
1. URL-decode the path segment after `/wiki/`.
2. Apply NFC normalisation (`unicodedata.normalize('NFC', s)`).
3. Strip ZWJ (`U+200D`) and ZWNJ (`U+200C`) per config (`strip_zwj`, `strip_zwnj`; both default `true`).

This NFC string is the canonical `keyword` identifier and the `natural_key` for `keywords`.

### 2.2 Page sections

Sections are introduced by an `<h2>` whose `<span class="mw-headline">` has a known id:

| `mw-headline` id    | `section_kind`   |
|---------------------|------------------|
| `सिद्धांतकोष_से`    | `siddhantkosh`   |
| `पुराणकोष_से`       | `puraankosh`     |
| anything else       | `misc`           |

A section is everything after its `<h2>` and before the next `<h2>`.

### 2.3 Section element order

Within a section, elements appear in this order (any may be absent):

1. **Definitions** — content before the first numbered heading (§3).
2. **Topic index** — leading `<ol>` listing subsections + cross-page `देखें` relations (§4).
3. **Subsections** — the body, organised as a topic tree (§5).
4. **Tables** — interleaved with subsections; treated as `extra_blocks` if before any heading (§6.5).
5. **Adjacent-page navigation** — `पूर्व पृष्ठ` / `अगला पृष्ठ` anchors; silently dropped (§6.6).

---

## 3. Definitions

A **definition** is a leading content block in a section, *before* any numbered topic heading.

### 3.1 SiddhantKosh definitions

Each `[GRef] → [SanskritText|PrakritText|…] → [HindiText]` group is one Definition.
A new leading `<span class="GRef">` or `<p>` containing only GRef(s) closes the
current definition and starts a new one.

Examples:
- आत्मा: ~5 separate `[GRef] [SanskritText] [HindiText]` groups → 5 `Definition` objects.
- द्रव्य: single intro `<p class="HindiText">` → 1 `Definition`.

### 3.2 PuranKosh definitions

Content is wrapped in `<div class="HindiText">`. Two patterns:

- **Numbered paragraphs**: multiple `<p id="N" class="HindiText">(N) …</p>` → N separate `Definition` objects, one per `<p id>`. The leading `(N)` prefix is stripped from prose (controlled by `definitions.numbering_strip_re`, default `^\s*\(\d+\)\s*`).
- **Single paragraph**: one `<p class="HindiText">` → 1 `Definition`.

PuranKosh has **no numbered subsections** — everything is definition.

### 3.3 Definition shape

```python
class Definition:
    definition_index: int    # 1-based, per section
    blocks: list[Block]
    raw_html: str | None     # debug
```

### 3.4 Idempotency contracts (envelope root, v1.2.0)

The `would_write` envelope carries a top-level `idempotency_contracts` map keyed
by `"<store>:<table>"`. Each entry describes the conflict key and field-level
merge policy so the orchestrator can perform truly idempotent upserts:

```jsonc
"idempotency_contracts": {
  "postgres:keywords": {
    "conflict_key": ["natural_key"],
    "on_conflict": "do_update",
    "fields_replace": ["display_text", "source_url"],
    "fields_append": ["definition_doc_ids"],
    "fields_skip_if_set": [],
    "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"]
  },
  "postgres:topics": { ... },
  "mongo:keyword_definitions": { ... },
  "mongo:topic_extracts": { ... },
  "neo4j:Keyword": { ... },
  "neo4j:Topic": { ... }
}
```

Controlled by `envelope.idempotency_mode` (default `envelope_root`).

### 3.5 `raw_html` whitespace policy

`Block(kind="table")` and inline `raw_html` fields always carry the **full
outerHTML**. Whitespace is collapsed: runs of whitespace reduced to a single
space. Controlled by `raw_html.collapse_whitespace` (default `true`).

---

## 4. Topic Index Parsing

A SiddhantKosh section may contain one or more leading `<ol>` blocks **before**
any `<strong id="…">` heading.

### 4.1 Index structure

```
<ol>                                          ← outer index list
  <li class="HindiText">
    <strong>section title</strong>
    <ol>                                      ← inner: in-page anchors — IGNORE
      <li><a href="#1.1">subsection title</a></li>
    </ol>
    <ul>                                      ← inner: cross-page देखें — CAPTURE
      <li>…label… - देखें <a href="/wiki/X">X</a></li>
      <li>…label… - देखें <a href="/wiki/X#1.2">X - 1.2</a></li>
      <li>…label… - देखें <a class="mw-selflink-fragment" href="#3">द्रव्य - 3</a></li>
    </ul>
  </li>
  <ul>…</ul>                                  ← keyword-level देखें (between top-level <li>s)
</ol>
```

### 4.2 Capture rules

1. `<a href="#X.Y">` inside any inner `<ol>` → **ignore** (duplicates body subsections).
2. `<li>` inside an inner `<ul>` → emit one `IndexRelation`. Text before `देखें` is the label; `<a>` is the target.
3. **Source of relation**: `<ul>` *inside* a top-level `<li>` → relation sourced from that section's topic. `<ul>` at outer `<ol>` level → keyword-level relation (`source = None`).

### 4.3 Range expansion for `देखें` links (v1.7.0)

When a `देखें` link target has a `target_topic_path` like `X.M` and the text
**immediately following** the anchor is `-N` (hyphen or en-dash + number, where N > M),
the parser expands the relation into N − M + 1 relations covering `X.M` through `X.N`.

Example from स्वभाव:
```
जीव पुद्गल का ऊर्ध अधोगति स्वभाव-देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-6।
→  four IndexRelations: target_topic_path = "1.3", "1.4", "1.5", "1.6"

वस्तु में अनंतों धर्म होते हैं-देखें <a href="/wiki/गुण#3.9">गुण - 3.9</a>-11।
→  three IndexRelations: target_topic_path = "3.9", "3.10", "3.11"
```

Rules:
- Only the **last** path segment is iterated; the prefix remains fixed.
- If `target_topic_path` is absent (keyword-only link), expansion is skipped.
- If N ≤ M, expansion is skipped and one relation is emitted as usual.
- All expanded relations share the same `label_text`, `source_topic_path_chain`, and `target_keyword`.
- Applies to both `IndexRelation` (index `<ol>`) and `see_also` `Block` (inline `देखें`).

Implemented in `see_also.py`:
- `_extract_range_suffix_after_anchor(a, nth_occurrence)` — detects the `-N` suffix
- `_expand_parsed_to_range(parsed, end_num)` — produces the list of expanded dicts

### 4.4 Three target formats for `देखें` links

| href shape | `target_keyword` | `target_topic_path` | `is_self` |
|---|---|---|---|
| `/wiki/X` | `X` (NFC) | `None` | `false` |
| `/wiki/X#Y` | `X` (NFC) | `Y` | `false` |
| `#X.Y` (`mw-selflink-fragment`) | current keyword | `X.Y` | `true` |
| `/w/index.php?title=X&action=edit&redlink=1` | `X` (decoded) | `None` | `false` / `target_exists=false` |

`target_keyword` from `/wiki/<percent-encoded>` is URL-decoded then NFC-normalised. Parse from URL fragment, not from visible link text.

### 4.5 Configurable `देखें` triggers

The trigger list is configurable in `parser_configs/jainkosh.yaml > index.see_also_triggers`
(e.g. `["देखें", "विशेष देखें"]`). Triggers are sorted longest-first and joined into a
regex alternation. The scanner uses a **full CSS `a`-element scan** (DFS) of the entire
index `<ol>` subtree — not a two-tier walk.

| Config key | Default | Meaning |
|---|---|---|
| `see_also_triggers` | `["देखें"]` | Trigger words |
| `see_also_window_chars` | `40` | Max preceding chars to inspect |
| `see_also_leading_punct_re` | `[(–\-।\s]*` | Punct allowed between label and trigger |

### 4.6 IndexRelation source chain resolution (v1.4.0)

`IndexRelation.source_topic_path_chain` and `source_topic_natural_key_chain` are
resolved by walking ancestor `<li>` containers upward through the index DOM.

Two fallback rules (v1.4.0):
- **Enclosing-`<li>` fallback**: when previous-sibling scan is exhausted, resolution
  climbs to the enclosing parent `<li>`.
- **Inner-`<ol>` path fallback**: for `<li>` headings where `<strong>` has plain text
  (no `<a href="#...">`), path is derived from the first direct inner-`<ol>` anchor by
  trimming its last segment (e.g. `#4.4.1` → `4.4`).

Controlled by:
- `index.source_chain.enclosing_li_fallback` (default `true`)
- `index.source_chain.li_path_from_inner_ol_fallback` (default `true`)

---

## 5. Subsections (Topic Seeds)

A subsection is a numbered heading + its content, possibly with children.
Subsections form a **tree** keyed by `topic_path` (e.g. `1`, `1.1`, `1.1.3`).

### 5.1 Heading variants

There are **5 active heading variants** plus one non-heading look-alike (V5-def).

| Variant | DOM shape | `topic_path` source | Heading text source | Seen in |
|---|---|---|---|---|
| **V1** | `<strong id="N">heading</strong>` | `@id` of `<strong>` | text of `<strong>` (numeric prefix stripped) | द्रव्य, पर्याय, स्वभाव |
| **V2** | `<span class="HindiText" id="N"><strong>heading</strong></span>` | `@id` of `<span>` | text of inner `<strong>` (numeric prefix stripped) | द्रव्य |
| **V2-bare** | `<span class="HindiText" id="N">N. heading</span>` (no inner `<strong>`) | `@id` of `<span>` | text after stripping leading `N. ` prefix (required) | स्वभाव |
| **V3** | `<li id="N"><span class="HindiText"><strong>heading</strong></span>` | `@id` of `<li>` | text of inner `<strong>` | पर्याय |
| **V4** | `<p class="HindiText"><b>N. heading</b></p>` | regex on text `^\s*(?P<id>\d+(?:\.\d+)*)[.\s]+(?P<heading>.+?)\s*$` | regex `heading` group | आत्मा |
| **V5** | `<p class="HindiText" id="N">N. heading</p>` (no child elements) | `@id` of `<p>` | text after stripping leading `N. ` prefix (required) | स्वभाव |
| **V5-def** | `<p id="N" class="HindiText">(N) text…</p>` | **Not a heading** — PuranKosh definition | — | आत्मा PuranKosh |

**Numeric prefix stripping** (V1, V2, V2-bare, V5): leading `\d+(?:\.\d+)*[.\s]+` is stripped
from `heading_text`. If stripping leaves an empty string, the element is rejected.
This does **not** affect natural keys (the `slug()` function already strips such prefixes).

**V2-bare guard**: the no-strong fallback only fires when (a) the span has no direct child
elements AND (b) the text starts with a numeric prefix. Plain `<span class="HindiText" id="N">text</span>`
without a numeric prefix is not treated as a heading.

**V5 guard**: same conditions as V2-bare but for `<p>` elements. Ensures PuranKosh definitions
`<p id="N" class="HindiText">(N) text</p>` (parenthesised prefix) are not promoted.

### 5.2 Topic path tree assembly

1. Walk the section's body in document order.
2. On each heading, parse its `topic_path`.
3. Look up parent path by removing the last segment (`"1.1.3"` → `"1.1"`).
4. **Synthesise missing intermediates**: if `1.1.3` appears but `1.1` was never declared,
   create a synthetic `1.1` with `is_synthetic=true`, `heading_text=""`.
5. Append as child of parent.

A subsection is a **leaf** iff it has zero child subsections.

### 5.3 Natural keys and slugging

Every subsection emits a `Topic` with:

- `natural_key`: `<keyword>:<slug(h1)>:<slug(h2)>:…` e.g. `द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ`
- `topic_path`: the numeric id path e.g. `"1.1"` (stored separately for cross-reference resolution).
- `parent_topic_natural_key`: parent's `natural_key`, or `None` for top-level.

**Slug rules (Devanagari-aware):**
- NFC-normalise.
- Strip V4 numeric prefix (already handled by regex).
- Replace whitespace runs (incl. NBSP) with `-`.
- Strip: `।`, `॥`, ASCII punct `.,;:!?()[]{}'"`.
- Preserve Devanagari characters as-is.
- Collapse multiple `-` into one; trim leading/trailing `-`.

Example: `आत्मा के बहिरात्मादि 3 भेद` → `आत्मा-के-बहिरात्मादि-3-भेद`

### 5.4 Label-before-`देखें` as synthetic topic seed (v1.1.0)

When a HindiText block takes the shape `• <label> - देखें <X>`, the text before
the `देखें` trigger becomes a **synthetic Topic seed**:

- `is_synthetic = True`, `label_topic_seed = True`, `topic_path = None`, `is_leaf = True`
- `natural_key` = slug of the label appended to the parent's `natural_key`.
- Attached as child of the **current open subsection**, or to
  `PageSection.label_topic_seeds` if at section root.

**Scope guard (v1.2.0)**: label-seed Topics are NOT emitted when the `देखें`
trigger appears inside translation prose (controlled by `label_to_topic.skip_in_source_kinds`).

**Row-relation relocation (v1.3.0)**: for row-style entries (`• label - देखें target`),
the `see_also` block is assigned to the **child seed's `blocks`**, not the parent
subsection's blocks. `RELATED_TO` edges are emitted from the child seed's `natural_key`.
Row detection happens at DOM element level before any text stripping (catches redlink rows).

### 5.5 Parenthesised `देखें` cleanup (v1.2.0)

When a `देखें` reference is parenthesised — e.g. `(देखें X)` — the entire parenthesised
fragment is stripped from `text_devanagari` and `hindi_translation`. The `see_also` block
is still emitted independently. Controlled by `paren_dekhen_strip.bracket_pairs`.

---

## 6. Block Kinds & Processing Rules

### 6.1 Recognised block kinds

| Block kind | DOM shape | Meaning |
|---|---|---|
| `sanskrit_text` | `<p class="SanskritText">` or `<span class="SanskritText">` | Source-language text |
| `sanskrit_gatha` | `<p class="SanskritGatha">` etc. | Source-language verse |
| `prakrit_text` | `<p class="PrakritText">` etc. | Source-language text |
| `prakrit_gatha` | `<p class="PrakritGatha">` etc. | Source-language verse |
| `hindi_text` | `<p class="HindiText">` or `<span class="HindiText">` | Translation or independent prose |
| `hindi_gatha` | `<p class="HindiGatha">` etc. | Hindi verse |
| `reference` | `<span class="GRef">` | Bibliographic citation |
| `see_also` | inline `देखें <a href="…">` pattern | Cross-reference relation |
| `table` | `<table>…</table>` | Tabular data (raw HTML kept) |

Block classes are **configurable** via `block_classes` in `jainkosh.yaml`.

### 6.2 The `=` translation marker

A source-language block is typically followed by `<p class="HindiText">= translation…</p>`.
When a HindiText block **starts with** `=`:
1. Strip the leading `=` (and any whitespace after).
2. Attach the resulting text to the **preceding source-language block** as `hindi_translation`.

If there is no preceding source-language block: keep as `hindi_text`, strip `=`, set `is_orphan_translation=true`.

### 6.3 References (GRef) — leading vs trailing

Any `<a href>` inside `<span class="GRef">` is **stripped** (only visible text kept).

- **Leading reference**: a `<p>` whose only meaningful child is one or more `<span class="GRef">`s,
  immediately *before* a body block → attached to the **following** block as `references[]`.
- **Trailing reference**: `<span class="GRef">` *inside* a body block → attached to that block.

**v1.4.0 — inline GRef-based block splitting**: when meaningful prose continues after an
inline reference, the block is split at GRef boundaries. Example:
- `TEXT_A <GRef>R1</GRef> TEXT_B <GRef>R2</GRef>` → two `hindi_text` blocks:
  1. `TEXT_A` with `R1`
  2. `TEXT_B` with `R2`

### 6.4 Nested-span exception

When a `<span class="SanskritText">` contains nested elements:
```html
<span class="SanskritText">topmost text…<br>
  <span class="GRef">ref</span>
  <span class="SanskritText">more sanskrit</span>
  =
  <span class="HindiText">hindi translation</span>
</span>
```

Resolution:
1. Emit the outer span's **direct text** (text nodes not inside any nested element) as a separate `sanskrit_text` block.
2. Iterate nested children left-to-right and emit them as further blocks using normal rules.

Configurable via `nested_span_flatten: true|false`.

**v1.6.0 — classless `<p>` container**: when a classless `<p>` element's direct children
are exclusively GRef spans, block-classed spans, and `<br>` tags, it is exploded into
its direct children before block stream processing (handled by `_is_block_span_container()`
helper in `parse_blocks.py`).

### 6.5 Tables

Tables are kept as full outerHTML in `Block(kind="table", raw_html="…")`.

Attachment (`table.attach_to`, default `current_subsection`):
- **Inside a subsection's body** → attach to that subsection's `blocks`.
- **Before any heading in section** (truly orphan) → attach to `PageSection.extra_blocks`.

Old behaviour (all tables to `extra_blocks`) recoverable by setting `table.attach_to: "section_root"`.

### 6.6 Adjacent-page navigation

Detect by text content of an `<a>`:
- `पूर्व पृष्ठ` → previous page.
- `अगला पृष्ठ` → next page.

The containing `<p>` is dropped; hrefs captured into `KeywordParseResult.nav`.

### 6.7 Inline `देखें` extraction

Any anchor whose **immediately preceding inline text** (within `see_also_window_chars` chars)
matches the configured trigger pattern is a `see_also` block. The trigger list is shared with
the index scanner.

**Redlink anchor**: when the anchor is a MediaWiki redlink (`class="new"`, or `href` contains
`redlink=1`), the `see_also` block is emitted with `target_exists=false` AND the
`देखें <redlink>` substring is removed from `text_devanagari`. If the block becomes empty
after stripping, it is dropped.

**Redlink edge suppression (v1.2.0)**: `RELATED_TO` edges are **not emitted** when
`target_exists=false`. Controlled by `neo4j.redlink_edges` (enum: `always` | `never` |
`only_if_topic`; default `never`).

### 6.8 Inline emphasis

| HTML | Markdown |
|---|---|
| `<b>x</b>`, `<strong>x</strong>` | `**x**` |
| `<i>x</i>`, `<em>x</em>` | `*x*` |

Applies only to *non-heading* contexts.

### 6.9 Whitespace normalisation

Applied to every text field after extraction:
1. Unicode NFC.
2. Replace NBSP (` `) with space.
3. Strip ZWJ/ZWNJ per config.
4. Collapse runs of whitespace to single space (preserve `\n` from `<br/>` only).
5. `.strip()` the final string.

### 6.10 `<br/>` handling

`<br/>` inside a block becomes `\n`. Multiple consecutive `<br/>` collapse to one `\n`.
Trailing `<br/>` is dropped.

### 6.11 Sibling text-node `=` translation marker

`=` as a **bare text node directly between two element siblings** in the same parent:
```html
<span class="PrakritGatha">दवियदि …</span>
=
<span class="HindiText">उन-उन सद्भाव …</span>
```
When the text node matches `^\s*=\s*$`, the HindiText sibling is merged into the
preceding source-language block as `hindi_translation`. Configurable via
`translation_marker.sibling_marker_enabled` and `translation_marker.sibling_marker_text_node_re`.
Also applies inside `_explode_nested_span`.

### 6.12 GRef text stripped from `text_devanagari`

Inline GRef nodes are extracted into `references[]`. Their visible text is **also
removed** from `text_devanagari`. Clean-up after strip:
- Collapse orphan `( )` and `[ ]` bracket pairs.
- Collapse multiple spaces.
- Remove space before danda `।` / `॥`.
- Strip leading/trailing chars in `ref_strip.trim_trailing_chars` (default ` ।॥;,`).

Configurable via `ref_strip.enabled` and related knobs.

### 6.13 See-also-only block drop (v1.2.0 / v1.3.0)

A block whose entire content is `• X – देखें Y` is **dropped** from the parent
`Subsection.blocks`. v1.3.0 also drops the accompanying `see_also` block from the
parent stream — it is relocated to the child label-seed subsection's `blocks`.
Controlled by `see_also_only_block.drop` (bool, default `true`).

### 6.14 DFS leading-GRef passthrough (v1.2.0)

Top-level `<span class="GRef">` siblings that appear inside an `<li>` heading body are
preserved as content events in `walk_and_collect_headings` so the leading GRef reaches
`parse_block_stream` and attaches to the next emitted block. Controlled by
`dfs.passthrough_leading_gref` (default `true`).

---

## 7. File Layout

```
workers/ingestion/jainkosh/
├── __init__.py
├── cli.py                  # `python -m workers.ingestion.jainkosh.cli ...`
├── config.py               # Pydantic models for YAML rules + loader
├── models.py               # Parser output models (KeywordParseResult, etc.)
├── normalize.py            # NFC, ZWJ/ZWNJ strip, whitespace, slug
├── selectors.py            # CSS selector + class constants (defaults)
├── parse_keyword.py        # Public entry: parse_keyword_html(html, url, config)
├── parse_section.py        # One section (h2 → next h2)
├── parse_index.py          # Leading <ol>/<ul> index → IndexRelation list
├── parse_subsections.py    # Heading detection + tree assembly
├── parse_blocks.py         # Block stream: refs, sanskrit, prakrit, hindi, table, see_also
├── parse_definitions.py    # Pre-heading content → Definition list
├── parse_reference.py      # Structured GRef resolution against shastra.json
├── refs.py                 # GRef extraction (leading vs trailing)
├── see_also.py             # देखें detection (index + inline)
├── topic_keys.py           # natural_key, slug, tree path math, parent inference
├── nav.py                  # पूर्व पृष्ठ / अगला पृष्ठ extraction & drop
├── tables.py               # Table block extraction (raw_html)
├── reference_edges.py      # Neo4j edge emission from Reference objects
├── envelope.py             # Build the "would_write" envelope
└── tests/
    ├── fixtures/           # HTML samples (symlink to samples/sample_html_jainkosh_pages/)
    │   ├── आत्मा.html
    │   ├── द्रव्य.html
    │   └── पर्याय.html
    ├── golden/             # Golden JSON for snapshot tests
    │   ├── आत्मा.json
    │   ├── द्रव्य.json
    │   └── पर्याय.json
    └── unit/               # Unit tests per module

parser_configs/
├── jainkosh.yaml           # Parsing rules config (schema-validated)
├── _manual_configs/
│   ├── shastra.json        # Shastra registry for reference resolution
│   └── publishers.json     # Publisher registry for edge emission
└── _schemas/
    └── jainkosh.schema.json
```

---

## 8. Configuration (`jainkosh.yaml`)

The config is the **single source of truth** for which DOM patterns map to which
logical concept. It is Pydantic-validated at load time against `_schemas/jainkosh.schema.json`.

### 8.1 Key sections

```yaml
version: "1.6.0"
parser_rules_version: "jainkosh.rules/1.6.0"

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
    boundary: "leading_reference_or_intro"
  puraankosh:
    boundary: "p_with_id_or_whole_block"

index:
  enabled_for: ["siddhantkosh"]
  see_also_triggers: ["देखें", "विशेष देखें"]
  see_also_window_chars: 40
  see_also_leading_punct_re: '[(–\-।\s]*'
  source_chain:
    enclosing_li_fallback: true
    li_path_from_inner_ol_fallback: true

block_classes:
  SanskritText: "sanskrit_text"
  SanskritGatha: "sanskrit_gatha"
  PrakritText: "prakrit_text"
  PrakritGatha: "prakrit_gatha"
  HindiText: "hindi_text"
  HindiGatha: "hindi_gatha"

reference:
  selector: "span.GRef"
  strip_inner_anchors: true
  entity_keywords:
    gatha: [गाथा, श्लोक, सूत्र, दोहक, वार्तिक]
    kalash: [कलश]
    page: [पृष्ठ]
    pankti: [पंक्ति]

translation_marker:
  prefix: "="
  source_kinds: ["sanskrit_text", "sanskrit_gatha", "prakrit_text", "prakrit_gatha"]
  hindi_kinds: ["hindi_text", "hindi_gatha"]
  sibling_marker_enabled: true
  sibling_marker_text_node_re: '^\s*=\s*$'

nested_span:
  flatten: true
  outer_kinds: ["sanskrit_text", "prakrit_text", "hindi_text"]

table:
  selector: "table"
  store_raw_html: true
  attach_to: "current_subsection"
  fallback_when_no_subsection: "section_root"

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

ref_strip:
  enabled: true
  collapse_double_spaces: true
  collapse_orphan_parens: true
  collapse_orphan_brackets: true
  trim_trailing_chars: " ।॥;,"

redlink:
  enabled: true
  anchor_class: "new"
  href_marker_substring: "redlink=1"
  prose_strip:
    enabled: true

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

slug:
  preserve_devanagari: true
  strip_chars: "।॥.,;:!?()[]{}'\"`-"
  whitespace_to: "-"
  collapse_dashes: true
  strip_v4_numeric_prefix: true
```

### 8.2 Selector DSL semantics

| Expression | Meaning |
|---|---|
| `self.text` | Current node's text content (post-normalize) |
| `self.attribute(X)` | Current node's attribute X |
| `parent.attribute(X)` | Direct parent's attribute X |
| `ancestor::tag[N].attribute(X)` | Nth-nearest ancestor `<tag>`'s attribute X |
| `regex_group(text, name)` | Apply `regex:` to text, return named group |

If multiple variants match the same DOM node, the first match (by YAML order) wins.

---

## 9. Pydantic Models

All models are in `workers/ingestion/jainkosh/models.py` with `ConfigDict(extra="forbid")`.

```python
class ResolvedField(BaseModel):
    field: str                        # Devanagari field name, e.g. "पुस्तक"
    value: Union[int, str]            # int for numeric, str for ranges

class Reference(BaseModel):
    text: str                         # NFC verbatim text of the GRef
    inline_reference: bool = False    # True if inline (not leading)
    needs_manual_match: bool = False
    is_teeka: bool = False
    teeka_name: str = ""
    shastra_name: Optional[str] = None  # canonical name from shastra.json
    match_method: Optional[Literal["shastra_name", "alternate_name", "short_form"]] = None
    resolved_fields: list[ResolvedField] = Field(default_factory=list)

class Block(BaseModel):
    kind: BlockKind                   # see §6.1
    text_devanagari: Optional[str] = None
    hindi_translation: Optional[str] = None
    references: list[Reference] = Field(default_factory=list)
    is_orphan_translation: bool = False
    is_bullet_point: bool = False
    raw_html: Optional[str] = None   # table only
    table_rows: Optional[list[list[str]]] = None
    # see_also fields:
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: Optional[str] = None
    is_self: bool = False
    target_exists: bool = True

class Definition(BaseModel):
    definition_index: int             # 1-based per section
    blocks: list[Block]
    raw_html: Optional[str] = None

class Subsection(BaseModel):
    topic_path: Optional[str] = None  # None for label-seed topics
    heading_text: str
    heading_path: list[str]
    natural_key: str
    parent_natural_key: Optional[str] = None
    is_leaf: bool
    is_synthetic: bool = False
    label_topic_seed: bool = False
    source_subkind: Optional[str] = None
    blocks: list[Block]
    children: list["Subsection"]

class IndexRelation(BaseModel):
    label_text: str
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: str
    is_self: bool = False
    target_exists: bool = True
    source_topic_path: Optional[str] = None
    source_topic_path_chain: list[str] = Field(default_factory=list)
    source_topic_natural_key_chain: list[str] = Field(default_factory=list)
    is_top_level_reference: bool = False

class PageSection(BaseModel):
    section_kind: SectionKind         # "siddhantkosh" | "puraankosh" | "misc"
    section_index: int
    h2_text: str
    definitions: list[Definition]
    index_relations: list[IndexRelation]
    subsections: list[Subsection]
    label_topic_seeds: list[Subsection] = Field(default_factory=list)
    extra_blocks: list[Block] = Field(default_factory=list)

class KeywordParseResult(BaseModel):
    keyword: str
    source_url: str
    page_sections: list[PageSection]
    nav: Nav
    parser_version: str
    parsed_at: datetime
    warnings: list[ParserWarning] = Field(default_factory=list)

class WouldWriteEnvelope(BaseModel):
    keyword_parse_result: KeywordParseResult
    would_write: dict                 # keys: "postgres", "mongo", "neo4j" + "idempotency_contracts"
```

---

## 10. Algorithms

### 10.1 `parse_keyword_html(html, url, config) -> KeywordParseResult`

```python
def parse_keyword_html(html: str, url: str, config: JainkoshConfig) -> KeywordParseResult:
    tree = HTMLParser(html)
    main = tree.css_first(config.sections.selector)       # div.mw-parser-output
    keyword = nfc(decode_keyword_from_url(url))
    nav = extract_nav(main, config)
    drop_nav_nodes(main, nav, config)

    h2_nodes = main.css(config.sections.h2_headline_selector)
    page_sections = []
    for i, h2 in enumerate(h2_nodes):
        section_kind = classify_section(h2, config)
        section_dom = collect_siblings_until_next_h2(h2)
        section = parse_section(section_dom, section_kind=section_kind,
                                section_index=i, h2_text=clean_text(h2.text()),
                                keyword=keyword, config=config)
        page_sections.append(section)

    return KeywordParseResult(keyword=keyword, source_url=url,
                              page_sections=page_sections, nav=nav,
                              parser_version=config.parser_rules_version,
                              parsed_at=datetime.utcnow())
```

### 10.2 `parse_section` pseudocode

```python
def parse_section(elements, *, section_kind, ...):
    # Split elements into: pre_heading, index_ols, body, extra_tables
    # An element is "index" if it's a top-level <ol> before any heading-bearing element.
    # An element "contains_heading" if any V1-V4 heading variant appears as a descendant.

    definitions = parse_siddhantkosh_definitions(pre_heading, config)
                  # or parse_puraankosh_definitions for puraankosh

    index_relations = parse_index_relations(index_ols, keyword, config)
                      # [] for non-siddhantkosh

    subsections = parse_subsections(body, keyword, config)

    extra_blocks = [Block(kind="table", raw_html=html_of(t)) for t in extra_tables]

    return PageSection(...)
```

### 10.3 DFS heading discovery in classless `<p>` containers

When a **classless `<p>`** element is encountered in the DFS walk it is no longer
treated unconditionally as a content block. Instead:

1. If `contains_heading(el, config)` returns `True` for that `<p>`, the DFS
   **recurses into its direct children** (any heading variants found inside become
   heading events; non-heading children become content blocks).
2. If the `<p>` has no heading descendants, it is treated as a plain content block
   (previous behaviour).

This fixes the case where a V2-bare or V1 heading is wrapped in a classless `<p>`:
```html
<p>
  <span class="HindiText" id="1.1.2">2. heading</span>   ← V2-bare
</p>
```

### 10.4 Subsection tree assembly

```python
def parse_subsections(body_elements, keyword, config):
    flat = walk_and_collect_headings(body_elements, config)
    # Each: (topic_path, heading_text, content_elements_until_next_heading)

    nodes: dict[str, Subsection] = {}
    roots: list[Subsection] = []

    for path, heading_text, content_els in flat:
        ensure_ancestors_exist(path, nodes, roots, keyword)   # synthesise if needed
        blocks = parse_block_stream(content_els, config)
        node = build_subsection_node(path, heading_text, blocks, keyword, nodes)
        nodes[path] = node
        attach_to_parent(node, parent_of(path), nodes, roots)

    for n in nodes.values():
        n.is_leaf = (len(n.children) == 0)
    return roots
```

`walk_and_collect_headings` recursively traverses the body DOM in pre-order,
tries each heading variant in YAML order (first hit wins), and yields flat
`(topic_path, heading_text, dom_slice)` tuples.

### 10.4 Block stream + translation marker

```python
def parse_block_stream(elements, config) -> list[Block]:
    out = []
    last_block = None
    pending_refs = []

    for el in flatten_for_blocks(elements, config):
        if is_leading_reference(el, config):
            pending_refs.extend(extract_refs(el, config))
            continue
        block = make_block(el, config)
        if block is None:
            continue
        # Translation marker check
        if block.kind in HINDI_KINDS and block.text_devanagari.lstrip().startswith("="):
            if last_block and last_block.kind in SOURCE_KINDS:
                last_block.hindi_translation = strip_eq_prefix(block.text_devanagari)
                last_block.references.extend(pending_refs)
                pending_refs.clear()
                continue
            else:
                block.is_orphan_translation = True
                block.text_devanagari = strip_eq_prefix(block.text_devanagari)
        block.references.extend(pending_refs)
        pending_refs.clear()
        out.append(block)
        last_block = out[-1]

    if pending_refs and last_block:
        last_block.references.extend(pending_refs)
    return out
```

### 10.5 Natural key and slug

```python
def slug(s: str, config) -> str:
    s = nfc(s)
    if config.slug.strip_v4_numeric_prefix:
        s = re.sub(r'^\s*\d+(?:\.\d+)*[.\s]+', '', s)
    for ch in config.slug.strip_chars:
        s = s.replace(ch, "")
    s = re.sub(r'\s+', config.slug.whitespace_to, s)
    if config.slug.collapse_dashes:
        s = re.sub(r'-+', '-', s)
    return s.strip('-').strip()

def natural_key(keyword: str, heading_path: list[str], config) -> str:
    return ":".join([keyword] + [slug(h, config) for h in heading_path])
```

---

## 11. Reference Parser

Spec for structured resolution of `<span class="GRef">` citation strings against
`parser_configs/_manual_configs/shastra.json`. Implemented in `parse_reference.py`.

### 11.1 `shastra.json` format DSL

Each entry carries a `"format"` array:
```json
{
  "shastra_name": "प्रवचनसार",
  "short_form": "प्र.सा./मू.",
  "format": ["गाथा/पृष्ठ", "गाथा"],
  "type": "shastra"
}
```

**Separators:**

| Separator | Meaning |
|---|---|
| `/` | Primary section boundary |
| `,` | Sub-separator within a group |
| `-` | Sub-separator within a group (or range indicator in values — see below) |
| `§` (prefix) | The whole group is optional; value signals presence by leading `§` |

**Rule for `-` ambiguity**: if the format group separator is `,`, then `"13-14"` in the
value is a single field value (range string). If the format group separator is `-`, then
`"13-14"` splits into two field values `"13"` and `"14"`.

### 11.2 Annotated format examples

```
Format:  पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा
Value:   1/1,1,1/84/1
→  पुस्तक=1, खण्ड=1, भाग=1, सूत्र=1, पृष्ठ=84, गाथा=1

Format:  पुस्तक,भाग/§प्रकरण/पृष्ठ/पंक्ति
Value with optional:  1,2/§181/217/1  →  पुस्तक=1, भाग=2, प्रकरण=181, पृष्ठ=217, पंक्ति=1
Value without:        1,2/217/1       →  पुस्तक=1, भाग=2, पृष्ठ=217, पंक्ति=1

Format:  मुख्याधिकार-प्रकरण/श्लोक/पृष्ठ
Value:   3-7/5/18  →  मुख्याधिकार=3, प्रकरण=7, श्लोक=5, पृष्ठ=18
```

### 11.3 `Reference` model fields (post-resolution)

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | NFC verbatim text of the GRef |
| `inline_reference` | `bool` | True if inline (not leading) |
| `needs_manual_match` | `bool` | True if resolution failed |
| `is_teeka` | `bool` | True if this is a teeka reference |
| `teeka_name` | `str` | Name of teeka (if applicable) |
| `shastra_name` | `Optional[str]` | Canonical name from registry |
| `match_method` | `Optional[Literal[...]]` | `"shastra_name"` / `"alternate_name"` / `"short_form"` |
| `resolved_fields` | `list[ResolvedField]` | Parsed numeric/field values |

### 11.4 `ShastraRegistry`

Loaded from `parser_configs/_manual_configs/shastra.json`. Provides:
- `get_type(shastra_name) -> Optional[str]`: returns `"shastra"` / `"teeka"` / `"publication"` / `None`.
- Internal NFC-normalised indexes for `shastra_name`, `alternate_name`, and `short_form`.

---

## 12. Neo4j Edge Emission from References

Spec for emitting Neo4j edges from resolved `Reference` objects. Implemented in `reference_edges.py`.

### 12.1 Block-context classification

| Context | Source | Target node | Edge type |
|---|---|---|---|
| **subsection** | `Subsection.blocks[i]` | `Topic` keyed by `subsection.natural_key` | `MENTIONS_TOPIC` |
| **definition** | `Definition.blocks[i]` | `Keyword` keyed by `result.keyword` | `CONTAINS_DEFINITION` |

`extra_blocks` and `label_topic_seeds[*].blocks` are ignored (no edges emitted).

### 12.2 Reference selection per block

```python
def _pick_reference(refs: list[Reference]) -> Optional[Reference]:
    for r in refs:
        if not r.inline_reference:
            return r    # first non-inline wins
    return refs[0] if refs else None
```

The picked reference is the **main reference** (processed with block-kind-aware rules).
All remaining are processed with simplified inline rules.

### 12.3 Edge props

```python
{
    "type": "MENTIONS_TOPIC" | "CONTAINS_DEFINITION",
    "from": {"label": <src_label>, "key": <src_key>},
    "to":   <topic_or_keyword_node>,
    "props": {
        "weight": 1.0,
        "source": "jainkosh",
        "block_index": <int>,            # 0-based
        "mention_path": <str>,           # see below
        "source_natural_key": <str>,
        # CONTAINS_DEFINITION only:
        "section_index": <int>,
        "definition_index": <int>,
        # when पंक्ति resolved:
        "pankti": <int>,
    }
}
```

`mention_path`:
- `CONTAINS_DEFINITION`: `"<section_index>/<definition_index>/<block_index>"`
- `MENTIONS_TOPIC`: `"<topic_natural_key>/<block_index>"`

### 12.4 Node-key formats

| Source label | Format |
|---|---|
| `Gatha` | `<shastra>:गाथा:<n>` |
| `GathaTeeka` | `<shastra>:<teeka>:गाथा:टीका:<n>` |
| `GathaTeekaBhaavarth` | `<shastra>:<teeka>:<publisher_id>:गाथा:टीका:भावार्थ:<n>` |
| `Kalash` | `<shastra>:<teeka>:कलश:<n>` |
| `KalashBhaavarth` | `<shastra>:<teeka>:<publisher_id>:कलश:भावार्थ:<n>` |
| `Page` | `<shastra>:<teeka>:<publisher_id>:पृष्ठ:<n>` |

### 12.5 Edge-emission rules by shastra type

**Gatha edges** (when resolved field `गाथा`/`श्लोक`/`सूत्र`/`दोहक`/`वार्तिक` is present):

| Type | Block kind | Emits |
|---|---|---|
| `shastra` | any | `Gatha("<shastra>:गाथा:<g>")` |
| `teeka` | gatha kinds | `Gatha("<shastra>:गाथा:<g>")` |
| `teeka` | text kinds | `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")` |
| `publication` | gatha kinds | `Gatha("<shastra>:गाथा:<g>")` |
| `publication` | text/prakrit kinds | `GathaTeeka(...)` |
| `publication` | `hindi_text` | 2 edges: `GathaTeeka` + `GathaTeekaBhaavarth` |

**Kalash edges** (when resolved field `कलश` is present):
- `teeka` gatha kinds → `Kalash`
- `publication` gatha kinds → `Kalash`; `hindi_text` → `KalashBhaavarth`

**Page edges** (when resolved field `पृष्ठ` is present):
- `publication` only (any block kind) → `Page`

**Guard rules** — skip emission when:
- `ref.shastra_name is None`
- `registry.get_type(shastra_name)` returns None
- Rule requires `teeka_name` but it is empty
- Required numeric field is absent from `resolved_fields`

### 12.6 Deduplication

```python
def _dedupe(edges):
    key = (type, from.label, from.key, to.label, to.key, mention_path)
    # dedupe by this key — preserves distinct citation contexts
```

---

## 13. Would-Write Envelope

`envelope.py` builds the "would_write" output showing what each store would receive.

### 13.1 Postgres fragment

```python
{
  "keywords": [{"table": "keywords", "natural_key": <keyword>, "display_text": <keyword>,
                "source_url": ..., "definition_doc_ids": []}],
  "topics": [
    {"table": "topics", "natural_key": <sub.natural_key>, "topic_path": <sub.topic_path>,
     "parent_topic_natural_key": <sub.parent_natural_key>,
     "display_text": [{"lang":"hin","script":"Deva","text":<heading>}],
     "source": "jainkosh", "parent_keyword_natural_key": <keyword>,
     "is_leaf": <bool>, "is_synthetic": <bool>}
  ],
  "keyword_aliases": []  # filled by orchestrator post-parse
}
```

### 13.2 Mongo fragment

```python
{
  "keyword_definitions": [{
    "collection": "keyword_definitions",
    "natural_key": <keyword>,
    "source_url": ...,
    "page_sections": [
      {
        "section_index": ..., "section_kind": ..., "h2_text": ...,
        "definitions": [...],
        "extra_blocks": [...],
        "index_relations": [...]
        # no subsection_tree here — removed in v1.1.0
      }
    ],
    "redirect_aliases": []
  }],
  "topic_extracts": [
    {
      "collection": "topic_extracts",
      "natural_key": <sub.natural_key>,
      "topic_path": ..., "parent_natural_key": ..., "is_leaf": ...,
      "heading": [{"lang":"hin","script":"Deva","text":<heading>}],
      "blocks": [...],
      "source": "jainkosh", "source_url": ...
    }
  ]
}
```

### 13.3 Neo4j fragment

Nodes:
- `{"label":"Keyword","key":<keyword>,"props":{...}}`
- `{"label":"Topic","key":<sub.natural_key>,"props":{...}}`

Edges:
- `Keyword → Topic`: `HAS_TOPIC` (for top-level subsections)
- `Topic → Topic`: `PART_OF` (child → parent)
- `see_also` blocks: `RELATED_TO` from the topic's `natural_key`
- `IndexRelation`: `RELATED_TO` from the source topic/keyword
- `Reference`-derived: `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` (§12)

**`see_also` edge target resolution:**
- Target has `target_topic_path` and `target_keyword`: `RELATED_TO` with placeholder
  `{"label":"Topic","resolve_by":{"parent_keyword":"X","topic_path":"1.2"}}` — resolved
  by orchestrator at apply time using Postgres.
- Target has only `target_keyword`: `RELATED_TO` to `{"label":"Keyword","key":"<target_keyword>"}`.

---

## 14. CLI

```
python -m workers.ingestion.jainkosh.cli parse <html_path> [options]

Options:
  --url URL              Source URL. If omitted, derived from filename stem.
  --config PATH          Path to jainkosh.yaml (default: parser_configs/jainkosh.yaml)
  --out PATH             Output JSON path (default: <input>.parsed.json)
  --pretty               Pretty-print JSON (default true)
  --validate-only        Parse but don't write; print summary stats
  --rules-version STR    Override parser_rules_version (for testing migrations)
  --frozen-time TS       Override parsed_at (for reproducible golden tests)

Exit codes:
  0  success
  1  parse error
  2  config validation error
  3  IO error
```

**Filename → URL convention**: URL-encode the filename stem when `--url` is omitted:
```
"samples/sample_html_jainkosh_pages/द्रव्य.html" → "https://www.jainkosh.org/wiki/द्रव्य"
```

**Reproducibility**: pass `--frozen-time 2026-05-02T00:00:00Z` in tests to make
golden output byte-identical across runs.

---

## 15. Tests

### 15.1 Test categories

| Category | Location | What it verifies |
|---|---|---|
| **Golden** | `tests/test_parse_keyword_golden.py` | Parser on all 3 sample HTMLs; diff against `tests/golden/<keyword>.json`. Must be byte-identical (idempotency). |
| **Heading variants** | `tests/unit/test_heading_variants.py` | V1–V4 with minimal HTML strings. V5 must be detected as a non-heading. |
| **Translation marker** | `tests/unit/test_translation_marker.py` | Sanskrit+Hindi pair, leading `=`, sibling `=`, orphan `=`. |
| **References** | `tests/unit/test_refs.py` | Leading GRef → next block; trailing inline GRef → same block; redlink GRef with `<a>` stripped. |
| **See-also** | `tests/unit/test_see_also.py` | All `देखें` formats; self-link; redlink; inline and index variants. |
| **Nested-span** | `tests/unit/test_nested_span.py` | द्रव्य L734-759 reduced to fixture; verify block count and order. |
| **Definitions** | `tests/unit/test_definitions.py` | आत्मा SiddhantKosh → 5 defs; द्रव्य SiddhantKosh → 1; आत्मा PuranKosh → 2; द्रव्य PuranKosh → 1. |
| **Index relations** | `tests/unit/test_index_relations.py` | Three target formats; redlink; keyword-level vs section-level source. |
| **Slugging** | `tests/unit/test_topic_keys.py` | Devanagari preservation, V4 prefix strip, danda strip, dash collapse, NBSP. |
| **Config schema** | `tests/unit/test_config_schema.py` | `jainkosh.yaml` validates against JSON schema. Missing required key → fail. |
| **CLI** | `tests/unit/test_cli.py` | `parse <fixture> --out <tmp>`; verify output is valid `WouldWriteEnvelope`. |
| **Reference parser** | `tests/unit/test_reference_format_parser.py` etc. | Format DSL parsing, range/list expansion, optional groups, multi-format tries. |
| **Reference edges** | `tests/unit/test_reference_edges.py` | Per-type/per-block-kind edge tables; inline refs; guard rules. |

### 15.2 Golden generation

```bash
python -m workers.ingestion.jainkosh.cli parse \
  samples/sample_html_jainkosh_pages/आत्मा.html \
  --out tests/golden/आत्मा.json \
  --frozen-time 2026-05-02T00:00:00Z
```

Goldens are hand-reviewed before commit. Subsequent runs must produce byte-identical output.

### 15.3 Golden sanity checks

**आत्मा.json:**
- 2 page sections: `siddhantkosh`, `puraankosh`.
- SiddhantKosh: 5 Definitions; first subsection is `topic_path == "2"` (no `"1"` — don't synthesise it).
- PuranKosh: 2 Definitions (one per `<p id="1">`, `<p id="2">`).
- `RELATED_TO` edges originate from child seed natural keys (e.g. `आत्मा:एक-आत्मा-…:जीवको-आत्मा-…`), not the parent topic key.

**द्रव्य.json:**
- SiddhantKosh: 1 Definition (intro `<p class="HindiText">`); many `index_relations`; multi-level subsection tree.
- 1 `extra_block` of kind `table` at section level (the table between sections 3 and 4).

**पर्याय.json:**
- Subsection paths up to 3 levels deep (`1.1.1`, etc.).
- All `is_synthetic` flags should be false.
- Many `index_relations` including `mw-selflink-fragment` self-links.

### 15.4 Performance budget (advisory)

| File | Size | Target |
|---|---|---|
| `आत्मा.html` | 58 KB | < 200 ms |
| `द्रव्य.html` | 290 KB | < 1.5 s |
| `पर्याय.html` | 192 KB | < 1.0 s |

---

## 16. Error Model

```python
class ParseError(Exception):
    def __init__(self, message: str, *, file=None, location=None): ...
```

**Raises `ParseError` when:**
- `mw-parser-output` div not found.
- Heading regex matches but `topic_path` is empty.
- Topic tree assembly creates a cycle (defensive).
- Config doesn't validate against schema.

**Silently handled (logged as `ParserWarning`):**
- Unknown CSS class on `<p>` or `<span>` — dropped.
- Empty `<p>` after whitespace-strip — dropped.
- Image, comment, script tags — dropped.
- Trailing GRef with no surrounding block — attached to last block (fallback); warning recorded.

`KeywordParseResult.warnings` is included in goldens; unexpected new warnings cause the golden test to fail. Empty list is the goal.

---

## 17. Versioning & Changelog

The parser tags every output with `parser_rules_version`:
```
parser_rules_version = "jainkosh.rules/1.6.0"
```

Written into `KeywordParseResult.parser_version` and into Postgres `parser_configs.version`.

| Version | Summary |
|---|---|
| `1.0.0` | Initial rules. |
| `1.1.0` | Configurable `देखें` triggers + full-DFS index scan; ref-strip from `text_devanagari`; sibling `=` translation marker; redlink prose-strip; label→synthetic topic seeds; tables attach to current subsection; `IndexRelation` source path chain; idempotency contracts on envelope rows. |
| `1.2.0` | Table full outerHTML + raw_html whitespace collapse; idempotency contracts hoisted to envelope root; IndexRelation source chain via ancestor `<strong>` text; DFS leading-GRef passthrough; parenthesised `देखें` stripped from prose; label-seed scope guard; see-also-only blocks dropped; definition `(N)` numbering prefix stripped; redlink edges suppressed in Neo4j. |
| `1.3.0` | Row-style `see_also` blocks relocated from parent `Subsection.blocks` to child label-seed `blocks`; row detection at DOM level (before text stripping); `RELATED_TO` edges emitted from child seed natural key. |
| `1.4.0` | IndexRelation source-chain fallbacks for enclosing `<li>` and plain-`<strong>` headings; V2 heading inline-content extraction; inline GRef-based block splitting for positional reference attribution; index relations materialized as synthetic topic seeds in envelope outputs. |
| `1.5.0` | Nested-span GRef attribution across `<br/>` boundaries; parser version bump and golden regeneration. |
| `1.6.0` | label_seed `RELATED_TO` edges emitted from child's natural_key; `inline_reference` flag on `Reference`; nth-occurrence anchor tracking fixes duplicate `IndexRelation` and missing entry for identical `<a>` HTML. Fix: classless `<p>` container with exclusively block-classed span children is now correctly exploded (fixes 0-definition output for `वस्तु.html`-style pages). |
| `1.7.0` | Range expansion for `देखें` links: trailing `-N` after an anchor with `target_topic_path=X.M` now emits one relation per path X.M … X.N. Applies to both `IndexRelation` (index `<ol>`) and inline `see_also` blocks. |
| `1.8.0` | **V1/V2 numeric prefix stripping**: leading `N. ` or `N.M. ` prefix stripped from heading_text for V1 and V2 (with strong). **V2-bare**: `<span class="HindiText" id="N">N. heading</span>` (no inner `<strong>`) now detected as a heading when text carries numeric prefix. **V5**: new heading variant `<p class="HindiText" id="N">N. heading</p>` (no child elements, numeric prefix required). **DFS fix**: classless `<p>` elements containing heading descendants are now recursed into instead of treated as content blocks. |

---

## Edge Cases Reference

| Page | Phenomenon | Rule |
|---|---|---|
| आत्मा | Section uses V4 headings; no `<ol>` index | Detect via V4 regex; `index_relations` is empty. |
| आत्मा | Standalone `• X - देखें Y` between subsections | Inline `देखें` (§6.7); attached to child label-seed. |
| आत्मा | PuranKosh `<p id="1">(1)…`, `<p id="2">…` | Two separate Definitions (§3.2). |
| द्रव्य | Mixed V1+V2 headings within same section | Detect both. |
| द्रव्य | Big `<table>` between sections 3 and 4 | Section's `extra_blocks` (§6.5). |
| द्रव्य | Nested `<span class="SanskritText">…<span>…</span></span>` | Flatten via §6.4. |
| द्रव्य | PuranKosh single paragraph in `<div class="HindiText">` | One Definition with one `hindi_text` block. |
| पर्याय | V3 (`<li>`) + V1 (`<strong>`) mixed | Both detected. |
| पर्याय | `<ul class="HindiText">` at outer index level | Keyword-level relation (§4.2). |
| पर्याय | 3-level deep paths (`1.1.3`) | Tree assembly synthesises missing parents if needed. |
| वस्तु | All SiddhantKosh content in a classless `<p>` wrapping block-class spans | Exploded by `_is_block_span_container()` helper. |
| any | Self-link `<a class="mw-selflink-fragment" href="#3">` | `is_self=true` (§4.3). |
| any | Redlink `/w/index.php?title=X&action=edit&redlink=1` | Capture with `target_exists=false`; no Neo4j edge. |
| any | Trailing `<br/>` and stray `&#160;` | Whitespace-normalise (§6.9). |
