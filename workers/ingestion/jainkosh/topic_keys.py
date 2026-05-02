"""Natural key and slug computation for jainkosh topics."""

from __future__ import annotations

import re
from typing import Optional

from .normalize import nfc


def slug(s: str, config) -> str:
    """Convert heading text to a URL-safe slug, preserving Devanagari."""
    s = nfc(s)
    # Strip V4-style numeric prefix (e.g. "1.1.3. heading" → "heading")
    if config.slug.strip_v4_numeric_prefix:
        s = re.sub(r"^\s*\d+(?:\.\d+)*[.\s]+", "", s)
    # Strip specified characters
    for ch in config.slug.strip_chars:
        s = s.replace(ch, "")
    # Replace whitespace / NBSP runs with separator
    s = re.sub(r"[\s  ]+", config.slug.whitespace_to, s)
    # Collapse multiple dashes
    if config.slug.collapse_dashes:
        s = re.sub(r"-+", "-", s)
    return s.strip("-").strip()


def natural_key(keyword: str, heading_path: list[str], config) -> str:
    """Build the colon-separated natural key for a topic."""
    parts = [keyword] + [slug(h, config) for h in heading_path]
    return ":".join(parts)


def parent_of(path: str) -> Optional[str]:
    """Return parent path by removing last segment. 'None' for root paths."""
    if "." not in path:
        return None
    return path.rsplit(".", 1)[0]
