# 01 — Parser: nikkyjain (per-file HTML format)

Parses the **per-file HTML** layout used by `nikkyjain.github.io/jainDataBase/shastra/`.
Each HTML file is one or more consecutive gathas.
The `myItem.js` file in the same directory is the authoritative gatha index.

This parser is **shastra-agnostic**: all shastra-specific values (paths, selectors, teeka labels)
are driven by a YAML config file. Samaysar is the reference implementation; other shastras use
the same code with their own config.

---

## 1. Source Layout

```
html/
├── myItem.js                # gatha index (JS) — source of truth for gatha numbers
├── 0000_<title>.html        # preamble page (add to skip_files in config)
├── 001.html                 # one gatha
├── 009-010.html             # two gathas on one page
├── 011.html                 # NOT in A's navbar → J-only kalash page
├── 012.html                 # NOT in A's navbar → J-only kalash page
├── 013.html                 # A's gatha 011  (html filename ≠ gatha number!)
├── 025-026-027.html         # three gathas on one page
...
```

`NIKKYJAIN_LOCAL_PATH` env-var points to the root of the local clone.

---

## 2. Parser Config (`parser_configs/nj/{shastra_natural_key}.yaml`)

All shastra-specific values live here. The parser reads this file and never hard-codes
any shastra identity.

### 2.1 Config Schema

```yaml
version: 1.0.0
source: nj                         # publisher identifier
shastra:
  natural_key: <str>               # e.g. "samaysar"
  title_hi: <str>
  author:
    natural_key: <str>             # e.g. "kundkundacharya"
    display_name_hi: <str>
    kind: acharya | poet | ...
  teekas:
    - natural_key: <str>           # e.g. "samaysar:amritchandra"
      teekakar_natural_key: <str>  # e.g. "amritchandracharya"
      teekakar_display_name_hi: <str>
      publication_natural_key: <str>  # e.g. "samaysar:amritchandra:nikkyjain"
      publisher_id: nikkyjain
      role: primary | secondary    # primary = A-teeka with kalashes; secondary = J-teeka

input:
  html_dir: "<NIKKYJAIN_LOCAL_PATH>/{path-to-shastra}/html"
  my_item_js: "myItem.js"
  encoding: utf-8
  skip_files:
    - "<preamble>.html"

selectors:
  primary_teeka_select: "select#select-native-0"   # A's gatha index
  secondary_teeka_select: "select#select-native-1" # J's gatha index (optional)
  gatha_title_div: "div.title[id^='gatha-']"
  gatha_heading_link: "div.title > span > a"
  gatha_prakrit: "div.gatha"
  gatha_sanskrit: "div.gathaS"
  gatha_hindi_chhand_body: "div.gadya"
  anyavartha_para: "div.paragraph"
  anyavartha_marker: "अन्वयार्थ"
  teeka0_div: "div#teeka0"
  teeka1_div: "div#teeka1"
  steeka0_div: "div.steeka#steeka0"
  steeka1_div: "div.steeka#steeka1"
  primary_teeka_label: "अमृतचंद्राचार्य"       # first-label text inside teeka0
  secondary_teeka_label: "जयसेनाचार्य"          # first-label text inside teeka1
  kalash_type_marker_color: "DarkSlateGray"
  kalash_word_meaning_color: "maroon"
  gatha_word_meaning_color: "darkRed"
  teeka_separator: "hr.type_7"
  gatha_teeka_start_markers:
    - "अथ सूत्रावतार"
    - "तत्र तावत्समय"
  gatha_teeka_bhaavarth_start_markers:
    - "अब सूत्र प्रकट होता है"
    - "अब यहाँ"
    - "अब शुद्ध परमात्म तत्त्व"

parsing:
  strip_zwj: false
  notes_teeka_index: 2              # skip teeka2 (notes div, not a real teeka)
```

### 2.2 Example: Samaysar Config (`parser_configs/nj/samaysar.yaml`)

