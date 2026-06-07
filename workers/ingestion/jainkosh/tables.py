"""Table block extraction."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional
from urllib.parse import unquote

from selectolax.parser import HTMLParser, Node

from .config import JainkoshConfig
from .models import Block, Multilingual, ParsedTable


_RAW_HTML_TEXT_RUN_RE = re.compile(r"(>)([^<]*)(<)")
_WS_RE = re.compile(r"[\t\n\r\f\v ]+")
_MULTI_SPACE_RE = re.compile(r" {2,}")


def _clean_raw_html(html: str, config: JainkoshConfig) -> str:
    if not html:
        return html
    if not config.table.raw_html.collapse_whitespace:
        return html

    def _collapse_run(match: re.Match[str]) -> str:
        left, run, right = match.group(1), match.group(2), match.group(3)
        if not run:
            return left + run + right
        collapsed = _WS_RE.sub(" ", run).strip()
        if not collapsed:
            return left + right
        return left + collapsed + right

    return _RAW_HTML_TEXT_RUN_RE.sub(_collapse_run, html)


def extract_table_block(table: Node, config: JainkoshConfig) -> Block:
    """Convert a <table> node into a Block(kind='table', raw_html=...)."""
    raw_html = table.html or ""
    if config.table.raw_html.collapse_whitespace:
        raw_html = _clean_raw_html(raw_html, config)
    block = Block(kind="table", raw_html=raw_html)
    if config.table.extraction_strategy == "raw_html_plus_rows":
        block.table_rows = _extract_rows(table)
    return block


def _extract_rows(table: Node) -> list[list[str]]:
    return []


def _cell_text(cell: Node) -> str:
    """Extract plain text from a <td> or <th> cell; <br> becomes \\n, NFC-normalized."""
    html = cell.html or ""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ").replace("&#xA0;", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = unicodedata.normalize("NFC", text)
    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _parse_cells(table: Node) -> tuple[list[list[str]], int]:
    """Return (cells_matrix, header_rows) from a <table> node."""
    rows: list[list[str]] = []
    header_row_count = 0
    in_header_section = True

    for tr in table.css("tr"):
        cells = tr.css("td, th")
        if not cells:
            continue
        row_texts = [_cell_text(c) for c in cells]
        all_th = all(c.tag == "th" or "header" in (c.attributes.get("class") or "").split()
                     for c in cells)
        rows.append(row_texts)
        if in_header_section and all_th:
            header_row_count += 1
        else:
            in_header_section = False

    # Pad rows to uniform width
    if rows:
        max_cols = max(len(r) for r in rows)
        rows = [r + [""] * (max_cols - len(r)) for r in rows]

    return rows, header_row_count


def _extract_inline_caption(table: Node) -> Optional[str]:
    caption_node = table.css_first("caption")
    if caption_node is None:
        return None
    text = unicodedata.normalize("NFC", caption_node.text(strip=True) or "")
    return text or None


def _extract_mentions(table: Node, config: JainkoshConfig) -> tuple[list[str], list[str]]:
    """Return (mentioned_keyword_nks, mentioned_topic_nks) from <a> tags in table."""
    keyword_nks: list[str] = []
    topic_nks: list[str] = []
    seen_kw: set[str] = set()
    seen_tp: set[str] = set()

    for a in table.css("a"):
        href = a.attributes.get("href", "") or ""
        if not href:
            continue
        if config.redlink.href_marker_substring in href:
            continue

        if href.startswith("/wiki/"):
            path_part = href[len("/wiki/"):]
            path, _, _ = path_part.partition("#")
            keyword = unicodedata.normalize("NFC", unquote(path, encoding="utf-8"))
            if keyword and keyword not in seen_kw:
                seen_kw.add(keyword)
                keyword_nks.append(keyword)
        elif href.startswith("#"):
            frag = href.lstrip("#")
            if frag and frag not in seen_tp:
                seen_tp.add(frag)
                topic_nks.append(frag)

    return keyword_nks, topic_nks


def parse_table_block(
    table_node: Node,
    config: JainkoshConfig,
    *,
    parent_natural_key: str,
    parent_kind: str,
    seq: int,
    source_url: Optional[str] = None,
    preceding_heading: Optional[str] = None,
) -> tuple[Block, ParsedTable]:
    """Parse a <table> node into an inline Block and a first-class ParsedTable.

    The returned Block is identical to what extract_table_block() produces and
    must be kept in its parent's block list for back-compat. The ParsedTable
    carries the parsed cell matrix, caption, and mention links.
    """
    block = extract_table_block(table_node, config)
    raw_html = block.raw_html or ""

    natural_key = f"table:jainkosh:{parent_natural_key}:{seq:02d}"

    caption: list[Multilingual] = []
    if config.table.parse_cells:
        inline_caption = _extract_inline_caption(table_node)
        caption_text = inline_caption or preceding_heading or ""
        if caption_text:
            caption = [Multilingual(lang="hin", script="Deva", text=caption_text)]

    cells: list[list[str]] = []
    header_rows = 0
    if config.table.parse_cells:
        cells, header_rows = _parse_cells(table_node)

    plaintext = ""
    if cells:
        plaintext = _MULTI_SPACE_RE.sub(
            " ",
            " ".join(cell for row in cells for cell in row if cell.strip()),
        ).strip()

    mentioned_kw_nks: list[str] = []
    mentioned_topic_nks: list[str] = []
    if config.table.parse_mentions:
        mentioned_kw_nks, mentioned_topic_nks = _extract_mentions(table_node, config)

    parsed_table = ParsedTable(
        natural_key=natural_key,
        seq=seq,
        parent_natural_key=parent_natural_key,
        parent_kind=parent_kind,  # type: ignore[arg-type]
        source_url=source_url,
        caption=caption,
        raw_html=raw_html,
        cells=cells,
        header_rows=header_rows,
        plaintext=plaintext,
        mentioned_keyword_natural_keys=mentioned_kw_nks,
        mentioned_topic_natural_keys=mentioned_topic_nks,
    )
    return block, parsed_table


def parse_table_block_from_html(
    raw_html: str,
    config: JainkoshConfig,
    *,
    parent_natural_key: str,
    parent_kind: str,
    seq: int,
    source_url: Optional[str] = None,
    preceding_heading: Optional[str] = None,
) -> ParsedTable:
    """Create a ParsedTable from an already-serialized raw_html string.

    Used by build_envelope() to construct ParsedTable objects from blocks that
    were already parsed and stored as raw_html.
    """
    tree = HTMLParser(raw_html)
    table_node = tree.css_first("table")
    if table_node is None:
        # Fallback: treat entire fragment as table content
        table_node = tree.root

    natural_key = f"table:jainkosh:{parent_natural_key}:{seq:02d}"

    caption: list[Multilingual] = []
    if config.table.parse_cells and table_node is not None:
        inline_caption = _extract_inline_caption(table_node)
        caption_text = inline_caption or preceding_heading or ""
        if caption_text:
            caption = [Multilingual(lang="hin", script="Deva", text=caption_text)]

    cells: list[list[str]] = []
    header_rows = 0
    if config.table.parse_cells and table_node is not None:
        cells, header_rows = _parse_cells(table_node)

    plaintext = ""
    if cells:
        plaintext = _MULTI_SPACE_RE.sub(
            " ",
            " ".join(cell for row in cells for cell in row if cell.strip()),
        ).strip()

    mentioned_kw_nks: list[str] = []
    mentioned_topic_nks: list[str] = []
    if config.table.parse_mentions and table_node is not None:
        mentioned_kw_nks, mentioned_topic_nks = _extract_mentions(table_node, config)

    return ParsedTable(
        natural_key=natural_key,
        seq=seq,
        parent_natural_key=parent_natural_key,
        parent_kind=parent_kind,  # type: ignore[arg-type]
        source_url=source_url,
        caption=caption,
        raw_html=raw_html,
        cells=cells,
        header_rows=header_rows,
        plaintext=plaintext,
        mentioned_keyword_natural_keys=mentioned_kw_nks,
        mentioned_topic_natural_keys=mentioned_topic_nks,
    )
