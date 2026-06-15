# Wiki: NikkYJain Parser (`workers/ingestion/nj/`)

Source design doc: `docs/design/data_sources/nikkyjain/01_parser_nj.md`

---

## What it does

Parses the **per-file HTML** layout of `nikkyjain.github.io/jainDataBase/shastra/`. Each HTML file is one or more consecutive gathas. The `myItem.js` file in the same directory is the authoritative gatha index.

The parser is **shastra-agnostic**: all shastra identity (paths, selectors, teeka labels) comes from a YAML config file. Samaysar is the reference implementation; adding a new shastra requires only a new config file, no code changes.

---

## Module layout

```
workers/ingestion/nj/
├── orchestrator.py         # top-level: load config → parse all HTML → ShastraParseResult
├── parse_myitem.py         # regex-parse myItem.js → GathaIndexEntry maps
├── classify_pages.py       # classify html files: primary_gatha | secondary_kalash | skip
├── parse_page.py           # parse one HTML file → list[GathaExtract] | KalashExtract
├── parse_primary_teeka.py  # structural extraction of primary teeka (with kalashes)
├── parse_secondary_teeka.py# secondary teeka extraction (§ teeka1 or secondary-only pages)
├── html_to_markdown.py     # node_to_markdown() — HTML subtree → Markdown string
├── models.py               # Pydantic extract models (GathaExtract, KalashExtract, etc.)
├── config.py               # load/validate parser_configs/nj/{shastra}.yaml
├── envelope.py             # build_envelope() — produces golden ingestion payload
├── cli.py                  # python -m workers.ingestion.nj.cli parse ...
└── tests/
    ├── fixtures/samaysaar/ # myItem_partial.js + sample .html pages
    └── (unit test files live in tests/workers/nj/)
```

---

## Config file

All shastra-specific values live in `parser_configs/nj/{shastra_filename}.yaml`. The config is loaded by `config.py` and injected into every parser function — nothing is hard-coded.

Key config sections:
- `shastra` — natural_key (Hindi), title_hi, author, teekas (role: primary/secondary)
- `input` — html_dir (resolved at runtime via `NIKKYJAIN_LOCAL_PATH`), skip_files
- `selectors` — CSS selectors for every significant HTML element
- `parsing` — strip_zwj, notes_teeka_index

Samaysar config: `parser_configs/nj/samaysaar.yaml`

**Important**: `natural_key` fields inside the YAML are **Hindi** (`समयसार`, `कुन्दकुन्दाचार्य`). The config file is discovered by its ASCII filename (`samaysaar.yaml`), but all downstream natural keys are derived from the Hindi values.

---

## Required environment variable

```
NIKKYJAIN_LOCAL_PATH=/path/to/local/clone/of/nikkyjain.github.io
```

The `html_dir` in each config is a path template that is expanded with this variable at runtime.

---

## Parsing pipeline (in order)

### Step 1 — Parse `myItem.js`

`myItem.js` is JavaScript, parsed via **regex** (no JS engine). It builds two maps:

- `primary_index: dict[html_filename, GathaIndexEntry]` — from `select#select-native-0`
- `secondary_index: dict[html_filename, GathaIndexEntry]` — from `select#select-native-1`

Each `GathaIndexEntry` has: `html_filename`, `gatha_number` (e.g. `"020-021-022"`), `heading_hi`, `adhikaar_hi`, `adhikaar_number` (1-based optgroup ordinal).

**Critical**: The `gatha_number` from `myItem.js` is **canonical** — it may differ from the HTML filename (e.g. filename `013.html` → gatha_number `"011"`).

### Step 2 — Classify pages

Each HTML file gets one of three classifications:
- `primary_gatha` — file is in `primary_index` → full parse (both teekas)
- `secondary_kalash` — not in primary, but in `secondary_index` → secondary-only kalash page
- `skip` — in neither index → logged as warning, skipped

### Step 3 — Per-page HTML parsing

