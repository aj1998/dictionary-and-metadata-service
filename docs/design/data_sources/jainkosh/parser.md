# JainKosh Parser — Complete Reference

> Single authoritative doc for anyone working with the JainKosh parser.
> Covers HTML structure rules, parser implementation, configuration, models,
> algorithms, CLI, tests, and edge-emission specs.
>
> **Current version**: `jainkosh.rules/1.11.2`
>
> Archived source specs (pre-v1.7 detail):
> `detailed_docs/parsing_rules.md`, `parser_spec.md`,
> `reference_parser_spec.md`, `reference_edge_creation_spec.md`

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
- No HTTP, no DB writes, no async I/O. Fully synchronous Python.
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

### 3.4 Idempotency contracts

The `would_write` envelope carries a top-level `idempotency_contracts` map keyed
by `"<store>:<table>"`. Describes conflict key + field-level merge policy for
idempotent upserts. Controlled by `envelope.idempotency_mode` (default `envelope_root`).
See `detailed_docs/parser_spec.md §3.4` for full schema.

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
3. `<ul>` *inside* a top-level `<li>` → relation sourced from that section's topic. `<ul>` at outer `<ol>` level → keyword-level relation (`source = None`).

### 4.3 Range expansion for `देखें` links (v1.7.0)

When a `देखें` link has `target_topic_path` like `X.M` and the text **immediately
following** the anchor is `-N` (hyphen or en-dash + number, where N > M), the parser
expands into N − M + 1 relations covering `X.M` through `X.N`.

Example from स्वभाव:
```
देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-6।
→  four IndexRelations: target_topic_path = "1.3", "1.4", "1.5", "1.6"

देखें <a href="/wiki/गुण#3.9">गुण - 3.9</a>-11।
→  three IndexRelations: target_topic_path = "3.9", "3.10", "3.11"
```

Rules:
- Only the **last** path segment is iterated; prefix remains fixed.
- If `target_topic_path` is absent (keyword-only link), expansion is skipped.
- If N ≤ M, one relation emitted as usual.
- All expanded relations share the same `label_text`, `source_topic_path_chain`, and `target_keyword`.
- Applies to both `IndexRelation` (index `<ol>`) and `see_also` `Block` (inline `देखें`).

Implemented in `see_also.py`:
- `_extract_range_suffix_after_anchor(a, nth_occurrence)` — detects the `-N` suffix
- `_expand_parsed_to_range(parsed, end_num)` — produces the list of expanded dicts

### 4.4 Three target formats for `देखें` links

| href shape | `target_keyword` | `target_topic_path` | `is_self` |
|---|---|---|---|
| `/wiki/X` | `X` (NFC, underscores preserved) | `None` | `false` |
| `/wiki/X#Y` | `X` (NFC, underscores preserved) | `Y` | `false` |
| `#X.Y` (`mw-selflink-fragment`) | current keyword | `X.Y` | `true` |
| `/w/index.php?title=X&action=edit&redlink=1` | `X` (decoded, underscores preserved) | `None` | `false` / `target_exists=false` |

`target_keyword` from `/wiki/<percent-encoded>` is URL-decoded then NFC-normalised. **Underscores are preserved** (not converted to spaces) — MediaWiki encodes spaces as `_` in URLs, so `प्रकृति_बंध` in a href represents the keyword `प्रकृति_बंध`, consistent with how `decode_keyword_from_url` processes the main page URL. (v1.11.1)

### 4.5 Configurable `देखें` triggers

Config: `index.see_also_triggers` (e.g. `["देखें", "विशेष देखें"]`). Triggers are sorted
longest-first and joined into a regex alternation. The scanner uses a **full CSS `a`-element
scan (DFS)** of the entire index `<ol>` subtree — not a two-tier walk.

| Config key | Default | Meaning |
|---|---|---|
| `see_also_triggers` | `["देखें"]` | Trigger words |
| `see_also_window_chars` | `40` | Max preceding chars to inspect |
| `see_also_leading_punct_re` | `[(–\-।\s]*` | Punct allowed between label and trigger |

### 4.6 IndexRelation source chain resolution (v1.4.0)

`IndexRelation.source_topic_path_chain` resolved by walking ancestor `<li>` containers upward.

Two fallback rules:
- **Enclosing-`<li>` fallback**: when previous-sibling scan is exhausted, resolution climbs to the enclosing parent `<li>`. (`index.source_chain.enclosing_li_fallback`, default `true`)
- **Inner-`<ol>` path fallback**: for `<li>` headings where `<strong>` has plain text (no `<a href="#...">`), path derived from first direct inner-`<ol>` anchor by trimming last segment (e.g. `#4.4.1` → `4.4`). (`index.source_chain.li_path_from_inner_ol_fallback`, default `true`)

---

## 5. Subsections (Topic Seeds)

A subsection is a numbered heading + its content, possibly with children.
Subsections form a **tree** keyed by `topic_path` (e.g. `1`, `1.1`, `1.1.3`).

