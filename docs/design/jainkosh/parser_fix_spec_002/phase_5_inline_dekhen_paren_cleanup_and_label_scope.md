# Phase 5 — Paren-`देखें` cleanup and label-seed scope guard

## Problem

Several issues, all stemming from how inline `देखें` references inside
prose are handled.

### 5a. Parenthesised `देखें` not stripped

Block in `द्रव्य.json`:

```jsonc
{
  "table": "topics",
  "natural_key": "...:एकांत-अभेद-वादियों-...-कह-सकते",
  "display_text": [{
    "lang": "hin", "script": "Deva",
    "text": "एकांत अभेद वादियों ... ‘द्रव्यं भव्ये’ यह लक्षण भी नहीं बनता (इसी प्रकार ‘गुणपर्ययवद् द्रव्यं’ या ‘गुणसमुदायो द्रव्यं’ भी वे नहीं कह सकते"
  }]
}
```

The trailing fragment was originally
`(इसी प्रकार ... कह सकते–देखें द्रव्य - 1.4\n)` in HTML. We want:

- The parenthesised `(... – देखें X ...)` substring removed from
  `text_devanagari` and from `hindi_translation`. Behaviour: when a
  `देखें` trigger is found inside an enclosing `(`/`)` pair (or `[`/`]`
  if configured), strip from the matching open bracket up to and
  including the matching close bracket.
- An un-parenthesised `देखें X` (e.g. `देखें जीव - 3.8`) is **kept** in
  the text — it stays as an inline `see_also` block but the prose itself
  is preserved.

### 5b. Label-seed Subsections spawned from in-prose `देखें`

In the same prose, the inline `(देखें X)` currently triggers
`extract_label_seed_candidates_from_elements` to produce a synthetic
Subsection whose heading is the entire surrounding prose. Concrete
example from `द्रव्य.json` line 593–602:

```jsonc
"heading_text": "जो सत् लक्षणवाला तथा उत्पादव्ययध्रौव्य युक्त है उसे द्रव्य कहते हैं। ( प्रवचनसार/95-96 )\n ( नयचक्र बृहद्/37 )\n ( आलापपद्धति/6 )\n ( योगसार (अमितगति)/2/6 )\n ( पंचाध्यायी / पूर्वार्ध/8,86 )"
```

This third-level synthetic Subsection should not be created — the prose
lives inside the `<span class="HindiText">` that is the translation
sibling of a `<span class="PrakritText">`, i.e. it is a translation, not
a topic-link list row. Label-seeds must only spawn from rows that look
like clear topic-link rows: bullet/dash-prefixed prose with the trigger
near the end (`• X – देखें Y`, `(N) X – देखें Y`).

### 5c. When a label IS emitted, it must be tightly trimmed

For the topic in 5a, we want the synthetic Topic's
`heading_text` to be:

```
इसी प्रकार ‘गुणपर्ययवद् द्रव्यं’ या ‘गुणसमुदायो द्रव्यं’ भी वे नहीं कह सकते
```

i.e. only the segment of prose between the immediately-preceding
sentence boundary (or open-paren) and the trigger. Today the entire
parent block's text is used.

## Failing tests (write first)

Create `workers/ingestion/jainkosh/tests/unit/test_paren_dekhen_strip.py`:

```python
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.see_also import strip_paren_dekhen


def _cfg():
    return load_config()


def test_strip_paren_around_dekhen_with_redlink():
    s = "X यह लक्षण नहीं बनता (इसी प्रकार ... कह सकते–देखें द्रव्य - 1.4)। बाकी।"
    assert strip_paren_dekhen(s, _cfg()) == "X यह लक्षण नहीं बनता । बाकी।"


def test_keep_unparenthesised_dekhen():
    s = "जीव शुद्ध है। देखें जीव - 3.8"
    assert strip_paren_dekhen(s, _cfg()) == s


def test_strip_paren_with_translation_newline():
    s = "...कहते हैं।\n(देखें सत्\n)।"
    assert strip_paren_dekhen(s, _cfg()) == "...कहते हैं।।"


def test_paren_dekhen_inside_brackets_when_enabled():
    s = "X [देखें Y] Z"
    out = strip_paren_dekhen(s, _cfg())
    assert "[" not in out and "]" not in out
    assert "देखें" not in out
```