**Body-level content** (before the teeka `<table>`):
- `div.gatha` → `prakrit_text` — cleaned by `_clean_verse_text`: strips `(N)` mid-verse line-number labels (ASCII and Devanagari digits), strips trailing `॥N॥`/`||N||` verse-end markers. **Before** stripping, `_parse_body_fields` scans the *raw* Prakrit text and captures every numbered marker into `prakrit_verse_markers: list[str]` (NFC-normalised, Devanagari digits converted to ASCII). For single-gatha pages the first marker is assigned to `GathaExtract.prakrit_verse_marker`; for combined pages it is sliced per chunk in source order (see Step 4). This carries the source's per-page verse number — typically the secondary teeka's gatha numbering — through to Postgres `gathas.prakrit_verse_marker` (migration `0023`) and is shown in the UI breadcrumb (e.g. `गाथा १०६ (आत्मख्याति) | गाथा ११३ (तात्पर्यवृत्ति)` for `112-113.html`).
- `div.gathaS` → `sanskrit_text` (optional) — same `_clean_verse_text` pass applied.
- `div.gadya` (outside teeka divs) → `hindi_chhands[]` (type defaults to `"harigeet"`); text cleaned by `_clean_verse_text` — strips `(N)` mid-verse labels and trailing `॥N॥`/`||N||` verse-end markers (same pass as Prakrit/Sanskrit)
- `div.paragraph` containing `अन्वयार्थ` → `anyavartha` (full text + tagged term list)

**Primary teeka** (`div#teeka0`, only if it starts with the primary teeka label):
- `div.steeka#steeka0` → structural walk to extract `kalash_san[]` (by `<font color=DarkSlateGray>` `(कलश-...)` markers) and `gatha_teeka_san` prose
- Nodes after `steeka0` → `kalash_hindi[]`, `kalash_word_meanings{}`, `gatha_teeka_bhaavarth_md`
- Classification is **purely structural** — no hardcoded text markers

**Secondary teeka** (`div#teeka1`): extracts Sanskrit (before `hr.type_7`) and Hindi bhaavarth after.

**Secondary-only pages** (pages not in primary index): `div#teeka0` contains the secondary teeka content; body-level fields still parsed normally.

### Step 4 — Multi-gatha page expansion

Pages like `009-010.html` (gatha_number = `"009-010"`) produce **one `GathaExtract` per individual gatha**. The combined text is split by `_split_combined_text_by_markers`, then each chunk is cleaned by `_clean_gatha_chunk`.

**Gatha-number expansion** (`_expand_gatha_numbers`): myItem.js encodes multi-gatha pages either as an explicit list (`"020-021-022"`) or as a **range** (`"098-100"` meaning gathas 98, 99, and 100). The expander treats a 2-part hyphenated value as an inclusive range and a 3-or-more-part value as an explicit list, preserving the leading-zero width of the start value. Without this, `"098-100"` was split into just `["098", "100"]` and only the first verse-end marker was used as a split point, causing the verses for gathas 99 and 100 to be merged onto gatha 100 (and gatha 99 to never receive its own text).

**Splitting** (`_split_combined_text_by_markers`): finds the first N−1 verse-end markers (`॥M॥` or `||M||`, any number M) in document order — positional, not keyed to specific gatha numbers. This handles pages where the verse-end marker number differs from the sequential gatha number (e.g., page `017-018.html` uses `॥20॥` as the boundary). Split markers are **not** included in the returned chunks.

**Chunk cleanup** (`_clean_gatha_chunk`): strips residual `(N)` mid-verse labels (for all gatha numbers on the page) and any remaining `॥M॥`/`||M||` markers; replaces them with newlines and re-normalises via `_clean_preserve_newlines`.

**`(N)` markers in single gathas**: `_clean_verse_text` (called in `_parse_body_fields`) also strips `(N)` labels from every gatha, not just combined pages — so single-gatha prakrit/sanskrit text is always clean.

Anyavartha and teeka content are shared across all expanded gathas. Each expanded gatha gets `is_combined_page=True` and `related_gatha_numbers` listing the other gathas from the same page.

