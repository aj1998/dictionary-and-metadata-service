"""Extract <table> blocks from NJ bhaavarth nodes and replace with Markdown placeholder links."""

from __future__ import annotations

import copy
import logging
import re
import unicodedata
from typing import Literal

from bs4 import BeautifulSoup, NavigableString, Tag

from workers.ingestion.jainkosh.models import Multilingual, ParsedTable

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"[\t\n\r\f\v ]+")
_MULTI_SPACE_RE = re.compile(r" {2,}")
_RAW_HTML_TEXT_RUN_RE = re.compile(r"(>)([^<]*)(<)")


def _clean_raw_html(html: str) -> str:
    """Collapse pure-whitespace text runs between tags."""
    def _collapse(m: re.Match[str]) -> str:
        left, run, right = m.group(1), m.group(2), m.group(3)
        if not run:
            return left + run + right
        collapsed = _WS_RE.sub(" ", run).strip()
        return (left + right) if not collapsed else (left + collapsed + right)
    return _RAW_HTML_TEXT_RUN_RE.sub(_collapse, html)


def _cell_text(cell: Tag) -> str:
    """Plain text from a <td>/<th>: <br> → \\n, NFC-normalized."""
    html = str(cell)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ").replace("&#xA0;", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = unicodedata.normalize("NFC", text)
    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _is_structural_table(table: Tag) -> bool:
    """Return True if table has ≥2 <tr> rows (i.e. it's not a trivial wrapper)."""
    return len(table.find_all("tr")) >= 2


def _is_layout_only(table: Tag) -> bool:
    """Return True for the single-<td>-no-inner-table layout wrapper pattern."""
    classes = table.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if "myAltColTable" not in classes:
        return False
    all_tds = table.find_all(["td", "th"])
    if len(all_tds) != 1:
        return False
    return table.find("table") is None


def _parse_cells(table: Tag) -> tuple[list[list[str]], int, str | None]:
    """Return (cells_matrix, header_rows, caption).

    Caption detection: if the first row has exactly one non-empty cell and it's a
    <th>, treat its text as the caption and exclude that row from header_rows.
    """
    # Build a row-major grid that respects rowspan/colspan: a spanned cell's
    # text is duplicated into every (row, col) position it occupies so the
    # resulting matrix stays rectangular and visually matches the source.
    trs = [tr for tr in table.find_all("tr") if tr.find_all(["td", "th"])]
    rows: list[list[str]] = [[] for _ in trs]
    # pending[col_index] = (text, remaining_rowspan) for cells continuing down
    pending: dict[int, tuple[str, int]] = {}

    def _span(cell: Tag, attr: str) -> int:
        try:
            v = int(str(cell.get(attr) or "1").strip())
            return v if v > 0 else 1
        except ValueError:
            return 1

    for r, tr in enumerate(trs):
        col = 0
        cells_in_row = tr.find_all(["td", "th"])
        ci = 0
        while ci < len(cells_in_row) or any(rem > 0 for _, rem in pending.values()):
            if col in pending and pending[col][1] > 0:
                text, rem = pending[col]
                rows[r].append(text)
                pending[col] = (text, rem - 1)
                if pending[col][1] == 0:
                    del pending[col]
                col += 1
                continue
            if ci >= len(cells_in_row):
                break
            cell = cells_in_row[ci]
            ci += 1
            text = _cell_text(cell)
            cs = _span(cell, "colspan")
            rs = _span(cell, "rowspan")
            for k in range(cs):
                rows[r].append(text)
                if rs > 1:
                    pending[col + k] = (text, rs - 1)
            col += cs

    rows = [r for r in rows if r]
    if not rows:
        return [], 0, None

    # Caption heuristic: first row has exactly one non-empty <th> (possibly alongside empty cells)
    caption: str | None = None
    caption_row_index: int | None = None
    first_tr = table.find("tr")
    if first_tr:
        cells_in_first = first_tr.find_all(["td", "th"])
        non_empty_cells = [c for c in cells_in_first if _cell_text(c).strip()]
        if (
            len(non_empty_cells) == 1
            and non_empty_cells[0].name == "th"
        ):
            caption = unicodedata.normalize("NFC", _cell_text(non_empty_cells[0]).strip())
            caption_row_index = 0

    if caption_row_index is not None:
        rows = rows[1:]

    # Pad rows to uniform width
    if rows:
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]

    # Count leading all-<th> rows (after caption exclusion)
    header_rows = 0
    in_header = True
    effective_trs = [
        tr for tr in table.find_all("tr")
    ]
    # Skip the caption row when counting headers
    if caption_row_index is not None and effective_trs:
        effective_trs = effective_trs[1:]
    for tr in effective_trs:
        cells = tr.find_all(["td", "th"])
        if cells and in_header and all(c.name == "th" for c in cells):
            header_rows += 1
        else:
            in_header = False

    return rows, header_rows, caption


