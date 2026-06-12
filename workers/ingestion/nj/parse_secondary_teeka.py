"""Parse secondary teeka blocks (div#teeka1 or secondary-only div#teeka0)."""

from __future__ import annotations

import unicodedata

from bs4 import NavigableString, Tag

from .config import NJConfig
from .models import SecondaryTeeka
from .shortfont_parser import extract_shortfont
from .tables import extract_tables_from_bhaavarth


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text.replace("\ufeff", "")).strip()


def _get_text(node: NavigableString | Tag) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if isinstance(node, Tag):
        return node.get_text(" ", strip=False)
    return ""


def _nodes_before_hr(parent: Tag, hr_selector: str) -> list[NavigableString | Tag]:
    out: list[NavigableString | Tag] = []
    hr = parent.select_one(hr_selector)
    for node in parent.children:
        if hr and node is hr:
            break
        out.append(node)
    return out


def _nodes_after_element(parent: Tag, element: Tag | None) -> list[NavigableString | Tag]:
    nodes = list(parent.children)
    if element is None:
        return nodes
    for i, node in enumerate(nodes):
        if node is element:
            return nodes[i + 1 :]
    return nodes


def parse_secondary_teeka(
    teeka_div: Tag,
    cfg: NJConfig,
    *,
    parent_bhaavarth_nk: str | None = None,
) -> SecondaryTeeka:
    """Parse either div#teeka1 (regular page) or div#teeka0 (secondary-only page)."""
    steeka = teeka_div.select_one("div.steeka")

    gatha_teeka_san = None
    if steeka:
        nodes = _nodes_before_hr(steeka, cfg.selectors.teeka_separator)
        gatha_teeka_san = _clean(" ".join(_get_text(n) for n in nodes)) or None

    nodes_after = _nodes_after_element(teeka_div, steeka)

    # Skip label node (e.g. <b><font color=darkgreen>जयसेनाचार्य</font></b>).
    # Walk past any leading whitespace NavigableStrings to find the first real Tag.
    first_tag_idx = next(
        (idx for idx, n in enumerate(nodes_after) if isinstance(n, Tag)),
        None,
    )
    if first_tag_idx is not None:
        first_tag = nodes_after[first_tag_idx]
        maybe_label = first_tag.find("font") if first_tag.name == "b" else None
        if (
            maybe_label
            and (maybe_label.get("color") or "").strip().lower() == "darkgreen"
            and first_tag.find("div") is None
        ):
            nodes_after = nodes_after[first_tag_idx + 1 :]

    bhaavarth_nodes = list(nodes_after)
    parsed_tables = []
    if parent_bhaavarth_nk:
        bhaavarth_nodes, parsed_tables = extract_tables_from_bhaavarth(
            bhaavarth_nodes,
            parent_natural_key=parent_bhaavarth_nk,
            parent_kind="gatha_teeka_bhaavarth",
            source_url=None,
        )

    cleaned_bhaavarth_md, shortfont_entries = extract_shortfont(bhaavarth_nodes)

    return SecondaryTeeka(
        gatha_teeka_san=gatha_teeka_san,
        gatha_teeka_bhaavarth_md=cleaned_bhaavarth_md or None,
        gatha_teeka_bhaavarth_shortfont=shortfont_entries,
        tables=parsed_tables,
    )
