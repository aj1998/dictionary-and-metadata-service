"""Unicode normalization utilities for Devanagari text."""

from __future__ import annotations

import re
import unicodedata

_ZWJ = "‍"
_ZWNJ = "‌"
_NBSP = " "
_NNBSP = " "


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def strip_zwj(text: str) -> str:
    return text.replace(_ZWJ, "").replace(_ZWNJ, "")


def normalize_whitespace(text: str) -> str:
    """Replace NBSP variants with space, collapse whitespace runs."""
    text = text.replace(_NBSP, " ").replace(_NNBSP, " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text


def normalize_text(text: str, *, strip_zwj_chars: bool = True,
                   collapse_ws: bool = True) -> str:
    """Full normalization pipeline: NFC → strip ZWJ/ZWNJ → collapse whitespace → strip."""
    text = nfc(text)
    if strip_zwj_chars:
        text = strip_zwj(text)
    if collapse_ws:
        text = normalize_whitespace(text)
    return text.strip()


def decode_keyword_from_url(url: str) -> str:
    """Extract and decode the keyword from a /wiki/<keyword> URL."""
    from urllib.parse import unquote
    # Handle both full URLs and path-only
    if "/wiki/" in url:
        path = url.split("/wiki/", 1)[1]
    else:
        path = url
    # Remove any fragment
    path = path.split("#")[0]
    # URL decode
    decoded = unquote(path, encoding="utf-8")
    # NFC + strip ZWJ/ZWNJ
    return strip_zwj(nfc(decoded))
