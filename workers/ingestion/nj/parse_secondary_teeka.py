"""Parse secondary teeka blocks (div#teeka1 or secondary-only div#teeka0)."""

from __future__ import annotations

import unicodedata

from bs4 import NavigableString, Tag

from .config import NJConfig
from .models import SecondaryTeeka
from .shortfont_parser import extract_shortfont


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


def parse_secondary_teeka(teeka_div: Tag, cfg: NJConfig) -> SecondaryTeeka:
    """Parse either div#teeka1 (regular page) or div#teeka0 (secondary-only page)."""
    steeka = teeka_div.select_one("div.steeka")

    gatha_teeka_san = None
    if steeka:
        nodes = _nodes_before_hr(steeka, cfg.selectors.teeka_separator)
        gatha_teeka_san = _clean(" ".join(_get_text(n) for n in nodes)) or None

    nodes_after = _nodes_after_element(teeka_div, steeka)

    # Skip label node (e.g. <b><font color=darkgreen>जयसेनाचार्य</font></b>)
    if nodes_after and isinstance(nodes_after[0], Tag):
        maybe_label = nodes_after[0].find("font") if nodes_after[0].name == "b" else None
        if maybe_label and (maybe_label.get("color") or "").strip().lower() == "darkgreen":
            nodes_after = nodes_after[1:]

    cleaned_bhaavarth_md, shortfont_entries = extract_shortfont(list(nodes_after))

    return SecondaryTeeka(
        gatha_teeka_san=gatha_teeka_san,
        gatha_teeka_bhaavarth_md=cleaned_bhaavarth_md or None,
        gatha_teeka_bhaavarth_shortfont=shortfont_entries,
    )
