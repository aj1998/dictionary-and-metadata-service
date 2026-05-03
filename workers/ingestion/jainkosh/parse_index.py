"""Index (<ol>/<ul>) parsing for topic relations."""

from __future__ import annotations

import re
from typing import Optional
from selectolax.parser import Node

from .config import JainkoshConfig
from .models import IndexRelation
from .normalize import nfc
from .see_also import parse_anchor, _extract_label_before_anchor, _preceding_inline_text

_HEADING_CHAINS_BY_REL_ID: dict[int, list[str]] = {}


def parse_index_relations(
    index_ols: list[Node],
    keyword: str,
    config: JainkoshConfig,
) -> list[IndexRelation]:
    """Full-DFS scan of index <ol> elements; emits one IndexRelation per देखें-anchored <a>."""
    out: list[IndexRelation] = []
    see_also_re = re.compile(config.index.see_also_text_pattern)

    for outer_ol in index_ols:
        for a in outer_ol.css("a"):
            prev_text = _preceding_inline_text(a, config.index.see_also_window_chars)
            if not see_also_re.search(prev_text):
                continue
            parsed = parse_anchor(a, config, current_keyword=keyword)
            label = _extract_label_before_anchor(a)
            source_path_chain = _ancestor_li_ids(a, config)
            rel = IndexRelation(
                label_text=label,
                source_topic_path_chain=source_path_chain,
                source_topic_natural_key_chain=[],
                **parsed,
            )
            _attach_heading_chain(rel, _ancestor_strong_chain(a, config))
            if config.index.top_level_reference_marking and not rel.source_topic_path_chain:
                rel.is_top_level_reference = True
            out.append(rel)

    return out


def _ancestor_li_ids(a: Node, config: JainkoshConfig) -> list[str]:
    """Return ancestor <li> ids from outermost to innermost (excluding footer-* ids)."""
    ids: list[str] = []
    row_li: Optional[Node] = None
    cur = a.parent
    skip_innermost_li = True
    while cur is not None:
        if cur.tag == "li":
            if skip_innermost_li:
                row_li = cur
                skip_innermost_li = False
            li_id = (cur.attributes or {}).get("id") or ""
            if not li_id:
                cur = cur.parent
                continue
            if config.index.source_chain.skip_li_with_footer_id and li_id.startswith("footer-"):
                cur = cur.parent
                continue
            if li_id:
                ids.append(li_id)
        cur = cur.parent
    ids.reverse()

    if row_li is None and config.index.source_chain.sibling_container_fallback:
        container = a.parent
        while container is not None and container.tag not in ("ul", "ol"):
            container = container.parent
        if container is not None:
            prev = container.prev
            while prev is not None:
                if prev.tag == "li":
                    path = _topic_path_from_li_heading_anchor(prev, config)
                    if path:
                        if not ids or ids[-1] != path:
                            ids.append(path)
                        return ids
                prev = prev.prev
        return ids

    contextual_path = _nearest_previous_heading_path_in_same_list(row_li, config)
    if contextual_path and (not ids or ids[-1] != contextual_path):
        ids.append(contextual_path)
    return ids


def _ancestor_strong_chain(a: Node, config: JainkoshConfig) -> list[str]:
    if not config.index.source_chain.enabled:
        return []
    chain_inner_to_outer: list[str] = []
    row_li: Optional[Node] = None
    cur = a.parent
    skip_innermost_li = True
    while cur is not None:
        if cur.tag == "li":
            if skip_innermost_li:
                row_li = cur
                skip_innermost_li = False
                cur = cur.parent
                continue
            li_id = (cur.attributes or {}).get("id") or ""
            if config.index.source_chain.skip_li_with_footer_id and li_id.startswith("footer-"):
                cur = cur.parent
                continue
            heading = _li_inline_heading_text(cur, config)
            if heading:
                chain_inner_to_outer.append(heading)
        cur = cur.parent
    chain = list(reversed(chain_inner_to_outer))
    contextual = _nearest_previous_heading_in_same_list(row_li, config)
    if contextual and (not chain or chain[-1] != contextual):
        chain.append(contextual)
    return chain


def _li_inline_heading_text(li: Node, config: JainkoshConfig) -> Optional[str]:
    for child in li.iter(include_text=False):
        if child.tag != "strong":
            continue
        strong_parent = child.parent
        if strong_parent is not None and strong_parent != li:
            continue
        anchor = child.css_first(config.index.source_chain.li_strong_a_selector)
        text = anchor.text(strip=True) if anchor is not None else child.text(strip=True)
        if text:
            return _normalize_heading_for_match(text)
    return None