### 5.1 Heading variants

There are **5 active heading variants** plus one non-heading look-alike (V5-def).

| Variant | DOM shape | `topic_path` source | Seen in |
|---|---|---|---|
| **V1** | `<strong id="N">heading</strong>` | `@id` of `<strong>` | द्रव्य, पर्याय, स्वभाव |
| **V2** | `<span class="HindiText" id="N"><strong>heading</strong></span>` | `@id` of `<span>` | द्रव्य |
| **V2-bare** | `<span class="HindiText" id="N">N. heading</span>` (no inner `<strong>`) | `@id` of `<span>` | स्वभाव |
| **V3** | `<li id="N"><span class="HindiText"><strong>heading</strong></span>` | `@id` of `<li>` | पर्याय |
| **V4** | `<p class="HindiText"><b>N. heading</b></p>` | regex on text `^\s*(?P<id>\d+(?:\.\d+)*)[.\s]+(?P<heading>.+?)\s*$` | आत्मा |
| **V5** | `<p class="HindiText" id="N">N. heading</p>` (no child elements) | `@id` of `<p>` | स्वभाव |
| **V5-def** | `<p id="N" class="HindiText">(N) text…</p>` | **Not a heading** — PuranKosh definition | आत्मा PuranKosh |

**Numeric prefix stripping** (V1, V2, V2-bare, V5): leading `\d+(?:\.\d+)*[.\s]+` is stripped
from `heading_text`. If stripping leaves an empty string, the element is rejected.

**V2-bare guard**: the no-strong fallback only fires when (a) the span has no direct child
elements AND (b) the text starts with a numeric prefix. Plain `<span class="HindiText" id="N">text</span>`
without a numeric prefix is not treated as a heading.

**V2-bare inline-content guard**: `_make_v2_content_block` returns `None` immediately for V2-bare
spans (no inner `<strong>`). Without this guard the entire heading text was re-emitted as a
`hindi_text` content block inside the subsection's own blocks. Affected: स्वभाव `1.1.2`, `1.1.3`, `1.1.4`.

**V5 guard**: same conditions as V2-bare but for `<p>` elements. Ensures PuranKosh definitions
`<p id="N" class="HindiText">(N) text</p>` (parenthesised prefix) are not promoted.

### 5.2 Topic path tree assembly

1. Walk the section's body in document order.
2. On each heading, parse its `topic_path`.
3. Look up parent path by removing the last segment (`"1.1.3"` → `"1.1"`).
4. **Synthesise missing intermediates**: if `1.1.3` appears but `1.1` was never declared,
   create a synthetic `1.1` with `is_synthetic=true`, `heading_text=""`.

### 5.3 Natural keys and slugging

Every subsection emits a `Topic` with:

- `natural_key`: `<keyword>:<slug(h1)>:<slug(h2)>:…` e.g. `द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ`
- `topic_path`: the numeric id path e.g. `"1.1"`.
- `parent_topic_natural_key`: parent's `natural_key`, or `None` for top-level.

**Slug rules (Devanagari-aware):**
- NFC-normalise → strip V4 numeric prefix → replace whitespace with `-` → strip `।॥` and ASCII punct → collapse `-` → trim.

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

### 5.5 After-`देखें` text as synthetic topic seed (v1.9.0)

When a HindiText block takes the shape `देखें <X> text_after` — i.e., the block
**starts** with the `देखें` trigger (only leading whitespace allowed before it) and
there is **Devanagari text following the anchor** — the text after the link becomes a
**synthetic Topic seed**:

- `is_synthetic = True`, `label_topic_seed = True`, `topic_path = None`, `is_leaf = True`
- `heading_text` = `text_after` (content text following the anchor).
- The `see_also` block pointing to `<X>` is assigned to the child seed's `blocks`.
- The original element is **skipped** in the parent's block stream.

**Detection rules:**
- Only fires when `label_to_topic.enabled = true`.
- Element's raw text must start with a `देखें` trigger — prose before the trigger disqualifies it.
- Parenthesised patterns like `(देखें X)` and mid-prose `... देखें X ...` are NOT affected.
- After text must contain at least one Devanagari character.

**`extract_text_after_anchor` stops at `<br/>`**: when the anchor is inside an element that has
multiple देखें lines separated by `<br/>`, only the text up to (and not including) the next
`<br/>` is returned as `after_anchor_text`. Prevents bleed-through of subsequent देखें lines.

**Implemented in:**
- `see_also.extract_text_after_anchor(a, nth_occurrence)` — extracts text after anchor, stopping at `<br/>`.
- `parse_blocks._is_after_dekhen_element(el, config)` — detection predicate.
- `parse_subsections.extract_after_dekhen_relations_from_elements(elements, keyword, config)`.
- `extract_label_seed_candidates_from_elements` — uses `after_anchor_text` as fallback label.

