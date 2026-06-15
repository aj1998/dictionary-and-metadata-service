# Phase 1 — shastra.json + config loader util

> **Read first**: [`00_compound_identifiers_overview.md`](../00_compound_identifiers_overview.md)
>
> **Goal**: introduce the `gatha_identifier` / `kalash_identifier` concept in the
> single source of truth (`shastra.json`), and provide a small reusable Python
> util in `jain_kb_common` that every downstream layer (NJ parser, JK reference
> parser, envelopes, API) can call to derive (a) the ordered identifier field
> list and (b) the canonical NK-segment name for each field.
>
> **Touch surface**: 2 files modified, 1 file added, ~80 LOC, 6 unit tests.
> No DB writes, no DB schema change, no API or UI change.

---

## 1. Update `parser_configs/_manual_configs/shastra.json`

For the `परमात्मप्रकाश` entry **only**, change:
```diff
-  "gatha_identifier": "अधिकार,गाथा"
+  "gatha_identifier": "अधिकार,परमात्मप्रकाशगाथा"
```
Leave every other entry untouched. Do **not** add `gatha_identifier` to other
shastras — they remain single-identifier and behaviour is unchanged.

Optional but recommended: also add `"kalash_identifier": null` to परमात्मप्रकाश
to document the negative. The reader util (below) treats missing and `null`
identically.

## 2. Add the reader util

**File** (new): `packages/jain_kb_common/jain_kb_common/shastra_identifiers.py`

```python
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
from typing import Sequence

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
```

## 3. Tests

**File** (new): `tests/jain_kb_common/test_shastra_identifiers.py`

| Test | Asserts |
|---|---|
| `test_get_entry_परमात्मप्रकाश_present` | returns dict, `gatha_identifier` is the expected string |
| `test_get_identifier_fields_compound` | `["अधिकार","परमात्मप्रकाशगाथा"]` for परमात्मप्रकाश |
| `test_get_identifier_fields_single_returns_none` | `None` for समयसार |
| `test_canonical_segment_strips_exact_prefix` | `परमात्मप्रकाशगाथा` → `गाथा`; `अधिकार` → `अधिकार` |
| `test_canonical_segment_no_prefix_match` | random word with shastra-prefix-look-alike not stripped |
| `test_build_compound_suffix` | `{अधिकार:"1", परमात्मप्रकाशगाथा:"2"}` → `"अधिकार:1:गाथा:2"` |
| `test_build_compound_suffix_missing_field_returns_none` | missing `परमात्मप्रकाशगाथा` → `None` |
| `test_build_compound_suffix_no_compound_returns_none` | समयसार with any values → `None` |
| `test_nfc_lookup_matches_decomposed_input` | decomposed `परमात्मप्रकाश` still matches NFC entry |

Run:
```bash
python -m pytest tests/jain_kb_common/test_shastra_identifiers.py -v
```

## 4. Implementation notes / done-checklist

- [x] Add util file
- [x] Add tests, all green
- [x] Update `shastra.json` for परमात्मप्रकाश (already had correct value; added `kalash_identifier: null`)
- [x] Run full repo test suite (`python -m pytest`) — 41 pre-existing failures (MongoDB/service tests, jainkosh goldens); 0 regressions from this phase
- [x] Update authoritative docs per the obligation in
      [`00_compound_identifiers_overview.md`](../00_compound_identifiers_overview.md) §"Doc-update obligation":
      - Mark this phase ✓ in the overview phase index.
      - Note in `docs/design/data_model/data_model_postgres.md` that
        `gathas.gatha_number` will, from phase 3 onward, hold the full
        compound NK suffix for shastras that declare `gatha_identifier`.

## 5. Out of scope

- No call sites are wired here. NJ parser / JK ref parser / envelope refer to
  this util in phases 2–4.
- No CLI exposure.
- No env-var override path beyond the optional `path` kwarg used by tests.