def _nearest_previous_heading_in_same_list(li: Optional[Node], config: JainkoshConfig) -> Optional[str]:
    if li is None:
        return None
    prev = li.prev
    while prev is not None:
        if prev.tag == "li":
            heading = _li_inline_heading_text(prev, config)
            if heading:
                return heading
        prev = prev.prev
    container = li.parent
    if container is None:
        return None
    prev = container.prev
    while prev is not None:
        heading = _heading_from_node_or_descendants(prev, config)
        if heading:
            return heading
        prev = prev.prev

    # Climb to enclosing <li> if container is inside one
    if config.index.source_chain.enclosing_li_fallback:
        enclosing_li = container.parent if container is not None else None
        if enclosing_li is not None and enclosing_li.tag == "li":
            heading = _li_inline_heading_text(enclosing_li, config)
            if heading:
                return heading
    return None


def _heading_from_node_or_descendants(node: Node, config: JainkoshConfig) -> Optional[str]:
    if node.tag == "li":
        heading = _li_inline_heading_text(node, config)
        if heading:
            return heading
    for child in node.iter(include_text=False):
        if child.tag != "li":
            continue
        heading = _li_inline_heading_text(child, config)
        if heading:
            return heading
    return None


def _nearest_previous_heading_path_in_same_list(li: Optional[Node], config: JainkoshConfig) -> Optional[str]:
    if li is None:
        return None
    if config.index.source_chain.row_li_self_path_check:
        self_path = _topic_path_from_li_heading_anchor(li, config)
        if self_path:
            return self_path
    prev = li.prev
    while prev is not None:
        path = _topic_path_from_li_heading_anchor(prev, config) if prev.tag == "li" else None
        if path:
            return path
        prev = prev.prev
    container = li.parent
    if container is None:
        return None
    prev = container.prev
    while prev is not None:
        path = _topic_path_from_node_or_descendants(prev, config)
        if path:
            return path
        prev = prev.prev

    # Climb to enclosing <li> if container is inside one
    if config.index.source_chain.enclosing_li_fallback:
        enclosing_li = container.parent if container is not None else None
        if enclosing_li is not None and enclosing_li.tag == "li":
            path = _topic_path_from_li_heading_anchor(enclosing_li, config)
            if path:
                return path
    return None


def _topic_path_from_node_or_descendants(node: Node, config: JainkoshConfig) -> Optional[str]:
    if node.tag == "li":
        path = _topic_path_from_li_heading_anchor(node, config)
        if path:
            return path
    for child in node.iter(include_text=False):
        if child.tag != "li":
            continue
        path = _topic_path_from_li_heading_anchor(child, config)
        if path:
            return path
    return None


def _topic_path_from_li_heading_anchor(li: Node, config: JainkoshConfig) -> Optional[str]:
    for child in li.iter(include_text=False):
        if child.tag != "strong":
            continue
        strong_parent = child.parent
        if strong_parent is not None and strong_parent != li:
            continue
        anchor = child.css_first(config.index.source_chain.li_strong_a_selector)
        if anchor is None:
            continue
        href = (anchor.attributes or {}).get("href") or ""
        if href.startswith("#"):
            return href[1:].strip() or None

    # Fallback: derive path from first anchor in an inner <ol>
    if config.index.source_chain.li_path_from_inner_ol_fallback:
        for child in li.iter(include_text=False):
            if child.tag != "ol":
                continue
            if child.parent is not None and child.parent != li:
                continue  # only direct <ol> children of this <li>
            for inner_li in child.iter(include_text=False):
                if inner_li.tag != "li":
                    continue
                if inner_li.parent is not None and inner_li.parent != child:
                    continue  # only direct <li> of the inner <ol>
                a = inner_li.css_first("a[href^='#']")
                if a:
                    href = (a.attributes or {}).get("href") or ""
                    if href.startswith("#"):
                        path = href[1:].strip()
                        parts = path.split(".")
                        if len(parts) > 1:
                            return ".".join(parts[:-1])
            break  # only check the first <ol>
    return None


def _normalize_heading_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", nfc(text)).strip()


def _attach_heading_chain(rel: IndexRelation, chain: list[str]) -> None:
    _HEADING_CHAINS_BY_REL_ID[id(rel)] = chain


def get_heading_chain(rel: IndexRelation) -> list[str]:
    return _HEADING_CHAINS_BY_REL_ID.get(id(rel), [])


def clear_heading_chains() -> None:
    _HEADING_CHAINS_BY_REL_ID.clear()
