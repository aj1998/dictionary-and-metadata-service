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
  natural_key: <str>               # Hindi name, e.g. "समयसार"
  title_hi: <str>
  author:
    natural_key: <str>             # Hindi name, e.g. "कुन्दकुन्दाचार्य"
    display_name_hi: <str>
    kind: acharya | poet | ...
  teekas:
    - natural_key: <str>           # "{shastra}:{teeka-name-hi}", e.g. "समयसार:आत्मख्याती"
      teekakar_natural_key: <str>  # Hindi name, e.g. "अमृतचंद्राचार्य"
      teekakar_display_name_hi: <str>
      publication_natural_key: <str>  # "{teeka}:{publisher}", e.g. "समयसार:आत्मख्याती:nikkyjain"
      publisher_id: nikkyjain      # publisher_id stays ASCII
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

parsing:
  strip_zwj: false
  notes_teeka_index: 2              # skip teeka2 (notes div, not a real teeka)
```

### 2.2 Example: Samaysar Config (`parser_configs/nj/samaysaar.yaml`)

```yaml
version: 1.0.0
source: nj
shastra:
  natural_key: samaysaar
  title_hi: समयसार
  author:
    natural_key: kundkundacharya
    display_name_hi: कुन्दकुन्दाचार्य
    kind: acharya
  teekas:
    - natural_key: samaysaar:amritchandra
      teekakar_natural_key: amritchandracharya
      teekakar_display_name_hi: अमृतचंद्राचार्य
      publication_natural_key: samaysaar:amritchandra:nikkyjain
      publisher_id: nikkyjain
      role: primary
    - natural_key: samaysaar:jaysenacharya
      teekakar_natural_key: jaysenacharya
      teekakar_display_name_hi: जयसेनाचार्य
      publication_natural_key: samaysaar:jaysenacharya:nikkyjain
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
    adhikaar_number: int | None  # optgroup ordinal (1-based) within this select block
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
prakrit_raw = clean_preserve_newlines(gatha_div.get_text("\n", strip=False))
```

Strip trailing verse number markers `॥N॥`:
`re.sub(r'\s*॥\s*[\d]+\s*॥\s*$', '', text)` — trailing only.

#### 4.1.3 Sanskrit Gatha (`div.gathaS`)

```python
gathaS_div = soup.select_one("div.gathaS")
sanskrit_text = clean_preserve_newlines(gathaS_div.get_text("\n", strip=False)) if gathaS_div else None
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
        text_hi=clean_preserve_newlines(div.get_text("\n", strip=False)),
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

    # full_anyavaarth should keep only Hindi explanatory text
    # (remove tagged source-word fonts like [वंदित्तु], [सव्व], etc.)
    full_div = deepcopy(div)
    for font in full_div.select("font[color='darkRed'], font[color='darkred']"):
        font.decompose()
    full_text = clean(full_div.get_text(" ", strip=False))
    full_anyavaarth = re.sub(r'^अन्वयार्थ\s*:\s*', '', full_text).strip()
    full_anyavaarth = re.sub(r"\s+", " ", full_anyavaarth).strip()

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

All content inside `div.steeka#steeka0` up to (but not including) `<hr class=type_7>`.

**Classification is purely structural — no text markers.**

- **Kalash Sanskrit verse**: text between two consecutive `<font color=DarkSlateGray>` markers.
- **GathaTeeka prose**: all text nodes in steeka0 that are NOT inside a kalash block.

Ordering is flexible: pages like `001.html` have kalashes first then prose; pages like
`025-026-027.html` have prose first then kalashes. The HTML-structural walk handles both.

```
(कलश-अनुष्टुभ्)          ← DarkSlateGray marker → start kalash 1
नम: समयसाराय...॥१॥       ← kalash 1 Sanskrit text (collect until next marker or end)
(कलश-मालिनी)             ← DarkSlateGray marker → flush kalash 1, start kalash 2
अनन्तधर्मणस्तत्त्वं...   ← kalash 2 Sanskrit text
<hr class=type_7>         ← stop; everything from here is separator
अथ सूत्रावतार -          ← outside kalash blocks → gathaTeeka prose
[Sanskrit prose...]
```

