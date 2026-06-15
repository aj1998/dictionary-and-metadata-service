from __future__ import annotations

import json
import logging
import os
import unicodedata
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_TRAVERSAL_CHARS = frozenset(["/", "\\", ".."])


def _has_traversal(value: str) -> bool:
    if ".." in value:
        return True
    if "/" in value or "\\" in value:
        return True
    return False


@lru_cache(maxsize=1)
def _load_shastra_config() -> list[dict]:
    base = os.path.dirname(__file__)
    path = os.path.normpath(
        os.path.join(base, "..", "..", "..", "..", "..", "parser_configs", "_manual_configs", "shastra.json")
    )
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


# An OffsetSpec is either a single integer (single offset applied to all pages),
# or a list of [up_to_published_page, offset] pairs. For a given published page P,
# the offset of the first pair (sorted by up_to_published_page asc) where
# P <= up_to_published_page is applied. Pages beyond the last threshold fall
# back to the last entry's offset.
OffsetSpec = int | list[list[int]]


def _coerce_offset_spec(value: object) -> OffsetSpec:
    if isinstance(value, list):
        return [[int(pair[0]), int(pair[1])] for pair in value]
    return int(value)  # type: ignore[arg-type]


def get_shastra_pdf_offsets(
    shastra_nk: str,
) -> tuple[OffsetSpec, dict[str, OffsetSpec] | None]:
    """Return (pdf_page_offset, pustak_offsets) for a shastra natural key."""
    entries = _load_shastra_config()
    nk_nfc = unicodedata.normalize("NFC", shastra_nk)
    for entry in entries:
        name = unicodedata.normalize("NFC", entry.get("shastra_name", ""))
        if name == nk_nfc:
            offset = _coerce_offset_spec(entry.get("pdf_page_offset", 0))
            pustak_raw = entry.get("pustak_offsets")
            pustak = (
                {k: _coerce_offset_spec(v) for k, v in pustak_raw.items()}
                if pustak_raw
                else None
            )
            return offset, pustak
    return 0, None


def get_shastra_pdf_offsets_with_availability(
    shastra_nk: str,
) -> tuple[OffsetSpec, dict[str, OffsetSpec] | None, bool]:
    """Return (pdf_page_offset, pustak_offsets, available) for a shastra natural key.

    `available` is True when the shastra entry in shastra.json explicitly carries
    a `pdf_page_offset` (or `pustak_offsets`), indicating that a local PDF is
    expected to exist.
    """
    entries = _load_shastra_config()
    nk_nfc = unicodedata.normalize("NFC", shastra_nk)
    for entry in entries:
        name = unicodedata.normalize("NFC", entry.get("shastra_name", ""))
        if name == nk_nfc:
            has_offset = "pdf_page_offset" in entry or "pustak_offsets" in entry
            offset = _coerce_offset_spec(entry.get("pdf_page_offset", 0))
            pustak_raw = entry.get("pustak_offsets")
            pustak = (
                {k: _coerce_offset_spec(v) for k, v in pustak_raw.items()}
                if pustak_raw
                else None
            )
            return offset, pustak, has_offset
    return 0, None, False


def resolve_pdf_path(
    pdf_dir: str,
    shastra_nk: str,
    pustak: str | None,
) -> Path | None:
    """
    Resolve the filesystem path for a shastra PDF.

    Returns None if traversal characters are detected (caller should 400).
    Raises FileNotFoundError if the file doesn't exist (caller should 404).

    Path rules:
    - If shastra config has pdf_filename: <dir>/<shastra_name>/<pdf_filename>[_<pustak>].pdf
    - Otherwise: <dir>/<shastra_name>[_<pustak>].pdf
    """
    nk_nfc = unicodedata.normalize("NFC", shastra_nk)

    if _has_traversal(nk_nfc):
        logger.error("Traversal attempt in shastra_nk: %r", shastra_nk)
        return None
    if pustak is not None and _has_traversal(pustak):
        logger.error("Traversal attempt in pustak: %r", pustak)
        return None

    entries = _load_shastra_config()
    pdf_filename: str | None = None
    for entry in entries:
        name = unicodedata.normalize("NFC", entry.get("shastra_name", ""))
        if name == nk_nfc:
            pdf_filename = entry.get("pdf_filename")
            break

    root = Path(pdf_dir).resolve()

    if pdf_filename is not None:
        stem = f"{pdf_filename}_{pustak}" if pustak is not None else pdf_filename
        resolved = (root / nk_nfc / f"{stem}.pdf").resolve()
    else:
        stem = f"{nk_nfc}_{pustak}" if pustak is not None else nk_nfc
        resolved = (root / f"{stem}.pdf").resolve()

    # Defence-in-depth: ensure resolved path stays inside root
    try:
        resolved.relative_to(root)
    except ValueError:
        logger.error("Path escape attempt: resolved=%s root=%s", resolved, root)
        return None

    return resolved