```yaml
version: 1.0.0
source: nj
shastra:
  natural_key: samaysar
  title_hi: समयसार
  author:
    natural_key: kundkundacharya
    display_name_hi: कुन्दकुन्दाचार्य
    kind: acharya
  teekas:
    - natural_key: samaysar:amritchandra
      teekakar_natural_key: amritchandracharya
      teekakar_display_name_hi: अमृतचंद्राचार्य
      publication_natural_key: samaysar:amritchandra:nikkyjain
      publisher_id: nikkyjain
      role: primary
    - natural_key: samaysar:jaysenacharya
      teekakar_natural_key: jaysenacharya
      teekakar_display_name_hi: जयसेनाचार्य
      publication_natural_key: samaysar:jaysenacharya:nikkyjain
      publisher_id: nikkyjain
      role: secondary
input:
  html_dir: "{NIKKYJAIN_LOCAL_PATH}/jainDataBase/shastra/01_द्रव्यानुयोग/01_समयसार--कुन्दकुन्दाचार्य/html"
  my_item_js: "myItem.js"
  encoding: utf-8
  skip_files:
    - "0000_शास्त्र-मंगलाचरण.html"
selectors:
  primary_teeka_select: "select#select-native-0"
  secondary_teeka_select: "select#select-native-1"
  gatha_title_div: "div.title[id^='gatha-']"
  gatha_heading_link: "div.title > span > a"
  gatha_prakrit: "div.gatha"
  gatha_sanskrit: "div.gathaS"
  gatha_hindi_chhand_body: "div.gadya"
  anyavartha_para: "div.paragraph"
  anyavartha_marker: "अन्वयार्थ"
  teeka0_div: "div#teeka0"
  teeka1_div: "div#teeka1"
  steeka0_div: "div.steeka#steeka0"
  steeka1_div: "div.steeka#steeka1"
  primary_teeka_label: "अमृतचंद्राचार्य"
  secondary_teeka_label: "जयसेनाचार्य"
  kalash_type_marker_color: "DarkSlateGray"
  kalash_word_meaning_color: "maroon"
  gatha_word_meaning_color: "darkRed"
  teeka_separator: "hr.type_7"
  gatha_teeka_start_markers:
    - "अथ सूत्रावतार"
    - "तत्र तावत्समय"
  gatha_teeka_bhaavarth_start_markers:
    - "अब सूत्र प्रकट होता है"
    - "अब यहाँ"
    - "अब शुद्ध परमात्म तत्त्व"
parsing:
  strip_zwj: false
  notes_teeka_index: 2
```

---

## 3. Step 1 — Parse `myItem.js`

`myItem.js` is JavaScript, not HTML. Use **regex-based extraction** (no JS engine needed).

### 3.1 Extract Primary Teeka Index (`select#select-native-0`)

Regex to match each option line:
```
\$optgrp\.append\("<option value='([^']+)'><b>([^<]+)</b>\s*-\s*[^\x{FEFF}"]*([^"]+)"
```

Pattern per `optgrp.append(...)` line:
- Group 1 → `html_filename` e.g. `"025-026-027.html"`
- Group 2 → `gatha_number` e.g. `"020-021-022"` (keep as-is; do not strip leading zeros)
- Group 3 → `heading_hi` e.g. `"अप्रतिबुद्ध - पर पदार्थ में अहंकार / ममकार"`

The `optgroup label=` line just before each set of appends gives the `adhikaar_hi`:
```
\$optgrp=\$\('<optgroup label="[^\x{FEFF}"]*([^"]+)">'
```

Build map: `primary_index: dict[html_filename, GathaIndexEntry]`

```python
@dataclass
class GathaIndexEntry:
    html_filename: str   # "025-026-027.html"
    gatha_number: str    # "020-021-022"
    heading_hi: str      # "अप्रतिबुद्ध - पर पदार्थ में अहंकार / ममकार"
    adhikaar_hi: str     # "जीव अधिकार"
```

### 3.2 Extract Secondary Teeka Index (`select#select-native-1`)

Same regex applied to the `mySel=$('select#select-native-1')` block.

Build map: `secondary_index: dict[html_filename, GathaIndexEntry]`

Skip this step if `cfg.selectors.secondary_teeka_select` is not set (single-teeka shastras).

### 3.3 Classify Pages

For each HTML file in `html_dir` (excluding `skip_files`):

```python
def classify_page(filename: str) -> Literal["primary_gatha", "secondary_kalash", "skip"]:
    if filename in primary_index:
        return "primary_gatha"
    if secondary_index and filename in secondary_index:
        return "secondary_kalash"
    return "skip"
```

- **`primary_gatha`** — regular gatha page parsed for both teekas.
  Canonical `gatha_number` = `primary_index[filename].gatha_number` (NOT the html div id).
- **`secondary_kalash`** — not in primary index; treated as a secondary-teeka standalone kalash.
  `kalash_number` = html-number from filename (e.g. `"012"` from `"012.html"`).