**Per-chunk `prakrit_verse_marker`**: the markers list captured up-front from the raw Prakrit text (see Step 3 note) is sliced per gatha — chunk *i* gets `prakrit_verse_markers[i]`. Scanning `base.prakrit_text` instead of the raw text would lose the last gatha's marker (because `_clean_verse_text` already stripped the trailing `॥M॥`), so the raw-text pre-scan is load-bearing for combined pages like `112-113.html` where canonical gatha 106 must carry marker `113`.

---

## Global kalash counter

The orchestrator tracks a `global_primary_kalash_counter` across all pages (sorted file order). Each page's primary teeka kalashes get sequential `global_kalash_index` values starting from where the previous page left off. This is the stable `kalash_number` used in Postgres and MongoDB.

---

## Output models (key types)

| Model | Description |
|---|---|
| `GathaExtract` | One individual gatha (after multi-page expansion) with all body + teeka fields |
| `KalashExtract` | One secondary-teeka standalone kalash page |
| `PrimaryTeeka` | kalash_san[], gatha_teeka_san, kalash_hindi[], kalash_word_meanings{}, gatha_teeka_bhaavarth_md |
| `SecondaryTeeka` | gatha_teeka_san, gatha_teeka_bhaavarth_md |
| `AnyavarthaItem` | full_anyavaarth (Hindi text only, darkRed fonts removed) + tagged_terms[] |
| `ShastraParseResult` | All gathas, secondary_kalashes, warnings, total file count |

Full model definitions: `workers/ingestion/nj/models.py`

---

## Golden output / CLI

The parser outputs a golden JSON envelope suitable for ingestion handoff:

```bash
python -m workers.ingestion.nj.cli parse \
  --config parser_configs/nj/samaysaar.yaml \
  --batch-offset 0 \
  --batch-limit 10 \
  --format golden
```

Default output path: `workers/ingestion/nj/tests/golden/{shastra_nk}_golden_o{offset}_l{limit}.json`

Golden filenames use the Hindi shastra natural key (e.g. `समयसार_golden_o0_l10.json`).

---

## Tests

```bash
# Unit tests (no DB, no NIKKYJAIN_LOCAL_PATH required for unit tests)
python -m pytest tests/workers/nj/ -v

# Integration tests (require NIKKYJAIN_LOCAL_PATH pointing to local nj repo clone)
export NIKKYJAIN_LOCAL_PATH="/path/to/nikkyjain.github.io"
python -m pytest tests/workers/nj/test_parse_page.py -v

# Full NJ suite — 72 tests pass (51 unit + 5 guarded integration + 16 apply unit)
python -m pytest tests/workers/nj/ -v
```

Test files:
- `test_parse_myitem_unit.py` — index extraction, adhikaar_number
- `test_classify_pages_unit.py` — page classification, preceding_primary_gatha
- `test_parse_page_unit.py` — body-level fields from fixtures
- `test_parse_primary_teeka_unit.py` — kalash extraction, gatha_teeka_san, bhaavarth
- `test_parse_secondary_teeka_unit.py` — secondary teeka extraction
- `test_html_to_markdown_unit.py` — node_to_markdown rules
- `test_orchestrator_unit.py` — end-to-end parse with fixtures
- `test_parse_page.py` — integration tests guarded by `NIKKYJAIN_LOCAL_PATH`
- `test_envelope.py` — envelope shape, natural keys, neo4j nodes/edges, idempotency contracts
- `test_apply_unit.py` — NFC normalization, cross-source merge, idempotency

---

## Key edge cases