**Example** (स्वभाव § 1.1.4):
```
<p class="HindiText">देखें <a href="/wiki/तत्त्व#1.1">तत्त्व - 1.1</a>
तत्त्व, परमार्थ, द्रव्य, स्वभाव, परमपरम ये सब एकार्थवाची हैं।</p>
→ child seed: heading = "तत्त्व, परमार्थ, द्रव्य, स्वभाव, परमपरम ये सब एकार्थवाची हैं"
              blocks  = [see_also → तत्त्व:1.1]
```

### 5.6 `<br/>`-separated `देखें` in definition elements → section-level seeds (v1.10.0)

When a HindiText element contains **initial prose** followed by one or more `<br/>`-separated
`देखें <link> (label text)` lines — i.e. the element does **not** start with the trigger —
each देखें line becomes a **section-level `label_topic_seed`** in `PageSection.label_topic_seeds`.

Pattern (वस्तु):
```html
<span class="HindiText">
  initial prose.<br/>
  देखें <a href="/wiki/X#1.7">X 1.7</a> - (label A).<br/>
  देखें <a href="/wiki/Y#1.4">Y 1.4</a> (label B).<br/>
</span>
```

**Processing rules:**
1. Detected by `_is_br_dekhen_element` (has `<br/>`, does NOT start with trigger, has देखें anchors with Devanagari after-text).
2. For each देखें anchor, `extract_text_after_anchor` (stopping at `<br/>`) retrieves the after-text.
3. Outer parentheses are stripped: `- (label text)।` → `label text`.
4. A `Subsection` seed created with `parent=None` (section root), `label_topic_seed=True`.
5. The matching `see_also` block is assigned to the seed's `blocks`.
6. **Post-processing of definitions**: देखें trigger lines stripped from `hindi_translation` using
   `_strip_br_dekhen_lines`. Corresponding `see_also` blocks removed from `Definition.blocks`.

**Implemented in:**
- `see_also.extract_text_after_anchor` — stops at `<br/>` (shared with §5.5).
- `parse_blocks._is_br_dekhen_element(el, config)`.
- `parse_subsections.extract_br_dekhen_seeds_from_elements(elements, keyword, config)`.
- `parse_subsections._strip_br_dekhen_lines(text, config)`.
- `parse_subsections._strip_outer_parens(text)`.
- `parse_section.parse_section` — populates `PageSection.label_topic_seeds` and post-processes definitions.

**Example** (वस्तु § definition 3):
```
<span class="HindiText">
  अर्थक्रियाकारित्व ही वस्तु का लक्षण है।<br/>
  देखें <a href="/wiki/द्रव्य#1.7">द्रव्य 1.7</a> - (सत्त, सत्त्व, …एकार्थवाची शब्द हैं)।
</span>
→ PageSection.label_topic_seeds[0]:
    heading_text = "सत्त, सत्त्व, …एकार्थवाची शब्द हैं"
    blocks       = [see_also → द्रव्य:1.7]
  Definition hindi_translation cleaned to: "अर्थक्रियाकारित्व ही वस्तु का लक्षण है।"
```

### 5.7 Parenthesised `देखें` cleanup (v1.2.0)

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

**Sibling text-node `=` (§6.11)**: `=` as a bare text node between two element siblings is
also recognised as a translation marker (configurable via `translation_marker.sibling_marker_enabled`).

### 6.3 References (GRef) — leading vs trailing

Any `<a href>` inside `<span class="GRef">` is **stripped** (only visible text kept).

- **Leading reference**: a `<p>` whose only meaningful child is one or more `<span class="GRef">`s,
  immediately *before* a body block → attached to the **following** block as `references[]`.
- **Trailing reference**: `<span class="GRef">` *inside* a body block → attached to that block.

**Inline GRef-based block splitting (v1.4.0)**: when meaningful prose continues after an
inline reference, the block is split at GRef boundaries:
- `TEXT_A <GRef>R1</GRef> TEXT_B <GRef>R2</GRef>` → two `hindi_text` blocks (TEXT_A with R1; TEXT_B with R2).

**GRef text stripped from `text_devanagari`**: clean-up collapses orphan brackets, multiple spaces,
space before danda `।`. Controlled by `ref_strip.enabled` and `ref_strip.trim_trailing_chars`.

### 6.4 Nested-span exception

When a `<span class="SanskritText">` contains nested elements, emit outer span's direct text
nodes as a separate block, then iterate nested children left-to-right using normal rules.
Configurable via `nested_span_flatten: true|false`.

**Classless `<p>` container (v1.6.0)**: when a classless `<p>` element's direct children are
exclusively GRef spans, block-classed spans, and `<br>` tags, it is exploded into its direct
children before block stream processing (`_is_block_span_container()` in `parse_blocks.py`).

### 6.5 Tables

Tables kept as full outerHTML in `Block(kind="table", raw_html="…")`.