- **`skip`** — file in neither index; log a warning and skip.

### 3.4 Find Preceding Primary-Gatha for Secondary-Only Pages

For each `secondary_kalash` page, find the last `primary_gatha` file before it in
**sorted file order**:

```python
def preceding_primary_gatha(filename: str, sorted_files: list[str]) -> str | None:
    idx = sorted_files.index(filename)
    for f in reversed(sorted_files[:idx]):
        if f in primary_index:
            return primary_index[f].gatha_number
    return None
```

This `preceding_gatha_number` is stored on the `Kalash` Postgres row as `gatha_id`.

---

## 4. Step 2 — Per-Page Parsing

### 4.1 Page-Level Content (before the teeka `<table>`)

All content between the navbar's closing `</div>` and the opening `<table width=90%>` is page-level.

#### 4.1.1 Topic / Heading

```python
title_div = soup.select_one("div.title[id^='gatha-']")
heading_hi = clean(title_div.select_one("a").get_text())
page_html_id = title_div["id"].removeprefix("gatha-")  # "009-010" (debug only)
```

`page_html_id` is for **logging / debugging only**. The canonical `gatha_number` always comes from myItem.js.

#### 4.1.2 Prakrit Gatha

```python
gatha_div = soup.select_one("div.gatha")
prakrit_raw = clean(gatha_div.get_text())
# Multi-gatha pages: text contains multiple verse numbers (॥9॥, ॥10॥).
# Store the full concatenated text — do NOT split.
```

Strip trailing verse number markers `॥N॥`:
`re.sub(r'\s*॥\s*[\d]+\s*॥\s*$', '', text)` — trailing only.

#### 4.1.3 Sanskrit Gatha (`div.gathaS`)

```python
gathaS_div = soup.select_one("div.gathaS")
sanskrit_text = clean(gathaS_div.get_text()) if gathaS_div else None
```

#### 4.1.4 Hindi Chhand (`div.gadya`, body scope only)

Select only `div.gadya` elements that appear **before the teeka `<table>`**:

```python
body_gadya_divs = [
    d for d in soup.select("div.gadya")
    if not d.find_parent("table") and not d.find_parent("div", id=re.compile("^teeka"))
]
chhands = []
for i, div in enumerate(body_gadya_divs, start=1):
    chhands.append(GathaHindiChhand(
        chhand_index=i,
        chhand_type="harigeet",   # default; no type marker in body gadya
        text_hi=clean(div.get_text()),
    ))
```

#### 4.1.5 Anyavartha / Word Meanings (`div.paragraph`)

Find the `<div class=paragraph>` containing the `अन्वयार्थ` marker (outside teeka divs):

```python
para_div = next(
    (d for d in soup.select("div.paragraph")
     if "अन्वयार्थ" in d.get_text() and not d.find_parent("div", id=re.compile("^teeka"))),
    None
)
if para_div:
    anyavartha = parse_anyavartha(para_div)
```

**`parse_anyavartha(div) → AnyavarthaItem`:**

```python
def parse_anyavartha(div) -> AnyavarthaItem:
    full_text = clean(div.get_text())
    full_anyavaarth = re.sub(r'^अन्वयार्थ\s*:\s*', '', full_text).strip()

    tagged_terms: list[GathaWordMeaningEntry] = []
    position = 1
    for font in div.select("font[color='darkRed'], font[color='darkred']"):
        key_text = clean(font.get_text()).strip("[]").strip()
        meaning = _text_after_element(font.parent, until_tag="b")
        tagged_terms.append(GathaWordMeaningEntry(
            source_word=key_text,    # brackets stripped
            meaning=clean(meaning),
            position=position,
        ))
        position += 1

    return AnyavarthaItem(
        full_anyavaarth=full_anyavaarth,
        tagged_terms=tagged_terms,
    )
```

Helper `_text_after_element(el, until_tag)`: iterate `.next_siblings` collecting text nodes
until a sibling with tag `until_tag` is found.

---

### 4.2 Primary Teeka (`div#teeka0`)

**Only parse if `div#teeka0` starts with the primary teeka label** (check first `<font color=darkgreen>`
text against `cfg.selectors.primary_teeka_label`).
If it starts with the secondary label instead, the page is a secondary-only kalash page;
skip this section and handle via §4.4.

#### 4.2.1 Sanskrit Section (`div.steeka#steeka0`)