| Case | Handling |
|---|---|
| Page not in either index | Logged as `WARN: unclassified page {filename}`, skipped |
| `div.gathaS` absent | `sanskrit_text = None`; no `gatha_sanskrit` doc written |
| No kalashes in steeka0 | `primary_teeka.kalash_san = []` |
| Kalash count mismatch (Hindi ≠ Sanskrit) | `WARN: kalash count mismatch on {filename}`; paired by position |
| BOM character `﻿` in text | Stripped from all extracted strings |
| Single-teeka shastra | `secondary_index = {}`; all pages classify as primary_gatha or skip |
| Multi-gatha text split fails | Falls back to keeping the original combined text per gatha |
| `(N)` mid-verse label in Prakrit/Sanskrit | Stripped by `_clean_verse_text` for all gathas; also by `_clean_gatha_chunk` for combined-page chunks |
| Hyphenated gatha_number is a range (e.g. `"098-100"`) | `_expand_gatha_numbers` expands 2-part hyphenated values as inclusive ranges and 3+-part values as explicit lists, so `"098-100"` becomes `["098","099","100"]` and `_split_combined_text_by_markers` uses N−1 = 2 verse-end markers as split points. |
| Verse-end marker number ≠ gatha number | Splitting is positional (finds first N−1 `||M||`/`॥M॥` regardless of M), so mismatched internal numbering (e.g. `॥20॥` on page 017-018) is handled correctly |
| Chhand marker missing `कलश-` prefix | Source HTML sometimes labels only the first marker as `(कलश-X)` and subsequent siblings as bare `(Y)` (e.g. samaysaar 016.html kalashes 12, 13). Marker detection uses a permissive regex `\(([^)]+)\)` inside a DarkSlateGray `<font>`; `_extract_chhand_type` strips an optional leading `कलश-`. Without this, multiple verses collapsed into a single kalash entry and the global kalash counter under-incremented, shifting subsequent kalashes onto the wrong gatha. |
| Sanskrit kalash newlines in `<br>`-separated nodes | `_parse_sanskrit_kalashes_from_nodes` (fallback path when kalashes are direct children of `steeka0`, not wrapped in a `div.gadya`) preserves `<br>` as `\n` and flushes via `_clean_preserve_newlines`, matching the gadya-path behaviour. |
| Kalash placed **before** the main Sanskrit teeka prose | Source pages like samaysaar `044-048.html` arrange `steeka0` as `intro → (कलश-X) → verse ॥N॥ → main Sanskrit teeka prose → <hr>` (kalash sits *between* a one-line intro and the main prose). `_parse_sanskrit_kalashes_from_nodes` now treats `॥N॥`/`||N||` as a hard kalash-close: after appending each text node while a kalash is open, it checks whether the accumulated text now ends with a verse-end marker and, if so, flushes and clears `current_type` so subsequent text nodes flow back into `prose_parts` (→ `gatha_teeka_san`). Without this, the trailing main teeka prose was absorbed into the kalash's `text_san`, which also stripped `_extract_verse_number` of its anchor and forced the kalash NK to fall back to the sequential `global_kalash_index` — causing kalash↔gatha attribution to drift. The gadya path is intentionally unchanged so the shared-marker multi-verse case (samaysaar `104.html` ॥६१॥+॥६२॥ under one `(कलश-अनुष्टुभ्)`) still accumulates both verses before `_split_kalash_verses` splits them. |
| Chhand marker with double-hyphen prefix `(कलश--X)` | Source occasionally uses `(कलश--शार्दूलविक्रीडित)` (double hyphen). `_extract_chhand_type` strips the `कलश-` prefix and then `lstrip("-")`s any residual leading hyphen so the chhand type comes out as `शार्दूलविक्रीडित`, not `-शार्दूलविक्रीडित`. |
| Shared chhand marker followed by multiple verses | Some pages (e.g. samaysaar `104.html` अनुष्टुभ्) have one `(कलश-X)` marker followed by **two consecutive verses** (`॥६१॥` then `॥६२॥`) without a second marker. `_split_kalash_verses` walks the collected chunk, splits on each `॥N॥`/`||N||` boundary, and emits one `KalashSanskritEntry` per verse — all inheriting the same `chhand_type`. Without this, verses 61+62 merged into one entry, undercounting kalashes and shifting subsequent kalashes (hindi side got orphaned onto the wrong gatha). |
| Bare `॥` / `||` verse-end (no digits) | Source occasionally ends a verse with a bare `॥` (e.g. samaysaar `123-125.html` gathas 119, 120). `_VERSE_END_MARKER_RE`, `_ANY_VERSE_MARKER_RE`, and `_TRAILING_VERSE_RE` accept either `॥N॥` or bare `॥`; alternation order keeps `॥N॥` preferred so digit markers still match as one unit. This unblocks multi-gatha splitting on pages where only a subset of verses have numbered end markers. |
| Hindi side has extra translation verses (e.g. `(हरिगीत)`) before the `(कलश)` block | `parse_primary_teeka` builds `san_by_verse = {kalash_san[i].verse_number → entry}` and, when walking `nodes_after`, only accepts a `b>div.gadya` as a Hindi kalash if its trailing ॥N॥ number matches a Sanskrit kalash's `verse_number`. Non-matching blocks (translations of preceding Prakrit gathas) fall through into `bhaavarth_nodes`. Matching entries inherit the Sanskrit kalash's `local_kalash_index` / `global_kalash_index` so pairing in `envelope.py` (`san_map`/`hi_map` keyed by `global_kalash_index`) lines up correctly. Without this, extra `(हरिगीत)` blocks on pages like samaysaar `014.html` shifted `hindi_counter` and the wrong Hindi entry paired with each Sanskrit kalash. |
| Secondary-only multi-gatha pages | Pages absent from the primary index but present in the secondary index with a hyphenated `gatha_number` (e.g. `131-133.html` → `"131-133"`) are now expanded by `parse_secondary_kalash_page`: it returns `list[KalashExtract]`, one per gatha number, splitting the prakrit text via `_split_combined_text_by_markers`. The shared `secondary_teeka` is copied to every entry. The orchestrator uses `secondary_kalashes.extend(...)` and passes `secondary_entry=secondary_index.get(filename)`. |

