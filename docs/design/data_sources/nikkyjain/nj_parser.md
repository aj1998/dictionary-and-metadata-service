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
- `div.gatha` → `prakrit_text` (with `॥N॥` verse markers stripped from tail)
- `div.gathaS` → `sanskrit_text` (optional)
- `div.gadya` (outside teeka divs) → `hindi_chhands[]` (type defaults to `"harigeet"`)
- `div.paragraph` containing `अन्वयार्थ` → `anyavartha` (full text + tagged term list)

**Primary teeka** (`div#teeka0`, only if it starts with the primary teeka label):
- `div.steeka#steeka0` → structural walk to extract `kalash_san[]` (by `<font color=DarkSlateGray>` `(कलश-...)` markers) and `gatha_teeka_san` prose
- Nodes after `steeka0` → `kalash_hindi[]`, `kalash_word_meanings{}`, `gatha_teeka_bhaavarth_md`
- Classification is **purely structural** — no hardcoded text markers

**Secondary teeka** (`div#teeka1`): extracts Sanskrit (before `hr.type_7`) and Hindi bhaavarth after.

**Secondary-only pages** (pages not in primary index): `div#teeka0` contains the secondary teeka content; body-level fields still parsed normally.

### Step 4 — Multi-gatha page expansion

Pages like `009-010.html` (gatha_number = `"009-010"`) produce **one `GathaExtract` per individual gatha**. The combined text is split by verse-number markers (`॥9॥`, `॥९॥`, `||9||`, `||९||`). Anyavartha and teeka content are shared across all expanded gathas.

Each expanded gatha gets `is_combined_page=True` and `related_gatha_numbers` listing the other gathas from the same page.

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

---

## Known open items

- `ingest_nj_apply.py` script (§5 of ingestion doc) is specified but not yet wired as a standalone CLI — ingestion is done via `apply.py` + `envelope.py` + manual invocation.
- JK parser must adopt `गाथा` label in gatha NKs for cross-source Neo4j MERGE to work correctly (currently `समयसार:गाथा:8` in NJ vs `समयसार:8` in JK).