```python
kalash_san_entries: list[KalashSanskritEntry] = []
gatha_teeka_parts: list[str] = []
current_kalash_type: str | None = None
current_kalash_parts: list[str] = []

def flush_kalash():
    if current_kalash_type is not None and current_kalash_parts:
        text = clean("\n".join(current_kalash_parts))
        if text:
            kalash_san_entries.append(KalashSanskritEntry(
                local_kalash_index=len(kalash_san_entries) + 1,
                global_kalash_index=global_kalash_start + len(kalash_san_entries),
                chhand_type=current_kalash_type,
                text_san=text,
            ))

for node in steeka0_nodes_before_hr:   # stop at <hr class=type_7>
    if is_kalash_type_marker(node):    # <font color=DarkSlateGray>(कलश-XXX)</font>
        flush_kalash()
        current_kalash_type = extract_chhand_type(node)  # "अनुष्टुभ्", "मालिनी" etc.
        current_kalash_parts = []
    elif current_kalash_type is not None:
        current_kalash_parts.append(get_text(node))
    else:
        text = get_text(node).strip()
        if text:
            gatha_teeka_parts.append(text)

flush_kalash()
gatha_teeka_san = clean("\n".join(gatha_teeka_parts)) or None
```

**Note**: `is_kalash_type_marker(node)` checks for a `<font>` element (possibly wrapped in `<b>`)
with `color=DarkSlateGray` whose text matches `(कलश-…)`. Extract chhand type via
`re.search(r'\(कलश-([^)]+)\)', text).group(1)`.

Page-local kalash index (`local_kalash_index`) is 1-based within the page.
The **global kalash counter** (used for Postgres `kalash_number`) is tracked by the orchestrator
across all pages in sorted file order.

#### 4.2.2 Hindi Content (after `div.steeka#steeka0` within `div#teeka0`)

Classification is **purely structural** — no text markers. Walk the children of `div#teeka0`
that come after `div.steeka#steeka0` and classify each node by its HTML shape:

| Node shape | Classified as |
|---|---|
| `<b>` wrapping a `<div class=gadya>` (detect with `node.find("div", class_="gadya")`) | Kalash Hindi chhand — extract chhand type from `<span class=notes>(कलश-XXX)</span>` |
| `<b>` whose text content starts with `[` and contains `<font color=maroon>` | Kalash word meaning entry for the most recent `hindi_kalash_counter` |
| Anything else (text, `<br>`, other tags) | Bhaavarth — convert to Markdown |

Ordering is flexible: kalash gadya and kalash WM may appear before or after bhaavarth text.
All three types may be interspersed across the page.
Kalash-word-meaning meaning text may continue outside the `<b>[<font color=maroon>...</font>]</b>` node,
including inline notes spans; parsing consumes sibling nodes until structural boundary (`<br><br>` or next kalash/bhaavarth block).

```python
hindi_kalash_counter = 0
kalash_hindi_entries: list[KalashHindiEntry] = []
kalash_wm_entries: dict[int, list[KalashWMEntry]] = defaultdict(list)
bhaavarth_parts: list[str] = []

for node in nodes_after_steeka0:
    if is_kalash_gadya(node):        # <b><div class=gadya>...</div></b>
        hindi_kalash_counter += 1
        chhand_type = extract_chhand_type_from_notes_span(node)
        text = clean_gadya_text(node)
        kalash_hindi_entries.append(KalashHindiEntry(
            local_kalash_index=hindi_kalash_counter,
            global_kalash_index=global_kalash_start + hindi_kalash_counter - 1,
            chhand_type=chhand_type,
            text_hi=text,
        ))
    elif is_kalash_word_meaning(node):   # <b>[<font color=maroon>...]...</b> + sibling continuation
        entry = parse_kalash_wm_with_siblings(node, following_nodes)
        kalash_wm_entries[hindi_kalash_counter].append(entry)
    else:
        md = node_to_markdown(node)
        if md.strip():
            bhaavarth_parts.append(md)

gatha_teeka_bhaavarth_md = "\n".join(bhaavarth_parts).strip() or None
```

**`is_kalash_gadya(node)`**: `isinstance(node, Tag) and node.name == "b" and node.find("div", class_="gadya") is not None`

