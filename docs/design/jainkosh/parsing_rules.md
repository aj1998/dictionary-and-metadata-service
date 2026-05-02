# JainKosh Parsing Rules (canonical)

> Authoritative rule document for parsing a JainKosh keyword page (e.g.
> `https://www.jainkosh.org/wiki/आत्मा`) into our intermediate `KeywordParseResult`.
> The parser implementation in `workers/ingestion/jainkosh/` MUST honour these rules.
> Anything that contradicts what's in `08_ingestion_jainkosh.md` — this file wins.

This document does **not** describe the parser code (see
[`parser_spec.md`](./parser_spec.md)) or the DB schema (see
[`schema_updates.md`](./schema_updates.md)). It describes only **what the
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
  `(N)` text is **kept as part of the hindi text** (do not strip).

PuranKosh has **no numbered subsections** — everything is definition.

### 3.3 Definition shape

```python
class Definition:
    definition_index: int          # 1-based, per section
    blocks: list[Block]            # see §6
    raw_html: str | None           # debug
```

### 3.4 Idempotency contract on emitted entities

Every row produced by the parser in the `would_write` envelope carries
an `idempotency_contract` sub-object. It describes the conflict key
and field-level merge policy so the orchestrator can perform truly
idempotent upserts without reverse-engineering each store:

```json
{
  "conflict_key": ["natural_key"],
  "on_conflict": "do_update",
  "fields_replace": ["display_text", "is_leaf", "…"],
  "fields_append": [],
  "fields_skip_if_set": [],
  "stores": ["postgres:keywords", "mongo:keyword_definitions", "neo4j:Keyword"]
}
```

The three canonical contracts (keyword, numeric-tree topic, label-seed
topic) are defined in
`parser_fix_spec_001/phase_3_redlink_prose_strip_and_label_to_synthetic_topic.md`
§5. The parser emits them; the orchestrator honours them.

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
NFC-normalised. The visible link text (e.g. `"X - 2.3"`) is **not**
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

---

## 5. Subsections (topic seeds)

A subsection is a numbered heading + its content, possibly with
children. Subsections form a **tree** keyed by `topic_path`
(e.g. `1`, `1.1`, `1.1.3`).

### 5.1 Heading variants

There are **5 known heading variants**. The parser MUST detect all
five. The list is **configurable** via
`parser_configs/jainkosh.yaml > headings.variants` so new variants can
be added without code changes (see [`parser_spec.md`](./parser_spec.md) §3).

| Variant | DOM shape | `topic_path` source | Heading text source | Seen in |
|---------|-----------|---------------------|---------------------|---------|
| **V1** | `<strong id="N">heading</strong>` | `@id` of `<strong>` | text of `<strong>` | द्रव्य L1+L2; पर्याय L3 |
| **V2** | `<span class="HindiText" id="N"><strong>heading</strong></span>` | `@id` of `<span>` | text of inner `<strong>` | द्रव्य (mixed) |
| **V3** | `<li id="N"><span class="HindiText"><strong>heading</strong></span>` | `@id` of `<li>` | text of inner `<strong>` | पर्याय L1, L2 |
| **V4** | `<p class="HindiText"><b>N. heading</b></p>` (no id attr; `N` is *prefixed in heading text*) | regex on text: `^\s*(?P<id>\d+(?:\.\d+)*)[.\s]+(?P<heading>.+?)\s*$` | regex `heading` group | आत्मा SiddhantKosh |
| **V5** | `<p id="N" class="HindiText">(N) text…</p>` | **Not a heading.** This is a definition-style numbered paragraph (see §3.2). | — | आत्मा PuranKosh |

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
one topic name. The `see_also` relation for the anchor is still
emitted independently.

Configuration knobs: `label_to_topic.enabled`,
`label_to_topic.emit_for_redlink`, `label_to_topic.emit_for_wiki_link`,
`label_to_topic.emit_for_self_link`, `label_to_topic.bullet_prefixes`,
`label_to_topic.label_trim_chars`.

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

Tables (`<table>`) are kept as raw HTML in a single
`Block(kind="table", raw_html="…")`. Attachment (controlled by
`table.attach_to`, default `current_subsection`):

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

---

## 7. Block flow within a subsection

Once a heading is detected (§5), the parser walks DOM children of the
heading's container (and onward to the next heading at any level)
producing a block stream:

```
[reference]      ← leading; will be attached to next block
[sanskrit_text]  ← consumes the leading reference
[hindi_text]     ← starts with "=" → consumed as sanskrit_text.hindi_translation
[reference]      ← leading; will attach to next
[prakrit_gatha]  ← consumes the leading reference
[hindi_text]     ← "=" prefix → consumed as prakrit_gatha.hindi_translation
[hindi_text]     ← no "=" prefix → standalone hindi_text block
[see_also]       ← inline देखें extraction
[table]          ← standalone table block
…
```

Algorithm:

```
buffer: list[Reference] = []
last_block: Block | None = None
out: list[Block] = []

for el in walk_until_next_heading():
    if el is leading_reference:
        buffer.append(extract_ref(el))
        continue
    if el is body_block:
        new = make_block(el)
        if new.kind in HINDI_KINDS and new.text.lstrip().startswith("="):
            if last_block is not None and last_block.kind in SOURCE_KINDS:
                last_block.hindi_translation = strip_eq_prefix(new.text)
                last_block.references.extend(buffer); buffer.clear()
                continue
            else:
                new.is_orphan_translation = True
                new.text = strip_eq_prefix(new.text)
        new.references.extend(buffer); buffer.clear()
        out.append(new); last_block = new

# Trailing references at end of subsection — attach to last_block (fallback).
if buffer and last_block is not None:
    last_block.references.extend(buffer)
```

`HINDI_KINDS = {"hindi_text", "hindi_gatha"}`.
`SOURCE_KINDS = {"sanskrit_text", "sanskrit_gatha", "prakrit_text", "prakrit_gatha"}`.

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
  multiple definitions — see [`schema_updates.md`](./schema_updates.md).

## 10. Versioning

The parser MUST tag every output with the rules version it implements.
Bump this version when any rule above changes:

```
parser_rules_version = "jainkosh.rules/1.1.0"     # bumped from 1.0.0 in fix-spec-001
```

This is written into `KeywordParseResult.parser_version` and into the
ingestion run's `parser_configs.version` row in Postgres.

### Changelog

| Version | Changes |
|---------|---------|
| `1.0.0` | Initial rules. |
| `1.1.0` | fix-spec-001: configurable `देखें` triggers + full-DFS index scan (§4.5); ref-strip from `text_devanagari` (§6.12); sibling `=` translation marker (§6.11); redlink prose-strip (§6.7); label→synthetic topic seeds (§5.6); tables attach to current subsection (§6.5); `IndexRelation` source path chain (Phase 5); idempotency contracts on all envelope rows (§3.4). See `parser_fix_spec_001/README.md`. |
