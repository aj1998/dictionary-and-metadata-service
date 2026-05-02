"""GRef extraction utilities."""

from __future__ import annotations

import re
from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Reference
from .normalize import normalize_text
from .selectors import is_gref_node


def extract_ref_text(node: Node, config: JainkoshConfig) -> str:
    """Extract text from a GRef node, stripping inner anchors if configured."""
    if config.reference.strip_inner_anchors:
        # Remove any <a href> tags, keeping their text
        html = node.html or ""
        html = re.sub(r"<a[^>]*>", "", html)
        html = re.sub(r"</a>", "", html)
        from selectolax.parser import HTMLParser
        text = HTMLParser(html).text(strip=True) or ""
    else:
        text = node.text(strip=True) or ""
    return normalize_text(text)


def extract_refs_from_node(node: Node, config: JainkoshConfig) -> list[Reference]:
    """Extract all GRef spans from a node."""
    refs = []
    for gref in node.css("span.GRef"):
        text = extract_ref_text(gref, config)
        if text:
            refs.append(Reference(text=text, raw_html=gref.html))
    return refs


def is_leading_reference_node(node: Node, config: JainkoshConfig) -> bool:
    """Return True if this node is a leading reference (only GRefs as meaningful content)."""
    if is_gref_node(node, config):
        return True
    if node.tag != "p":
        return False
    # Check if the p contains only GRef spans (and whitespace/punctuation text)
    # Use direct children via iter() - they are direct children of p
    meaningful_children = []
    for child in node.iter(include_text=False):
        # iter() returns direct children only in selectolax
        tag = child.tag
        if not tag or tag in ("-text", "#text"):
            continue
        cls = child.attributes.get("class", "") or ""
        if "GRef" in cls.split():
            meaningful_children.append(("gref", child))
        else:
            meaningful_children.append(("other", child))

    if not meaningful_children:
        # Only text nodes - check if it's empty or punctuation
        text = normalize_text(node.text(strip=True) or "")
        return not text

    # Must have at least one gref and no "other" elements
    has_gref = any(kind == "gref" for kind, _ in meaningful_children)
    has_other = any(kind == "other" for kind, _ in meaningful_children)

    if has_other:
        return False

    # Also check: the direct text (not from children) should be trivial
    # Use a quick heuristic: strip all GRef text and see if what's left is trivial
    full_text = normalize_text(node.text(strip=True) or "")
    gref_texts = []
    for kind, child in meaningful_children:
        if kind == "gref":
            gref_texts.append(normalize_text(child.text(strip=True) or ""))

    remaining = full_text
    for gt in gref_texts:
        remaining = remaining.replace(gt, "", 1)
    remaining = re.sub(r"[,;\s]+", "", remaining)
    return not remaining


import re
