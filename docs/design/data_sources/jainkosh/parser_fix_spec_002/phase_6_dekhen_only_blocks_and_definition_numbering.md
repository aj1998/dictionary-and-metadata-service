# Phase 6 — Drop see-also-only blocks and strip definition `(N)` numbering

## Problem

### 6a. `देखें`-only rows leak into main blocks

In `आत्मा.json`, blocks like:

```jsonc
{
  "kind": "hindi_text",
  "text_devanagari": "• जीवको आत्मा कहनेकी विवक्षा - देखें जीव",
  "hindi_translation": null,
  "references": []
}
```

appear inside `Subsection.blocks` and inside `mongo.topic_extracts[*].blocks`
and inside `keyword_definitions.page_sections[*].extra_blocks`. They
should not. These rows carry no information beyond what is already
captured in the corresponding `see_also` block (and its derived `RELATED_TO`
edge in `would_write.neo4j.edges`). Keeping them duplicates the
information and pollutes the prose corpus.

Rule: a block whose entire content is `<bullet?> <label> <connector?> <trigger> <target>` with
no other prose is a **see-also-only block**. Detection criteria
(configurable):

- `block.kind` is one of the prose kinds (`hindi_text`, `hindi_gatha`,
  `prakrit_text`, `prakrit_gatha`, `sanskrit_text`, `sanskrit_gatha`).
- `block.text_devanagari` after stripping bullets / dashes / whitespace
  matches the regex
  `^.*?[\-–]\s*(?:विशेष\s+)?देखें\s+\S.*$`
  AND there is exactly one `देखें` occurrence and it lies in the trailing
  third of the string (post-bullet-prefix).
- The block has no `hindi_translation`.

When detected, the block is **dropped** from `Subsection.blocks` (and
from any `extra_blocks` list). The corresponding `Block(kind="see_also")`
that the parser already emits is the only retained representation.

### 6b. Definition `(N)` numbering inside prose

In PuranKosh definitions (and occasionally SiddhantKosh ones with
multiple definitions), the prose starts with a literal `(1) `, `(2) `,
... prefix:

```
(1) मरुवक्षेत्रके गन्धमादन पर्वतकी पूर्व श्रेणीका एक नगर ।
(2) उन्नतपुर नगरका वैभार पर्वत ।
```

These prefixes are redundant with `definition_index` and need to be
stripped from the leading prose of each `Definition.blocks[0].text_devanagari`.

## Failing tests (write first)

`workers/ingestion/jainkosh/tests/unit/test_see_also_only_block_drop.py`:

```python
from selectolax.parser import HTMLParser
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream


def test_dekhen_only_hindi_text_block_dropped_from_block_stream():
    html = '<p class="HindiText">• जीवको आत्मा कहनेकी विवक्षा - देखें <a href="/wiki/%E0%A4%9C%E0%A5%80%E0%A4%B5">जीव</a></p>'
    el = HTMLParser(html).css_first("p")
    blocks = parse_block_stream([el], load_config(), current_keyword="आत्मा")
    assert all(b.kind != "hindi_text" for b in blocks)
    sees = [b for b in blocks if b.kind == "see_also"]
    assert len(sees) == 1
    assert sees[0].target_keyword == "जीव"


def test_real_prose_with_inline_dekhen_kept():
    html = '<p class="HindiText">जीव शुद्ध है। देखें <a href="/wiki/%E0%A4%9C%E0%A5%80%E0%A4%B5">जीव</a> - 3.8</p>'
    el = HTMLParser(html).css_first("p")
    blocks = parse_block_stream([el], load_config(), current_keyword="आत्मा")
    text_blocks = [b for b in blocks if b.kind == "hindi_text"]
    assert len(text_blocks) == 1
    assert "जीव शुद्ध है" in (text_blocks[0].text_devanagari or "")
```

`workers/ingestion/jainkosh/tests/unit/test_definition_numbering_strip.py`:

```python
from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def test_purankosh_definitions_have_no_paren_n_prefix():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())
    purankosh_secs = [s for s in res.page_sections if s.section_kind == "puraankosh"]
    assert purankosh_secs
    for sec in purankosh_secs:
        for d in sec.definitions:
            text = (d.blocks[0].text_devanagari or "")
            assert not text.lstrip().startswith("(")
            import re
            assert re.match(r"^\s*\(\d+\)\s*", text) is None, text
```

