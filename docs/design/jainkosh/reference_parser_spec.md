# JainKosh Reference Parser — Implementation Spec

> Specification for structured resolution of `<span class="GRef">` citation
> strings against `parser_configs/_manual_configs/shastra.json`.
>
> **Status**: Design-complete. Do not implement without regenerating all three
> golden JSON files afterwards.
>
> Audience: any implementer who hasn't been in the design conversation.

---

## 0. Scope

### In scope
- New module `workers/ingestion/jainkosh/parse_reference.py` — all resolution logic.
- `ShastraRegistry` — loads, normalises, and indexes `shastra.json`.
- Changes to `models.py` — `Reference` model augmented; `raw_html` removed.
- Changes to `config.py` / `jainkosh.yaml` — new config knobs.
- Unit tests for each algorithmic layer.
- Golden regeneration (models change, so all three goldens become stale).

### Out of scope
- Neo4j `CITES` edges (deferred).
- Fuzzy / Levenshtein matching (exact only for now).
- Admin review UI for `needs_manual_match` records.

---

## 1. The `shastra.json` format DSL

Every entry in `parser_configs/_manual_configs/shastra.json` carries a `"format"` string
that describes how the numeric portion of a reference is structured.

### 1.1 Separators

| Separator | Where | Meaning |
|-----------|-------|---------|
| `/` | Between groups | Primary section boundary (same as `/` in the reference value) |
| `,` | Within a group | Sub-separator: multiple fields share the same slash section |
| `-` | Within a group | Sub-separator: same semantics as `,` within that section |
| `§` | Prefix on a field name | The whole group is optional; the value signals its presence by prefixing the value with `§` |

Rules:
- Each `/`-separated segment in the format defines one **format group**.
- Within a format group, fields are sub-separated by `,` **or** `-` (not both in one group).
- The sub-separator used in the format group is the same separator used when splitting the
  corresponding value group.
- A `-` that appears in a VALUE string is a range indicator (e.g. `"13-14"`) and is **not**
  split further, UNLESS the format group's separator is `-`.  
  → If format group separator is `,`: `"13-14"` in value → single field value `"13-14"`.  
  → If format group separator is `-`: `"13-14"` in value → two field values `"13"` and `"14"`.
- A `§`-prefixed field makes the **entire group** optional. The corresponding value group is
  detected by a leading `§` character in the raw value string.

### 1.2 Annotated examples

```
Format:  पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा
Groups:  [पुस्तक] / [खण्ड, भाग, सूत्र] / [पृष्ठ] / [गाथा]
         sep=None    sep=","               sep=None   sep=None

Reference value (after stripping name):  1/1,1,1/84/1
Group 0: "1"     → पुस्तक=1
Group 1: "1,1,1" → खण्ड=1, भाग=1, सूत्र=1
Group 2: "84"    → पृष्ठ=84
Group 3: "1"     → गाथा=1
```

```
Format:  पुस्तक,भाग/§प्रकरण/पृष्ठ/पंक्ति
Groups:  [पुस्तक, भाग] / [§प्रकरण (optional)] / [पृष्ठ] / [पंक्ति]

Reference value with optional present:  1,2/§181/217/1
Group 0: "1,2"   → पुस्तक=1, भाग=2
Group 1: "§181"  → (§ detected) प्रकरण=181
Group 2: "217"   → पृष्ठ=217
Group 3: "1"     → पंक्ति=1

Reference value with optional absent:  1,2/217/1
Group 0: "1,2"  → पुस्तक=1, भाग=2
Group 1: "217"  → no leading § → skip optional group
Group 2: "217"  → पृष्ठ=217
Group 3: "1"    → पंक्ति=1
```

```
Format:  मुख्याधिकार-प्रकरण/श्लोक/पृष्ठ
Groups:  [मुख्याधिकार, प्रकरण] / [श्लोक] / [पृष्ठ]
         sep="-"                  sep=None   sep=None

Reference value:  3-7/5/18
Group 0: "3-7" → split by "-" → मुख्याधिकार=3, प्रकरण=7
Group 1: "5"   → श्लोक=5
Group 2: "18"  → पृष्ठ=18
```

### 1.3 Parsed representation

```python
@dataclass
class FormatField:
    name: str        # Devanagari field name without §
    optional: bool   # True when § was present (on the group)

@dataclass
class FormatGroup:
    fields: list[FormatField]
    sub_separator: Optional[str]   # None | "," | "-"

    @property
    def is_optional(self) -> bool:
        return any(f.optional for f in self.fields)

    @property
    def has_required_field(self) -> bool:
        return any(not f.optional for f in self.fields)
```

`FormatGroup.fields` always contains at least one `FormatField`.
`FormatGroup.sub_separator` is `None` for single-field groups.

---

## 2. Model changes (`models.py`)

### 2.1 New `ResolvedField` model

```python
class ResolvedField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str                     # field name from format, e.g. "पुस्तक"
    value: Union[int, str]         # int for pure numeric, str for ranges/alphanumeric
```

`value` is coerced to `int` when the stripped value string matches `^\d+$`, otherwise kept as `str`.

### 2.2 Updated `Reference` model

Remove `raw_html`. Remove `parsed` entirely — it was redundant with `needs_manual_match`.
Add structured resolution fields.

```python
class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    # raw_html — REMOVED
    # parsed — REMOVED (redundant: resolved iff needs_manual_match=False and shastra_name is not None)
    inline_reference: bool = False
    # --- resolution fields (all default when not resolved) ---
    needs_manual_match: bool = False
    is_teeka: bool = False
    teeka_name: str = ""
    shastra_name: Optional[str] = None            # matched canonical shastra_name from registry
    match_method: Optional[Literal[
        "shastra_name", "alternate_name", "short_form"
    ]] = None
    resolved_fields: list[ResolvedField] = Field(default_factory=list)
```

**Invariants**:
- `needs_manual_match == True` implies `resolved_fields == []`. When the numeric portion
  cannot be fully matched to the format (extra groups, sub-group mismatch), no partial
  fields are emitted — the caller must inspect the reference manually.
- `needs_manual_match == True` and `shastra_name is None` means the shastra itself was
  not identified. `needs_manual_match == True` and `shastra_name is not None` means the
  shastra was found but the numeric format did not match.

### 2.3 `ParsedReference` — remove

`ParsedReference` is dead code. Remove the class.
No golden or test references it with a non-`None` value (it was always `null`).

### 2.4 JSON output shape for a resolved reference

Fully resolved — shastra found, format matched exactly:
```json
{
  "text": "धवला 1/1,1,1/84/1",
  "inline_reference": false,
  "needs_manual_match": false,
  "is_teeka": false,
  "teeka_name": "",
  "shastra_name": "धवला",
  "match_method": "shastra_name",
  "resolved_fields": [
    {"field": "पुस्तक", "value": 1},
    {"field": "खण्ड",   "value": 1},
    {"field": "भाग",    "value": 1},
    {"field": "सूत्र",  "value": 1},
    {"field": "पृष्ठ",  "value": 84},
    {"field": "गाथा",   "value": 1}
  ]
}
```

Resolved with teeka — shastra found, format matched:
```json
{
  "text": "प्रवचनसार / तत्त्वप्रदीपिका 1/5/10",
  "inline_reference": false,
  "needs_manual_match": false,
  "is_teeka": true,
  "teeka_name": "तत्त्वप्रदीपिका",
  "shastra_name": "प्रवचनसार",
  "match_method": "shastra_name",
  "resolved_fields": [...]
}
```

Partial match — shastra found, format has too many value groups:
```json
{
  "text": "सर्वार्थसिद्धि/1/5/17/5",
  "inline_reference": false,
  "needs_manual_match": true,
  "is_teeka": false,
  "teeka_name": "",
  "shastra_name": "सर्वार्थसिद्धि",
  "match_method": "shastra_name",
  "resolved_fields": []
}
```

No match — shastra not identified:
```json
{
  "text": "अज्ञात शास्त्र 1/5",
  "inline_reference": false,
  "needs_manual_match": true,
  "is_teeka": false,
  "teeka_name": "",
  "shastra_name": null,
  "match_method": null,
  "resolved_fields": []
}
```

Partial numeric match — shastra found, value has fewer groups than format (valid: `on_missing_fields=false`):
```json
{
  "text": "पंचास्तिकाय/10",
  "inline_reference": false,
  "needs_manual_match": false,
  "is_teeka": false,
  "teeka_name": "",
  "shastra_name": "पंचास्तिकाय",
  "match_method": "shastra_name",
  "resolved_fields": [
    {"field": "गाथा", "value": 10}
  ]
}
```

---

## 3. `ShastraRegistry` (`parse_reference.py`)

### 3.1 Loading and indexing

