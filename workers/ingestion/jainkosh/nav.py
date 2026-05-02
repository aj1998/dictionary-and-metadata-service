"""Adjacent-page navigation extraction and removal."""

from __future__ import annotations

from typing import Optional

from selectolax.parser import HTMLParser, Node

from .config import JainkoshConfig
from .models import Nav
from .normalize import normalize_text


def extract_nav(main: Node, config: JainkoshConfig) -> Nav:
    """Extract prev/next page links from the main content node."""
    prev_url: Optional[str] = None
    next_url: Optional[str] = None

    for a in main.css("a"):
        text = normalize_text(a.text(strip=True) or "")
        href = a.attributes.get("href", "") or ""
        if config.navigation.prev_text in text:
            prev_url = href
        elif config.navigation.next_text in text:
            next_url = href

    return Nav(prev=prev_url, next=next_url)


def drop_nav_nodes(main: Node, config: JainkoshConfig) -> None:
    """Remove nav-containing <p> elements from the main content."""
    to_remove = []
    for p in main.css(config.navigation.containing_tag):
        has_nav = False
        for a in p.css("a"):
            text = normalize_text(a.text(strip=True) or "")
            if config.navigation.prev_text in text or config.navigation.next_text in text:
                has_nav = True
                break
        if has_nav:
            to_remove.append(p)

    for node in to_remove:
        node.decompose()
