# JainKosh Parsing Rules (canonical)

> Authoritative rule document for parsing a JainKosh keyword page (e.g.
> `https://www.jainkosh.org/wiki/आत्मा`) into our intermediate `KeywordParseResult`.
> The parser implementation in `workers/ingestion/jainkosh/` MUST honour these rules.
> Anything that contradicts what's in `08_ingestion_jainkosh.md` — this file wins.

This document does **not** describe the parser code (see
[`parser_spec.md`](./parser_spec.md)) or the DB schema (see
[`schema_updates.md`](../parser/archived/schema_updates.md)). It describes only **what the
HTML means**, in enough detail that a different implementer could rebuild
the parser without re-reading the source HTML.

---

## 1. Page anatomy

A keyword page is a MediaWiki-rendered article. The parsable region is
`div.mw-parser-output` (one per page). Inside it, top-level children
(direct, not deeply nested) are processed in document order.

The page contains zero or more **page sections**, each introduced by an
`<h2>` whose `<span class="mw-headline">` has one of these well-known
ids:

| `mw-headline` id          | section_kind   | Hindi label                  |
|---------------------------|----------------|------------------------------|
| `सिद्धांतकोष_से`           | `siddhantkosh` | सिद्धांतकोष से                |
| `पुराणकोष_से`              | `puraankosh`   | पुराणकोष से                  |
| anything else             | `misc`         | (verbatim)                   |

A section is everything after its `<h2>` and before the next `<h2>` (or
end of `mw-parser-output`).

Within a section, the elements appear in this conceptual order (any of
them may be absent):

1. **Definitions** — content before the first numbered heading (see §3).
2. **Topic index** — a leading `<ol>` that lists subsections plus
   cross-page `देखें` relations (see §4).
3. **Subsections** — the body of the section, organised as a *tree* of
   topic seeds keyed by `topic_path` (`1`, `1.1`, `1.1.3`, …) (see §5).
4. **Tables** — interleaved with subsections; treated as section-level
   `extra_blocks` (see §6.5).
5. **Adjacent-page navigation** — `पूर्व पृष्ठ` / `अगला पृष्ठ` anchors;
   silently dropped (see §6.6).

---

## 2. Identifying the keyword

The keyword name is **not** taken from page text (titles change). It
comes from the source URL:

```
https://www.jainkosh.org/wiki/<keyword>          # canonical
https://www.jainkosh.org/wiki/<percent-encoded-keyword>
```

The parser:

1. URL-decodes the path segment after `/wiki/`.
2. Applies NFC normalisation (`unicodedata.normalize('NFC', s)`).
3. Strips ZWJ (`U+200D`) and ZWNJ (`U+200C`) per the parser config flag
   (`strip_zwj`, `strip_zwnj`; default both `true` for JainKosh).

This NFC string is the canonical `keyword` identifier and the
`natural_key` for `keywords`.

---

## 3. Definitions (replaces the old "single optional `<p class='HindiText'>`" rule)

A **definition** is a leading content block in a section, *before* any
numbered topic heading. It has the same block kinds as a topic body
(see §6) but no heading of its own. There can be **zero, one, or
many** definitions per section, in either SiddhantKosh or PuranKosh.

### 3.1 SiddhantKosh definitions

Each `[GRef] → [SanskritText|PrakritText|SanskritGatha|PrakritGatha] → [HindiText]`
triplet (or any subset) before the first numbered heading is a single
**definition**. A definition is delimited by **the next leading
reference** (`<p>` or bare `<span class="GRef">` introducing the next
quotation): when we encounter a new leading GRef, we close the
current definition and start a new one.

Examples:
- आत्मा SiddhantKosh: ~5 separate `[GRef] [SanskritText] [HindiText]`
  groups → 5 `Definition` objects.
- द्रव्य SiddhantKosh: a single intro `<p class="HindiText">…</p>`
  paragraph (no GRef, no Sanskrit) → 1 `Definition` with one
  `hindi_text` block.
- पर्याय SiddhantKosh: similar single-paragraph intro → 1 `Definition`.

### 3.2 PuranKosh definitions

PuranKosh content is wrapped in `<div class="HindiText">`. Two patterns:

- **Single paragraph** (द्रव्य, पर्याय) — one `<p class="HindiText">…</p>`
  with inline references → 1 `Definition` with one `hindi_text` block.
- **Numbered paragraphs** (आत्मा) — multiple
  `<p id="1" class="HindiText">(1) …</p>`, `<p id="2" class="HindiText">(2) …</p>` →
  **N separate `Definition` objects**, one per `<p id>`. The leading
  `(N)` prefix **is stripped** from the prose text (v1.2.0); `definition_index` is
  the only counter signal. Stripping is controlled by
  `definitions.numbering_strip_re` (default `^\s*\(\d+\)\s*`).

PuranKosh has **no numbered subsections** — everything is definition.

### 3.3 Definition model and idempotency contracts

The `Definition` Pydantic model, idempotency contracts schema, and `raw_html`
whitespace policy are implementation details — see `parser_spec.md §4` (models)
and `parser_spec.md §6` (would_write envelope) for authoritative specs.

---

## 4. Topic index parsing

A SiddhantKosh section may contain one or more leading `<ol>` blocks
**before** any `<strong id="…">` heading. These are the "topic index"
and serve only to enumerate subsections and cross-page relations.

### 4.1 Index structure