```python
class ShastraEntry:
    shastra_name: str            # canonical key from JSON
    alternate_name: Optional[str]
    short_form: str
    format_str: str              # raw format string, e.g. "पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"
    format_groups: list[FormatGroup]  # pre-parsed at load time

class ShastraRegistry:
    entries: list[ShastraEntry]
    _by_primary:   dict[str, ShastraEntry]  # normalised shastra_name → entry
    _by_alternate: dict[str, ShastraEntry]  # normalised alternate_name → entry
    _by_short_form: dict[str, ShastraEntry] # normalised short_form → entry

    @classmethod
    def load(cls, path: Path, norm_config: "DevanagariNormalizationConfig") -> "ShastraRegistry":
        raw = json.loads(path.read_text("utf-8"))
        registry = cls()
        for item in raw:
            entry = ShastraEntry(
                shastra_name=item["shastra_name"],
                alternate_name=item.get("alternate_name"),
                short_form=item.get("short_form", ""),
                format_str=item.get("format", ""),
                format_groups=parse_format_string(item.get("format", "")),
            )
            registry.entries.append(entry)
            registry._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
            if entry.alternate_name:
                registry._by_alternate[_normalise(entry.alternate_name, norm_config)] = entry
            if entry.short_form:
                registry._by_short_form[_normalise(entry.short_form, norm_config)] = entry
        return registry
```

`_normalise(text, config)` is defined in §4.

### 3.2 Lookup

```python
def lookup(
    self,
    normalised_name: str,
) -> tuple[Optional[ShastraEntry], Optional[str]]:
    """
    Returns (entry, match_method) where match_method is one of
    "shastra_name" | "alternate_name" | "short_form" | None.
    Priority: shastra_name → alternate_name → short_form.
    """
    entry = self._by_primary.get(normalised_name)
    if entry:
        return entry, "shastra_name"
    entry = self._by_alternate.get(normalised_name)
    if entry:
        return entry, "alternate_name"
    entry = self._by_short_form.get(normalised_name)
    if entry:
        return entry, "short_form"
    return None, None
```

---

## 4. Devanagari normalisation for matching

### 4.1 Purpose

Two equivalences are required for matching:

1. **Anusvar ↔ explicit nasal conjunct**:
   - `गोम्मटसार जीवकांड` ↔ `गोम्मटसार जीवकाण्ड`
   - `काण्ड` ↔ `कांड`

2. **Space-agnostic matching**: the shastra name in `shastra.json` may have internal
   spaces that the referenced text omits (or vice versa):
   - `"तत्त्वार्थ सूत्र"` (registry) ↔ `"तत्त्वार्थसूत्र"` (reference text)
   - `"राजवार्तिक हिन्दी"` (registry) ↔ `"राजवार्तिकहिन्दी"` (reference text)

### 4.2 Function

```python
def _normalise(text: str, config: "DevanagariNormalizationConfig") -> str:
    """NFC + configurable substitutions + space removal. For matching only — never stored."""
    text = unicodedata.normalize("NFC", text)
    if config.enabled:
        for sub in config.substitutions:
            text = text.replace(sub.from_, sub.to)
    # Normalise whitespace around "/" so "name / teeka" and "name/teeka" are the same key
    text = re.sub(r"\s*/\s*", "/", text)
    # Remove all remaining spaces so "तत्त्वार्थ सूत्र" and "तत्त्वार्थसूत्र" match
    text = text.replace(" ", "")
    return text
```

The old `re.sub(r"\s+", " ", text).strip()` step is replaced by the slash normalisation
followed by full space removal. The slash step must come first so "name / teeka" collapses
to "name/teeka" before space removal, preserving the "/" boundary correctly.

Applied to both the query string and the indexed keys at load time. Keys are stored
pre-normalised; the query is normalised on each lookup call.

### 4.3 Default substitution table (in `jainkosh.yaml`)

```yaml
reference:
  devanagari_normalization:
    enabled: true
    substitutions:
      - {from: "ण्ड", to: "ंड"}
      - {from: "ण्ठ", to: "ंठ"}
      - {from: "ञ्च", to: "ंच"}
      - {from: "ञ्ज", to: "ंज"}
      - {from: "न्त", to: "ंत"}
      - {from: "न्द", to: "ंद"}
      - {from: "म्ब", to: "ंब"}
      - {from: "न्व", to: "ंव"}
```

The table is applied in order; extend without code changes.

---

## 4A. Text pre-processing

Before `split_name_and_numeric` is called, the raw reference text is cleaned through
a three-step pipeline. The original `text` stored on `Reference` is **never mutated** —
a `_clean` working copy is produced and used only for resolution.

### 4A.1 Pipeline overview

```
raw text
  → step 1: strip all parentheses
  → step 2: remove noise phrases (whole-phrase, configurable)
  → step 3: remove section keywords (word-boundary, configurable)
  → step 4: collapse whitespace
  → _clean  (passed to split_name_and_numeric)
```

### 4A.2 Step 1 — Strip all parentheses

Remove every `(` and `)` character from the text (regardless of position).

```python
def _strip_parens(text: str) -> str:
    return text.replace("(", "").replace(")", "")
```

Examples:

| Input | After step 1 |
|-------|-------------|
| `"( ज्ञानार्णव अधिकार 32/5/317)"` | `" ज्ञानार्णव अधिकार 32/5/317"` |
| `"(द्रव्यसंग्रह / मूल या टीका गाथा 14/46)"` | `"द्रव्यसंग्रह / मूल या टीका गाथा 14/46"` |
| `"धवला 1/5"` | `"धवला 1/5"` (unchanged) |

### 4A.3 Step 2 — Remove noise phrases

