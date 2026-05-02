"""Index (<ol>/<ul>) parsing for topic relations."""

from __future__ import annotations

import re
from selectolax.parser import Node

from .config import JainkoshConfig
from .models import IndexRelation
from .normalize import normalize_text
from .see_also import parse_anchor, _extract_label_before_anchor, _preceding_inline_text


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
            source_path_chain = _ancestor_li_ids(a)
            out.append(IndexRelation(
                label_text=label,
                source_topic_path_chain=source_path_chain,
                source_topic_natural_key_chain=[],
                **parsed,
            ))

    return out


def _ancestor_li_ids(a: Node) -> list[str]:
    """Return ancestor <li> ids from outermost to innermost (excluding footer-* ids)."""
    ids: list[str] = []
    cur = a.parent
    while cur is not None:
        if cur.tag == "li":
            li_id = (cur.attributes or {}).get("id") or ""
            if li_id and not li_id.startswith("footer-"):
                ids.append(li_id)
        cur = cur.parent
    ids.reverse()
    return ids