All content inside `div.steeka#steeka0` (before `<hr class=type_7>`).

**Parse kalash Sanskrit verses** — delimited by `<font color=DarkSlateGray>(कलश-XXX)</font>` markers:

```
(कलश-अनुष्टुभ्)         ← kalash 1 type
नम: समयसाराय...॥१॥      ← kalash 1 Sanskrit text
(कलश-मालिनी)            ← kalash 2 type
अनन्तधर्मणस्तत्त्वं...  ← kalash 2 Sanskrit text
अथ सूत्रावतार -         ← gathaTeeka starts (NOT a kalash)
[Sanskrit prose...]
<hr class=type_7>
```

```python
kalash_san_entries: list[KalashSanskritEntry] = []
gatha_teeka_san: str | None = None
current_type: str = ""
current_text_parts: list[str] = []
in_teeka = False

for node in steeka0_div.children:
    if is_kalash_type_marker(node):          # <font color=DarkSlateGray>(कलश-XXX)</font>
        if current_text_parts and not in_teeka:
            kalash_san_entries.append(...)   # flush previous kalash Sanskrit
        current_type = extract_chhand_type(node)   # "अनुष्टुभ्", "मालिनी" etc.
        current_text_parts = []
        in_teeka = False
    elif is_gatha_teeka_start(node):         # text matches gatha_teeka_start_markers
        if current_text_parts and not in_teeka:
            kalash_san_entries.append(...)   # flush last kalash before teeka
        in_teeka = True
        current_text_parts = [get_text(node)]
    elif in_teeka:
        current_text_parts.append(get_text(node))
    else:
        current_text_parts.append(get_text(node))

if in_teeka and current_text_parts:
    gatha_teeka_san = clean("\n".join(current_text_parts))
```

**Note**: On some pages kalash_sanskrit appears AFTER gathaTeeka. Both orderings must be handled;
`is_gatha_teeka_start` detection flips `in_teeka=True` and everything after goes to `gatha_teeka_san`.

Page-local kalash index (`local_kalash_index`) is 1-based within the page.
The **global kalash counter** (used for Postgres `kalash_number`) is tracked by the orchestrator
across all pages in sorted file order.

#### 4.2.2 Hindi Content (after `div.steeka#steeka0` within `div#teeka0`)

Three interspersed element types — process by walking children in order:

| Element type | Action |
|---|---|
| `div.gadya` (wrapped in `<b>`) | New kalash Hindi chhand. Extract chhand type from `<span class=notes>(कलश-XXX)</span>`. Increment `hindi_kalash_counter`. |
| `<b>[<font color=maroon>...]</font>]</b>` | Kalash word meaning entry for current `hindi_kalash_counter`. |
| Text matching bhaavarth start marker | Everything from here to end of `teeka0` is bhaavarth Markdown. |

```python
hindi_kalash_counter = 0
kalash_hindi_entries: list[KalashHindiEntry] = []
kalash_wm_entries: dict[int, list[KalashWMEntry]] = defaultdict(list)
bhaavarth_parts: list[str] = []
in_bhaavarth = False

for node in nodes_after_steeka0:
    if in_bhaavarth:
        bhaavarth_parts.append(node_to_markdown(node))
        continue
    if is_bhaavarth_start(node):
        in_bhaavarth = True
        bhaavarth_parts.append(node_to_markdown(node))
        continue
    if is_kalash_gadya(node):       # <b><div class=gadya>...</div></b>
        hindi_kalash_counter += 1
        chhand_type = extract_chhand_type_from_notes_span(node)
        text = clean_gadya_text(node)
        kalash_hindi_entries.append(KalashHindiEntry(
            local_kalash_index=hindi_kalash_counter,
            chhand_type=chhand_type,
            text_hi=text,
        ))
    elif is_kalash_word_meaning(node):   # <b>[<font color=maroon>]...</b>
        entry = parse_kalash_wm(node)
        kalash_wm_entries[hindi_kalash_counter].append(entry)
```

**`node_to_markdown(node)`** — converts HTML subtree to Markdown string:

| HTML construct | Markdown equivalent |
|---|---|
| `<b>...</b>` | `**...**` |
| `<i>...</i>` | `*...*` |
| `<font color=X>...</font>` (non-label colors) | `<span style="color:X">...</span>` |
| `<span class=notes>...</span>` | `*(..)*` (italic) |
| `<ul><li>...</ul>` | Markdown list |
| `<br>` | `\n` |
| Square brackets `[...]` in text | Preserved as-is |

