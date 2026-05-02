"""Index (<ol>/<ul>) parsing for topic relations."""

from __future__ import annotations

import re
from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import IndexRelation
from .normalize import normalize_text
from .see_also import find_see_alsos_in_element


def parse_index_relations(
    index_ols: list[Node],
    keyword: str,
    config: JainkoshConfig,
) -> list[IndexRelation]:
    """
    Parse index <ol>/<ul> elements into IndexRelation objects.
    Ignores inner <ol> anchor links (#N); captures inner <ul> देखें relations.
    """
    relations: list[IndexRelation] = []
    see_also_re = re.compile(config.index.see_also_text_pattern)

    for outer_ol in index_ols:
        # Walk the outer <ol>. For each top-level <li>, extract its id (= source_topic_path).
        # Then look for inner <ul> with देखें links.
        for child in _direct_children_of(outer_ol):
            if child.tag == "li":
                li_id = child.attributes.get("id", None)
                source_path = li_id
                # Inner <ul> = देखें relations at the li level
                for inner_child in _direct_children_of(child):
                    if inner_child.tag == "ul":
                        _parse_ul_relations(inner_child, keyword, config, source_path, relations, see_also_re)
            elif child.tag == "ul":
                # Keyword-level <ul> (direct child of outer_ol between top-level <li>s)
                _parse_ul_relations(child, keyword, config, None, relations, see_also_re)

    return relations


def _parse_ul_relations(
    ul: Node,
    keyword: str,
    config: JainkoshConfig,
    source_topic_path: Optional[str],
    out: list[IndexRelation],
    see_also_re: re.Pattern,
) -> None:
    """Parse a <ul> for देखें links and append IndexRelations to out."""
    from .see_also import parse_anchor, _extract_label_before_anchor
    for li in ul.css("li"):
        # Find <a> links in this <li>
        for a in li.css("a"):
            # Check if this is a देखें link
            prev_text = _preceding_text_in_li(a, li)
            if not see_also_re.search(prev_text):
                continue

            parsed = parse_anchor(a, config, current_keyword=keyword)
            label = _extract_label_before_anchor(a)

            out.append(IndexRelation(
                label_text=label,
                source_topic_path=source_topic_path,
                **parsed,
            ))


def _preceding_text_in_li(a: Node, li: Node) -> str:
    """Get text preceding an <a> within its <li>."""
    li_html = li.html or ""
    a_html = a.html or ""
    idx = li_html.find(a_html)
    if idx < 0:
        return ""
    before = li_html[:idx]
    import re
    before_text = re.sub(r"<[^>]+>", "", before)
    return before_text[-40:]


def _direct_children_of(node: Node):
    """Yield direct children of a node (iter() returns direct children in selectolax)."""
    yield from node.iter(include_text=False)