---

## Canonical kalash number

`kalash_number` is now derived from the source-of-truth `॥N॥` verse-end marker inside each kalash's text (Devanagari or ASCII digits, NFC-normalised). The new `verse_number: Optional[str]` field on `KalashSanskritEntry` and `KalashHindiEntry` carries this. The envelope (`envelope.py`) prefers `verse_number` for both the Mongo `kalash_number` field and the NK suffix (`…:कलश:{verse_number}`), falling back to the sequential `global_kalash_index` when the marker is absent. This makes NKs stable against parser undercounts and matches the source's printed kalash numbering.

## Anyavartha char offsets

When building `teeka_gatha_mapping` documents, the envelope now walks `full_anyavaarth` in source order and records each tagged term's `start_offset` / `end_offset` char positions. Because tagged terms are emitted in source order and `full_anyavaarth` is the same prose minus the bracketed source-word markers, a sequential cursor-search captures the correct span even when the same meaning string repeats in connecting prose. The UI uses these offsets directly to highlight, eliminating "n-th occurrence" guessing.

---

## Bhaavarth shortFont (Phase 1 — implemented 2026-06-10)

New module `workers/ingestion/nj/shortfont_parser.py` extracts `<span class=shortFont>` footnote glossaries from bhaavarth HTML and strips the inline `<sup>N</sup>` digit markers from the resulting Markdown.

### Models added (`models.py`)

| Model | Description |
|---|---|
| `ShortFontAnchor` | `start_offset`, `end_offset` (char positions in cleaned bhaavarth Markdown) |
| `ShortFontEntry` | `marker_number` (int), `marker_devanagari` (str), `anchor_text`, `meaning`, `is_definition` (bool), `occurrences: list[ShortFontAnchor]` |

`PrimaryTeeka.gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = []`
`SecondaryTeeka.gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = []`
`KalashHindiEntry.shortfont: list[ShortFontEntry] = []`

### `extract_shortfont(nodes, warnings)` contract