Attachment (`table.attach_to`, default `current_subsection`):
- **Inside a subsection's body** → attach to that subsection's `blocks`.
- **Before any heading in section** (orphan) → attach to `PageSection.extra_blocks`.

### 6.6 Adjacent-page navigation

`<a>` with text `पूर्व पृष्ठ` / `अगला पृष्ठ` — containing `<p>` is dropped; hrefs captured
into `KeywordParseResult.nav`.

### 6.7 Inline `देखें` extraction

Any anchor whose **immediately preceding inline text** (within `see_also_window_chars` chars)
matches the configured trigger pattern is a `see_also` block.

**Redlink anchor**: when anchor is a MediaWiki redlink (`class="new"` or `href` contains
`redlink=1`), the `see_also` block is emitted with `target_exists=false` AND the
`देखें <redlink>` substring is removed from `text_devanagari`. If block becomes empty after
stripping, it is dropped.

**Redlink edge suppression (v1.2.0)**: `RELATED_TO` edges are **not emitted** when
`target_exists=false`. Controlled by `neo4j.redlink_edges` (default `never`).

### 6.8 See-also-only block drop (v1.2.0 / v1.3.0)

A block whose entire content is `• X – देखें Y` is **dropped** from the parent
`Subsection.blocks`. The accompanying `see_also` block is relocated to the child
label-seed subsection's `blocks`. Controlled by `see_also_only_block.drop` (default `true`).

### 6.9 DFS leading-GRef passthrough (v1.2.0)

Top-level `<span class="GRef">` siblings inside an `<li>` heading body are preserved as
content events in `walk_and_collect_headings` so the leading GRef reaches `parse_block_stream`
and attaches to the next emitted block. (`dfs.passthrough_leading_gref`, default `true`)

### 6.10 DFS heading discovery in classless `<p>` containers (v1.8.0)

When a **classless `<p>`** element is encountered in the DFS walk:
1. If `contains_heading(el, config)` → DFS **recurses into its direct children**.
2. Otherwise → treated as a plain content block.

This fixes the case where a V2-bare or V1 heading is wrapped in a classless `<p>`:
```html
<p>
  <span class="HindiText" id="1.1.2">2. heading</span>   ← V2-bare inside classless p
</p>
```

### 6.11 Whitespace normalisation

Applied to every text field after extraction:
1. Unicode NFC → Replace NBSP with space → Strip ZWJ/ZWNJ → Collapse whitespace runs to single space (preserve `\n` from `<br/>`) → `.strip()`.

`<br/>` inside a block becomes `\n`. Multiple consecutive `<br/>` collapse to one `\n`. Trailing `<br/>` dropped.

---

## 7. File Layout

```
workers/ingestion/jainkosh/
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
    ├── golden/             # Golden JSON for snapshot tests
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

The config is the **single source of truth** for DOM-to-concept mapping. Schema-validated at
load time against `_schemas/jainkosh.schema.json`. See `detailed_docs/parser_spec.md §3`
for the full annotated YAML. Key top-level sections:

| Section | Purpose |
|---|---|
| `normalization` | NFC, ZWJ/ZWNJ strip, whitespace collapse, br→newline |
| `sections` | `div.mw-parser-output` selector + `h2` headline selector + section kind ids |
| `definitions` | Boundary rules per section kind |
| `index` | `see_also_triggers`, `see_also_window_chars`, `source_chain` fallbacks |
| `block_classes` | CSS class → block kind mapping |
| `reference` | `span.GRef` selector, `strip_inner_anchors` |
| `translation_marker` | `=` prefix + sibling text-node marker config |
| `nested_span` | `flatten` + `outer_kinds` |
| `table` | Selector, `attach_to` strategy |
| `headings.variants` | V1–V4 variant definitions (V5/V2-bare handled in code) |
| `ref_strip` | `trim_trailing_chars`, bracket collapse |
| `redlink` | `anchor_class`, `href_marker_substring`, `prose_strip` |
| `label_to_topic` | `enabled`, bullet prefixes, `attach_to`, seed flags |
| `slug` | `preserve_devanagari`, `strip_chars`, `whitespace_to`, `strip_v4_numeric_prefix` |

### 8.1 Selector DSL semantics

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

All models in `workers/ingestion/jainkosh/models.py` with `ConfigDict(extra="forbid")`.

| Model | Key fields |
|---|---|
| `Reference` | `text`, `inline_reference`, `needs_manual_match`, `is_teeka`, `teeka_name`, `shastra_name`, `match_method`, `resolved_fields: list[ResolvedField]` |
| `Block` | `kind: BlockKind`, `text_devanagari`, `hindi_translation`, `references`, `is_orphan_translation`, `raw_html` (table only), `target_keyword/topic_path/url/is_self/target_exists` (see_also) |
| `Definition` | `definition_index` (1-based), `blocks`, `raw_html` |
| `Subsection` | `topic_path` (None for label-seed), `heading_text`, `heading_path`, `natural_key`, `parent_natural_key`, `is_leaf`, `is_synthetic`, `label_topic_seed`, `blocks`, `children` |
| `IndexRelation` | `label_text`, `target_keyword`, `target_topic_path`, `target_url`, `is_self`, `target_exists`, `source_topic_path`, `source_topic_path_chain`, `source_topic_natural_key_chain`, `is_top_level_reference` |
| `PageSection` | `section_kind`, `section_index`, `h2_text`, `definitions`, `index_relations`, `subsections`, `label_topic_seeds`, `extra_blocks` |
| `KeywordParseResult` | `keyword`, `source_url`, `page_sections`, `nav`, `parser_version`, `parsed_at`, `warnings` |
| `WouldWriteEnvelope` | `keyword_parse_result`, `would_write` (keys: `postgres`, `mongo`, `neo4j`, `idempotency_contracts`) |

---

## 10. Algorithms

### 10.1 Top-level flow

```python
parse_keyword_html(html, url, config):
    tree = HTMLParser(html)
    main = tree.css_first("div.mw-parser-output")
    keyword = nfc(decode_keyword_from_url(url))
    nav = extract_nav(main, config); drop_nav_nodes(main, nav, config)
    for h2 in main.css("h2 span.mw-headline"):
        section_dom = collect_siblings_until_next_h2(h2)
        section = parse_section(section_dom, section_kind, ...)
    return KeywordParseResult(...)