**`is_kalash_word_meaning(node)`**: `isinstance(node, Tag) and node.name == "b" and node.find("font", color=re.compile("^maroon$", re.I)) is not None`

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
BOM is stripped from final markdown.

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
1. Parse as above.
2. Detect multi-gatha from `gatha_number` containing a hyphen (`"009-010"`).
3. Split individual numbers: `["009", "010"]`.
4. Split `prakrit_text`, `sanskrit_text`, and each `hindi_chhands[*].text_hi` by verse-number markers:
   - supported markers: `॥9॥`, `॥९॥`, `||9||`, `||९||` (and corresponding values for each gatha in page range).
   - if split markers are not found, fallback is to keep original combined text.
5. `anyavartha` and teeka content remain shared for split gathas (same source block for the page).
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
    global_kalash_index: int  # sequential across all pages in sorted file order
    chhand_type: str           # "अनुष्टुभ्", "मालिनी", "रोला" etc.
    text_san: str

class KalashHindiEntry(BaseModel):
    local_kalash_index: int
    global_kalash_index: int  # sequential across all pages in sorted file order
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
    adhikaar_number: int | None       # optgroup ordinal (1-based) from myItem.js
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
    │   ├── samaysaar/
    │   │   ├── myItem_partial.js
    │   │   ├── 001.html
    │   │   ├── 009-010.html
    │   │   ├── 012.html          # secondary-only kalash
    │   │   └── 025-026-027.html  # multi-gatha
    │   └── samaysaar.yaml         # test config pointing to fixtures/samaysaar/
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
| No non-kalash prose in steeka0 | `primary_teeka.gatha_teeka_san = None`; no `gatha_teeka_sanskrit` doc. |
| `div#teeka1` absent | `secondary_teeka = None`. |
| Secondary-only page with no steeka | `secondary_teeka.gatha_teeka_san = None`. |
| Kalash count mismatch (hindi ≠ sanskrit) | Emit `WARN: kalash count mismatch on {filename}`. Pair by position; orphans flagged. |
| BOM character `﻿` at text start | Strip from all extracted text strings. |
| Single-teeka shastra (no secondary) | `secondary_index = {}`; all pages classify as `primary_gatha` or `skip`. |

---

## 10. Definition of Done (Status: 2026-05-24)

(Fixtures based on Samaysar; the framework must work for any config-driven shastra.)

- [x] `parse_myitem("myItem.js")` correctly extracts ≥ 200 primary-gatha entries and ≥ 200 secondary-gatha entries for samaysaar.
- [x] `classify_page("012.html")` → `"secondary_kalash"`.
- [x] `classify_page("001.html")` → `"primary_gatha"`.
- [x] `parse_primary_page(soup("001.html"), ...)` implementation exists and returns `GathaExtract` with fields:
  - `gatha_number = "001"`, `heading_hi = "सिद्धों को नमस्कार"`
  - `prakrit_text` starts with `"वंदित्तु सव्वसिद्धे"`
  - `primary_teeka.kalash_san` has 3 entries (अनुष्टुभ्, मालिनी, मालिनी)
  - `primary_teeka.gatha_teeka_san` starts with `"अथ सूत्रावतार"`
  - `primary_teeka.gatha_teeka_bhaavarth_md` is non-empty
  - `anyavartha.tagged_terms` has ≥ 8 entries; all `source_word` values have no brackets.
