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
- `div.gatha` → `prakrit_text` — cleaned by `_clean_verse_text`: strips `(N)` mid-verse line-number labels (ASCII and Devanagari digits), strips trailing `॥N॥`/`||N||` verse-end markers.
- `div.gathaS` → `sanskrit_text` (optional) — same `_clean_verse_text` pass applied.
- `div.gadya` (outside teeka divs) → `hindi_chhands[]` (type defaults to `"harigeet"`)
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
| Shared chhand marker followed by multiple verses | Some pages (e.g. samaysaar `104.html` अनुष्टुभ्) have one `(कलश-X)` marker followed by **two consecutive verses** (`॥६१॥` then `॥६२॥`) without a second marker. `_split_kalash_verses` walks the collected chunk, splits on each `॥N॥`/`||N||` boundary, and emits one `KalashSanskritEntry` per verse — all inheriting the same `chhand_type`. Without this, verses 61+62 merged into one entry, undercounting kalashes and shifting subsequent kalashes (hindi side got orphaned onto the wrong gatha). |
| Bare `॥` / `||` verse-end (no digits) | Source occasionally ends a verse with a bare `॥` (e.g. samaysaar `123-125.html` gathas 119, 120). `_VERSE_END_MARKER_RE`, `_ANY_VERSE_MARKER_RE`, and `_TRAILING_VERSE_RE` accept either `॥N॥` or bare `॥`; alternation order keeps `॥N॥` preferred so digit markers still match as one unit. This unblocks multi-gatha splitting on pages where only a subset of verses have numbered end markers. |
| Secondary-only multi-gatha pages | Pages absent from the primary index but present in the secondary index with a hyphenated `gatha_number` (e.g. `131-133.html` → `"131-133"`) are now expanded by `parse_secondary_kalash_page`: it returns `list[KalashExtract]`, one per gatha number, splitting the prakrit text via `_split_combined_text_by_markers`. The shared `secondary_teeka` is copied to every entry. The orchestrator uses `secondary_kalashes.extend(...)` and passes `secondary_entry=secondary_index.get(filename)`. |

---

## Canonical kalash number

`kalash_number` is now derived from the source-of-truth `॥N॥` verse-end marker inside each kalash's text (Devanagari or ASCII digits, NFC-normalised). The new `verse_number: Optional[str]` field on `KalashSanskritEntry` and `KalashHindiEntry` carries this. The envelope (`envelope.py`) prefers `verse_number` for both the Mongo `kalash_number` field and the NK suffix (`…:कलश:{verse_number}`), falling back to the sequential `global_kalash_index` when the marker is absent. This makes NKs stable against parser undercounts and matches the source's printed kalash numbering.

## Anyavartha char offsets

When building `teeka_gatha_mapping` documents, the envelope now walks `full_anyavaarth` in source order and records each tagged term's `start_offset` / `end_offset` char positions. Because tagged terms are emitted in source order and `full_anyavaarth` is the same prose minus the bracketed source-word markers, a sequential cursor-search captures the correct span even when the same meaning string repeats in connecting prose. The UI uses these offsets directly to highlight, eliminating "n-th occurrence" guessing.

---

## Known open items

- `ingest_nj_apply.py` script (§5 of ingestion doc) is specified but not yet wired as a standalone CLI — ingestion is done via `apply.py` + `envelope.py` + manual invocation.
- JK parser must adopt `गाथा` label in gatha NKs for cross-source Neo4j MERGE to work correctly (currently `समयसार:गाथा:8` in NJ vs `समयसार:8` in JK).