Remove each phrase in `config.noise_phrases.phrases` as a **whole literal string**
from the working text. Phrases are applied in order; each replacement is a single
space (so adjacent words don't merge). Only applies when `noise_phrases.enabled=true`.

```python
def _strip_noise_phrases(text: str, config: "ReferenceNoisePhraseConfig") -> str:
    if not config.enabled:
        return text
    for phrase in config.phrases:
        text = text.replace(phrase, " ")
    return text
```

Default phrase list (in `jainkosh.yaml`):

```yaml
reference:
  noise_phrases:
    enabled: true
    phrases:
      - "मूल गाथा या टीका"
```

This step runs **before** individual keyword removal so that compound phrases like
`"मूल गाथा या टीका"` are removed as a unit — preventing "गाथा" from being left
behind as a dangling word that would then be removed by step 3 (correct outcome but
only by accident), and ensuring the matched phrase boundary is clean.

Example:

| Input after step 1 | After step 2 |
|--------------------|-------------|
| `"द्रव्यसंग्रह / मूल गाथा या टीका 14/46"` | `"द्रव्यसंग्रह /  14/46"` |
| `"समाधिशतक / मूल या टीका गाथा 4"` | `"समाधिशतक / मूल या टीका गाथा 4"` (unchanged — different phrase) |

### 4A.4 Step 3 — Remove section keywords

Remove each keyword in `config.section_keywords.keywords` when it appears **surrounded
by whitespace on both sides** (i.e., it is an isolated word, not part of a longer
Devanagari compound). Removal replaces the keyword (and its surrounding whitespace)
with a single space. Only applies when `section_keywords.enabled=true`.

```python
def _strip_section_keywords(text: str, config: "ReferenceSectionKeywordsConfig") -> str:
    if not config.enabled:
        return text
    for kw in config.keywords:
        # \s+ on both sides — keyword must be surrounded by whitespace
        text = re.sub(r"\s+" + re.escape(kw) + r"\s+", " ", text)
    return text
```

**Key rule**: a keyword at the very start or very end of the text (no whitespace on
one side) is NOT removed. This prevents accidentally stripping a keyword that is itself
the shastra name (e.g., a reference that is just `"गाथा"` with no numeric part).

Default keyword list (in `jainkosh.yaml`):

```yaml
reference:
  section_keywords:
    enabled: true
    keywords:
      - गाथा
      - श्लोक
      - पंक्ति
      - कलश
      - अधिकार
      - अध्याय
      - सर्ग
      - परिच्छेद
      - प्रकरण
      - खण्ड
      - भाग
      - पुस्तक
```

Examples (continuing from after step 2):

| Input after step 2 | After step 3 |
|--------------------|-------------|
| `"धवला पुस्तक 13/5,5,50/282/9"` | `"धवला 13/5,5,50/282/9"` |
| `"ज्ञानार्णव अधिकार 32/5/317"` | `"ज्ञानार्णव 32/5/317"` |
| `"ज्ञानसार श्लोक 29"` | `"ज्ञानसार 29"` |
| `"समयसार / आत्मख्याति गाथा 8"` | `"समयसार / आत्मख्याति 8"` |
| `"द्रव्यसंग्रह /  14/46"` (from step 2) | `"द्रव्यसंग्रह / 14/46"` (spaces collapsed next) |

### 4A.5 Step 4 — Collapse whitespace

```python
def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
```

### 4A.6 Combined helper

```python
def _preprocess_text(text: str, config: "ReferenceConfig") -> str:
    text = _strip_parens(text)
    text = _strip_noise_phrases(text, config.noise_phrases)
    text = _strip_section_keywords(text, config.section_keywords)
    text = _collapse_ws(text)
    return text
```

Called at the top of `parse_reference_text` before `split_name_and_numeric`.

### 4A.7 End-to-end pre-processing examples

| Original text | After pre-processing | name_raw | numeric_raw |
|---------------|----------------------|----------|-------------|
| `"धवला पुस्तक 13/5,5,50/282/9"` | `"धवला 13/5,5,50/282/9"` | `"धवला"` | `"13/5,5,50/282/9"` |
| `"( ज्ञानार्णव अधिकार 32/5/317)"` | `"ज्ञानार्णव 32/5/317"` | `"ज्ञानार्णव"` | `"32/5/317"` |
| `"( ज्ञानसार श्लोक 29)"` | `"ज्ञानसार 29"` | `"ज्ञानसार"` | `"29"` |
| `"(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)"` | `"द्रव्यसंग्रह / 14/46"` | `"द्रव्यसंग्रह"` | `"14/46"` |
| `"समयसार / आत्मख्याति गाथा 8"` | `"समयसार / आत्मख्याति 8"` | `"समयसार / आत्मख्याति"` | `"8"` |
| `"(परमात्मप्रकाश / मूल या टीका अधिकार 1/11)"` | `"परमात्मप्रकाश / मूल या टीका 1/11"` | `"परमात्मप्रकाश / मूल या टीका"` | `"1/11"` |

Note: in the last row, "अधिकार" is removed (keyword surrounded by spaces). "मूल या टीका"
remains in the name and becomes the teeka candidate in `match_shastra` step 3.

---

## 5. Name extraction algorithm

### 5.1 Split `name_raw` and `numeric_raw`

A GRef text like `"धवला 1/1,1,1/84/1"` or `"पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12"`.

```python
def split_name_and_numeric(text: str) -> tuple[str, str]:
    """
    Returns (name_raw, numeric_raw).
    name_raw  = everything before the first digit or § character.
    numeric_raw = everything from the first digit or § onward.
    Both are stripped of leading/trailing whitespace and leading/trailing /.
    """
    # Find first position of a digit or § (the numeric section starts here)
    m = re.search(r"[\d§]", text)
    if m is None:
        return text.strip().strip("/").strip(), ""
    name_raw    = text[:m.start()].strip().strip("/").strip()
    numeric_raw = text[m.start():].strip().strip("/").strip()
    return name_raw, numeric_raw
```

Examples:

| Input | name_raw | numeric_raw |
|-------|----------|-------------|
| `"धवला 1/1,1,1/84/1"` | `"धवला"` | `"1/1,1,1/84/1"` |
| `"धवला1/84"` | `"धवला"` | `"1/84"` |
| `"पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12"` | `"पंचास्तिकाय / तात्पर्यवृत्ति"` | `"16/35/12"` |
| `"कषायपाहुड़ 1/1,13-14/ §181/217/1"` | `"कषायपाहुड़"` | `"1/1,13-14/§181/217/1"` |
| `"धवला"` (name only) | `"धवला"` | `""` |

### 5.2 Numeric string cleaning

Before format resolution, remove all space characters from `numeric_raw`:

```python
numeric_clean = numeric_raw.replace(" ", "")
```

---

## 6. Shastra matching algorithm

### 6.1 Full pipeline

```python
def match_shastra(
    name_raw: str,
    registry: ShastraRegistry,
    config: "ReferenceParseConfig",
) -> tuple[Optional[ShastraEntry], Optional[str], bool, str]:
    """
    Returns (entry, match_method, is_teeka, teeka_name).
    is_teeka=True only when the combined name was not itself in the registry
    and the right-hand slash-part is treated as a teeka.
    """
    norm = lambda s: _normalise(s, config.devanagari_normalization)

    # ── Step 1: try full name_raw as-is ──────────────────────────────────
    entry, method = registry.lookup(norm(name_raw))
    if entry:
        return entry, method, False, ""

    # ── Step 2: strip mool keyword and retry ─────────────────────────────
    stripped = _strip_mool(name_raw, config)
    if stripped != name_raw:
        entry, method = registry.lookup(norm(stripped))
        if entry:
            return entry, method, False, ""

    # ── Step 3: teeka detection (slash split) ────────────────────────────
    # Normalise slashes before splitting so "name / teeka" and "name/teeka" work.
    name_for_split = re.sub(r"\s*/\s*", "/", name_raw)
    if "/" in name_for_split:
        base, _, teeka_candidate = name_for_split.partition("/")
        base = base.strip()
        teeka_candidate = teeka_candidate.strip()
        # Try full base (with any remaining / after the first)
        entry, method = registry.lookup(norm(base))
        if not entry:
            # Also try mool-stripped base
            stripped_base = _strip_mool(base, config)
            if stripped_base != base:
                entry, method = registry.lookup(norm(stripped_base))
                if entry:
                    base = stripped_base
        if entry:
            return entry, method, True, teeka_candidate

    # ── No match ─────────────────────────────────────────────────────────
    return None, None, False, ""
```

### 6.2 `_strip_mool` helper

```python
def _strip_mool(name: str, config: "ReferenceParseConfig") -> str:
    """
    Strip trailing mool keywords (e.g. " मूल", "/मूल") from name, unless the name
    is in or starts with a mool_exception entry.
    """
    norm_name = unicodedata.normalize("NFC", name)
    for exc in config.mool.exceptions:
        if norm_name == unicodedata.normalize("NFC", exc):
            return name  # exact exception — don't strip anything
        if norm_name.startswith(unicodedata.normalize("NFC", exc)):
            return name  # starts with exception — don't strip

    for kw in config.mool.keywords:
        kw_nfc = unicodedata.normalize("NFC", kw)
        # trailing " keyword"
        if norm_name.endswith(" " + kw_nfc):
            return name[: -(1 + len(kw))].strip()
        # trailing "/keyword"
        if norm_name.endswith("/" + kw_nfc):
            return name[: -(1 + len(kw))].rstrip("/").strip()
    return name
```

### 6.3 Matching priority summary

1. Full `name_raw` → `shastra_name`, `alternate_name`, `short_form`
2. `name_raw` after मूल stripping → same three
3. Base of `name_raw` (part before first `/`) → same three
4. Base after मूल stripping → same three
5. No match → `needs_manual_match = True`

---

## 7. Format string parser

### 7.1 Grammar (pseudo-BNF)

```
format_str   = group ( "/" group )*
group        = field ( sub_sep field )*
sub_sep      = "," | "-"
field        = ["§"] hindi_word
hindi_word   = <one or more non-"/" non-"," non-"-" non-"§" characters>
```

Rules:
- A group with `§` on any field is an optional group.
- Sub-separator for a group is determined by the first sub-separator character found in it.
  Only one type of sub-separator is expected per group.

### 7.2 Implementation

```python
_FIELD_RE = re.compile(r"(§?)([^/,\-§]+)")

def parse_format_string(fmt: str) -> list[FormatGroup]:
    if not fmt:
        return []
    groups = []
    for group_str in fmt.split("/"):
        group_str = group_str.strip()
        if not group_str:
            continue

        # Detect sub-separator
        if "," in group_str:
            sub_sep = ","
            raw_fields = group_str.split(",")
        elif "-" in group_str and len(re.findall(r"[^ऀ-ॿऀ-ॿ]", group_str)) > 0:
            # "-" only counts as separator if surrounded by field names (not part of a Hindi word)
            # Heuristic: split by "-" when the group contains no ","
            sub_sep = "-"
            raw_fields = group_str.split("-")
        else:
            sub_sep = None
            raw_fields = [group_str]

        fields = []
        for rf in raw_fields:
            rf = rf.strip()
            m = _FIELD_RE.match(rf)
            if not m:
                continue
            optional = m.group(1) == "§"
            name = m.group(2).strip()
            fields.append(FormatField(name=name, optional=optional))

        if fields:
            groups.append(FormatGroup(fields=fields, sub_separator=sub_sep))
    return groups
```

**Note on `-` detection**: The separator `-` ambiguity (Hindi word containing `-` vs sub-separator) is resolved by checking: if the token between two `-` characters is a valid Devanagari word (contains at least one Devanagari char, no digits), treat `-` as separator. Otherwise treat it as part of the field name. In practice, all current format strings with `-` follow `Word-Word` patterns.

---

## 8. Value resolution algorithm

### 8.1 Main function

```python
def resolve_fields(
    numeric_clean: str,
    format_groups: list[FormatGroup],
    config: "ReferenceNeedsManualMatchConfig",
) -> tuple[list[ResolvedField], bool]:
    """
    Returns (resolved_fields, needs_manual_match).
    numeric_clean = slash-separated value string with spaces already removed.
    """
    if not numeric_clean:
        # No numeric part at all
        # If any required format fields exist → needs_manual_match
        has_required = any(g.has_required_field for g in format_groups)
        return [], has_required and config.on_missing_fields

    value_groups = numeric_clean.split("/")
    resolved: list[ResolvedField] = []
    needs_manual = False
    v_idx = 0

    for f_group in format_groups:
        if v_idx >= len(value_groups):
            # Ran out of values
            if f_group.has_required_field and config.on_missing_fields:
                needs_manual = True
            continue  # optional groups with no value → fine

        if f_group.is_optional:
            # Only consume this value group if it starts with §
            if value_groups[v_idx].startswith("§"):
                value_str = value_groups[v_idx][1:]  # strip §
                partial, mismatch = _assign_group(f_group, value_str)
                resolved.extend(partial)
                if mismatch and config.on_missing_fields:
                    needs_manual = True
                v_idx += 1
            # else: skip this optional group, don't advance v_idx
        else:
            value_str = value_groups[v_idx]
            partial, mismatch = _assign_group(f_group, value_str)
            resolved.extend(partial)
            if mismatch and config.on_missing_fields:
                needs_manual = True
            v_idx += 1

    # Leftover value groups
    if v_idx < len(value_groups) and config.on_extra_groups:
        needs_manual = True

    return resolved, needs_manual
```

### 8.2 `_assign_group` helper

```python
def _assign_group(
    f_group: FormatGroup,
    value_str: str,
) -> tuple[list[ResolvedField], bool]:
    """
    Split value_str using the group's sub_separator, assign to fields in order.
    Returns (resolved_fields, mismatch_flag).
    mismatch_flag = True when counts don't align.
    """
    sep = f_group.sub_separator
    if sep:
        parts = [p.strip() for p in value_str.split(sep)]
    else:
        parts = [value_str.strip()]

    fields = f_group.fields
    mismatch = len(parts) != len(fields)
    resolved = []

    for i, field in enumerate(fields):
        if i < len(parts):
            resolved.append(ResolvedField(field=field.name, value=_coerce_value(parts[i])))
        # If len(parts) < len(fields): remaining fields get no entry → mismatch already True

    # If len(parts) > len(fields): extra parts are discarded, mismatch already True
    return resolved, mismatch


def _coerce_value(s: str) -> Union[int, str]:
    s = s.strip()
    if s.isdigit():
        return int(s)
    return s
```

### 8.3 needs_manual_match summary and resolved_fields invariant

`needs_manual_match` is set to `True` when ANY of the following occur (each
independently configurable via `reference.needs_manual_match`):

| Trigger | Config knob | Default | Example |
|---------|------------|---------|---------|
| Value has more slash-groups than format defines | `on_extra_groups` | `true` | Format 3 groups, value has 4 (`"सर्वार्थसिद्धि/1/5/17/5"`) |
| Required format field has no corresponding value | `on_missing_fields` | `false` | Format needs 4, value provides 2 (`"पंचास्तिकाय/10"`) |
| Sub-split mismatch (parts ≠ fields within a group) | `on_missing_fields` | `false` | Format `खण्ड,भाग,सूत्र` but value has `1,2` |

**`on_missing_fields` default is `false`**: providing fewer slash-groups than the
format expects is treated as a valid partial citation, not a resolution failure. Only
extra (unrecognised) groups trigger `needs_manual_match`.

**`resolved_fields` invariant**: whenever `needs_manual_match=True` (for any reason),
`resolved_fields` **must be `[]`**. Partial field resolution is not exposed — the
caller must treat the reference as unresolved and inspect it manually. This is enforced
in `parse_reference_text` (§9) after `resolve_fields` returns, not inside `resolve_fields`
itself (which still computes fields internally for its mismatch/leftover detection logic).

---

## 9. Top-level entry point (`parse_reference.py`)

```python
def parse_reference_text(
    text: str,
    registry: ShastraRegistry,
    config: "ReferenceConfig",
) -> None:
    """
    Called from refs.py. Mutates a Reference object by populating resolution fields.
    Returns None — caller applies result to the Reference.
    Actually returns a dict of kwargs to pass into Reference construction.
    """
```

More precisely, `parse_reference_text` is a **pure function** returning a
`_ResolutionResult` (internal dataclass) which `extract_refs_from_node` in
`refs.py` uses when constructing each `Reference` object.

```python
@dataclass
class _ResolutionResult:
    # parsed field REMOVED — callers check needs_manual_match and shastra_name directly
    needs_manual_match: bool
    is_teeka: bool
    teeka_name: str
    shastra_name: Optional[str]
    match_method: Optional[str]
    resolved_fields: list[ResolvedField]
```

Full implementation:

```python
def parse_reference_text(
    text: str,
    registry: ShastraRegistry,
    config: "ReferenceConfig",
) -> _ResolutionResult:
    EMPTY = _ResolutionResult(
        needs_manual_match=False,
        is_teeka=False, teeka_name="",
        shastra_name=None, match_method=None,
        resolved_fields=[],
    )

    if not text:
        return EMPTY

    # Pre-process: strip parens, noise phrases, section keywords
    clean = _preprocess_text(text, config)
    if not clean:
        return EMPTY

    name_raw, numeric_raw = split_name_and_numeric(clean)
    if not name_raw:
        return EMPTY

    numeric_clean = numeric_raw.replace(" ", "")

    entry, method, is_teeka, teeka_name = match_shastra(name_raw, registry, config)

    if entry is None:
        return _ResolutionResult(
            needs_manual_match=True,
            is_teeka=False, teeka_name="",
            shastra_name=None, match_method=None,
            resolved_fields=[],
        )

    resolved_fields, needs_manual = resolve_fields(
        numeric_clean, entry.format_groups, config.needs_manual_match
    )

    # Invariant: when needs_manual_match=True, resolved_fields must be empty
    if needs_manual:
        resolved_fields = []

    return _ResolutionResult(
        needs_manual_match=needs_manual,
        is_teeka=is_teeka,
        teeka_name=teeka_name,
        shastra_name=entry.shastra_name,
        match_method=method,
        resolved_fields=resolved_fields,
    )
```

---

## 10. Integration with existing code

### 10.1 `config.py` — new config classes

Add to `config.py`:

```python
class DevanagariNormSubstitution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: str = Field(alias="from")
    to: str

class DevanagariNormalizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    substitutions: list[DevanagariNormSubstitution] = Field(default_factory=list)

class ReferenceMoolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keywords: list[str] = Field(default_factory=lambda: ["मूल"])
    exceptions: list[str] = Field(default_factory=lambda: ["मूलाचार"])

class ReferenceNeedsManualMatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_extra_groups: bool = True
    on_missing_fields: bool = False   # changed from True — partial citations are valid

class ReferenceNoisePhraseConfig(BaseModel):
    """Whole-phrase noise strings removed from reference text before matching."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    phrases: list[str] = Field(default_factory=lambda: ["मूल गाथा या टीका"])

class ReferenceSectionKeywordsConfig(BaseModel):
    """Single-word section headers removed when surrounded by whitespace."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    keywords: list[str] = Field(default_factory=lambda: [
        "गाथा", "श्लोक", "पंक्ति", "कलश", "अधिकार", "अध्याय",
        "सर्ग", "परिच्छेद", "प्रकरण", "खण्ड", "भाग", "पुस्तक",
    ])
```

Add fields to `ReferenceConfig`:

```python
class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    strip_inner_anchors: bool
    parse_strategy: Literal["text_only", "structured", "text_plus_structured"] = "text_only"
    raw_html: ReferenceRawHtmlConfig = Field(default_factory=ReferenceRawHtmlConfig)
    semicolon_split: ReferenceSemicolonSplitConfig = Field(...)
    annotate_inline_position: bool = True
    # --- new fields ---
    shastra_config_path: Optional[str] = None
    devanagari_normalization: DevanagariNormalizationConfig = Field(
        default_factory=DevanagariNormalizationConfig
    )
    mool: ReferenceMoolConfig = Field(default_factory=ReferenceMoolConfig)
    needs_manual_match: ReferenceNeedsManualMatchConfig = Field(
        default_factory=ReferenceNeedsManualMatchConfig
    )
    noise_phrases: ReferenceNoisePhraseConfig = Field(
        default_factory=ReferenceNoisePhraseConfig
    )
    section_keywords: ReferenceSectionKeywordsConfig = Field(
        default_factory=ReferenceSectionKeywordsConfig
    )
```

### 10.2 `ShastraRegistry` loading

`ShastraRegistry` is loaded once at config-load time and attached to `JainkoshConfig`
as a non-YAML field:

```python
class JainkoshConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ...all existing fields...

    # Not loaded from YAML — populated by load_config()
    shastra_registry: Optional[Any] = Field(default=None, exclude=True)
```

In `load_config()`:

```python
cfg = JainkoshConfig.model_validate(raw)

if cfg.reference.parse_strategy != "text_only" and cfg.reference.shastra_config_path:
    shastra_path = Path(cfg.reference.shastra_config_path)
    if not shastra_path.is_absolute():
        shastra_path = Path(__file__).parents[3] / shastra_path
    cfg.shastra_registry = ShastraRegistry.load(
        shastra_path, cfg.reference.devanagari_normalization
    )

return cfg
```

`shastra_registry` is `exclude=True` so it doesn't appear in `model_dump()` / JSON.

### 10.3 `refs.py` — `extract_refs_from_node`

Replace `raw_html` handling and update `Reference` construction:

```python
def extract_refs_from_node(
    node: Node,
    config: JainkoshConfig,
    *,
    inline: bool = False,
) -> list[Reference]:
    refs = []
    for gref in node.css("span.GRef"):
        full_text = extract_ref_text(gref, config)
        if not full_text:
            continue
        parts = _split_gref_text(full_text, config)
        for part in parts:
            resolution = _resolve_reference(part, config)
            inline_flag = inline if config.reference.annotate_inline_position else False
            refs.append(Reference(
                text=part,
                # raw_html NOT passed — field removed
                # parsed NOT passed — field removed
                inline_reference=inline_flag,
                **resolution,  # needs_manual_match, is_teeka, teeka_name, shastra_name, …
            ))
    return refs


def _resolve_reference(text: str, config: JainkoshConfig) -> dict:
    if (
        config.reference.parse_strategy == "text_only"
        or config.shastra_registry is None
    ):
        return {}  # all new fields keep their defaults (needs_manual_match=False, etc.)

    from .parse_reference import parse_reference_text
    result = parse_reference_text(text, config.shastra_registry, config.reference)
    return {
        # "parsed" key omitted — field removed from Reference model
        "needs_manual_match": result.needs_manual_match,
        "is_teeka": result.is_teeka,
        "teeka_name": result.teeka_name,
        "shastra_name": result.shastra_name,
        "match_method": result.match_method,
        "resolved_fields": result.resolved_fields,
    }
```

Remove the now-unused `_clean_raw_html` function from `refs.py`.

### 10.4 `jainkosh.yaml` changes

```yaml
reference:
  selector: "span.GRef"
  strip_inner_anchors: true
  parse_strategy: "structured"           # was "text_only"
  shastra_config_path: "parser_configs/_manual_configs/shastra.json"
  devanagari_normalization:
    enabled: true
    substitutions:
      - {from: "ण्ड", to: "ंड"}
      - {from: "ण्ठ", to: "ंठ"}
      - {from: "ञ्च", to: "ंच"}
      - {from: "ञ्ज", to: "ंज"}
      - {from: "न्त", to: "ंत"}
      - {from: "न्द", to: "ंद"}
      - {from: "म्ब", to: "ंब"}
      - {from: "न्व", to: "ंव"}
  mool:
    keywords: ["मूल"]
    exceptions: ["मूलाचार"]
  needs_manual_match:
    on_extra_groups: true
    on_missing_fields: false             # changed: partial citations are valid
  noise_phrases:                         # NEW — whole-phrase removals before keyword strip
    enabled: true
    phrases:
      - "मूल गाथा या टीका"
  section_keywords:                      # NEW — word-boundary keyword removals
    enabled: true
    keywords:
      - गाथा
      - श्लोक
      - पंक्ति
      - कलश
      - अधिकार
      - अध्याय
      - सर्ग
      - परिच्छेद
      - प्रकरण
      - खण्ड
      - भाग
      - पुस्तक
  # existing fields stay unchanged:
  raw_html:
    collapse_whitespace: true
  semicolon_split:
    enabled: true
    split_re: '(?<=\))\s*;\s*(?=\()'
  annotate_inline_position: true
```

---

## 11. File layout additions

```
workers/ingestion/jainkosh/
├── parse_reference.py          # NEW — all reference resolution logic
│   ├── FormatField, FormatGroup (dataclasses)
│   ├── ShastraEntry, ShastraRegistry
│   ├── parse_format_string(fmt) -> list[FormatGroup]
│   ├── _normalise(text, config) -> str            # NFC + substitutions + space removal
│   ├── _strip_parens(text) -> str                 # NEW
│   ├── _strip_noise_phrases(text, config) -> str  # NEW
│   ├── _strip_section_keywords(text, config) -> str # NEW
│   ├── _collapse_ws(text) -> str                  # NEW
│   ├── _preprocess_text(text, config) -> str      # NEW — orchestrates steps 1–4
│   ├── split_name_and_numeric(text) -> (str, str)
│   ├── _strip_mool(name, config) -> str
│   ├── match_shastra(name_raw, registry, config) -> (entry, method, is_teeka, teeka_name)
│   ├── resolve_fields(numeric_clean, groups, config) -> (list[ResolvedField], bool)
│   └── parse_reference_text(text, registry, config) -> _ResolutionResult
└── tests/unit/
    ├── test_reference_name_extraction.py   # NEW
    ├── test_shastra_registry.py            # NEW
    ├── test_reference_format_parser.py     # NEW
    ├── test_reference_value_resolver.py    # NEW
    ├── test_parse_reference_integration.py # NEW
    └── test_reference_preprocessor.py      # NEW
```

---

## 12. Test plan

### 12.0 `test_reference_preprocessor.py` — NEW

Test `_preprocess_text()` end-to-end and each step individually:

**`_strip_parens`**:

| Input | Expected |
|-------|----------|
| `"( ज्ञानसार श्लोक 29)"` | `" ज्ञानसार श्लोक 29"` |
| `"(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)"` | `"द्रव्यसंग्रह / मूल गाथा या टीका 14/46"` |
| `"धवला 1/5"` | `"धवला 1/5"` |

**`_strip_noise_phrases`** (with phrases=`["मूल गाथा या टीका"]`):

| Input | Expected |
|-------|----------|
| `"द्रव्यसंग्रह / मूल गाथा या टीका 14/46"` | `"द्रव्यसंग्रह /  14/46"` |
| `"समाधिशतक / मूल या टीका गाथा 4"` | `"समाधिशतक / मूल या टीका गाथा 4"` (unchanged) |

**`_strip_section_keywords`** (with default keyword list):

| Input | Expected |
|-------|----------|
| `"धवला पुस्तक 13/5"` | `"धवला 13/5"` |
| `"ज्ञानार्णव अधिकार 32/5/317"` | `"ज्ञानार्णव 32/5/317"` |
| `"ज्ञानसार श्लोक 29"` | `"ज्ञानसार 29"` |
| `"समयसार / आत्मख्याति गाथा 8"` | `"समयसार / आत्मख्याति 8"` |
| `"गाथा 5"` | `"गाथा 5"` (no leading space — not removed) |

**`_preprocess_text`** (full pipeline):

| Input | Expected cleaned text |
|-------|-----------------------|
| `"( ज्ञानार्णव अधिकार 32/5/317)"` | `"ज्ञानार्णव 32/5/317"` |
| `"(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)"` | `"द्रव्यसंग्रह / 14/46"` |
| `"धवला पुस्तक 13/5,5,50/282/9"` | `"धवला 13/5,5,50/282/9"` |
| `"समयसार / आत्मख्याति गाथा 8"` | `"समयसार / आत्मख्याति 8"` |
| `"(परमात्मप्रकाश / मूल या टीका अधिकार 1/11)"` | `"परमात्मप्रकाश / मूल या टीका 1/11"` |

### 12.1 `test_reference_name_extraction.py`

Test `split_name_and_numeric()` parametrically (inputs are post-preprocess):

| Input | Expected name_raw | Expected numeric_raw |
|-------|--------------------|----------------------|
| `"धवला 1/1,1,1/84/1"` | `"धवला"` | `"1/1,1,1/84/1"` |
| `"धवला1/84"` | `"धवला"` | `"1/84"` |
| `"पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12"` | `"पंचास्तिकाय / तात्पर्यवृत्ति"` | `"16/35/12"` |
| `"कषायपाहुड़ 1/1,13-14/ §181/217/1"` | `"कषायपाहुड़"` | `"1/1,13-14/§181/217/1"` |
| `"धवला"` | `"धवला"` | `""` |
| `"प्रवचनसार मूल 1/5"` | `"प्रवचनसार मूल"` | `"1/5"` |

### 12.2 `test_shastra_registry.py`

Build a minimal in-memory fixture with 3–5 entries. Test:
- Exact `shastra_name` match returns `("shastra_name", entry)`.
- `alternate_name` match (e.g. `"गोम्मटसार जीवकांड/मूल"` → matches `alternate_name`
  `"गोम्मटसार जीवकांड/मूल"` after NFC/substitution normalisation).
- `short_form` match (`"ध"` → धवला).
- Unknown name → `(None, None)`.
- Substitution: `"काण्ड"` in registry, query `"कांड"` — both normalise to same key → match.

### 12.3 `test_reference_format_parser.py`

Test `parse_format_string()`:

| Input | Expected output (summarised) |
|-------|------------------------------|
| `"श्लोक"` | 1 group, 1 field `श्लोक`, no sep |
| `"पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा"` | 4 groups; group[1].fields = 3; sep=`,` |
| `"पुस्तक/§प्रकरण/पृष्ठ"` | group[1].is_optional=True |
| `"मुख्याधिकार-प्रकरण/श्लोक"` | group[0].fields=2, sep=`-` |
| `"पुस्तक,भाग/§प्रकरण/पृष्ठ/पंक्ति"` | 4 groups; group[0].sep=`,`; group[1].optional |
| `""` | empty list |

### 12.4 `test_reference_value_resolver.py`

Test `resolve_fields()` directly. Note: this function returns raw `(resolved_fields,
needs_manual)` — the caller (`parse_reference_text`) is responsible for clearing
`resolved_fields` when `needs_manual=True`. These tests assert the raw output.

| Format | Value | on_extra | on_missing | Expected resolved_fields (raw) | needs_manual |
|--------|-------|----------|------------|-------------------------------|--------------|
| `पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा` | `1/1,1,1/84/1` | T | F | 6 fields, all int | False |
| `पुस्तक/§प्रकरण/पृष्ठ` | `1/§5/10` | T | F | पुस्तक=1, प्रकरण=5, पृष्ठ=10 | False |
| `पुस्तक/§प्रकरण/पृष्ठ` | `1/10` | T | F | पुस्तक=1, पृष्ठ=10 (optional absent) | False |
| `अधिकार/श्लोक` | `1/2/3/extra` | T | F | [अधिकार=1, श्लोक=2] + leftover | True |
| `अधिकार/श्लोक/पृष्ठ` | `1` | T | F | [अधिकार=1] (missing not flagged) | False |
| `अधिकार/श्लोक/पृष्ठ` | `1` | T | T | [अधिकार=1] (missing flagged) | True |
| `पुस्तक,भाग/पृष्ठ` | `1,13-14/84` | T | F | पुस्तक=1, भाग="13-14" (range preserved), पृष्ठ=84 | False |
| `मुख्याधिकार-प्रकरण/श्लोक` | `3-7/5` | T | F | मुख्याधिकार=3, प्रकरण=7, श्लोक=5 | False |

### 12.5 `test_parse_reference_integration.py`

End-to-end tests using a fixture registry built from a small slice of `shastra.json`
(or a test-only fixture JSON — do not load the full production file in unit tests).
These use the full `parse_reference_text` pipeline including pre-processing.

| Input text | Expected outcome |
|------------|-----------------|
| `"धवला 1/1,1,1/84/1"` | needs_manual=False, shastra_name="धवला", 6 resolved_fields |
| `"प्रवचनसार / तत्त्वप्रदीपिका 1/5/10"` | needs_manual=False, is_teeka=True, teeka_name="तत्त्वप्रदीपिका" |
| `"पंचास्तिकाय / तात्पर्यवृत्ति/16/35/12"` | needs_manual=False, is_teeka=False (full combined entry matches) |
| `"प्रवचनसार मूल 1/5"` | needs_manual=False, shastra_name="प्रवचनसार" (मूल stripped) |
| `"मूलाचार 15"` | needs_manual=False, shastra_name="मूलाचार" (no stripping — exception) |
| `"अज्ञात ग्रन्थ 1/5"` | needs_manual=True, shastra_name=None, resolved_fields=[] |
| `"गोम्मटसार जीवकांड/मूल 5/10"` (anusvar form) | needs_manual=False, shastra_name="गोम्मटसार जीवकाण्ड/मूल" |
| `"ध 1/1,1,1/84/1"` (short_form) | needs_manual=False, match_method="short_form" |
| `"पंचास्तिकाय/10"` | needs_manual=False, shastra_name="पंचास्तिकाय", resolved_fields=[गाथा=10] |
| `"सर्वार्थसिद्धि/1/5/17/5"` (extra group) | needs_manual=True, shastra_name="सर्वार्थसिद्धि", resolved_fields=[] |
| `"राजवार्तिक/5/2/2/436/26"` (extra group) | needs_manual=True, shastra_name="राजवार्तिक", resolved_fields=[] |
| `"धवला पुस्तक 13/5,5,50/282/9"` | needs_manual=False, shastra_name="धवला", 6 resolved_fields |
| `"( ज्ञानार्णव अधिकार 32/5/317)"` | needs_manual=False, shastra_name="ज्ञानार्णव", 3 resolved_fields |
| `"( ज्ञानसार श्लोक 29)"` | needs_manual=False, shastra_name="ज्ञानसार", resolved_fields=[श्लोक=29] |
| `"तत्त्वार्थसूत्र 1/5"` (no space) | needs_manual=False, shastra_name="तत्त्वार्थ सूत्र" |
| `"समयसार / आत्मख्याति गाथा 8"` | needs_manual=False, shastra_name="समयसार/आत्मख्याति" (or is_teeka variant), resolved_fields=[गाथा=8] |
| `"(द्रव्यसंग्रह / मूल गाथा या टीका 14/46)"` | needs_manual=False, shastra_name="द्रव्यसंग्रह", resolved_fields=[गाथा=14, पृष्ठ=46] |

### 12.6 Existing test impact

All existing tests that assert on `Reference` objects must be updated:
- Remove `raw_html` assertions.
- Remove `parsed` assertions entirely (field deleted).
- For references that previously had `needs_manual_match=True` due to missing fields
  (e.g. `"पंचास्तिकाय/10"`), update expected output: `needs_manual_match=False`,
  `resolved_fields` populated with the fields that were provided.
- For references with extra groups (e.g. `"सर्वार्थसिद्धि/1/5/17/5"`), confirm
  `needs_manual_match=True` and `resolved_fields=[]`.
- No new fields need asserting in existing tests unless a test specifically exercises GRefs
  with structured parsing (in which case extend the test fixture).

---

## 13. Golden regeneration

The `Reference` model changes (`raw_html` removed, `parsed` removed, new pre-processing
behaviour, `resolved_fields=[]` invariant) make all three golden JSON files stale.
After implementation:

1. Set `parse_strategy: "text_only"` temporarily to keep goldens stable
   while other changes are verified → then switch to `"structured"` and
   regenerate all three.
2. Run `python -m workers.ingestion.jainkosh.cli parse <fixture> --frozen-time 2026-05-02T00:00:00Z --out tests/golden/<name>.json` for all three.
3. Manually inspect every `references` array in the new goldens:
   - `raw_html` absent on every Reference ✓
   - `parsed` key absent on every Reference ✓
   - For references with a matched shastra: `shastra_name` populated ✓
   - For unmatched or extra-group references: `needs_manual_match: true`, `resolved_fields: []` ✓
   - Previously-failing references (parens, section keywords, noise phrases): now resolved ✓
4. Commit goldens only after human review.

---

## 14. `jainkosh.yaml` schema (`jainkosh.schema.json`) additions

The JSON Schema for `jainkosh.yaml` must be extended to permit the new `reference` sub-keys.
Specifically, add to the `reference` object in the schema:

```json
"shastra_config_path": {"type": "string"},
"devanagari_normalization": {
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean"},
    "substitutions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "from": {"type": "string"},
          "to": {"type": "string"}
        },
        "required": ["from", "to"],
        "additionalProperties": false
      }
    }
  }
},
"mool": {
  "type": "object",
  "properties": {
    "keywords": {"type": "array", "items": {"type": "string"}},
    "exceptions": {"type": "array", "items": {"type": "string"}}
  }
},
"needs_manual_match": {
  "type": "object",
  "properties": {
    "on_extra_groups": {"type": "boolean"},
    "on_missing_fields": {"type": "boolean"}
  }
},
"noise_phrases": {
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean"},
    "phrases": {"type": "array", "items": {"type": "string"}}
  },
  "additionalProperties": false
},
"section_keywords": {
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean"},
    "keywords": {"type": "array", "items": {"type": "string"}}
  },
  "additionalProperties": false
}
```

---

## 14A. Amendments — review round 2

This section supersedes the corresponding parts of §§1–13 wherever it contradicts
them. Implementer must read this *first*; older sections remain for context.

### 14A.1 Skip puraankosh sections entirely

Reference resolution must NOT run on definitions inside `section_kind == "puraankosh"`.
A separate `shastra.json` (purankosh-specific) will be wired up later. For now:

- In `refs.py::extract_refs_from_node` (or its caller in `parse_section.py` /
  `parse_definitions.py`), thread the current `section_kind` through and short-circuit
  to `parse_strategy="text_only"` behaviour when `section_kind == "puraankosh"`.
- Concretely: when `section_kind == "puraankosh"`, build each `Reference` with only
  `text` and `inline_reference` populated; never call `parse_reference_text`.
- The simplest implementation is a new parameter on `extract_refs_from_node`:

  ```python
  def extract_refs_from_node(
      node: Node,
      config: JainkoshConfig,
      *,
      inline: bool = False,
      section_kind: SectionKind = "siddhantkosh",
  ) -> list[Reference]: ...
  ```

  and inside `_resolve_reference`:

  ```python
  if section_kind == "puraankosh":
      return {}
  ```

  Update all call sites in `parse_definitions.py` / `parse_section.py` to pass the
  section kind through. (`parse_keyword.py` already classifies sections; reuse.)

- Add a `puraankosh_skips_resolution` golden assertion to
  `test_parse_reference_integration.py` once a purankosh fixture is available.

### 14A.2 Strict format-group count matching

Change `ReferenceNeedsManualMatchConfig.on_missing_fields` default back to **`True`**.
The justification for `false` (partial citations are valid) is overruled — partial
matches were resolving citations the curator did not intend. New rule:

- Let `R` = number of required (non-`§`) format groups.
- Let `O` = number of optional (`§`) format groups.
- Let `V` = number of value groups (after splitting `numeric_clean` on `/`).
- Acceptable: `V == R` (no optionals) or `R <= V <= R + O` (with optionals — verify
  via leading-`§` detection per §8.1).
- Otherwise → `needs_manual_match = True`, `resolved_fields = []`.

Examples that must now be rejected (golden has them currently mis-resolved):

| Text | Format | V | R | Outcome |
|------|--------|---|---|---------|
| `( आलापपद्धति/6 )` | `अधिकार/सूत्र/पृष्ठ` | 1 | 3 | needs_manual |
| `( धवला 15/33/9 )` | `पुस्तक/खण्ड,भाग,सूत्र/पृष्ठ/गाथा` | 3 | 4 | needs_manual |
| `पंचास्तिकाय/10` | `गाथा/पृष्ठ` | 1 | 2 | needs_manual (was previously `गाथा=10`) |

Update §8.3 table, §10.1 default, §10.4 yaml, §12.4 / §12.5 fixtures, and §13
golden expectations. The previously-documented "valid partial citation" case in §2.4
("Partial numeric match — pंchastikai/10") is REMOVED.

### 14A.3 `alternate_name` is a list

Both the `shastra.json` schema and `ShastraEntry` change.

```python
class ShastraEntry:
    shastra_name: str
    alternate_names: list[str]      # was: alternate_name: Optional[str]
    short_form: str
    format_str: str
    format_groups: list[FormatGroup]
```

Loader (§3.1): accept either string (legacy) or list:

```python
raw_alt = item.get("alternate_name", []) or item.get("alternate_names", [])
if isinstance(raw_alt, str):
    raw_alt = [raw_alt]
entry.alternate_names = [a for a in raw_alt if a]
for alt in entry.alternate_names:
    registry._by_alternate[_normalise(alt, norm_config)] = entry
```

Lookup priority unchanged (§3.2): `shastra_name` → `alternate_name` (any) → `short_form`.
A single hit on any element of `alternate_names` returns `match_method="alternate_name"`.

When two entries claim the same alternate (collision), the **first** loaded wins;
log a warning at registry load time.

`shastra.json` should be progressively migrated; the existing single-string form must
keep working until the file is fully updated.

### 14A.4 Range / list value expansion → multiple `Reference` objects

When any `ResolvedField.value` contains a numeric range (`a-b`) or numeric list
(`a,b,c`) or a combination (`a-b,c`), expand the parent `Reference` into multiple
`Reference` objects — one per concrete numeric value. All other fields stay identical
across the expansions; `text` is preserved as the original (un-split) string.

Specification:

1. Expansion happens **after** field resolution, in a new helper
   `_expand_resolved_fields(resolved_fields) -> list[list[ResolvedField]]`,
   called by `parse_reference_text` when `needs_manual_match=False`.
2. `parse_reference_text` returns `list[_ResolutionResult]` instead of a single
   result. `refs.py` constructs one `Reference` per result.
3. Expansion rules per field value (string form):
   - `"95-96"` → `[95, 96]` (inclusive range; both ends must be ints; if step
     would yield > 50 values, abort expansion → `needs_manual_match=True`).
   - `"8,86"` → `[8, 86]`.
   - `"1-3,39"` → `[1, 2, 3, 39]`.
   - Pure int (already coerced) → `[value]`.
   - Non-numeric string remaining after digit-strip (§14A.5) → no expansion;
     leave field as-is (this should not happen post-strip, but guard anyway).
4. If multiple fields each expand, take the **cartesian product** (e.g.
   `गाथा="1-2"` × `पृष्ठ="5,6"` → 4 references). Cap total expansion at 50;
   if exceeded → `needs_manual_match=True`, no expansion, `resolved_fields=[]`.

Examples (from `द्रव्य.json`):

| Original `resolved_fields` | After expansion |
|----------------------------|-----------------|
| `[{गाथा: "95-96"}]` | 2 refs: `[गाथा=95]`, `[गाथा=96]` |
| `[{श्लोक: "8,86"}]` | 2 refs: `[श्लोक=8]`, `[श्लोक=86]` |
| `[{सूत्र: "1-3,39"}]` | 4 refs: `[सूत्र=1]`, `[सूत्र=2]`, `[सूत्र=3]`, `[सूत्र=39]` |

Helper grammar:

```python
_RANGE_LIST_RE = re.compile(r"^\s*(\d+(?:-\d+)?)(?:\s*,\s*(\d+(?:-\d+)?))*\s*$")

def _expand_value(s: str) -> list[int] | None:
    if not _RANGE_LIST_RE.match(s):
        return None
    out: list[int] = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = (int(x) for x in chunk.split("-", 1))
            if b < a or b - a > 50:
                return None
            out.extend(range(a, b + 1))
        else:
            out.append(int(chunk))
    return out
```

Add unit tests in `test_reference_value_resolver.py` and integration tests covering
all three example shapes above plus the cartesian-product case.

### 14A.5 Numeric-only `resolved_fields.value`

`ResolvedField.value` must always be `int` for resolved references (the
`Union[int, str]` typing in §2.1 stays for the model, but post-resolution any
non-int value is a bug).

Coercion change in `_coerce_value` (§8.2):

```python
_LEADING_DIGITS_RE = re.compile(r"^\s*(\d+)")

def _coerce_value(s: str) -> Optional[int]:
    """Return int if a leading digit run can be extracted, else None."""
    m = _LEADING_DIGITS_RE.match(s)
    return int(m.group(1)) if m else None
```

In `_assign_group`: if `_coerce_value` returns `None` for a part, treat it as a
mismatch → `needs_manual_match=True` (subject to `on_missing_fields`).

For range/list strings (`"95-96"`, `"1-3,39"`), `_assign_group` keeps the original
string and §14A.4's `_expand_value` runs over it. Detect range/list with
`_RANGE_LIST_RE` *before* `_coerce_value` so they aren't lossy-coerced to a single int.

Examples this fixes:

| Raw value part | Old coerced | New coerced |
|----------------|-------------|-------------|
| `"309परउद्धृत"` | `"309परउद्धृत"` (str) | `309` (int) |
| `"42abc"` | `"42abc"` (str) | `42` (int) |
| `"abc"` | `"abc"` (str) | `None` → mismatch → needs_manual |
| `"95-96"` | `"95-96"` (str, no expansion) | kept as `"95-96"` for §14A.4 expansion |

### 14A.6 Punctuation cleanup + mool-as-teeka fix

Two related issues, one solution.

(a) **Strip comma punctuation** from the working text during pre-processing
(§4A). Add step 1.5:

```python
def _strip_punct(text: str) -> str:
    # Punctuation that never carries semantic meaning in citations.
    return text.replace(",", " ").replace("।", " ").replace("॥", " ")
```

Run this between `_strip_parens` and `_strip_noise_phrases`. Update §4A.1
pipeline diagram and §4A.6 helper:

```
raw → strip_parens → strip_punct → strip_noise → strip_keywords → collapse_ws
```

(b) **Mool keyword wrongly retained as teeka.** For input
`परमात्मप्रकाश/ मूल/2/27`, the current pipeline:

1. `name_raw = "परमात्मप्रकाश/ मूल"`, `numeric_raw = "2/27"`.
2. `_strip_mool` strips ` मूल` → `परमात्मप्रकाश/`, lookup fails (trailing slash).
3. Teeka split sees `मूल` as candidate teeka → `is_teeka=True`, `teeka_name="मूल"`.

Two fixes, both required:

- In `_strip_mool` (§6.2), trim trailing `/` and whitespace **after** stripping the
  keyword, so `परमात्मप्रकाश/` becomes `परमात्मप्रकाश` and the §6.1 step-2 lookup
  succeeds:

  ```python
  return name[: -(1 + len(kw))].rstrip(" /").strip()
  ```

- In `match_shastra` (§6.1) step 3, after splitting on the first `/`, check whether
  `teeka_candidate` (after NFC) is in `config.mool.keywords` *or* its first
  whitespace-separated token is. If so, do **not** treat it as a teeka — instead
  retry lookup with `base` only and `is_teeka=False`. Pseudocode:

  ```python
  first_token = teeka_candidate.split()[0] if teeka_candidate else ""
  is_mool_marker = (
      teeka_candidate in config.mool.keywords
      or first_token in config.mool.keywords
  )
  if is_mool_marker:
      entry, method = registry.lookup(norm(base))
      if entry:
          return entry, method, False, ""
      # else fall through to no-match
  else:
      # existing teeka path
      ...
  ```

Either fix on its own would resolve the case; both are needed because (a) covers
the common mool-after-slash case and (b) covers cases where the slash form is
also in the registry as `परमात्मप्रकाश/मूल` or where the trailing slash heuristic
is brittle.

### 14A.7 Normalization: short/long `i` (ि ↔ ी)

`वसुनन्दि श्रावकाचार` (registry) and `वसुनंदी श्रावकाचार` (cited form) currently
fail to match. After existing substitutions, the pair reduces to:

- `वसुनंदि श्रावकाचार` (after `न्द → ंद`)
- `वसुनंदी श्रावकाचार`

The remaining diff is `दि` vs `दी` (matra `ि` vs `ी`). Add a normalization step
that collapses both short and long `i` matras to a single canonical form **for
matching only**:

```yaml
reference:
  devanagari_normalization:
    substitutions:
      # ...existing...
      - {from: "ी", to: "ि"}     # collapse long-i to short-i (matching only)
```

Caveats:

- This is aggressive and will create false positives in theory (e.g. `मीन` and
  `मिन` would normalise to the same key). In the shastra registry this is
  acceptable — names are long enough that collisions are vanishingly unlikely,
  and the alternative is per-entry alternate_names. If a collision is observed,
  remove this rule and add explicit `alternate_names` instead.
- Apply *after* the conjunct-substitutions (table is order-sensitive — already
  documented in §4.3).
- Do NOT also collapse `ु`/`ू`, `े`/`ै`, etc. unless a concrete miss is observed;
  add per-pair as needed, with this matter documented.

Add a unit test in `test_shastra_registry.py`:

```python
("वसुनन्दि श्रावकाचार", "वसुनंदी श्रावकाचार") -> match (alternate or primary)
```

### 14A.8 Strip trailing non-numeric tokens from numeric portion

For input `धवला 3/1,2,1/2/ पंक्ति नं.`, after current pre-processing:

- Step 3 strips `पंक्ति` (whitespace-bounded keyword) → `धवला 3/1,2,1/2/  नं.`
- Step 4 collapses → `धवला 3/1,2,1/2/ नं.`
- `split_name_and_numeric` → `numeric_raw = "3/1,2,1/2/ नं."`
- `numeric_clean = "3/1,2,1/2/नं."` → 5 groups → fails group-count check.

Fix: after `split_name_and_numeric`, run a trailing-noise strip on `numeric_raw`
before the space-removal step:

```python
def _strip_trailing_non_numeric(numeric: str) -> str:
    """
    Drop trailing slash-segments that contain no digits.
    Example: '3/1,2,1/2/ नं.' -> '3/1,2,1/2'
    """
    parts = numeric.split("/")
    while parts and not re.search(r"\d", parts[-1]):
        parts.pop()
    return "/".join(parts)
```

Call site (insert before `numeric_clean = numeric_raw.replace(" ", "")` in §9):

```python
numeric_raw = _strip_trailing_non_numeric(numeric_raw)
numeric_clean = numeric_raw.replace(" ", "")
```

This also handles citations that end with stray text accidentally not stripped by
section_keywords (e.g. abbreviated headers like `नं.`, `पृ.`).

Add tests in `test_reference_preprocessor.py` and an integration case for
`धवला 3/1,2,1/2/ पंक्ति नं.` → `धवला 3/1,2,1/2` → fully resolved (4 groups,
matches format).

### 14A.9 Updated Definition of Done deltas (additive to §15)

- [ ] `extract_refs_from_node` skips resolution when `section_kind == "puraankosh"`.
- [ ] `on_missing_fields` default flipped back to `True`; group-count strictness enforced.
- [ ] `ShastraEntry.alternate_names: list[str]` (loader accepts string-or-list legacy form).
- [ ] `parse_reference_text` returns `list[_ResolutionResult]`; range/list values expand into multiple `Reference` objects (cap 50, fall back to needs_manual on overflow).
- [ ] `_coerce_value` extracts leading digits → `int`; non-numeric → mismatch.
- [ ] Pre-processing pipeline includes `_strip_punct` (commas/dandas) between paren-strip and noise-strip.
- [ ] `_strip_mool` trims trailing `/` and whitespace after keyword removal.
- [ ] `match_shastra` step-3 teeka path detects mool keywords and retries base-only lookup instead.
- [ ] `devanagari_normalization.substitutions` includes `{from: "ी", to: "ि"}`; `वसुनन्दि ↔ वसुनंदी` test passes.
- [ ] `_strip_trailing_non_numeric` runs on `numeric_raw` after `split_name_and_numeric`.
- [ ] All goldens regenerated; `द्रव्य.json` lines 688, 736, 915, 979, 1364, 2122, 2717, 3246 (cited examples) match the new expected shapes documented above.
- [ ] `parser_rules_version` bumped to `"jainkosh.rules/1.9.0"`.

---

## 15. Definition of Done

- [ ] `parse_reference.py` exists; all functions have type hints and no external I/O.
- [ ] `ShastraRegistry.load()` reads `shastra.json`, normalises keys (NFC + substitutions +
      space removal), pre-parses all format strings.
- [ ] `_normalise()` strips all spaces after slash-normalisation (space-agnostic matching).
- [ ] `Reference.raw_html` field is removed; `ParsedReference` class is removed.
- [ ] `Reference.parsed` field is **removed**; new fields (`is_teeka`, `teeka_name`,
      `shastra_name`, `match_method`, `needs_manual_match`, `resolved_fields`) are present
      with correct defaults.
- [ ] **Invariant enforced**: `needs_manual_match=True` → `resolved_fields=[]` always.
- [ ] `ResolvedField` model exists with `field: str` and `value: Union[int, str]`.
- [ ] Pre-processing pipeline implemented: paren removal → noise phrase removal →
      section keyword removal → whitespace collapse.
- [ ] `ReferenceNoisePhraseConfig` and `ReferenceSectionKeywordsConfig` added to `config.py`.
- [ ] `ReferenceNeedsManualMatchConfig.on_missing_fields` default is `False`.
- [ ] `refs.py` no longer passes `raw_html` to `Reference`; calls `_resolve_reference` when
      `parse_strategy != "text_only"`.
- [ ] `config.py` has all new config classes; `JainkoshConfig.shastra_registry` attached at load.
- [ ] `jainkosh.yaml` has `parse_strategy: "structured"`, `on_missing_fields: false`,
      `noise_phrases`, and `section_keywords` blocks present.
- [ ] `jainkosh.schema.json` updated to permit `noise_phrases` and `section_keywords` keys.
- [ ] All 6 new test files pass (including `test_reference_preprocessor.py`).
- [ ] All existing unit tests updated: `raw_html` removed, `parsed` field assertions deleted,
      `needs_manual_match` and `resolved_fields` expectations corrected.
- [ ] All three goldens regenerated and human-reviewed.
- [ ] Golden tests are byte-identical idempotent after regeneration.
- [ ] `config_schema` unit test still passes.
- [ ] `parser_rules_version` bumped to `"jainkosh.rules/1.8.0"` in YAML and goldens.
- [ ] No changes to HTML parsing, block extraction, or envelope logic.