Create `workers/ingestion/jainkosh/tests/unit/test_label_seed_scope.py`:

```python
from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _result():
    return parse_keyword_html(
        Path(__file__).parents[1].joinpath("fixtures", "द्रव्य.html").read_text(encoding="utf-8"),
        "https://example.org/wiki/द्रव्य",
        load_config(),
    )


def _walk(subs):
    for s in subs:
        yield s
        yield from _walk(s.children)


def test_no_label_seed_for_translation_inline_dekhen():
    res = _result()
    bad = [
        s for sec in res.page_sections for s in _walk(sec.subsections)
        if "जो सत् लक्षणवाला" in (s.heading_text or "")
        and s.is_synthetic
    ]
    assert bad == [], bad


def test_label_seed_for_redlink_row_uses_trimmed_label():
    res = _result()
    target = None
    for sec in res.page_sections:
        for s in _walk(sec.subsections):
            if s.heading_text == "इसी प्रकार ‘गुणपर्ययवद् द्रव्यं’ या ‘गुणसमुदायो द्रव्यं’ भी वे नहीं कह सकते":
                target = s
                break
    assert target is not None, "label-seed not emitted with trimmed text"
    assert target.label_topic_seed is True
```

Run: must FAIL.

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
paren_dekhen_strip:
  enabled: true
  bracket_pairs:
    - ["(", ")"]
    - ["[", "]"]
  trigger_required_inside: true   # only strip if a configured trigger appears between the brackets
  collapse_double_punct: true      # ".।" → "।", "  " → " " after stripping

label_to_topic:
  skip_in_source_kinds: ["hindi_text"]   # don't seed when the label-bearing block kind is in this set AND the trigger is inside brackets
  trim_to_clause: true                   # when emitting, take only the segment between the last sentence boundary and the trigger
  clause_boundary_chars: "।॥.()[]"
  preserve_inner_quotes: true
```

`config.py`:

```python
class ParenDekhenStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    bracket_pairs: list[tuple[str, str]] = Field(
        default_factory=lambda: [("(", ")"), ("[", "]")]
    )
    trigger_required_inside: bool = True
    collapse_double_punct: bool = True


class LabelToTopicConfig(BaseModel):
    ...
    skip_in_source_kinds: list[str] = Field(default_factory=lambda: ["hindi_text"])
    trim_to_clause: bool = True
    clause_boundary_chars: str = "।॥.()[]"
    preserve_inner_quotes: bool = True


class JainkoshConfig(BaseModel):
    ...
    paren_dekhen_strip: ParenDekhenStripConfig = Field(default_factory=ParenDekhenStripConfig)
```

## Implementation

### 5.1 `strip_paren_dekhen` — new helper in `see_also.py`

```python
def strip_paren_dekhen(text: str, config: JainkoshConfig) -> str:
    if not text or not config.paren_dekhen_strip.enabled:
        return text
    triggers = config.index.see_also_triggers
    out = text
    for opn, cls in config.paren_dekhen_strip.bracket_pairs:
        pattern = re.compile(
            re.escape(opn) + r"[^" + re.escape(opn + cls) + r"]*?"
            + r"(?:" + "|".join(re.escape(t) for t in sorted(triggers, key=len, reverse=True)) + r")"
            + r"[^" + re.escape(opn + cls) + r"]*?" + re.escape(cls),
            flags=re.DOTALL,
        )
        out = pattern.sub("", out)
    if config.paren_dekhen_strip.collapse_double_punct:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\s+([।॥,;])", r"\1", out)
        out = re.sub(r"([।॥])\s*\1+", r"\1", out)
        out = re.sub(r"\n[ \t]*\n", "\n", out)
    return out.strip()
