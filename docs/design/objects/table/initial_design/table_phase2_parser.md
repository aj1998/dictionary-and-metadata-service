# Phase 2 — Table: JainKosh parser emits Table nodes

**Owner**: backend / parsers
**Prereqs**: [Phase 1](./table_phase1_schema.md) merged.
**Scope**: `workers/ingestion/jainkosh/` only. No apply, no UI.

## Goal

Each `Block(kind="table", raw_html=...)` produced today by `workers/ingestion/jainkosh/tables.py` must (a) stay inline inside its containing `topic_extract` / `keyword_definition` block list for back-compat, AND (b) emit a parallel first-class `Table` node into the `WouldWriteEnvelope` with parsed cell matrix, caption, and mentioned-keyword/topic edges.

## 1. New parser models

In `workers/ingestion/jainkosh/models.py`, add:

```python
class ParsedTable(BaseModel):
    natural_key: str
    seq: int
    parent_natural_key: str
    parent_kind: Literal["topic", "keyword", "gatha", "gatha_teeka",
                          "gatha_teeka_bhaavarth", "kalash",
                          "kalash_bhaavarth", "page"]
    source_url: str | None = None
    caption: list[LangText] = []
    raw_html: str
    cells: list[list[str]] = []
    header_rows: int = 0
    plaintext: str = ""
    mentioned_keyword_natural_keys: list[str] = []
    mentioned_topic_natural_keys: list[str] = []
```

Add `tables: list[ParsedTable] = []` to `WouldWriteEnvelope`.

## 2. Parsing logic — `workers/ingestion/jainkosh/tables.py`

Extend `parse_table_block()` (currently returns a `Block(kind="table", raw_html=...)`) to additionally return a `ParsedTable`:

```python
def parse_table_block(table_node, config, *, parent_natural_key, parent_kind,
                     seq, source_url, preceding_heading) -> tuple[Block, ParsedTable]: ...
```

Steps:

1. **raw_html**: existing `_clean_raw_html()` output. Preserve as-is.
2. **cells**: walk `<tr>` / `<td>`/`<th>`. Each cell's plain text = `HTMLParser(cell.html).text(strip=True)`, NFC-normalized. `<br>` becomes `\n`. Pad short rows with `''` so the matrix is rectangular (max-cols width).
3. **header_rows**: count leading rows whose cells are all `<th>` (or have `class="header"` if site uses that — check fixtures).
4. **caption**: prefer an inline `<caption>` if present; else use `preceding_heading` (the section heading the parser is already tracking — typically the topic heading text). Multilingual = `[{lang:"hin", script:"Deva", text: ...}]` after NFC.
5. **plaintext**: `" ".join(cell for row in cells for cell in row if cell)` collapsed to single spaces.
6. **mentioned_keyword_natural_keys / mentioned_topic_natural_keys**: walk `<a>` tags in the raw HTML. Resolve `/wiki/<keyword>` hrefs to keyword naturalKeys; resolve hash anchors (`#<topic-slug>`) to topic naturalKeys using the same logic `refs.py` / `parse_subsections.py` already use for `extracted_keyword_natural_keys` in `topic_extracts`. Reuse helpers; do not fork the resolution code.
7. **naturalKey**: `f"table:{source}:{parent_natural_key}:{seq:02d}"` with `source = "jainkosh"`.

`seq` is assigned by the caller — it owns a counter per parent.

## 3. Wiring into the envelope

In the callers that currently emit `Block(kind="table", ...)` (look at `parse_subsections.py`, the topic-extract and keyword-definition builders), do:

1. Keep the existing inline `Block` in `blocks[]` (no change for back-compat).
2. Append the `ParsedTable` to `envelope.tables` with the correct `parent_natural_key` and `parent_kind` (the natural_key + kind of the topic/keyword that owns the block being walked).
3. Increment a parser-local seq counter keyed by `parent_natural_key`.

## 4. Config

`workers/ingestion/jainkosh/config.py` already has `TableExtractionConfig.extraction_strategy: Literal["raw_html_only", "raw_html_plus_rows"]`. Default it to `"raw_html_plus_rows"` for JainKosh going forward. Add:

```python
class TableExtractionConfig(BaseModel):
    ...
    emit_first_class_node: bool = True   # new — gates Phase 2 emission
    parse_cells: bool = True
    parse_mentions: bool = True
```