def _extract_mentions(table: Tag) -> list[str]:
    """Return mentioned keyword natural keys from /wiki/<kw> anchors."""
    from urllib.parse import unquote
    nks: list[str] = []
    seen: set[str] = set()
    for a in table.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.startswith("/wiki/"):
            path = href[len("/wiki/"):].split("#")[0]
            kw = unicodedata.normalize("NFC", unquote(path, encoding="utf-8"))
            if kw and kw not in seen:
                seen.add(kw)
                nks.append(kw)
    return nks


def extract_tables_from_bhaavarth(
    nodes: list[NavigableString | Tag],
    *,
    parent_natural_key: str,
    parent_kind: Literal["gatha_teeka_bhaavarth", "kalash_bhaavarth"],
    source_url: str | None,
) -> tuple[list[NavigableString | Tag], list[ParsedTable]]:
    """Walk nodes; for each structural <table> replace it with a placeholder <a> and emit a ParsedTable.

    Returns (mutated_nodes, parsed_tables). The caller passes the mutated nodes to
    extract_shortfont() so the placeholder becomes a Markdown link.
    """
    if not nodes:
        return nodes, []

    # Wrap a deep copy so we can mutate freely
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    assert wrapper is not None
    for n in nodes:
        wrapper.append(copy.deepcopy(n))

    all_tables = wrapper.find_all("table")
    parsed_tables: list[ParsedTable] = []
    seq = 0

    for table in all_tables:
        if not _is_structural_table(table):
            logger.debug("tables.py: skipping table with <2 <tr> inside %s", parent_natural_key)
            continue
        if _is_layout_only(table):
            logger.debug("tables.py: skipping layout-only myAltColTable inside %s", parent_natural_key)
            continue

        seq += 1
        natural_key = f"table:nj:{parent_natural_key}:{seq:02d}"

        cells, header_rows, caption_text = _parse_cells(table)

        caption = []
        if caption_text:
            caption = [Multilingual(lang="hin", script="Deva", text=caption_text)]

        plaintext = _MULTI_SPACE_RE.sub(
            " ",
            " ".join(cell for row in cells for cell in row if cell.strip()),
        ).strip()

        raw_html = _clean_raw_html(str(table))

        mentioned_kw_nks = _extract_mentions(table)

        parsed_table = ParsedTable(
            natural_key=natural_key,
            seq=seq,
            parent_natural_key=parent_natural_key,
            parent_kind=parent_kind,  # type: ignore[arg-type]
            table_type="index",
            source_url=source_url,
            caption=caption,
            raw_html=raw_html,
            cells=cells,
            header_rows=header_rows,
            plaintext=plaintext,
            mentioned_keyword_natural_keys=mentioned_kw_nks,
        )
        parsed_tables.append(parsed_table)

        # Replace the table with a placeholder anchor
        new_tag = BeautifulSoup(
            f'<a class="nj-table-link" data-table-nk="{natural_key}">तालिका देखें</a>',
            "html.parser",
        ).find("a")
        table.replace_with(new_tag)
        logger.debug("tables.py: extracted table %s", natural_key)

    mutated_nodes: list[NavigableString | Tag] = list(wrapper.children)
    return mutated_nodes, parsed_tables
