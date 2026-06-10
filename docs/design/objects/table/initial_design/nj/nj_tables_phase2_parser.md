# NJ Tables — Phase 2: Parser

Extract `<table>` blocks from NJ bhaavarth HTML into first-class `ParsedTable` records (with `table_type="index"`) and **replace** each table's serialised HTML in the bhaavarth Markdown with a `[तालिका देखें](table://<natural_key>)` link so the UI can render an inline opener.

Depends on: [Phase 1 — Schema](./nj_tables_phase1_schema.md)
Parent wiki: [../README.md](../../README.md)
NJ parser wiki: [../../../data_sources/nikkyjain/nj_parser.md](../../../../data_sources/nikkyjain/nj_parser.md)

---

## 1. Scope

Tables appear in:
1. `div#teeka0` primary teeka bhaavarth (the `bhaavarth_nodes` list collected in `parse_primary_teeka.py`).
2. `div#teeka1` secondary teeka bhaavarth (`parse_secondary_teeka.py`).
3. Standalone secondary kalash pages (`parse_secondary_teeka.parse_secondary_kalash_page`).

Out of scope for Phase 2:
- Tables outside bhaavarth (e.g. inside `div.steeka#steeka0` Sanskrit prose) — none observed in sample pages.
- `<table class="myAltColTable">` used as a layout wrapper — only structural `<table>` with `<tr>/<td>` content qualifies (heuristic: ≥2 `<tr>` and not the page's outer layout wrapper).

---

## 2. Natural-key format

Reuse the parent wiki format but with `nj` source:

```
table:nj:<parent_natural_key>:<seq:02d>
```

`parent_natural_key` is the **GathaTeekaBhaavarth** NK (primary/secondary):
```
{publication_nk}:गाथा:टीका:भावार्थ:{gatha_num}            # primary
{publication_nk}:गाथा:टीका:भावार्थ:{gatha_num}            # secondary
{publication_nk}:कलश:भावार्थ:{kalash_num}                 # standalone kalash bhaavarth
```

`parent_kind = "gatha_teeka_bhaavarth"` for gatha bhaavarth, `"kalash_bhaavarth"` for standalone kalash. (Both are already supported in `PARENT_KIND_TO_LABEL` from the JK apply layer.)

`seq` is 1-indexed in DOM source order within the bhaavarth nodes.

---

## 3. New module — `workers/ingestion/nj/tables.py`

Mirrors `workers/ingestion/jainkosh/tables.py` but BS4-based (NJ uses BS4 everywhere, not selectolax).

```python
def extract_tables_from_bhaavarth(
    nodes: list[NavigableString | Tag],
    *,
    parent_natural_key: str,
    parent_kind: Literal["gatha_teeka_bhaavarth", "kalash_bhaavarth"],
    source_url: str | None,
) -> tuple[list[NavigableString | Tag], list[ParsedTable]]:
    """Walk nodes; for each <table> at this level (or nested anywhere inside
    a node that contains exactly one structural table), replace it with a
    placeholder <a class='nj-table-link' data-table-nk='<nk>'>तालिका देखें</a>
    anchor and emit a ParsedTable.

    Returns (mutated_nodes, parsed_tables). The caller passes the mutated
    nodes to extract_shortfont() so the placeholder becomes a Markdown link.
    """
```

### Step-by-step

1. Deep-copy node list into a `<div>` wrapper (same pattern as `extract_shortfont`).
2. `soup.find_all("table")` in DOM order.
3. For each table:
   - Skip if it has `<= 1` `<tr>` or if it's the outermost layout wrapper (`class="myAltColTable"` containing only a single nested `<td>` with no inner `<table>`).
   - Build `seq = current_index + 1` (per-parent counter).
   - Build `natural_key` per §2.
   - Parse cells via a BS4 walker (`<tr>` → `<td>/<th>` → `_clean(get_text(' '))`, NFC, `<br>` → `\n`). Pad rows to uniform width.
   - Count leading header rows (all-`<th>` rows).
   - Caption: prefer `<caption>` tag, else the first row when it is a single-cell `<th>` that spans the table (e.g. *प्रथम महाधिकार के द्वितीय अंतराधिकार की सारिणी* in the sample). If used as caption, exclude it from `header_rows`.
   - Mentions: walk `<a>` — `/wiki/<kw>` → keyword nk (none expected on NJ but support symmetrically); fragment anchors ignored on NJ.
   - `plaintext = " ".join(non-empty cells)`.
   - `raw_html = str(table)` cleaned of pure-whitespace text runs (same `_clean_raw_html` regex as JK module — copy and trim).
   - Build `ParsedTable(table_type="index", ...)`.
   - Replace the `<table>` element with `<a class="nj-table-link" data-table-nk="{nk}">तालिका देखें</a>` (BS4 `table.replace_with(new_tag)`).
4. Return the mutated wrapper's children list + `parsed_tables`.

### Markdown rendering of the placeholder

In `workers/ingestion/nj/html_to_markdown.py`, add an `<a>` handler:

```python
if tag == "a":
    classes = node.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if "nj-table-link" in classes:
        nk = node.get("data-table-nk", "")
        return f"[तालिका देखें](table://{nk})"
    # default: pass through children
    return children_md
```

Result: `cleaned_md` returned by `extract_shortfont` will already contain the inline Markdown link in place of the `<table>` HTML. Shortfont anchor offsets are computed **after** the table replacement so they stay valid.

---

## 4. Integration points

### `parse_primary_teeka.parse_primary_teeka`

```python
# after `bhaavarth_nodes` is collected, before extract_shortfont():
bhaavarth_nodes, parsed_tables_primary = extract_tables_from_bhaavarth(
    bhaavarth_nodes,
    parent_natural_key=parent_bhaavarth_nk,  # plumbed in via new arg
    parent_kind="gatha_teeka_bhaavarth",
    source_url=None,
)
cleaned_bhaavarth_md, shortfont_entries = extract_shortfont(bhaavarth_nodes)
# expose parsed_tables_primary on PrimaryTeeka.tables
```

The caller (`parse_page` → `parse_primary_teeka`) must now pass the computed bhaavarth NK. Compute it at the call-site (it already builds the gatha NK + publication NK), don't duplicate the format in the teeka parser.

Same surgery for `parse_secondary_teeka` and `parse_secondary_kalash_page`.

### `models.py`

```python
class PrimaryTeeka(BaseModel):
    ...
    tables: list[ParsedTable] = []

class SecondaryTeeka(BaseModel):
    ...
    tables: list[ParsedTable] = []

class KalashExtract(BaseModel):
    ...
    # tables already inside SecondaryTeeka.tables
```

`ParsedTable` is imported from `workers.ingestion.jainkosh.models` (or moved to a shared location in Phase 1).

### `envelope.py`

- Add `"tables": []` to the `would_write` skeleton.
- After building each gatha's mongo fragments, append `g.primary_teeka.tables` and `g.secondary_teeka.tables` (model_dump) to `ww["tables"]`.
- Same for secondary kalashes.
- Add idempotency contract:
  ```python
  "postgres:tables": {
      "conflict_key": ["natural_key"],
      "on_conflict": "do_update",
      "fields_replace": ["table_type","caption","raw_html_doc_id","seq","parent_natural_key","parent_kind"],
      "fields_append": [], "fields_skip_if_set": [],
      "stores": ["postgres:tables","mongo:tables","neo4j:Table"],
  },
  ```

---

## 5. Tests (`tests/workers/nj/`)

- `test_table_parser_unit.py`
  - `test_extracts_single_table_from_bhaavarth_nodes` (use fixture from sample `007.html`).
  - `test_table_replaced_by_md_link` — asserts `cleaned_md` contains `[तालिका देखें](table://table:nj:...:01)` and does **not** contain `<table` or any cell text.
  - `test_natural_key_format_and_seq_per_parent`.
  - `test_caption_detected_from_single_th_first_row`.
  - `test_header_rows_count`.
  - `test_table_type_is_index`.
  - `test_no_table_when_only_layout_wrapper`.
  - `test_shortfont_offsets_remain_valid_after_table_replacement`.

- `tests/workers/nj/fixtures/` — copy a slice of `007.html` containing the सारिणी table + the surrounding bhaavarth paragraph; commit as `panchaastikaay_007_fragment.html`.

- `test_envelope.py` — extend to assert `would_write.tables` contains the parsed table and that the bhaavarth_md contains the link.

### Run

```bash
export NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io
python -m pytest tests/workers/nj/ -v
```

Regenerate goldens if needed:
```bash
python -m workers.ingestion.nj.cli parse --config parser_configs/nj/panchastikaya.yaml --batch-offset 6 --batch-limit 1 --format golden
```

---

## 6. Done when

- `WouldWriteEnvelope.tables` has the expected `ParsedTable` for `007.html` gatha 7.
- `gatha_teeka_bhaavarth_md` (and shortfont offsets) reference the table only via the inline Markdown link.
- All NJ unit + envelope tests green.
- No apply / API / UI changes yet (Phase 3 / Phase 4).

---

## 7. Implementation Notes

**Implemented:** 2026-06-10

### Files changed
- `workers/ingestion/nj/tables.py` — new module with `extract_tables_from_bhaavarth()`
- `workers/ingestion/nj/html_to_markdown.py` — added `<a class="nj-table-link">` handler
- `workers/ingestion/nj/models.py` — added `tables: list[ParsedTable]` to `PrimaryTeeka` and `SecondaryTeeka`; imported `ParsedTable` from jainkosh models
- `workers/ingestion/nj/parse_primary_teeka.py` — added `parent_bhaavarth_nk` keyword arg; calls `extract_tables_from_bhaavarth` before `extract_shortfont`
- `workers/ingestion/nj/parse_secondary_teeka.py` — same as above; also handles `kalash_bhaavarth` parent_kind for standalone kalash pages
- `workers/ingestion/nj/parse_page.py` — computes `parent_bhaavarth_nk` for primary and secondary teekas; passes correct `kalash_bhaavarth` NK for `parse_secondary_kalash_page`
- `workers/ingestion/nj/envelope.py` — added `"tables": []` key to `would_write`; appends tables from all three teeka types; added `postgres:tables` idempotency contract
- `tests/workers/nj/fixtures/panchaastikaay_007_fragment.html` — fixture with सारिणी table
- `tests/workers/nj/test_table_parser_unit.py` — 10 unit tests (all green)
- `tests/workers/nj/test_envelope.py` — 6 new envelope tests (all green)

### Divergences from spec
- `parent_bhaavarth_nk` is `None` when no teeka config is present (graceful no-op); the spec assumed it would always be passed.
- The `_is_layout_only` check uses `myAltColTable` class + single `<td>` + no inner `<table>` as the layout wrapper heuristic. In 007.html the `myAltColTable` is a content table (9+ `<tr>`), so it is correctly extracted.
- Caption heuristic: first row where exactly one non-empty cell is a `<th>` (irrespective of empty `<td class=emptyTableCell>` alongside it).

### Verified end-to-end
```
Tables found: 1
NK: table:nj:पंचास्तिकाय:तात्पर्यवृत्ति:0:गाथा:टीका:भावार्थ:7:01
caption: प्रथम महाधिकार के द्वितीय अंतराधिकार की सारिणी
header_rows: 1, table_type: index
Secondary bhaavarth MD has table link: True, no raw <table>: True
```