```

### 5.2 Apply strip in `parse_blocks.py`

After the existing `text = strip_refs_from_text(text, refs, config)` line
in `make_block`, also run:

```python
text = strip_paren_dekhen(text, config)
```

And in `_emit` / translation-absorption, run `strip_paren_dekhen` on
`hindi_translation` before assigning. Easiest: after each
`last_block.hindi_translation = ...` assignment, wrap with
`strip_paren_dekhen(...)`.

The existing `strip_dekhen_redlink_substring` (fix-spec-001 phase 3)
remains in place — it strips the **un-parenthesised** redlink form
`X – देखें <redlink>`. The new helper is additive: it only strips
`(...देखें...)` enclosed forms.

### 5.3 Label-seed scope guard in `parse_subsections.py`

`extract_label_topic_seeds` and `extract_label_seed_candidates_from_elements`
must consult the **block kind that surrounds the trigger** and skip when
that kind is in `config.label_to_topic.skip_in_source_kinds`.

Concretely, in `_find_preceding_text_block`, return both the block AND
its kind, then in the caller:

```python
prose, prose_kind = _find_preceding_text_block(blocks, i)
if prose is None:
    continue
inside_brackets = _trigger_inside_brackets(prose.text_devanagari or "", config)
if inside_brackets and prose_kind in config.label_to_topic.skip_in_source_kinds:
    continue
```

`_trigger_inside_brackets` walks the prose and returns True if the
trigger position is inside any configured open/close bracket pair.

Apply the same guard inside
`extract_label_seed_candidates_from_elements`: pass the parent element's
block kind through and skip when it would have produced a label-seed
inside a `(...देखें...)` form **and** the parent is a translation
(`hindi_text`).

### 5.4 Trim label to clause — `extract_label_before_trigger`

Update `extract_label_before_trigger`:

```python
def extract_label_before_trigger(text: str, config: JainkoshConfig) -> str:
    triggers = sorted(config.index.see_also_triggers, key=len, reverse=True)
    for trigger in triggers:
        idx = text.rfind(trigger)
        if idx <= 0:
            continue
        label = text[:idx]
        if config.label_to_topic.trim_to_clause:
            boundary_chars = config.label_to_topic.clause_boundary_chars
            last = -1
            for ch in boundary_chars:
                last = max(last, label.rfind(ch))
            if last >= 0:
                label = label[last + 1:]
        for bullet in config.label_to_topic.bullet_prefixes:
            label = label.lstrip(bullet)
        label = re.sub(r"[\-–]\s*$", "", label)
        label = label.strip(config.label_to_topic.label_trim_chars + " \t\n")
        return normalize_text(label)
    return ""
```

This trims the label to the segment between the last `।`/`.`/`(`/`[`
and the trigger. For un-parenthesised redlink rows like
`• द्रव्य का लक्षण ‘अर्थक्रियाकारित्व’। – देखें वस्तु`, trimming yields
the existing label `द्रव्य का लक्षण ‘अर्थक्रियाकारित्व’` because the
trim only kicks in when there's a boundary inside the prefix; if the
prefix is already a clean bullet+label the existing bullet-strip path
handles it.

For the parenthesised case, the trimmed segment is the in-paren clause
(without the leading `(`).

### 5.5 Documentation

`docs/design/jainkosh/parsing_rules.md` §5.7 (NEW) — *Parenthesised
देखें cleanup* and §5.8 (NEW) — *Label-seed scope rules*.

## Definition of Done

- [ ] `test_paren_dekhen_strip.py` passes.
- [ ] `test_label_seed_scope.py` passes.
- [ ] In `द्रव्य.json` regenerated golden, the synthetic Subsection with
      heading starting `"जो सत् लक्षणवाला..."` is gone.
- [ ] In its place, a label-seed Subsection with `heading_text =
      "इसी प्रकार ‘गुणपर्ययवद् द्रव्यं’ या ‘गुणसमुदायो द्रव्यं’ भी वे नहीं कह सकते"`
      exists with `label_topic_seed=true`.
- [ ] `text_devanagari` of the affected `hindi_text` blocks no longer
      contains `(देखें ...)` substrings.
- [ ] Un-parenthesised `देखें X` strings remain in prose.
- [ ] No regression in fix-spec-001 phase 3 (redlink prose strip).