```
<ol>                                                     ← outer index list
  <li class="HindiText">                                  ← entry per top-level section
    <strong>section title</strong>          (or: <strong><a href="#N">title</a></strong>)
    <br/>
    <ol>                                                  ← inner: in-page anchors. IGNORE these.
      <li><a href="#1.1">subsection title</a></li>
      …
    </ol>
    <ul>                                                  ← inner: cross-page देखें relations. CAPTURE these.
      <li>…label… - देखें <a href="/wiki/X">X</a></li>
      <li>…label… - देखें <a href="/wiki/X#1.2" title="X">X - 1.2</a></li>
      <li>…label… - देखें <a class="mw-selflink-fragment" href="#3">द्रव्य - 3</a></li>
    </ul>
    <ol start="N">                                        ← may be split by inner <ul>; still ignore inner anchors.
      <li><a href="#1.7">…</a></li>
      …
    </ol>
    <ul>…</ul>
    …
  </li>
  <li>section 2</li>
  …
  <ul>…</ul>                                              ← keyword-level देखें (between top-level <li>s)
</ol>
```

### 4.2 Capture rules

Walk the index DOM:

1. **`<a href="#X.Y">` inside any inner `<ol>`** → ignore (duplicates body
   subsections, which we'll parse anyway).
2. **`<li>` inside an inner `<ul>`** → emit one `IndexRelation` (see §4.3).
   The `<li>` text up to the `देखें` token is the relation **label**;
   the `<a>` is the **target**.
3. **Position matters for relation source:**
   - `<ul>` *inside* a top-level `<li>` of the outer `<ol>` →
     `relation_source_path = id_of_that_top_level_li` (so the relation
     is from that *section's topic*, not from the keyword).
   - `<ul>` at the *outer* `<ol>` level (between top-level `<li>` items
     or before the first one) → `relation_source_path = None` (keyword-
     level relation; HAS_TOPIC equivalent does not apply, but
     `RELATED_TO` from the keyword does).

### 4.3 Three target formats for `देखें` links

Each `IndexRelation` resolves the `<a>` href into one of:

| href shape                                  | `target_keyword` | `target_topic_path` | `is_self` |
|---------------------------------------------|------------------|---------------------|-----------|
| `/wiki/X`                                    | `X` (NFC)        | `None`              | `false`   |
| `/wiki/X#Y` (Y is a path like `1.2` or `II.3.3`) | `X` (NFC)   | `Y`                 | `false`   |
| `#X.Y` (anchor on `<a class="mw-selflink-fragment">`) | current keyword | `X.Y`        | `true`    |
| `/w/index.php?title=X&action=edit&redlink=1` | `X` (decoded)    | `None`              | `false` (target page does not exist yet — emit relation but flag `target_exists=false`) |

`target_keyword` from `/wiki/<percent-encoded>` is URL-decoded then
NFC-normalised. **Underscores are preserved** — MediaWiki encodes page
title spaces as `_` in URLs, so a href ending `प्रकृति_बंध` yields
`target_keyword = "प्रकृति_बंध"`. (v1.11.1 changed from converting `_` to space.)
The visible link text (e.g. `"X - 2.3"`) is **not**
parsed for the path — always parse from the URL fragment.

### 4.4 Relation type

Every captured `IndexRelation` becomes a `RELATED_TO` edge in Neo4j.
Direction: `source → target`. Source is either the keyword node or a
topic node (per §4.2).

### 4.5 Configurable `देखें` triggers and full-DOM scan

The token that signals a see-also relation is **not** hard-coded to
`देखें`. The trigger list is configurable in
`parser_configs/jainkosh.yaml > index.see_also_triggers` (e.g.
`["देखें", "विशेष देखें"]`). Pattern construction: triggers are sorted
longest-first and joined into a regex alternation so `विशेष देखें`
matches before `देखें`.

The scanner uses a **full CSS `a`-element scan** of the entire index
`<ol>` subtree (DFS), not a two-tier `<ol> → <li> → <ul>` walk. For
each `<a>`, the parser walks up the ancestor chain collecting up to
`index.see_also_window_chars` characters of preceding inline text; if
the pattern matches, the anchor is a see-also target. This captures
deeply nested `<ul>` entries that the old two-tier walker missed.

Configurable knobs:

| Key | Default | Meaning |
|-----|---------|---------|
| `see_also_triggers` | `["देखें"]` | List of trigger words |
| `see_also_window_chars` | `40` | Max chars of preceding text to inspect |
| `see_also_leading_punct_re` | `[(–\-।\s]*` | Punct allowed between label and trigger |

The same trigger list and window are used for **inline** `देखें`
detection in body blocks (§6.7).

### 4.6 IndexRelation source chain resolution (v1.4.0)

`IndexRelation.source_topic_path_chain` and
`source_topic_natural_key_chain` are resolved by walking ancestor
`<li>` containers of each `देखें` entry upward through the index DOM
and matching their inline heading context against parsed subsection
topics.

v1.4.0 adds two fallback rules that fix unresolved or mis-resolved
chains in nested index structures:

- **Enclosing-`<li>` fallback**: when previous-sibling scan in the same
  list is exhausted, resolution climbs to the enclosing parent `<li>`
  and derives path/heading from that container.
- **Inner-`<ol>` path fallback**: for `<li>` headings where
  `<strong>` has plain text (no `<a href="#...">`), the path is derived
  from the first direct inner-`<ol>` anchor by trimming its last path
  segment (e.g. `#4.4.1` → `4.4`).

This removes chain drift such as `["4","4.2"]` incorrectly attributed to
neighbors when the current row belongs under `4.3`/`4.4`, and repairs
empty chains under top-level scoped `<ul>` entries.

Controlled by:
- `index.source_chain.enclosing_li_fallback` (default `true`)
- `index.source_chain.li_path_from_inner_ol_fallback` (default `true`)
- `index.source_chain.ancestor_strong_selectors` (existing)

### 4.7 Range expansion for `देखें` links (v1.7.0)

When a `देखें` link has `target_topic_path` like `X.M` and the text **immediately
following** the anchor is `-N` (hyphen or en-dash + number, N > M), the parser
expands into N − M + 1 relations covering `X.M` through `X.N`.

Example: `देखें <a href="/wiki/गति#1.3">गति - 1.3</a>-6।` → four relations for
`target_topic_path = "1.3"`, `"1.4"`, `"1.5"`, `"1.6"`.

Rules:
- Only the **last** path segment is iterated; the prefix stays fixed.
- If `target_topic_path` absent (keyword-only link), expansion skipped.
- If N ≤ M, single relation emitted.
- Applies to both index `<ol>` relations and inline `see_also` blocks.

---

## 5. Subsections (topic seeds)

A subsection is a numbered heading + its content, possibly with
children. Subsections form a **tree** keyed by `topic_path`
(e.g. `1`, `1.1`, `1.1.3`).

### 5.1 Heading variants

There are **7 heading variants** (V1–V5 + V2-bare + V5-def which is NOT a heading).
The list is **configurable** via `parser_configs/jainkosh.yaml > headings.variants`
(see [`parser_spec.md`](./parser_spec.md) §3).

| Variant | DOM shape | `topic_path` source | Seen in |
|---------|-----------|---------------------|---------|
| **V1** | `<strong id="N">heading</strong>` | `@id` of `<strong>` | द्रव्य, पर्याय, स्वभाव |
| **V2** | `<span class="HindiText" id="N"><strong>heading</strong></span>` | `@id` of `<span>` | द्रव्य |
| **V2-bare** (v1.8) | `<span class="HindiText" id="N">N. heading</span>` (no `<strong>`, numeric prefix required) | `@id` of `<span>` | स्वभाव |
| **V3** | `<li id="N"><span class="HindiText"><strong>heading</strong></span>` | `@id` of `<li>` | पर्याय |
| **V4** | `<p class="HindiText"><b>N. heading</b></p>` | regex `^\s*(?P<id>\d+(?:\.\d+)*)[.\s]+(?P<heading>.+?)\s*$` | आत्मा |
| **V5** (v1.8) | `<p class="HindiText" id="N">N. heading</p>` (no child elements, numeric prefix required) | `@id` of `<p>` | स्वभाव |
| **V5-def** | `<p id="N" class="HindiText">(N) text…</p>` | **Not a heading** — PuranKosh definition (see §3.2) | आत्मा PuranKosh |

V1, V2, V2-bare, V5: leading `\d+(?:\.\d+)*[.\s]+` is stripped from `heading_text` before use.

V5 is included only to make the *non-match* explicit: V5 paragraphs are
**not** subsections. The parser must recognise them as PuranKosh
definitions.

### 5.2 Parsing the path tree

`topic_path` strings use dot-separated segments (`1`, `1.1`, `1.1.3`).
Some pages may use Roman numerals (`II.3.3`) — these are still treated
as opaque segment strings. The parser **does not** invent paths; it
uses whatever the source provides.

Tree assembly:

1. Walk the section's body in document order.
2. On each detected heading, parse its `topic_path` (e.g. `"1.1.3"`).
3. Look up the parent path by removing the last segment (`"1.1"`). The
   parent must already exist *or* be synthesisable.
4. **Synthesise missing intermediates.** If `1.1.3` appears but `1.1`
   was never declared, create a synthetic `1.1` subsection with
   `is_synthetic=true`, `heading_text=""`, `is_leaf=false` so the tree
   is well-formed. (In practice all observed samples declare
   intermediates; this is defence in depth.)
5. Append the new subsection as a child of the parent.

A subsection is a **leaf** iff it has zero child subsections. Both
leaves and inner nodes are emitted as topic seeds (per §5.4).

### 5.3 Subsection content (between this heading and the next)

Walk the DOM forward from a heading until the next heading at *any*
level. Every block encountered becomes a `Block` (see §6) on the
current subsection.

Edge case: in V1/V3/V2 the heading is a child of an `<li>`; the body
content lives as further children of the same `<li>`. After exhausting
the `<li>`, look at the **next sibling `<li>`** at the appropriate
nesting depth — its first child is usually the next heading.

### 5.4 Topic seeds and natural keys

Every subsection (leaf and intermediate, synthetic or real) emits a
`Topic` row with:

- `natural_key`: dot-separated slug path, **no source prefix**. Format:
  `<keyword>:<slug(heading-of-1)>:<slug(heading-of-1.1)>:<slug(heading-of-1.1.3)>`.
  E.g. `द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ`.
- `topic_path`: the **numeric** id path, e.g. `"1.1"`. Stored as a
  separate field for cross-reference resolution (`देखें X - 1.2`).
- `display_text`: multilingual array, Hindi-only for now.
- `parent_topic_natural_key`: the parent's `natural_key`, or `None` for
  top-level (`1`, `2`, …).
- `is_leaf`: bool.

Slug rules (Devanagari-aware):

- NFC-normalise.
- Strip leading `<b>N. ` numeric prefix only for V4 headings (already
  done by the regex).
- Replace runs of whitespace (incl. NBSP ` `) with `-`.
- Strip Devanagari danda `।`, daṇḍa `॥`, ASCII punctuation
  `.,;:!?()[]{}'"` etc.
- Preserve Devanagari characters as-is.
- Collapse multiple `-` into one; trim leading/trailing `-`.

Example: `आत्मा के बहिरात्मादि 3 भेद` → `आत्मा-के-बहिरात्मादि-3-भेद`.

### 5.5 Heading-text vs link-wrapped headings

In पर्याय's index, top-level headings appear as
`<strong><a href="#1">भेद व लक्षण </a></strong>` — i.e., the heading
text is wrapped in an in-page anchor. The body version is plain
`<strong>भेद व लक्षण</strong>`. Always use the body version's text
for slug + display. The index is parsed only for `<ul>` `देखें`
relations.

### 5.6 Label-before-`देखें` as synthetic topic seed

When a `HindiText` prose block takes the shape
`• <label> - देखें <X>` or `<label> - देखें <X>`, the text before
the `देखें` trigger (stripped of leading bullet, trailing connector
`–`/`-`, and surrounding whitespace/danda) becomes a **synthetic
`Topic` seed**:

- `Subsection.is_synthetic = True`
- `Subsection.label_topic_seed = True`
- `Subsection.topic_path = None` (no numeric path from HTML)
- `Subsection.is_leaf = True`
- `natural_key` = slug of the label appended to the parent's natural
  key (or to the keyword alone if outside any subsection).

The seed is attached as a child of the **current open subsection**
when inside one, or to `PageSection.label_topic_seeds` (a separate
list, to keep the numeric-path tree unambiguous) when at section root.

Commas inside the label are **not delimiters** — the entire text is
one topic name.

Configuration knobs: `label_to_topic.enabled`,
`label_to_topic.emit_for_redlink`, `label_to_topic.emit_for_wiki_link`,
`label_to_topic.emit_for_self_link`, `label_to_topic.bullet_prefixes`,
`label_to_topic.label_trim_chars`.

**Scope guard (v1.2.0)**: a label-seed `Topic` is NOT emitted when
the `देखें` trigger appears inside translation prose (i.e. a block
whose `source_kind` is in `label_to_topic.skip_in_source_kinds`,
default `["hindi_translation"]`). This prevents spurious topic seeds
from inline cross-references embedded inside Hindi translations.

The label text is trimmed to only the segment between the nearest
sentence-end / bullet and the trigger; trailing connectors (`–`, `-`)
are stripped as before.

**Row-relation relocation (v1.3.0)**: for row-style entries
(`• label - देखें target`, including redlink targets), the
`see_also` block that represents the cross-reference relation is
assigned to the **child seed's `blocks`**, not the parent subsection's
blocks. Specifically:

- The parent subsection's block stream receives neither the row prose
  block nor the corresponding `see_also` block.
- The child label-seed subsection's `blocks` contains exactly the
  `see_also` block(s) derived from that row.
- Row detection is performed at the DOM element level, before any
  destructive text stripping (so redlink rows are correctly detected
  even though their `देखें` text is later stripped from prose).
- `RELATED_TO` edges in Neo4j are emitted **from the child seed's
  natural key**, not from the parent subsection's key.
- Existing redlink edge suppression policy is unchanged (redlink
  `see_also` blocks are kept in the child seed's `blocks`; no
  `RELATED_TO` edge is emitted for them).

### 5.7 Parenthesised `देखें` cleanup (v1.2.0)

When a `देखें` reference is parenthesised — e.g. `(देखें X)` — the
entire parenthesised fragment (including parentheses) is stripped from
`text_devanagari` and `hindi_translation`. An un-parenthesised `देखें`
text is preserved in prose as before.

Rules:
- Bracket pairs matched by `paren_dekhen_strip.bracket_pairs` (default
  `[["(", ")"]]`).
- Pattern: `\(<open>…<trigger>…<target>…<close>\)` (configurable via
  `paren_dekhen_strip.pattern`).
- The `see_also` block is still emitted independently; only the prose
  text is cleaned.

### 5.8 V2-bare heading variant (v1.8.0)

`<span class="HindiText" id="N">N. heading</span>` with no inner `<strong>` is
treated as a heading when: (a) span has no direct child elements AND (b) text starts
with a numeric prefix. Plain spans without a numeric prefix are NOT headings.

**V2-bare inline-content guard (v1.8.1)**: `_make_v2_content_block` returns `None` for
V2-bare spans. Without this, the heading text would be re-emitted as a `hindi_text`
block in the subsection's own content.

### 5.9 V5 heading variant (v1.8.0)

`<p class="HindiText" id="N">N. heading</p>` (no child elements, numeric prefix required).

**V5 guard**: same conditions as V2-bare but for `<p>`. PuranKosh definitions use
parenthesised prefix `(N)` not `N.` — parenthesised prefix is **not** V5.

### 5.10 DFS classless-`<p>` recursion (v1.8.0)

When a classless `<p>` element is encountered in the DFS walk and `contains_heading(el)` returns
True, the walker **recurses into its direct children** rather than treating the `<p>` as a content
block. This fixes cases where a V2-bare or V1 heading is wrapped in a classless `<p>`.

### 5.11 After-`देखें` text as synthetic topic seed (v1.9.0)

When a HindiText element starts with the `देखें` trigger (only leading whitespace allowed before it)
AND Devanagari text follows the anchor, that text becomes a synthetic `label_topic_seed` child topic:
- `heading_text` = text after the anchor (stopping at `<br/>`).
- `see_also` block assigned to the seed's `blocks`.
- Original element skipped in the parent's block stream.

Mid-prose `... देखें X ...` and parenthesised `(देखें X)` are NOT affected.

### 5.12 `<br/>`-separated `देखें` as section-level seeds (v1.10.0)

When a HindiText element contains **initial prose** + one or more `<br/>`-separated
`देखें <link> (label)` lines (element does NOT start with the trigger), each देखें line becomes a
`PageSection.label_topic_seeds` entry:
- Outer parentheses stripped from after-anchor text to form seed heading.
- Corresponding `see_also` blocks relocated to seed's `blocks`.
- Definition `hindi_translation` cleaned of the देखें lines.

`extract_text_after_anchor` stops at `<br/>` (shared with §5.11 — prevents bleed-through
when multiple देखें lines are separated by `<br/>`).

### 5.13 Body-element br-dekhen seeds (v1.11.4)

In addition to the section-level seeds (§5.12), subsection body `content_els` are also scanned
for `<br/>`-separated `देखें` patterns. When a mid-body HindiText element contains initial prose
followed by one or more `<br/>`-separated `देखें <link>` lines, each such line produces a
`see_also` label-topic seed in the subsection's `after_dekhen_relations`. The trigger lines and
any following pure-punctuation lines are stripped from `hindi_translation` via
`_strip_dekhen_trigger_lines`.

This handles patterns like `देखें जीव - 3.8\n(context)।` inside a `=`-sibling HindiText
element that would otherwise leak into the translation of the preceding source block.

---

## 6. Block kinds

Blocks are the atoms of body content inside a definition or
subsection. Block kinds are **configurable** via
`parser_configs/jainkosh.yaml > block_classes` (CSS class → block kind).

### 6.1 Recognised block kinds

| Block kind          | DOM shape                                     | Treated as                      |
|---------------------|-----------------------------------------------|---------------------------------|
| `sanskrit_text`     | `<p class="SanskritText">…</p>` or `<span class="SanskritText">…</span>` | source-language text |
| `sanskrit_gatha`    | `<p class="SanskritGatha">…</p>` or `<span class="SanskritGatha">…</span>` | source-language verse |
| `prakrit_text`      | `<p class="PrakritText">…</p>` etc.           | source-language text |
| `prakrit_gatha`     | `<p class="PrakritGatha">…</p>` etc.          | source-language verse |
| `hindi_text`        | `<p class="HindiText">…</p>` or `<span class="HindiText">…</span>` | translation or independent prose |
| `hindi_gatha`       | `<p class="HindiGatha">…</p>` etc.            | Hindi verse |
| `reference`         | `<span class="GRef">…</span>` (or `<p>` containing only one) | bibliographic citation |
| `see_also`          | inline `देखें <a href="…">…</a>` pattern      | cross-reference relation |
| `table`             | `<table>…</table>`                            | tabular data (raw HTML kept) |

### 6.2 The `=` translation marker

A SanskritText / PrakritText / SanskritGatha / PrakritGatha block is
typically followed by `<p class="HindiText">= translation…</p>`. The
`=` (or `“=”`) is a **translation marker**: when a HindiText block
**starts with** `=` (after trimming whitespace and NBSP), the parser:

1. Strips the leading `=` (and any whitespace immediately after).
2. Attaches the resulting Hindi text to the **immediately preceding**
   source-language block as `hindi_translation`, instead of emitting it
   as a standalone `hindi_text` block.

The marker can also appear **inline** within a HindiText paragraph
(e.g. `<p class="HindiText">= द्वादशांग का नाम… <b>प्रश्न</b> -…</p>`).
This is **the same case** — the leading `=` is the marker; the rest of
the text is the translation. Only a *leading* `=` is the marker; an
embedded `=` is literal text.

If there is no preceding source-language block (rare; defensive), keep
the block as a `hindi_text` block but **strip the leading `=`** and set
`is_orphan_translation=true`.

### 6.3 References (GRef) — leading vs trailing

A `<span class="GRef">…</span>` cites a shastra/teeka/page. The text
between the tags is kept verbatim (NFC). Any `<a href>` inside the
`<span>` is **stripped** (we keep only the visible text). Two
attachment rules:

- **Leading reference** — a `<p>` whose only meaningful child is one or
  more `<span class="GRef">`s (or a bare `<span class="GRef">` between
  blocks) immediately *before* a Sanskrit/Prakrit/Hindi block: the
  reference is attached to the **following** block as `references[]`
  (NOT the previous; this corrects a mistake in the older doc).
- **Trailing reference** — a `<span class="GRef">` *inside* a
  Sanskrit/Prakrit/Hindi block (i.e. inline at the end of the prose):
  attached to that same block as `references[]`.

If a leading reference has no following block before the next heading,
it attaches to the most recent block (fallback only).

v1.4.0 additionally preserves reference position by **splitting a body
block at inline GRef boundaries** when meaningful prose continues after
an inline reference. This prevents unrelated prose passages from being
collapsed into one block with merged references.

Example:
- `TEXT_A <span class="GRef">R1</span> TEXT_B <span class="GRef">R2</span>`
- emits two `hindi_text` blocks:
  1. `TEXT_A` with `R1`
  2. `TEXT_B` with `R2`

This rule applies to text-like block kinds (`hindi_*`, `sanskrit_*`,
`prakrit_*`) and does not change table or see-also extraction rules.

### 6.4 Nested-span exception (multiple definitions in one `<span>`)

In द्रव्य L734–759 (and similar), a single
`<span class="SanskritText">` contains multiple nested definitions:

```html
<span class="SanskritText">topmost text…<br>
  <span class="GRef">ref</span>
  <span class="SanskritText">more sanskrit</span>
  =
  <span class="HindiText">hindi translation</span>
  <span class="GRef">ref</span>
  <span class="SanskritText">…</span>
  =
  <span class="HindiText">…</span>
</span>
```

Resolution:

1. Treat the **direct text** of the outer `<span>` (text nodes that are
   *not* inside any nested element) as a *separate* `sanskrit_text`
   block — its references are any `<span class="GRef">` that appear
   between the start of the outer span and its first nested element of
   another kind.
2. Then iterate nested children left-to-right and emit them as further
   blocks using the same rules as top-level (so a nested
   `<span class="SanskritText">` followed by `=` followed by
   `<span class="HindiText">` is one source-block + translation).

This is implemented by a recursive DOM walker that flattens nested
spans into a sequential block stream. Configurable via
`parser_configs/jainkosh.yaml > nested_span_flatten: true|false`.

### 6.5 Tables

Tables (`<table>`) are kept as **full outerHTML** (including the
`<table>` tag itself) in a single `Block(kind="table", raw_html="…")`.
Whitespace within the stored `raw_html` is collapsed per §3.5.
Attachment (controlled by `table.attach_to`, default
`current_subsection`):

- **Inside a subsection's body** → attach to that subsection's
  `blocks`. This is the default for any `<table>` encountered after
  the first heading in a section.
- **Before any heading in the section** (truly orphan) → attach to the
  section's `extra_blocks: list[Block]`. `extra_blocks` is reserved
  for future use and is always present (possibly empty) in the
  envelope.

The old behaviour (all tables to `extra_blocks`) is recoverable by
setting `table.attach_to: "section_root"` in YAML.

### 6.6 Adjacent-page navigation

Detect by text content of an `<a>`:

- `पूर्व पृष्ठ` → previous page link.
- `अगला पृष्ठ` → next page link.

The whole containing `<p>` (and any sibling `<p>` with only `<br/>`)
is dropped from block extraction. The hrefs are captured separately
into `KeywordParseResult.nav = {"prev": "/wiki/…", "next": "/wiki/…"}`.

### 6.7 Inline `देखें` extraction

Any anchor whose **immediately preceding inline text** (within the
same ancestor chain, up to `index.see_also_window_chars` chars,
default 40) matches the configured trigger pattern (§4.5) is a
**`see_also` block**. The trigger list is shared with the index
scanner — adding a new trigger word to YAML covers both contexts
automatically. Patterns observed:

- `(देखें <a>X</a>)` — within a HindiText body
- `–देखें <a>X</a>` — at the start of an index `<ul>` `<li>`
- `- देखें <a>X</a>` — variant with hyphen-space
- `देखें <a>X</a>` — bare

The `see_also` block carries the same `(target_keyword, target_topic_path,
is_self)` fields as `IndexRelation` (§4.3). The `देखें` text and the
anchor are **not stripped** from the surrounding Hindi text — they
remain in the `hindi_text` block so the prose reads naturally. The
`see_also` block is *additionally* emitted alongside the hindi block,
so the graph layer can build a `RELATED_TO` edge.

**Redlink anchor**: when the anchor is a MediaWiki redlink
(`class="new"`, `title` ends with `(page does not exist)`, or `href`
contains `redlink=1`), the `see_also` block is emitted with
`target_exists=false` AND the `देखें <redlink>` substring (plus its
connector punctuation `–`/`-`) is removed from `text_devanagari`. If
the block becomes empty after stripping, it is dropped. Configurable
via `redlink.prose_strip.enabled`.

**Redlink edge suppression (v1.2.0)**: a `RELATED_TO` edge in
`would_write.neo4j.edges` is **not emitted** when the target node has
`target_exists=false`. This applies to both `IndexRelation`-derived and
`Block(kind="see_also")`-derived edges. Controlled by
`neo4j.redlink_edges` (enum: `always` | `never` | `only_if_topic`;
default `never`).

### 6.8 Inline emphasis (`<b>`, `<i>`, `<strong>`, `<em>`)

When `<b>` or `<strong>` (or `<i>`/`<em>`) appears **inline inside**
a Hindi/Sanskrit/Prakrit body block (i.e., not as a heading), preserve
it as Markdown:

| HTML        | Markdown |
|-------------|----------|
| `<b>x</b>`, `<strong>x</strong>` | `**x**` |
| `<i>x</i>`, `<em>x</em>`         | `*x*`    |

This applies only to *non-heading* contexts; a `<strong id="…">` at
the start of a block is a heading and is consumed by §5.

### 6.9 Whitespace normalisation

Applied to every text field after extraction:

1. Unicode NFC.
2. Replace NBSP (` `) and ` `-` ` with space.
3. Strip ZWJ (`‍`) and ZWNJ (`‌`) per config.
4. Collapse runs of whitespace to single space (preserve `\n` for
   inside `<br/>` only — see §6.10).
5. `.strip()` the final string.

### 6.10 `<br/>` handling

`<br/>` inside a block becomes `\n`. Multiple consecutive `<br/>`
collapse to a single `\n`. Trailing `<br/>` is dropped.

### 6.11 Sibling text-node `=` translation marker

In addition to the HindiText-starts-with-`=` rule (§6.2), the parser
also detects `=` as a **bare text node directly between two element
siblings** in the same parent container. This covers the द्रव्य
L724–759 case where:

```html
<span class="PrakritGatha">दवियदि …</span>
=
<span class="HindiText">उन-उन सद्भाव …</span>
```

When the text node matches `^\s*=\s*$`, the HindiText sibling is
merged into the preceding source-language block as `hindi_translation`
(same semantics as §6.2). Configurable via
`translation_marker.sibling_marker_enabled` and
`translation_marker.sibling_marker_text_node_re`.

This also applies inside `_explode_nested_span` (§6.4) — `=` text
nodes between nested siblings are treated identically.

Reference ordering on the merged block: leading references first, then
inline references in document order (`reference_ordering:
"leading_then_inline"`).

### 6.12 GRef text stripped from `text_devanagari`

Inline `<span class="GRef">` nodes are extracted into `references[]`.
Their visible text is **also removed** from `text_devanagari` (the
ref-strip pass). Clean-up rules applied after each strip:

- Collapse orphan `( )` and `[ ]` bracket pairs left behind.
- Collapse runs of multiple spaces.
- Remove space before a danda `।` / `॥`.
- Strip leading/trailing chars listed in
  `ref_strip.trim_trailing_chars` (default ` ।॥;,`).

This rule applies to **all** block kinds that carry `text_devanagari`
(sanskrit/prakrit/hindi text and gathas). Configurable via
`ref_strip.enabled` and related knobs.

### 6.13 See-also-only block drop (v1.2.0 / v1.3.0)

A block whose entire content is `• X – देखें Y` (a "see-also row")
is **dropped** from the parent `Subsection.blocks`. This prevents
redundant prose blocks that carry no information beyond what the graph
edge already expresses. Controlled by `see_also_only_block.drop` (bool,
default `true`) and `see_also_only_block.pattern` (regex matching the
full block text).

**v1.3.0 — also drops the accompanying `see_also` block from the
parent stream.** The corresponding `see_also` block is relocated to
the child label-seed subsection's `blocks` (see §5.6). Row detection
happens at DOM element level, before any text stripping, so redlink
rows (whose `देखें` text is stripped from prose) are caught correctly.

### 6.14 DFS leading-GRef passthrough (v1.2.0)

Top-level `<span class="GRef">` siblings that appear inside an `<li>`
heading body are now preserved as **content events** in
`walk_and_collect_headings` so the leading GRef reaches
`parse_block_stream` and attaches to the next emitted block. Previously
these GRefs were silently swallowed, losing the topmost reference
(e.g. `पंचास्तिकाय/9`). Controlled by `dfs.passthrough_leading_gref`
(default `true`).

---

## 7. Block flow within a subsection

The block stream algorithm (leading-reference buffering, `=` translation marker,
nested-span flatten, see_also extraction) is the implementation's concern.
See `parser_spec.md §5.5 – §5.7` for the full pseudocode.

Conceptual ordering within a subsection:
```
[leading reference] → attaches to next block
[source-language block] (+ leading references)
[hindi_text starting with "="] → merged as hindi_translation
[standalone hindi_text]
[see_also] → emitted alongside (not instead of) its parent block
[table]
```

---

## 8. Edge cases observed in samples

| Page | Phenomenon | Rule |
|------|-----------|------|
| आत्मा | Section uses V4 headings; no `<ol>` index | Detect headings via V4 regex; index_relations is empty. |
| आत्मा | Standalone `<p class="HindiText">• X - देखें Y</p>` between subsections | Inline `देखें` (§6.7); attached to current subsection's blocks. |
| आत्मा | PuranKosh has `<p id="1">(1) …</p>`, `<p id="2">…</p>` | Each is a separate `Definition` (§3.2). |
| द्रव्य | Mixed V1+V2 headings within same section | Detect both. |
| द्रव्य | Big `<table>` between sections 3 and 4 | Section's `extra_blocks` (§6.5). |
| द्रव्य | Nested `<span class="SanskritText">…<span>…</span></span>` | Flatten via §6.4. |
| द्रव्य | PuranKosh single paragraph wrapped in `<div class="HindiText">` | One `Definition` with one `hindi_text` block. |
| पर्याय | V3 (id on `<li>`) + V1 (id on `<strong>`) mixed | Both detected. |
| पर्याय | `<ul class="HindiText">` at outer index level | Keyword-level relation (§4.2). |
| पर्याय | 3-level deep paths (`1.1.3`) | Tree assembly synthesises missing parents if needed. |
| any | Self-link `<a class="mw-selflink-fragment" href="#3">` | `is_self=true` (§4.3). |
| any | Redlink `/w/index.php?title=X&action=edit&redlink=1` | Capture with `target_exists=false`. |
| any | Trailing `<br/>` and stray `&#160;` in headings/blocks | Whitespace-normalise (§6.9). |

---

## 9. What this document does NOT cover

- **HTTP fetching, rate limiting, snapshot writing** — see
  `08_ingestion_jainkosh.md`.
- **MediaWiki redirect API** for alias mining — see
  `08_ingestion_jainkosh.md` §"Alias mining".
- **Parser implementation (modules, Pydantic types, CLI, tests)** —
  see [`parser_spec.md`](./parser_spec.md).
- **Database schema additions** to support hierarchical topics and
  multiple definitions — see [`schema_updates.md`](../parser/archived/schema_updates.md).

## 10. Versioning

The parser tags every output with `parser_rules_version` written into
`KeywordParseResult.parser_version`. See `parser_spec.md` for the
implementation-level versioning details.

### Changelog

| Version | Changes |
|---------|---------|
| `1.0.0` | Initial rules. |
| `1.1.0` | Configurable `देखें` triggers + full-DFS index scan (§4.5); ref-strip (§6.12); sibling `=` marker (§6.11); redlink prose-strip (§6.7); label→topic seeds (§5.6); table attachment (§6.5); IndexRelation source chain; idempotency contracts. |
| `1.2.0` | Table full outerHTML; idempotency contracts hoisted to envelope root; IndexRelation source chain (§4.6); DFS leading-GRef passthrough (§6.14); paren-`देखें` stripped (§5.7); label-seed scope guard (§5.6); see-also-only blocks dropped (§6.13); definition `(N)` numbering prefix stripped (§3.2); redlink edges suppressed. |
| `1.3.0` | Row-style `see_also` blocks relocated to child label-seed `blocks`; row detection at DOM level; `RELATED_TO` edges from child seed natural key. |
| `1.4.0` | IndexRelation source-chain fallbacks (§4.6); V2 heading inline-content extraction; inline GRef-based block splitting (§6.3); index relations as synthetic topic seeds. |
| `1.5.0` | Nested-span GRef attribution across `<br/>` boundaries. |
| `1.6.0` | label_seed `RELATED_TO` edges from child natural_key; `inline_reference` flag on `Reference`; nth-occurrence anchor dedup. Classless `<p>` container with block-class span children exploded via `_is_block_span_container()`. |
| `1.7.0` | **Range expansion for `देखें` links**: trailing `-N` after anchor with `target_topic_path=X.M` expands to one relation per path X.M…X.N. Applies to both index `<ol>` (§4.3) and inline `see_also` blocks (§6.7). |
| `1.8.0` | **V1/V2 numeric prefix stripping**: leading `N. ` stripped from heading_text. **V2-bare**: `<span class="HindiText" id="N">N. heading</span>` (no inner `<strong>`) detected as heading when text has numeric prefix. **V5**: `<p class="HindiText" id="N">N. heading</p>` (no child elements, numeric prefix required) as new heading variant. **DFS fix**: classless `<p>` elements containing heading descendants are recursed into instead of treated as content blocks. |
| `1.8.1` | V2-bare inline-content fix: `_make_v2_content_block` returns `None` for V2-bare spans to prevent heading text re-emission as a `hindi_text` block. |
| `1.9.0` | **After-`देखें` text as topic seed**: HindiText element starting with `देखें <link> text_after` (no prose before trigger) → synthetic label-seed child topic. `extract_text_after_anchor` stops at `<br/>`. |
| `1.10.0` | **`<br/>`-separated `देखें` as section-level seeds**: initial prose + `<br/>`-separated `देखें <link> (label)` lines → `PageSection.label_topic_seeds`. Definition `hindi_translation` cleaned of trigger lines. `extract_text_after_anchor` stops at `<br/>` (shared fix). |
| `1.11.1` | Multi-verse block splitting (§6.X); keyword underscore preservation (§6.7); space-to-slash shastra matching; `hindi_text` + null translation → `GathaTeekaBhaavarth`. |
| `1.11.2` | Stray-semicolon cleanup after ref-strip; flexible-whitespace ref matching fallback. |
| `1.11.3` | Keyword trigger groups `{word/word}field` in format strings. |
| `1.11.4` | **(1) HTML entity decoding** in `_render_inline` (`&nbsp;`, `&amp;`, `&lt;`/`&gt;`, `&quot;`, `&apos;`). **(2) Extended stray-punct cleanup**: `,`-only lines, trailing `;`/`,` after `।`/`॥`, danda-only lines removed after ref-strip. **(3) Verse-marker spacing fix**: `।\s*N\s*।` regex (was literal `।N।`) in `_split_text_at_verse_markers`. **(4) Auto-detect verse splitting (Case B)**: when both `text_devanagari` and `hindi_translation` contain 2+ identical `।N।` markers and no multi-ref Case A applies, split is triggered automatically. **(5) `देखें` stripping from translation**: `_emit` strips trigger lines and following paren/punctuation lines from `hindi_translation` before emitting. **(6) Body br-dekhen seeds**: `parse_subsections` extracts `<br/>`-separated `देखें` seeds from subsection body `content_els` (§5.13). |
| `1.11.5` | **(1) Case A/B split ordering by text position**: refs are ordered by sequential `।N।` marker occurrence in `text_devanagari` (greedy `_order_pairs_by_text_position`) rather than ascending gatha value. Fixes GRef lists like `168,15,168` where the comma order reflects text order and values may be non-ascending or repeated. **(2) Deterministic gatha field name** in Case B synthetic refs: field name preserved from base_ref's resolved_fields instead of non-deterministic set iteration. **(3) Teeka name keyword cleanup**: all trailing `/<field_keyword>` segments iteratively stripped from `teeka_candidate` in `match_shastra`, covering both section keywords (गाथा, पंक्ति, …) and entity keywords (पृष्ठ, कलश, …). Handles multi-segment suffixes like `"/गाथा /पृष्ठ / पंक्ति"` → `""`. |
| `1.11.6` | **`prakrit_gatha`/`sanskrit_gatha` multi-verse splitting**: both kinds added to `reference_splitting.applicable_block_kinds`. **Case A source-text guard**: all gatha values must appear as `।N।` markers in `text_devanagari` before Case A fires; when absent, falls through to Case C. **Case C — equal-count independent-marker split**: when src and tl each have exactly N (≥ 2) verse markers (same count, different values OK) and exactly N unique-gatha non-inline refs, splits src at src markers and tl at tl markers, pairing positionally. `_do_split` extended with `tl_nums` kwarg. |
| `1.11.8` | **(1) Hybrid `<ol>` dual index + body processing**: in `parse_section` phase 1, an `<ol>` that both contains headings (body content) AND is the first `<ol>` seen (no prior pure index `<ol>`) is added to `index_ols` for देखें scanning AND to `body` for subsection parsing. Guard `not index_ols` prevents द्रव्य-style body `<ol>` elements from being false-positively added after a genuine index `<ol>` has already been seen. **(2) DFS deep-heading recursion for block-class elements**: in `walk_and_collect_headings._dfs`, block-class elements (e.g. `<li class="HindiText">`) that have no heading as a *direct* child but do contain a heading *descendant* (via `contains_heading`) are now recursed into instead of emitted as flat content blocks. Fixes गुण, where entire page content is nested inside a single `<li class="HindiText">` that wraps both the index and body `<ol>`s. |
| `1.11.12` | **Teeka-keyword space suffix detection in `match_shastra`**: when name_raw ends with ` टीका` or ` की टीका` (space-separated, no `/` required), the suffix is stripped and the base is looked up as a shastra. If found, returns `is_teeka=True`, `teeka_name="टीका"`. Implemented as Step 2.6, inserted before the slash-split Step 3. Fixes `परमात्मप्रकाश टीका/1/57` and similar references. |
