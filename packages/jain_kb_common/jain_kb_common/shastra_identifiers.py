"""Resolve compound identifier schemes declared in shastra.json.

Single source of truth: parser_configs/_manual_configs/shastra.json.

A "compound identifier" is a list of fields whose values together identify
a Gatha (or Kalash) within a shastra — e.g. परमात्मप्रकाश's gatha is identified
by (अधिकार, गाथा). The natural-key suffix is built by emitting `<field>:<value>`
pairs in declaration order; the field name is the canonical noun obtained
by stripping the exact shastra-name prefix.
"""

from __future__ import annotations

import json
import functools
import unicodedata
from pathlib import Path

# Discovery path relative to repo root. Override via env JAIN_SHASTRA_JSON.
_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "parser_configs" / "_manual_configs" / "shastra.json"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


@functools.lru_cache(maxsize=1)
def _load(path: str | None = None) -> list[dict]:
    p = Path(path) if path else _DEFAULT_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def get_shastra_entry(shastra_name: str, *, path: str | None = None) -> dict | None:
    """Return the JSON entry for a shastra by its NFC `shastra_name`."""
    target = _nfc(shastra_name)
    for e in _load(path):
        if _nfc(e.get("shastra_name", "")) == target:
            return e
    return None


def get_identifier_fields(
    shastra_name: str, kind: str = "gatha", *, path: str | None = None,
) -> list[str] | None:
    """Return the **raw** field list declared in shastra.json, or None.

    `kind` ∈ {"gatha", "kalash"} → reads `gatha_identifier` / `kalash_identifier`.
    `None` is returned when the shastra is single-identifier (no compound).
    """
    if kind not in ("gatha", "kalash"):
        raise ValueError(f"kind must be 'gatha' or 'kalash', got {kind!r}")
    entry = get_shastra_entry(shastra_name, path=path)
    if not entry:
        return None
    raw = entry.get(f"{kind}_identifier")
    if not raw:
        return None
    fields = [f.strip() for f in raw.split(",") if f.strip()]
    return fields or None


def canonical_segment_name(shastra_name: str, field_name: str) -> str:
    """Strip the exact `{shastra_name}` prefix from a field name.

    `परमात्मप्रकाशगाथा` + `परमात्मप्रकाश` → `गाथा`.
    `अधिकार` (no prefix) → `अधिकार`.
    Empty remainder → falls back to the original field name (no rename).
    """
    s = _nfc(shastra_name)
    f = _nfc(field_name)
    if f.startswith(s):
        rest = f[len(s):]
        if rest:
            return rest
    return f


def build_compound_suffix(
    shastra_name: str,
    values: dict[str, str],
    *,
    kind: str = "gatha",
    path: str | None = None,
) -> str | None:
    """Build the compound NK suffix `<seg>:<val>:<seg>:<val>...` in declaration order.

    Returns None when:
      • the shastra has no compound identifier of this kind, or
      • any declared field is missing from `values`.
    """
    fields = get_identifier_fields(shastra_name, kind, path=path)
    if not fields:
        return None
    parts: list[str] = []
    for f in fields:
        v = values.get(f)
        if v is None or str(v) == "":
            return None
        seg = canonical_segment_name(shastra_name, f)
        parts.append(f"{seg}:{v}")
    return ":".join(parts)
