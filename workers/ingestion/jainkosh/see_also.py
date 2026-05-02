"""देखें (see_also) extraction utilities."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import unquote, urlparse, parse_qs

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, IndexRelation
from .normalize import nfc, normalize_text


def _build_see_also_re(config: JainkoshConfig) -> re.Pattern:
    return re.compile(config.index.see_also_text_pattern)


def parse_anchor(a: Node, config: JainkoshConfig, *, current_keyword: str = "") -> dict:
    """Parse an <a> anchor into a see_also/IndexRelation field dict."""
    href = a.attributes.get("href", "") or ""
    cls = a.attributes.get("class", "") or ""

    if "redlink=1" in href:
        # Extract title from query string
        parsed_url = urlparse(href)
        qs = parse_qs(parsed_url.query)
        title = qs.get("title", [None])[0]
        if title:
            title = nfc(unquote(title)).replace("_", " ")
        else:
            title = normalize_text(a.text(strip=True) or "")
        return dict(
            target_keyword=title,
            target_topic_path=None,
            target_url=href,
            is_self=False,
            target_exists=False,
        )

    if config.index.self_link_class in cls.split():
        frag = href.lstrip("#")
        return dict(
            target_keyword=current_keyword or None,
            target_topic_path=frag or None,
            target_url=href,
            is_self=True,
            target_exists=True,
        )

    if href.startswith("/wiki/"):
        path_part = href[len("/wiki/"):]
        path, _, frag = path_part.partition("#")
        keyword = nfc(unquote(path, encoding="utf-8")).replace("_", " ")
        return dict(
            target_keyword=keyword,
            target_topic_path=frag or None,
            target_url=href,
            is_self=False,
            target_exists=True,
        )

    # Fallback
    return dict(
        target_keyword=None,
        target_topic_path=None,
        target_url=href,
        is_self=False,
        target_exists=True,
    )


def find_see_alsos_in_element(
    el: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
    source_topic_path: Optional[str] = None,
    as_index_relation: bool = False,
) -> list[Block | IndexRelation]:
    """Find देखें links in an element. Returns Block or IndexRelation depending on context."""
    see_also_re = _build_see_also_re(config)
    results = []

    for a in el.css("a"):
        # Get the preceding inline text within the same parent (max ~20 chars)
        prev_text = _preceding_inline_text(a, max_chars=40)
        if not see_also_re.search(prev_text):
            continue

        parsed = parse_anchor(a, config, current_keyword=current_keyword)
        label_text = _extract_label_before_anchor(a)

        if as_index_relation:
            results.append(IndexRelation(
                label_text=label_text,
                source_topic_path=source_topic_path,
                **parsed,
            ))
        else:
            results.append(Block(
                kind="see_also",
                **{k: v for k, v in parsed.items()},
            ))

    return results


def _preceding_inline_text(a: Node, max_chars: int = 40) -> str:
    """Get inline text immediately preceding an <a> tag within its parent."""
    parent = a.parent
    if parent is None:
        return ""

    # Collect all text up to this <a>
    parent_html = parent.html or ""
    a_html = a.html or ""

    # Find position of this anchor in parent's HTML
    idx = parent_html.find(a_html)
    if idx < 0:
        return ""

    before = parent_html[:idx]
    # Strip HTML tags
    import re
    before_text = re.sub(r"<[^>]+>", "", before)
    # Get last max_chars
    return before_text[-max_chars:] if len(before_text) > max_chars else before_text


def _extract_label_before_anchor(a: Node) -> str:
    """Extract the label text before the देखें link in an <li>."""
    parent = a.parent
    if parent is None:
        return ""
    parent_html = parent.html or ""
    a_html = a.html or ""
    idx = parent_html.find(a_html)
    if idx < 0:
        return ""
    before = parent_html[:idx]
    import re
    # Strip HTML tags
    label = re.sub(r"<[^>]+>", "", before)
    # Remove देखें and surrounding punctuation
    label = re.sub(r"[(–\-]\s*देखें\s*$", "", label).strip()
    label = re.sub(r"देखें\s*$", "", label).strip()
    return normalize_text(label)