When `emit_first_class_node=False`, parser behaves as before (inline block only).

## 5. Goldens

`workers/ingestion/jainkosh/tests/golden/*.json` — regenerate. The `द्रव्य.json` fixture contains the `3.10` topic with one table — expect a corresponding entry in `envelope.tables[]`. Add a snapshot for the table's `cells`, `caption`, and `mentioned_*` arrays.

Refresh stats: `python scripts/golden_stats.py` and update the table in the root README's "JainKosh Parser" section to include a `Table` column (under Nodes) and a `CONTAINS_TABLE` column (under Edges).

## 6. Unit tests

`tests/workers/jainkosh/` — add:

- `test_table_parser.py::test_parses_cell_matrix_from_fixture` — uses a small inline HTML fixture (no network), asserts cells, header_rows, caption.
- `test_table_parser.py::test_collects_mentioned_keywords_and_topics` — table with `<a href="/wiki/जीव">` and `<a href="#बहिरात्मादि_3_भेद">`.
- `test_table_parser.py::test_natural_key_and_seq` — two tables under same topic get `:01` and `:02`.
- `test_envelope_includes_tables` — full small fixture round-trip → `envelope.tables` populated.
- Re-snapshot `tests/workers/jainkosh/test_golden_envelope.py` against the refreshed golden JSONs.

```bash
python -m pytest tests/workers/jainkosh/ -v
```

## 7. Doc updates

- [`docs/design/data_sources/jainkosh/parser.md`](../../data_sources/jainkosh/parser.md) — new section "Table extraction": describes `ParsedTable`, naturalKey scheme, mention resolution, the inline-block-plus-first-class-node duality.
- [`docs/design/data_sources/jainkosh/ingestion.md`](../../data_sources/jainkosh/ingestion.md) — add `WouldWriteEnvelope.tables: list[ParsedTable]` to the envelope schema section; the actual apply behaviour comes in Phase 3.
- [`README.md`](../../../../README.md) (root) — regenerate the JainKosh Parser summary tables (Nodes + Edges columns) via `scripts/golden_stats.py`.

## 8. Definition of Done

- [ ] `parse_table_block()` returns both inline `Block` and `ParsedTable`.
- [ ] Envelope JSON has top-level `tables[]` array.
- [ ] All four parser unit tests pass.
- [ ] Goldens regenerated; `pytest tests/workers/jainkosh/` green.
- [ ] Parser doc updated; root README stats refreshed.

## 9. Implementation notes

- `ParsedTable` re-uses the existing `Multilingual` model (renamed `LangText` in spec) for `caption` entries. No new type added.
- `parse_table_block()` and `parse_table_block_from_html()` both live in `tables.py`. The envelope-building path uses the `_from_html` variant since DOM nodes are no longer available at envelope-build time; cells/mentions are re-parsed from `block.raw_html` via `HTMLParser`.
- `_collect_parsed_tables()` in `envelope.py` is called from `build_envelope()`. It walks definitions, `extra_blocks`, and all subsections in source order, maintaining a per-parent seq counter keyed by `parent_natural_key`.
- `table.extraction_strategy` YAML default changed to `"raw_html_plus_rows"` (was `"raw_html_only"`). The `block.table_rows` field still returns `[]` (placeholder from original `_extract_rows`) — full row parsing now lives in `ParsedTable.cells`. This is intentional: `block.table_rows` is a legacy field from before `ParsedTable` existed; in Phase 3 it will be deprecated in favour of `ParsedTable.cells`.
- Topic natural_keys from `#<anchor>` hrefs are stored as anchor text strings (e.g. `"बहिरात्मादि_3_भेद"`). Phase 3 will resolve these to full natural keys after the topic tree is built.
- Goldens regenerated with `--frozen-time 2026-05-04T00:00:00Z`. All fixtures now have a top-level `"tables": [...]` array; `द्रव्य.json` has one table entry.

**Definition of Done checklist:**

- [x] `parse_table_block()` returns both inline `Block` and `ParsedTable`.
- [x] Envelope JSON has top-level `tables[]` array.
- [x] All four parser unit tests pass (6 tests total, including 2 extra coverage tests).
- [x] Goldens regenerated; `pytest tests/workers/jainkosh/` green (590 tests).
- [x] Parser doc updated (§6.5 and §13); ingestion doc updated (new `WouldWriteEnvelope.tables` section).