```

### 10.2 `parse_section` flow

Split elements into pre-heading, index `<ol>`s, body, extra-tables →
`parse_definitions` → `parse_index_relations` → `parse_subsections` → `PageSection`.

### 10.3 Subsection tree assembly

Walk body DOM in pre-order yielding `(topic_path, heading_text, dom_slice)` tuples.
For each path: synthesise missing ancestors, build node, attach to parent.
After all nodes: mark leaves (`is_leaf = len(children) == 0`).

### 10.4 Block stream

For each element in `flatten_for_blocks(elements, config)`:
- Leading GRef-only `<p>` → accumulate `pending_refs`.
- HindiText starting with `=` + previous block is source kind → merge as `hindi_translation`.
- Otherwise → emit block, flush `pending_refs`.

### 10.5 Natural key / slug

```python
slug(s): nfc → strip V4 prefix → replace whitespace with '-' → strip punct → collapse dashes
natural_key(keyword, heading_path): ":".join([keyword] + [slug(h) for h in heading_path])
```

---

## 11. Reference Parser

Structured resolution of `<span class="GRef">` citation strings against `shastra.json`.
Implemented in `parse_reference.py`. See `detailed_docs/reference_parser_spec.md`
for full format DSL, annotated examples, and `ShastraRegistry` spec.

**Key format DSL rules:**
- `/` = primary section boundary; `,` or `-` = sub-separator within a group; `§` prefix = optional group.
- `-` ambiguity: if format group separator is `,` then `"13-14"` is a range string (single value); if separator is `-` then `"13-14"` splits into two field values.
- **`{word1/word2}fieldname` — keyword trigger group (v1.11.3)**: a group enclosed in `{…}` lists exact trigger words separated by `/`. If the corresponding position in the reference numeric stream starts with any of the listed words, the following number is mapped to `fieldname`. The matched trigger is suppressed from level-2 `_extract_keyword_fields`. Used in धवला format 1 to unambiguously capture `गाथा` or `श्लोक` as the गाथा field when the word appears literally between other numeric groups.
- Resolution tries `shastra_name`, then `alternate_name`, then `short_form` (sets `match_method`).
- **Space-to-slash fallback (v1.11.1)**: if name_raw contains spaces and all lookups fail, also try replacing spaces with `/` — handles `(नयचक्र (श्रुतभवन)/N)` which after paren-stripping gives `"नयचक्र श्रुतभवन"`, matched as `"नयचक्र/श्रुतभवन"`.
- Unresolved → `needs_manual_match=true`.

**Two-pass numeric resolution (v1.11.3)**: when a format has keyword trigger groups, the parser computes a second preprocessing pass that skips section-keyword stripping so the keywords remain visible in the numeric stream (`numeric_clean_with_kw`). This is used only for formats that contain `{…}` groups; regular formats continue to use the keyword-stripped numeric string.

**`ShastraRegistry`**: loaded from `shastra.json`; NFC-indexed on name/alternate/short_form.
`get_type(shastra_name)` → `"shastra"` | `"teeka"` | `"publication"` | `None`.

**Multi-verse block splitting (v1.11.1)**: when a leading GRef expands to 2+ references all from the same source text with distinct `गाथा` field values, the associated source-language block is split into N blocks at `।{verse_number}।` Devanagari markers. Each split block carries exactly one non-inline reference. Inline references travel with the last split block. When a verse number marker is absent from one of the language layers (source or translation), the corresponding segment gets all text up to the next marker or all remaining text. Implemented in `parse_blocks.split_multi_verse_blocks` (called as post-processing in `parse_block_stream`).

---

## 12. Neo4j Edge Emission from References

Implemented in `reference_edges.py`. See `detailed_docs/reference_edge_creation_spec.md`
for full block-context classification, guard rules, and node-key formats.

### 12.1 Edge types

| Context | Source node | Edge type |
|---|---|---|
| subsection block | `Topic` keyed by `subsection.natural_key` | `MENTIONS_TOPIC` |
| definition block | `Keyword` keyed by `result.keyword` | `CONTAINS_DEFINITION` |

`extra_blocks` and `label_topic_seeds[*].blocks` → no edges.

### 12.2 Gatha edge rules by shastra type + block kind

| Type | Block kind | Condition | Target node |
|---|---|---|---|
| `shastra` | any | — | `Gatha("<shastra>:गाथा:<g>")` |
| `teeka` | gatha kinds | — | `Gatha` |
| `teeka` | text kinds | — | `GathaTeeka("<shastra>:<teeka>:गाथा:टीका:<g>")` |
| `publication` | gatha kinds | — | `Gatha` |
| `publication` | text/prakrit kinds | — | `GathaTeeka` |
| `publication` | `hindi_text` | teeka present | 2 edges: `GathaTeeka` + `GathaTeekaBhaavarth` |
| `publication` | `hindi_text` | no teeka, `hindi_translation` present | `Gatha` |
| `publication` | `hindi_text` | no teeka, `hindi_translation` is `null` | `GathaTeekaBhaavarth("<shastra>:<pub_id>:गाथा:टीका:भावार्थ:<g>")` |

**`hindi_text` bhaavarth rule (v1.11.1)**: when a `hindi_text` block has `hindi_translation=null`, the block is standalone prose (not a verse translation) and is emitted as `GathaTeekaBhaavarth` rather than `Gatha`.

**Kalash**: `teeka`/`publication` gatha → `Kalash`; `publication` `hindi_text` → `KalashBhaavarth`.
**Page**: `publication` only → `Page`. **Guard**: skip when `shastra_name=None`, type=None, required field absent.

### 12.3 `see_also` edge target resolution

- `target_topic_path` present → `RELATED_TO` with placeholder `{"label":"Topic","resolve_by":{"parent_keyword":"X","topic_path":"1.2"}}` — resolved by orchestrator using Postgres.
- Only `target_keyword` → `RELATED_TO` to `{"label":"Keyword","key":"<target_keyword>"}`.

---

## 13. Would-Write Envelope

`envelope.py` builds the "would_write" output. See `detailed_docs/parser_spec.md §5`
for full annotated JSON examples.

**Postgres**: `keywords` row + `topics` rows (one per non-synthetic subsection + synthetic label seeds).

**Mongo**: `keyword_definitions` doc (sections with definitions + index_relations, no subsection_tree since v1.1.0)
+ `topic_extracts` docs (one per subsection, with blocks).

**Neo4j**:
- Nodes: `Keyword` + `Topic` per subsection.
- Edges: `HAS_TOPIC` (Keyword→top-level Topic), `PART_OF` (Topic→parent Topic),
  `RELATED_TO` (from see_also + IndexRelation), `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` (from §12).

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

Exit codes: 0=success  1=parse error  2=config validation error  3=IO error
```