- Accepts `list[NavigableString | Tag]` (caller's already-collected bhaavarth nodes) so it is teeka-agnostic.
- Deep-copies the node list into a `<div>` wrapper before mutation — caller's BS4 tree is never modified.
- Returns `(cleaned_md: str, entries: list[ShortFontEntry])`.
- Offsets are relative to the post-conversion, NFC-normalised `cleaned_md`; validated by `cleaned_md[start:end] == anchor_text`.
- Asterisk markers (`<sup>*</sup>`) mapped to negative int keys (`*` → −1, `**` → −2) so they get unique slots without colliding with digit markers.
- Top-level `<sup>` siblings (e.g. panchaastikaya) handled by wrapping nodes into a single `<div>` before `find_all("sup")` — avoids missing sups that are direct siblings rather than nested children.
- Inline `**[word]**` shabdaarth headers are forced onto their own line via a `re.sub(r"(?<!\n)[ \t]*(\*\*\[)", r"\n\1", cleaned_md)` pass. Source HTML for some teekas (e.g. samaysaar gatha 9 jayasenacharya) emits multiple `<b>[word]</b> meaning … <b>[word]</b> meaning …` inline within a single paragraph; without the per-`[word]` line break, the UI `bhaavarth-segments` parser only detects the first as a compact entry and the shabdaarth chip component never renders. Plain prose paragraphs (e.g. panchaastikaya 005) contain no `**[` and are unaffected — `<br><br>` → `\n\n` continues to be the only paragraph break, and inline `<span class=notes>` / `<sup>` stay on the same line.

### Tests

New file `tests/workers/nj/test_shortfont_parser_unit.py` — covers: definition entries, bare-narrative footnotes, repeated markers, orphan handling (both directions), offset round-trip, `<span class=notes>` parentheticals left untouched, top-level sup siblings, asterisk markers, inline `**[word]**` line-splitting, and plain-prose paragraph preservation.

Full NJ suite: **105 tests green**.

---

## NJ Table extraction (Phase 2 — implemented 2026-06-10)

New module `workers/ingestion/nj/tables.py` extracts `<table>` blocks from bhaavarth HTML into first-class `ParsedTable` records with `table_type="index"`, and replaces each table in the bhaavarth nodes with a `[तालिका देखें](table://<natural_key>)` Markdown link.

### Natural-key format

```
table:nj:<parent_bhaavarth_nk>:<seq:02d>
```

`seq` is 1-indexed in DOM source order within the bhaavarth nodes. `parent_bhaavarth_nk` is the `GathaTeekaBhaavarth` or `KalashBhaavarth` node key.

### `extract_tables_from_bhaavarth()` contract

- Accepts `list[NavigableString | Tag]` plus `parent_natural_key`, `parent_kind`, `source_url` kwargs.
- Layout-only tables (`class="myAltColTable"` + single `<td>` + no inner `<table>`) are skipped.
- Caption: prefers `<caption>` tag; falls back to first row when it is a single non-empty `<th>` (irrespective of empty `<td class=emptyTableCell>` alongside it).
- Each extracted table is replaced inline with `<a class="nj-table-link" data-table-nk="{nk}">तालिका देखें</a>`.
- Returns `(mutated_nodes, parsed_tables)`.

### Markdown rendering

`workers/ingestion/nj/html_to_markdown.py` handles `<a class="nj-table-link">` and emits `[तालिका देखें](table://{nk})`. Shortfont anchor offsets are computed **after** table replacement so they remain valid.

### Integration points

- `parse_primary_teeka.py` and `parse_secondary_teeka.py` both call `extract_tables_from_bhaavarth` before `extract_shortfont`. `parse_page.py` computes the `parent_bhaavarth_nk` and passes it through.
- `models.py`: `PrimaryTeeka.tables: list[ParsedTable] = []` and `SecondaryTeeka.tables: list[ParsedTable] = []`. `ParsedTable` is imported from `workers.ingestion.jainkosh.models`.
- `envelope.py`: `would_write["tables"]` collects all parsed tables from all teeka types; `postgres:tables` idempotency contract added.

### Verified end-to-end (पंचास्तिकाय gatha 7)

```
NK: table:nj:पंचास्तिकाय:तात्पर्यवृत्ति:0:गाथा:टीका:भावार्थ:7:01
caption: प्रथम महाधिकार के द्वितीय अंतराधिकार की सारिणी
header_rows: 1, table_type: index
```

### Tests

- `tests/workers/nj/test_table_parser_unit.py` — 10 unit tests covering extraction, NK format, caption detection, header_rows, layout-wrapper skip, and shortfont offset validity.
- `tests/workers/nj/test_envelope.py` extended with 6 table-related assertions.

Full NJ suite: **101 tests green**.

---

## Compound identifier support (Phase 2 — implemented 2026-06-16)

Some shastras (e.g. **परमात्मप्रकाश**) identify each gatha by more than one field
(`अधिकार` + `परमात्मप्रकाशगाथा`). The compound identifier scheme is declared in
`parser_configs/_manual_configs/shastra.json` via the `gatha_identifier` key (comma-separated
field list). When `gatha_identifier` is absent, behaviour is unchanged for that shastra.

### Bare `mySel.append` format

परमात्मप्रकाश's `myItem.js` has **no `<optgroup>` wrapper** — options are appended directly:

```js
mySel.append("<option value='1-001.html'><b>1-001</b> - आत्मस्वरूप</option>")
```

A new regex `_OPTION_BARE_RE` in `parse_myitem.py` matches this form. The existing
`_OPTION_RE` (optgroup path) is unchanged.

### `_split_leading_adhikaar`

Gatha-number values like `"1-001"` and `"1-019-021"` carry an adhikaar prefix. The helper
`_split_leading_adhikaar(value)` strips it and returns `(adhikaar_int, canonical_gatha_str)`.

**Heuristic**: the prefix is only stripped when `len(prefix_digits) < len(first_trailing_segment)`.
This distinguishes `"1-001"` (1 < 3 → split) from `"009-010"` (3 == 3 → keep as range).

Applied in both `_OPTION_RE` and `_OPTION_BARE_RE` paths. For the optgroup path, the
optgroup-derived `current_adhikaar_number` takes precedence over the value-parsed `adh_num`.

### `NJAdhikaar` / `ShastraConfig.adhikaars`

`config.py` now accepts an optional `adhikaars: list[NJAdhikaar]` in the `shastra:` block.
After `parse_myitem` returns its indexes, the orchestrator calls `_enrich_adhikaar_hi` to
fill in the Hindi adhikaar name from config when the index entry doesn't carry one (which
happens in the bare-append layout since there are no optgroup labels).