Strip `<font color=darkgreen>` and `<font color=red>` decorative label nodes.

#### 4.2.3 Matching Hindi Kalashes to Sanskrit Kalashes

After parsing both steeka0 and the Hindi section:
- `kalash_san_entries[i]` corresponds to `kalash_hindi_entries[i]` (by local 1-based index).
- If counts don't match: log `WARN: kalash count mismatch on {filename}`. Pair by position; orphans flagged.

---

### 4.3 Secondary Teeka (`div#teeka1`)

Verify: `div#teeka1` starts with `cfg.selectors.secondary_teeka_label`.

#### 4.3.1 Sanskrit Teeka (`div.steeka#steeka1`)

```python
steeka1 = teeka1_div.select_one("div.steeka#steeka1")
gatha_teeka_j_san = clean(steeka1.get_text()) if steeka1 else None
# Stop at <hr class=type_7> (separator between Sanskrit and Hindi).
```

#### 4.3.2 Hindi Bhaavarth (after `div.steeka#steeka1`)

```python
j_bhaavarth_parts = []
after_steeka = False
for node in teeka1_div.children:
    if node == steeka1_div:
        after_steeka = True
        continue
    if after_steeka:
        j_bhaavarth_parts.append(node_to_markdown(node))
gatha_teeka_j_bhaavarth_md = "\n".join(j_bhaavarth_parts).strip()
```

Collect everything after steeka1 (no start-marker check needed for secondary teeka).

---

### 4.4 Secondary-Only Kalash Pages (pages not in primary index)

`div#teeka0` starts with the secondary teeka label on these pages.

```python
def is_secondary_only_page(teeka0_div, cfg) -> bool:
    first_label = teeka0_div.select_one("font[color='darkgreen']")
    return first_label and cfg.selectors.secondary_teeka_label in first_label.get_text()
```

Extract:
- Body-level fields (Prakrit, anyavartha) exactly as in §4.1. No Sanskrit or Hindi chhand on most secondary-only pages.
- Secondary teeka: content inside `div#teeka0` after the label.
  - If `div.steeka#steeka0` present → Sanskrit teeka.
  - After steeka (or if none): Hindi bhaavarth.

---

## 5. Multi-Gatha Page Handling

A page like `009-010.html` (gatha_number = `"009-010"`) contains two Prakrit verses,
two Sanskrit verses, two Hindi chhands, and one combined anyavartha paragraph.

**Parsing rules:**
1. Parse as above — extract all text from combined divs unchanged.
2. Detect multi-gatha from `gatha_number` containing a hyphen (`"009-010"`).
3. Split individual numbers: `["009", "010"]`.
4. Each individual gatha gets its own `GathaExtract` with these fields **duplicated** from the combined page:
   - `prakrit_text`, `sanskrit_text`, `hindi_chhands`, `anyavartha`, teeka content.
5. On the duplicated `GathaExtract`, populate `related_gatha_numbers` with the OTHER numbers:
   - gatha `"009"` on page `"009-010"`: `related_gatha_numbers = ["010"]`
   - gatha `"010"` on page `"009-010"`: `related_gatha_numbers = ["009"]`
6. `GathaExtract.is_combined_page = True` for all gathas from a multi-gatha page.

---

## 6. Pydantic Extract Models