**Filename → URL convention**: URL-encode the filename stem when `--url` is omitted.

**Reproducibility**: pass `--frozen-time 2026-05-02T00:00:00Z` in tests to make
golden output byte-identical across runs.

---

## 15. Tests

| Category | Location | What it verifies |
|---|---|---|
| **Golden** | `tests/test_parse_keyword_golden.py` | Parser on all sample HTMLs; diff against `tests/golden/<keyword>.json`. Must be byte-identical. |
| **Heading variants** | `tests/unit/test_heading_variants.py` | V1–V4 with minimal HTML; V5 detected as non-heading. |
| **Translation marker** | `tests/unit/test_translation_marker.py` | Sanskrit+Hindi pair, leading `=`, sibling `=`, orphan `=`. |
| **References** | `tests/unit/test_refs.py` | Leading GRef → next block; trailing inline; redlink `<a>` stripped. |
| **See-also** | `tests/unit/test_see_also.py` | All `देखें` formats; self-link; redlink; inline and index variants. |
| **Nested-span** | `tests/unit/test_nested_span.py` | द्रव्य L734-759 reduced fixture; verify block count and order. |
| **Definitions** | `tests/unit/test_definitions.py` | आत्मा SiddhantKosh → 5 defs; द्रव्य → 1; आत्मा PuranKosh → 2. |
| **Index relations** | `tests/unit/test_index_relations.py` | Three target formats; redlink; keyword-level vs section-level source. |
| **Slugging** | `tests/unit/test_topic_keys.py` | Devanagari preservation, V4 prefix strip, danda strip, dash collapse, NBSP. |
| **Config schema** | `tests/unit/test_config_schema.py` | `jainkosh.yaml` validates against JSON schema. |
| **CLI** | `tests/unit/test_cli.py` | `parse <fixture> --out <tmp>`; verify valid `WouldWriteEnvelope`. |
| **Reference parser** | `tests/unit/test_reference_format_parser.py` | Format DSL, range/list expansion, optional groups, multi-format tries. |
| **Reference edges** | `tests/unit/test_reference_edges.py` | Per-type/per-block-kind edge tables; inline refs; guard rules. |

