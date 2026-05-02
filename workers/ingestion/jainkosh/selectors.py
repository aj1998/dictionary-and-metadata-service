"""CSS selector and class constants."""

from __future__ import annotations

from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .normalize import normalize_text


def block_class_kind(node: Node, config: JainkoshConfig) -> Optional[str]:
    """Return the block kind for a node based on its CSS class, or None."""
    cls = node.attributes.get("class", "") or ""
    for class_name, kind in config.block_classes.items():
        if class_name in cls.split():
            return kind
    return None


def is_gref_node(node: Node, config: JainkoshConfig) -> bool:
    """Return True if the node is a <span class="GRef">."""
    if node.tag != "span":
        return False
    cls = node.attributes.get("class", "") or ""
    return "GRef" in cls.split()


def get_node_text(node: Node, config: JainkoshConfig, *, handle_br: bool = True) -> str:
    """Extract text from a node with br→newline and normalization."""
    if not handle_br:
        return normalize_text(node.text(strip=True) or "")

    # Walk the HTML, replacing <br> with \n
    raw_html = node.html or ""
    # Replace <br/> or <br> tags with newline
    import re
    raw_html = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    # Strip remaining tags via selectolax
    from selectolax.parser import HTMLParser
    text = HTMLParser(raw_html).text(strip=False) if raw_html else ""
    # Normalize each line separately then join
    lines = text.split("\n")
    lines = [normalize_text(line) for line in lines]
    # Remove empty lines at ends; collapse multiple blank lines
    result = "\n".join(lines).strip()
    # Remove consecutive newlines
    result = re.sub(r"\n{2,}", "\n", result)
    return result


def node_outer_html(node: Node, config: Optional[JainkoshConfig] = None) -> str:
    """Return the outer HTML of a node."""
    html = node.html or ""
    if config is None:
        return html
    if hasattr(config, "reference") and config.reference.raw_html.collapse_whitespace:
        from .refs import _clean_raw_html
        return _clean_raw_html(html, config)
    return html