- [x] Page `009-010.html` returns 2 `GathaExtract` objects (`"009"`, `"010"`), each with `is_combined_page=True` and `related_gatha_numbers` set.
- [x] Page `025-026-027.html` returns 3 `GathaExtract` objects for gatha_numbers `"020"`, `"021"`, `"022"` (from primary index, not the filename).
- [x] Page `012.html` returns one `KalashExtract` with `kalash_number="012"`.
- [x] `global_primary_kalash_counter` advances correctly across pages (page 001 has 3 kalashes → next page's primary kalashes start at 4).
- [x] All extracted strings are NFC-normalized and BOM-stripped.
- [x] `pytest workers/ingestion/nj/tests/` passes.
- [x] Passing a different shastra config (e.g. a single-teeka shastra) runs without code changes (config-driven parser structure implemented).

---

## 11. Final Implementation Notes

This section records the final state after implementing the remaining parser work.

### 11.1 Already Implemented Before This Pass

- `workers/ingestion/nj/models.py` with Pydantic extract models:
  - `GathaExtract`, `KalashExtract`, `PrimaryTeeka`, `SecondaryTeeka`
  - `AnyavarthaItem`, `GathaWordMeaningEntry`
  - `KalashSanskritEntry`, `KalashHindiEntry`, `KalashWMEntry`
  - `ShastraParseResult`
- `workers/ingestion/nj/config.py`:
  - config schema and loader for `parser_configs/nj/{shastra}.yaml`
  - selector fields and parsing options updated to structural parsing
- `workers/ingestion/nj/parse_myitem.py`:
  - regex extraction of `primary_index` and `secondary_index`
  - `GathaIndexEntry` map keyed by `html_filename`
- `workers/ingestion/nj/classify_pages.py`:
  - `classify_page(...)` and `preceding_primary_gatha(...)`
- `workers/ingestion/nj/html_to_markdown.py`:
  - bhaavarth markdown conversion with required formatting rules
- `parser_configs/nj/samaysaar.yaml`:
  - updated parser selectors and removed old text-marker dependency

### 11.2 Implemented In This Pass

- `workers/ingestion/nj/parse_primary_teeka.py`:
  - structural extraction of primary teeka Sanskrit blocks from `steeka0`
  - kalash marker detection by `DarkSlateGray` `(कलश-...)`
  - extraction of:
    - `kalash_san[]`
    - `gatha_teeka_san`
    - `kalash_hindi[]` from `<b><div class=gadya>...</div></b>`
    - `kalash_word_meanings{}` from maroon-font nodes
    - `gatha_teeka_bhaavarth_md` via `node_to_markdown(...)`
  - returns `(PrimaryTeeka, kalash_delta)` for global counter progression
- `workers/ingestion/nj/parse_secondary_teeka.py`:
  - parses either `div#teeka1` (regular page) or `div#teeka0` (secondary-only page)
  - extracts Sanskrit (before `hr.type_7`) and markdown bhaavarth after steeka
- `workers/ingestion/nj/parse_page.py`:
  - body-level parse for `prakrit_text`, `sanskrit_text`, body `hindi_chhands`, `anyavartha`
  - primary-page parse wiring (`teeka0` + optional `teeka1`)
  - secondary-only kalash-page parse wiring (`teeka0` as secondary)
  - multi-gatha expansion (`009-010` style) with:
    - `is_combined_page=True`
    - `related_gatha_numbers`
- `workers/ingestion/nj/orchestrator.py`:
  - end-to-end parse loop over sorted HTML files
  - page classification and routing
  - global kalash counter tracking
  - parse result assembly into `ShastraParseResult`
- `workers/ingestion/nj/tests/test_parse_page.py`:
  - tests for index counts, classification, primary page parse, multi-gatha parse, and secondary-kalash parse
  - guarded by `NIKKYJAIN_LOCAL_PATH` presence

### 11.3 Validation Performed

- Full NJ unit suite passes:
  - `pytest -q workers/ingestion/nj/tests`
  - latest run status: `25 passed, 5 skipped`

### 11.4 Golden JSON Output for Ingestion

Implemented Jainkosh-style NJ golden generation for ingestion handoff:

- Added `workers/ingestion/nj/envelope.py`
  - `build_envelope(result, cfg)` returns:
    - `shastra_parse_result` (raw parsed output)
    - `would_write` (ingestion-ready payload skeleton with `postgres`, `mongo`, `neo4j`, `idempotency_contracts`)
  - Uses natural-key conventions from `02_ingestion_nj.md`.
- Added `workers/ingestion/nj/cli.py`
  - Command:
    - `python -m workers.ingestion.nj.cli parse --config ... --batch-offset ... --batch-limit ... --format golden`
  - Default golden output path:
    - `workers/ingestion/nj/tests/golden/{shastra}_golden_o{offset}_l{limit}.json`
- Added test:
  - `workers/ingestion/nj/tests/test_envelope.py`
  - Validates top-level envelope shape and key natural-key mappings.

First batch (10 pages) golden was generated at:

- `workers/ingestion/nj/tests/golden/samaysaar_golden_o0_l10.json`

Second batch (next 10 pages) golden was generated at:

- `workers/ingestion/nj/tests/golden/samaysaar_golden_o10_l10.json`

### 11.5 Post-Implementation Bugfixes

After initial implementation, the following parser correctness fixes were applied:

1. Newline preservation
- `prakrit_text`, `sanskrit_text`, and `hindi_chhands[].text_hi` now preserve line boundaries via `\n` (using `<br>`/line-break aware extraction) instead of flattening to one line.
- Primary teeka `kalash_san[].text_san` also preserves multi-line verse structure.

2. `anyavartha.full_anyavaarth` cleanup
- Now stores only Hindi explanatory text.
- Tagged source words from darkRed fonts (`[वंदित्तु]`, etc.) are removed from `full_anyavaarth` while still captured in `tagged_terms`.

3. Primary teeka Sanskrit segmentation fix (`001.html` class of pages)
- Correctly separates:
  - `kalash_san[]` (all Sanskrit kalashes inside the kalash gadya block), and
  - `gatha_teeka_san` (e.g., `अथ सूत्रावतार ...`) outside that kalash block.
- Prevents सूत्रावतार prose from being incorrectly absorbed into the first kalash.

4. Kalash word-meaning population fix
- Kalash WM meaning text frequently continues outside the maroon `<b>[...]</b>` node.
- Parsing now consumes structural sibling continuation (including notes spans), so meanings are not empty.
- Envelope mapping also handles local-to-global kalash index alignment when emitting `kalash_word_meanings`.

5. Bhaavarth boundary fix (structural, not marker hardcoded)
- `gatha_teeka_bhaavarth_md` no longer starts from the middle of kalash WM tail text.
- Boundary is determined structurally by consuming complete WM block first, then continuing with remaining prose nodes.
- BOM stripped from final markdown string.

6. Multi-gatha splitting fix (`009-010`, etc.)
- Previously combined-page text was duplicated across split gathas.
- Now marker-based splitting is applied for each split gatha on:
  - `prakrit_text`
  - `sanskrit_text`
  - `hindi_chhands[].text_hi`
- Supports both ASCII and Devanagari number markers:
  - `॥9॥`, `॥९॥`, `||9||`, `||९||` (and corresponding page numbers).

7. Adhikaar number support
- Added `adhikaar_number` (1-based optgroup ordinal) from `myItem.js`.
- Carried through:
  - `GathaIndexEntry`
  - `GathaExtract`
  - golden/postgres gatha payloads in envelope.
- Regex for optgroup parsing updated to support both observed JS forms:
  - `label="...'"` and `label="...">'`.

### 11.6 Pass-3 Fixes and Additions (2026-05-25)

#### 11.6.1 `preceding_primary_gatha_number` — last gatha from combined page
- `classify_pages.preceding_primary_gatha(...)` now returns only the **last** individual gatha number from a combined-page gatha_number (e.g., `"009-010"` → `"010"`).
- This means `KalashExtract.preceding_primary_gatha_number` and the postgres `kalashas.gatha_natural_key` for secondary kalashes now correctly point to the last gatha of the preceding page, not the combined string.

#### 11.6.2 `gatha_word_meanings` removed from envelope
- `gatha_word_meanings` is a separate collection handled elsewhere. It is no longer emitted in the mongo section of `build_envelope`.
- The `AnyavarthaItem.tagged_terms` field is **kept** in the parse model and still feeds `teeka_gatha_mapping.tagged_terms`.

#### 11.6.3 `teeka_gatha_mapping` — primary teeka only
- Only the primary teeka entry is written to `mongo.teeka_gatha_mapping`.
- The secondary teeka entry was removed — it serves a different ingestion path.

#### 11.6.4 Neo4j nodes and edges
`build_envelope` now populates `neo4j.nodes` and `neo4j.edges`:

| Object | Label / Type | key |
|---|---|---|
| Shastra | `Shastra` | `समयसार` |
| Per-gatha heading (deduplicated) | `Topic` | heading text itself (e.g., `"सिद्धों को नमस्कार"`) |
| Each gatha | `Gatha` | `समयसार:1` |
| Gatha → Topic | edge `MENTIONS_TOPIC` | from: `gatha_nk`, to: `heading_hi` |

- Topic nodes are deduplicated — gathas sharing the same heading share one Topic node.
- No Topic node or edge is emitted for gathas with `heading_hi = None`.
- Edge type is `MENTIONS_TOPIC` (per `data_model_graph.md`; `HAS_TOPIC` is Keyword→Topic).
- Node shape: `{label, key, props}` matching JK envelope format.

#### 11.6.5 `teeka_chapters` postgres table and envelope output
- New migration `migrations/versions/0019_teeka_chapters.py` creates the `teeka_chapters` table:
  ```sql
  teeka_chapters (
      natural_key TEXT UNIQUE,
      teeka_id UUID FK → teekas,
      chapter_number INTEGER,
      name JSONB,
      start_gatha_id UUID FK → gathas,
      end_gatha_id UUID REFERENCES gathas NULL,
      UNIQUE(teeka_id, chapter_number)
  )
  ```
- `build_envelope` computes chapters from the primary teeka's gathas, grouped by `adhikaar_number`.
- Chapter `natural_key`: `{primary.natural_key}:chapter:{adhikaar_number}` (no zero-padding)
- `start_gatha_natural_key` / `end_gatha_natural_key` are the first and last gathas seen in the adhikaar within the current batch.
- Only the primary teeka gets chapter records; secondary teeka is not chaptered.

#### 11.6.6 Test suite updated
- `tests/workers/nj/test_classify_pages_unit.py`: assertion for `preceding_primary_gatha` updated to expect `"010"` for page following `009-010.html`.
- `tests/workers/nj/test_envelope.py`: fully rewritten with coverage for:
  - `gatha_word_meanings` absent from mongo
  - `teeka_gatha_mapping` primary-only
  - neo4j Shastra / Topic / Gatha nodes and `MENTIONS_TOPIC` edges
  - `teeka_chapters` grouping, name format, and null-adhikaar skip
  - secondary kalash `gatha_natural_key` uses last gatha number
  - `table` field on all postgres rows (JK parity)
  - `collection` field on all mongo docs (JK parity)
  - detailed idempotency contracts (19 keys, all with `conflict_key`, `on_conflict`, `fields_replace`, `stores`)
- All 51 NJ tests pass.

### 11.7 Pass-4: Hindi Natural Keys and Number Normalization (2026-05-25)

#### 11.7.1 Hindi natural keys everywhere
All natural keys in `parser_configs/nj/samaysaar.yaml` — and therefore in all envelope output — now use Hindi names. The config file is still discovered by its ASCII filename (`samaysaar.yaml`), but the `natural_key` fields inside are Hindi.

| Field | Before | After |
|---|---|---|
| `shastra.natural_key` | `samaysaar` | `समयसार` |
| `shastra.author.natural_key` | `kundkundacharya` | `कुन्दकुन्दाचार्य` |
| `teekas[0].teekakar_natural_key` | `amritchandracharya` | `अमृतचंद्राचार्य` |
| `teekas[0].natural_key` | `samaysaar:amritchandra` | `समयसार:आत्मख्याती` |
| `teekas[0].publication_natural_key` | `samaysaar:amritchandra:nikkyjain` | `समयसार:आत्मख्याती:nikkyjain` |
| `teekas[1].teekakar_natural_key` | `jaysenacharya` | `जयसेनाचार्य` |
| `teekas[1].natural_key` | `samaysaar:jaysenacharya` | `समयसार:तात्पर्यवृत्ति` |
| `teekas[1].publication_natural_key` | `samaysaar:jaysenacharya:nikkyjain` | `समयसार:तात्पर्यवृत्ति:nikkyjain` |

- Teeka natural keys use the **teeka name** (the commentary title), not the teekakar's name.
- `publisher_id: nikkyjain` stays ASCII — it is a system identifier, not a displayed name.
- All downstream keys (gatha, kalash, chapter, mongo doc, neo4j) automatically pick up the Hindi shastra/teeka key since they are composed from config values.

#### 11.7.2 Number normalization — `_norm_num()`
A `_norm_num(s: str) -> str` helper was added to `envelope.py`. It strips leading zeros from numeric strings (`"001"` → `"1"`, `"011"` → `"11"`). Applied to:

- Gatha natural keys via `_gatha_nk`: `समयसार:001` → `समयसार:1`
- `gatha_number` field values in all postgres and mongo output
- Kalash natural keys and `kalash_number` field values (primary and secondary)
- Teeka chapter natural keys: `chapter:01` → `chapter:1`
- Chhand natural keys: `chhand:01` → `chhand:1`

#### 11.7.3 Golden files renamed
Golden filenames are derived from `cfg.shastra.natural_key`, so they also became Hindi:
- `samaysaar_golden_o0_l10.json` → `समयसार_golden_o0_l10.json`
- `samaysaar_golden_o10_l10.json` → `समयसार_golden_o10_l10.json`

The old English-named goldens were deleted.

#### 11.7.4 Tests updated
All hardcoded natural key strings in `tests/workers/nj/test_envelope.py` updated to Hindi and normalized numbers. All 51 NJ tests pass.