### 15.1 Golden generation

```bash
python -m workers.ingestion.jainkosh.cli parse \
  samples/sample_html_jainkosh_pages/आत्मा.html \
  --out tests/golden/आत्मा.json \
  --frozen-time 2026-05-02T00:00:00Z
```

Goldens are hand-reviewed before commit. Subsequent runs must produce byte-identical output.

### 15.2 Golden sanity checks

**आत्मा.json:** 2 sections (siddhantkosh, puraankosh). SiddhantKosh: 5 Definitions; first subsection
`topic_path == "2"` (no `"1"` — don't synthesise it). PuranKosh: 2 Definitions (one per `<p id>`).
`RELATED_TO` edges from child seed natural keys (not parent topic key).

**द्रव्य.json:** SiddhantKosh: 1 Definition; many `index_relations`; multi-level subsection tree.
1 `extra_block` of kind `table` at section level.

**पर्याय.json:** Subsection paths up to 3 levels (`1.1.1`). All `is_synthetic` flags false.
Many `index_relations` including `mw-selflink-fragment` self-links.

---

## 16. Error Model

**Raises `ParseError` when:**
- `mw-parser-output` div not found.
- Heading regex matches but `topic_path` is empty.
- Topic tree assembly creates a cycle (defensive).
- Config doesn't validate against schema.

**Silently handled (logged as `ParserWarning`):**
- Unknown CSS class on `<p>` or `<span>` — dropped.
- Empty `<p>` after whitespace-strip — dropped.
- Image, comment, script tags — dropped.
- Trailing GRef with no surrounding block — attached to last block; warning recorded.

`KeywordParseResult.warnings` is included in goldens; unexpected new warnings cause the golden test to fail.

---

## 17. Versioning & Changelog

The parser tags every output with `parser_rules_version` written into `KeywordParseResult.parser_version`.

**v1.0.0–v1.6.0** — See `detailed_docs/parser_spec.md` header for phased fix specs.
Summary: configurable triggers, ref-strip, sibling `=` marker, redlink prose-strip, label→topic seeds,
table attachment, IndexRelation chain, idempotency contracts, row-style relocation, GRef block splitting,
DFS leading-GRef passthrough, paren-`देखें` cleanup, nth-occurrence anchor dedup.

| Version | Summary |
|---|---|
| `1.7.0` | Range expansion for `देखें` links: trailing `-N` after an anchor with `target_topic_path=X.M` emits one relation per path X.M…X.N. Applies to both `IndexRelation` and inline `see_also` blocks. |
| `1.8.0` | V1/V2 numeric prefix stripping. V2-bare variant (`<span id="N">N. heading</span>`). V5 variant (`<p id="N">N. heading</p>`). DFS classless `<p>` recursion fix. |
| `1.8.1` | V2-bare inline-content fix: `_make_v2_content_block` returns `None` for V2-bare spans, preventing heading text re-emission as `hindi_text` block. |
| `1.9.0` | After-`देखें` text as topic seed: HindiText element starting with `देखें <link> text_after` creates synthetic child seed. `extract_text_after_anchor` stops at `<br/>`. |
| `1.10.0` | `<br/>`-separated `देखें` as section-level seeds: initial prose + `<br/>`-separated `देखें (label)` lines → `PageSection.label_topic_seeds`. Definition `hindi_translation` cleaned. |
| `1.10.1` | Classless `<p>` containers with `<strong>/<b>` direct children: `_is_block_span_container` now allows `<strong>/<b>` as transparent wrappers. `parse_block_stream` carries the sibling `=` marker forward when a `<strong>/<b>` between source block and HindiText span produces no block, accumulating its text into the translation prefix. Fixes स्वभाव subsection 2.4 where `<strong><span class="HindiText">प्रश्न</span></strong>` was silently dropped. |
| `1.11.1` | **(1)** Multi-verse block splitting: blocks whose non-inline refs all come from the same GRef text and carry multiple गाथा values are split at `।N।` markers (one block per verse). **(2)** Keyword underscore preservation: `target_keyword` in `see_also` blocks now keeps MediaWiki URL underscores (`प्रकृति_बंध`) instead of converting to spaces. **(3)** Space-to-slash matching in `ShastraRegistry`: names with spaces are tried as `/`-joined variants to handle `(नयचक्र (श्रुतभवन)/N)` after paren stripping. **(4)** `hindi_text` + `hindi_translation=null` + publication type + no teeka → `GathaTeekaBhaavarth` edge (was `Gatha`). |
| `1.11.2` | **(1)** Stray-semicolon cleanup: after `strip_refs_from_text`, lines that consist solely of `;` (inter-GRef separator text left after stripping adjacent `<span class="GRef">` elements) are removed and multiple blank lines collapsed. **(2)** Flexible-whitespace ref matching: when exact `ref.text` is not found in the block text (because `_render_inline` normalises HTML-source newlines per line while `extract_ref_text` uses `text(strip=True)` which preserves internal `\n`), a regex with `\s+` between tokens is tried as a fallback. Both fixes apply in `strip_refs_from_text`. |
| `1.11.3` | **Keyword trigger groups in format strings**: `{word1/word2}fieldname` syntax in `shastra.json` format strings. When the numeric stream at this position starts with one of the listed words, the trailing number is mapped to `fieldname` and the trigger word is suppressed from level-2 keyword extraction. Resolves धवला references of the form `धवला N/K,B,S/ गाथा G/P` and `धवला N/K,B,S/ श्लोक G/P` correctly — `गाथा`/`श्लोक` trigger maps to the `गाथा` field, and `पृष्ठ` follows. Previously these were `needs_manual_match=true` (गाथा refs) or produced wrong field order plus an extra `श्लोक` field (श्लोक refs). |

---

## Edge Cases Reference

| Page | Phenomenon | Rule |
|---|---|---|
| आत्मा | V4 headings; no `<ol>` index | Detect via V4 regex; `index_relations` is empty. |
| आत्मा | Standalone `• X - देखें Y` between subsections | Inline `देखें` (§6.7); attached to child label-seed. |
| आत्मा | PuranKosh `<p id="1">(1)…`, `<p id="2">…` | Two separate Definitions (§3.2). |
| द्रव्य | `धवला N/K,B,S/ गाथा G/P` and `धवला N/K,B,S/ श्लोक G/P` citations | Keyword trigger group `{श्लोक/गाथा}गाथा` (§11): `गाथा`/`श्लोक` maps to गाथा field; trigger suppressed from level-2 extraction. |
| द्रव्य | Mixed V1+V2 headings within same section | Detect both. |
| द्रव्य | Big `<table>` between sections 3 and 4 | Section's `extra_blocks` (§6.5). |
| द्रव्य | Nested `<span class="SanskritText">…<span>…</span></span>` | Flatten via §6.4. |
| पर्याय | V3 (`<li>`) + V1 (`<strong>`) mixed | Both detected. |
| पर्याय | `<ul class="HindiText">` at outer index level | Keyword-level relation (§4.2). |
| पर्याय | 3-level deep paths (`1.1.3`) | Tree assembly synthesises missing parents if needed. |
| स्वभाव | V2-bare headings wrapped in classless `<p>` | DFS classless-`<p>` recursion (§6.10). |
| स्वभाव | `देखें <link> text_after` element (§ 1.1.4, 1.4, 2.4) | After-`देखें` seed (§5.5). |
| स्वभाव | Classless `<p>` for subsection 2.4 contains `<strong><span HindiText>` as direct child | `_is_block_span_container` allows `<strong>/<b>`; carry-forward in `parse_block_stream` merges bold prefix into translation (v1.10.1). |
| वस्तु | All SiddhantKosh content in classless `<p>` wrapping block-class spans | Exploded by `_is_block_span_container()`. |
| वस्तु | `<span class="HindiText">` with initial prose + `<br/>`-separated `देखें (label)` | `<br/>`-dekhen pattern (§5.6): section-level seeds; definition cleaned. |
| स्वभाव | `प्रवचनसार / तत्त्वप्रदीपिका/19,96,98` — text has `।19। ... ।96। ... ।98।` | Multi-verse split (§11): 3 separate blocks, one per gatha. |
| स्वभाव | `नयचक्र बृहद्/59-60` — text has `।59। ... ।60।` | Multi-verse split (§11): 2 separate blocks. |
| स्वभाव | `(नयचक्र (श्रुतभवन)/61)` — paren-stripping gives `नयचक्र श्रुतभवन/61` | Space-to-slash matching (§11) resolves to `नयचक्र/श्रुतभवन`. |
| स्वभाव | `देखें ... प्रकृति_बंध` href | Underscore preserved in `target_keyword` (§4.4). |
| any | `hindi_text` block with `hindi_translation=null` + publication shastra | `GathaTeekaBhaavarth` edge (§12.2). |
| any | Self-link `<a class="mw-selflink-fragment" href="#3">` | `is_self=true` (§4.3). |
| any | Redlink `/w/index.php?title=X&action=edit&redlink=1` | `target_exists=false`; no Neo4j edge. |
| any | Trailing `<br/>` and stray `&#160;` | Whitespace-normalise (§6.11). |