```python
# workers/ingestion/nj/models.py

class GathaWordMeaningEntry(BaseModel):
    source_word: str       # prakrit/sanskrit key, brackets stripped
    meaning: str           # hindi meaning
    position: int          # 1-based position in anyavartha

class AnyavarthaItem(BaseModel):
    full_anyavaarth: str           # complete Hindi anyavartha text (no markup)
    tagged_terms: list[GathaWordMeaningEntry]

class GathaHindiChhand(BaseModel):
    chhand_index: int      # 1-based
    chhand_type: str       # "harigeet" default for body chhands
    text_hi: str

class KalashSanskritEntry(BaseModel):
    local_kalash_index: int   # 1-based within this page
    chhand_type: str           # "अनुष्टुभ्", "मालिनी", "रोला" etc.
    text_san: str

class KalashHindiEntry(BaseModel):
    local_kalash_index: int
    chhand_type: str           # from <span class=notes>(कलश-XXX)</span>
    text_hi: str

class KalashWMEntry(BaseModel):
    source_word: str           # text inside [<font color=maroon>...]
    meaning: str               # Hindi meaning text following the key

class PrimaryTeeka(BaseModel):
    """Teeka with kalashes (e.g. अमृतचंद्राचार्य)."""
    kalash_san: list[KalashSanskritEntry] = []
    gatha_teeka_san: str | None = None          # Sanskrit prose "अथ सूत्रावतार..."
    kalash_hindi: list[KalashHindiEntry] = []
    kalash_word_meanings: dict[int, list[KalashWMEntry]] = {}   # key = local_kalash_index
    gatha_teeka_bhaavarth_md: str | None = None   # Markdown with inline HTML for colors

class SecondaryTeeka(BaseModel):
    """Teeka without kalashes (e.g. जयसेनाचार्य)."""
    gatha_teeka_san: str | None = None
    gatha_teeka_bhaavarth_md: str | None = None

class GathaExtract(BaseModel):
    # Identity — all from config + myItem.js; never hard-coded
    shastra_natural_key: str          # from cfg.shastra.natural_key
    gatha_number: str                 # from primary index: "001", "009-010"
    page_html_id: str                 # from div.title id (debug only)
    html_filename: str                # "009-010.html"
    adhikaar_hi: str | None           # optgroup label from myItem.js
    heading_hi: str | None            # option text from myItem.js
    is_combined_page: bool = False
    related_gatha_numbers: list[str] = []   # other gathas on the same page

    # Gatha content
    prakrit_text: str | None = None
    sanskrit_text: str | None = None
    hindi_chhands: list[GathaHindiChhand] = []
    anyavartha: AnyavarthaItem | None = None

    # Teekas (None if absent)
    primary_teeka: PrimaryTeeka | None = None
    secondary_teeka: SecondaryTeeka | None = None

class KalashExtract(BaseModel):
    """Secondary-teeka standalone kalash pages (pages not in the primary index)."""
    shastra_natural_key: str
    kalash_number: str                # html filename number e.g. "011"
    html_filename: str
    heading_hi: str | None
    preceding_primary_gatha_number: str | None   # e.g. "009-010"

    prakrit_text: str | None = None
    anyavartha: AnyavarthaItem | None = None
    secondary_teeka: SecondaryTeeka | None = None

class ShastraParseResult(BaseModel):
    shastra_natural_key: str
    gathas: list[GathaExtract]              # one per individual gatha (after expansion)
    secondary_kalashes: list[KalashExtract]
    total_html_files_processed: int
    warnings: list[str]
    parser_version: str
    parsed_at: datetime
```

---

## 7. Worker Structure

```
workers/ingestion/nj/
├── __init__.py
├── orchestrator.py        # top-level: load config → parse → emit GathaExtracts
├── parse_myitem.py        # parse myItem.js → GathaIndexEntry maps
├── classify_pages.py      # classify html files: primary_gatha | secondary_kalash | skip
├── parse_page.py          # parse one HTML file → list[GathaExtract] | KalashExtract
├── parse_primary_teeka.py # §4.2 — primary teeka extraction (with kalashes)
├── parse_secondary_teeka.py  # §4.3 / §4.4 — secondary teeka extraction
├── html_to_markdown.py    # node_to_markdown() utility
├── models.py              # Pydantic extract models (§6)
├── config.py              # load/validate parser_configs/nj/{shastra}.yaml
└── tests/
    ├── fixtures/
    │   ├── samaysar/
    │   │   ├── myItem_partial.js
    │   │   ├── 001.html
    │   │   ├── 009-010.html
    │   │   ├── 012.html          # secondary-only kalash
    │   │   └── 025-026-027.html  # multi-gatha
    │   └── samaysar.yaml         # test config pointing to fixtures/samaysar/
    └── test_parse_page.py
```

---

## 8. Orchestrator Pseudocode