परमात्मप्रकाश config (`parser_configs/nj/parmatmaprakash.yaml`) declares:
```yaml
adhikaars:
  - { number: 1, name_hi: "परमात्म-अधिकार" }
  - { number: 2, name_hi: "मोक्ष-अधिकार" }
```

### `identifier_values` field

`GathaExtract.identifier_values: dict[str, str]` and `KalashExtract.identifier_values`
carry the structured compound identifier for each extract. Built by `_build_identifier_values`
in `orchestrator.py` after page parsing:

```python
{"अधिकार": "1", "परमात्मप्रकाशगाथा": "001"}
```

Fields are declared in declaration order from `shastra.json`. When `gatha_identifier` is
absent (single-identifier shastra), `identifier_values` is `{}`.

Phase 3 (envelope) uses these values to build the compound NK suffix.

### Known edge case update

| Case | Handling |
|---|---|
| परमात्मप्रकाश bare `mySel.append` (no optgroups) | `_OPTION_BARE_RE` in `parse_myitem._parse_block`; adhikaar number extracted from value prefix via `_split_leading_adhikaar` |
| Gatha-range value vs adhikaar-prefix value (`009-010` vs `1-001`) | `_split_leading_adhikaar` only strips prefix when its digit width is strictly less than the first trailing segment |

---

## Known open items

- `ingest_nj_apply.py` script (§5 of ingestion doc) is specified but not yet wired as a standalone CLI — ingestion is done via `apply.py` + `envelope.py` + manual invocation.
- JK parser must adopt `गाथा` label in gatha NKs for cross-source Neo4j MERGE to work correctly (currently `समयसार:गाथा:8` in NJ vs `समयसार:8` in JK).