Run: must FAIL.

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
see_also_only_block:
  enabled: true
  prose_kinds: ["hindi_text", "hindi_gatha", "prakrit_text", "prakrit_gatha", "sanskrit_text", "sanskrit_gatha"]
  match_re: '^[\s•·*\-–]*[^।॥]*?[\-–]?\s*(?:विशेष\s+)?देखें\s+[^।॥]*$'
  drop_from_extra_blocks: true

definitions:
  numbering_strip:
    enabled: true
    leading_re: '^\s*\(\d+\)\s*'
```

`config.py`:

```python
class SeeAlsoOnlyBlockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    prose_kinds: list[str] = Field(default_factory=lambda: [
        "hindi_text", "hindi_gatha", "prakrit_text", "prakrit_gatha",
        "sanskrit_text", "sanskrit_gatha",
    ])
    match_re: str = r'^[\s•·*\-–]*[^।॥]*?[\-–]?\s*(?:विशेष\s+)?देखें\s+[^।॥]*$'
    drop_from_extra_blocks: bool = True


class DefinitionsNumberingStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    leading_re: str = r"^\s*\(\d+\)\s*"


class DefinitionsConfig(BaseModel):
    siddhantkosh: DefinitionBoundaryConfig
    puraankosh: DefinitionBoundaryConfig
    numbering_strip: DefinitionsNumberingStripConfig = Field(default_factory=DefinitionsNumberingStripConfig)


class JainkoshConfig(BaseModel):
    ...
    see_also_only_block: SeeAlsoOnlyBlockConfig = Field(default_factory=SeeAlsoOnlyBlockConfig)
```

## Implementation

### 6.1 Drop see-also-only blocks — `parse_blocks.py`

After all blocks are produced in `parse_block_stream`, run a post-pass:

```python
def _drop_see_also_only(blocks: list[Block], config) -> list[Block]:
    if not config.see_also_only_block.enabled:
        return blocks
    pattern = re.compile(config.see_also_only_block.match_re)
    out = []
    pending_see_also: list[Block] = []
    for b in blocks:
        if b.kind == "see_also":
            pending_see_also.append(b)
            continue
        if (
            b.kind in config.see_also_only_block.prose_kinds
            and not b.hindi_translation
            and pattern.match(b.text_devanagari or "")
        ):
            # consume the matching see_also if present (already in pending), keep it
            for sa in pending_see_also:
                out.append(sa)
            pending_see_also = []
            continue
        for sa in pending_see_also:
            out.append(sa)
        pending_see_also = []
        out.append(b)
    for sa in pending_see_also:
        out.append(sa)
    return out
```

Call it at the bottom of `parse_block_stream` before returning:

```python
return _drop_see_also_only(out, config)
```

The `extra_blocks` list in `parse_section.py` is populated from
`extract_table_block`, not the prose stream, so it is unaffected. But
add the same drop-pass to any future per-section extra-blocks builder
that aggregates prose. Today, no change there.

### 6.2 Strip `(N)` numbering — `parse_definitions.py`

After producing each `Definition`, walk its `blocks` and strip the
leading `(\d+)\s*` prefix from the **first** prose block:

```python
def _strip_numbering(definitions, config) -> None:
    if not config.definitions.numbering_strip.enabled:
        return
    pat = re.compile(config.definitions.numbering_strip.leading_re)
    for d in definitions:
        for b in d.blocks:
            if b.kind in {"hindi_text", "hindi_gatha", "prakrit_text", "prakrit_gatha", "sanskrit_text", "sanskrit_gatha"} \
               and b.text_devanagari:
                stripped = pat.sub("", b.text_devanagari, count=1)
                if stripped != b.text_devanagari:
                    b.text_devanagari = stripped
                break  # only first prose block per definition
```

Call from both `parse_siddhantkosh_definitions` and
`parse_puraankosh_definitions` before returning.

### 6.3 Documentation

`docs/design/jainkosh/parsing_rules.md` §4.6 (NEW) — *See-also-only
block drop rule* and §6.10 (NEW) — *Definition prose numbering strip*.

## Definition of Done

- [ ] `test_see_also_only_block_drop.py` passes.
- [ ] `test_definition_numbering_strip.py` passes.
- [ ] Goldens regenerated; in `आत्मा.json`, no `Subsection.blocks` entry
      contains a `hindi_text` block whose `text_devanagari` starts with
      `• ... - देखें` and has no translation.
- [ ] In all goldens, no `Definition.blocks[*].text_devanagari` matches
      `^\s*\(\d+\)\s*`.
- [ ] No regression in fix-spec-001 phases.