```python
# workers/ingestion/nj/orchestrator.py

def parse_shastra(cfg: ShastraConfig) -> ShastraParseResult:
    shastra_nk = cfg.shastra.natural_key

    # 1. Parse myItem.js
    primary_index, secondary_index = parse_myitem(cfg)

    # 2. Sort and classify HTML files
    sorted_files = sorted(f for f in os.listdir(cfg.input.html_dir) if f.endswith(".html"))
    sorted_files = [f for f in sorted_files if f not in cfg.input.skip_files]

    # 3. Parse each file
    all_gathas: list[GathaExtract] = []
    secondary_kalashes: list[KalashExtract] = []
    global_primary_kalash_counter = 0   # global sequential counter for primary-teeka kalashes

    for filename in sorted_files:
        kind = classify_page(filename, primary_index, secondary_index)
        soup = parse_html(cfg.input.html_dir / filename, cfg.input.encoding)

        if kind == "primary_gatha":
            idx_entry = primary_index[filename]
            page_gathas, kalash_delta = parse_primary_page(
                soup, idx_entry, cfg,
                global_kalash_start=global_primary_kalash_counter + 1
            )
            global_primary_kalash_counter += kalash_delta
            all_gathas.extend(page_gathas)

        elif kind == "secondary_kalash":
            preceding = preceding_primary_gatha(filename, sorted_files, primary_index)
            kalash = parse_secondary_kalash_page(soup, filename, preceding, cfg)
            secondary_kalashes.append(kalash)

    return ShastraParseResult(
        shastra_natural_key=shastra_nk,
        gathas=all_gathas,
        secondary_kalashes=secondary_kalashes,
        total_html_files_processed=len(sorted_files),
        warnings=[...],
        parser_version=cfg.version,
        parsed_at=datetime.utcnow(),
    )
```

`parse_primary_page` returns:
1. `list[GathaExtract]` — one per gatha number in the combined string (after multi-page expansion).
2. `kalash_delta: int` — number of primary-teeka kalashes found on this page.

---

## 9. Edge Cases and Warnings

| Case | Handling |
|---|---|
| Page not in either index | Log `WARN: unclassified page {filename}` and skip. |
| `div.gathaS` absent | `sanskrit_text = None`; no `gatha_sanskrit` Mongo doc written. |
| No kalashes in steeka0 | `primary_teeka.kalash_san = []`; no `kalash_*` docs written. |
| No `gatha_teeka_start_marker` in steeka0 | `primary_teeka.gatha_teeka_san = None`; no `gatha_teeka_sanskrit` doc. |
| `div#teeka1` absent | `secondary_teeka = None`. |
| Secondary-only page with no steeka | `secondary_teeka.gatha_teeka_san = None`. |
| Kalash count mismatch (hindi ≠ sanskrit) | Emit `WARN: kalash count mismatch on {filename}`. Pair by position; orphans flagged. |
| BOM character `﻿` at text start | Strip from all extracted text strings. |
| Single-teeka shastra (no secondary) | `secondary_index = {}`; all pages classify as `primary_gatha` or `skip`. |

---

## 10. Definition of Done

(Fixtures based on Samaysar; the framework must work for any config-driven shastra.)

- [ ] `parse_myitem("myItem.js")` correctly extracts ≥ 270 primary-gatha entries and ≥ 280 secondary-gatha entries for samaysar.
- [ ] `classify_page("012.html")` → `"secondary_kalash"`.
- [ ] `classify_page("001.html")` → `"primary_gatha"`.
- [ ] `parse_primary_page(soup("001.html"), ...)` returns `GathaExtract` with:
  - `gatha_number = "001"`, `heading_hi = "सिद्धों को नमस्कार"`
  - `prakrit_text` starts with `"वंदित्तु सव्वसिद्धे"`
  - `primary_teeka.kalash_san` has 3 entries (अनुष्टुभ्, मालिनी, मालिनी)
  - `primary_teeka.gatha_teeka_san` starts with `"अथ सूत्रावतार"`
  - `primary_teeka.gatha_teeka_bhaavarth_md` is non-empty
  - `anyavartha.tagged_terms` has ≥ 8 entries; all `source_word` values have no brackets.
- [ ] Page `009-010.html` returns 2 `GathaExtract` objects (`"009"`, `"010"`), each with `is_combined_page=True` and `related_gatha_numbers` set.
- [ ] Page `025-026-027.html` returns 3 `GathaExtract` objects for gatha_numbers `"020"`, `"021"`, `"022"` (from primary index, not the filename).
- [ ] Page `012.html` returns one `KalashExtract` with `kalash_number="012"`.
- [ ] `global_primary_kalash_counter` advances correctly across pages (page 001 has 3 kalashes → next page's primary kalashes start at 4).
- [ ] All extracted strings are NFC-normalized and BOM-stripped.
- [ ] `pytest workers/ingestion/nj/tests/` passes (fixture-based, no network).
- [ ] Passing a different shastra config (e.g. a single-teeka shastra) runs without code changes.
