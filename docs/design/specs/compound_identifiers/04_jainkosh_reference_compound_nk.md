# Phase 4 — JainKosh reference parser: compound NK resolution

> **Read first**: phases [`00`](./00_compound_identifiers_overview.md),
> [`01`](./01_shastra_json_and_config_loader.md),
> [`03`](./03_envelope_and_apply_compound_nk.md).
>
> **Goal**: when a JainKosh page cites a परमात्मप्रकाश gatha — e.g.
> `(प.प्र./मू./1/19/...)` — the reference parser must resolve it to the
> **compound NK** that the NJ envelope writes (`परमात्मप्रकाश:अधिकार:1:गाथा:19`),
> so the `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` edge lands on the same node.
> Today the reference parser only knows the legacy `{shastra}:गाथा:{n}` pattern.

---

## 1. Reference grammar refresher

In `shastra.json`:
```
"shastra_name": "परमात्मप्रकाश",
"format": [
  "अधिकार/परमात्मप्रकाशगाथा/पृष्ठ/पंक्ति",
  "अधिकार/परमात्मप्रकाशगाथा/पृष्ठ",
  "अधिकार/परमात्मप्रकाशगाथा"
]
```

The reference parser already tokenises citations against these `format` strings
and maps each path segment to a named field (`अधिकार`, `परमात्मप्रकाशगाथा`, …).

## 2. Reference-edge NK resolution

**File**: `workers/ingestion/jainkosh/reference_edges.py` (and any NK helper
in `parse_reference.py`).

Today, the gatha branch builds:
```python
gatha_nk = f"{shastra_nk}:गाथा:{n}"
```

Replace with:
```python
from jain_kb_common.shastra_identifiers import (
    get_identifier_fields, build_compound_suffix,
)

def _build_gatha_nk_from_reference(shastra_nk: str, parsed_fields: dict[str, str]) -> str | None:
    """Resolve a reference's named fields to a Gatha NK.

    Compound case: use `gatha_identifier` from shastra.json.
    Legacy case:   fall back to `{shastra_nk}:गाथा:{n}`.
    Returns None when required fields are missing.
    """
    fields = get_identifier_fields(shastra_nk, "gatha")
    if fields:
        suffix = build_compound_suffix(shastra_nk, parsed_fields, kind="gatha")
        if not suffix:
            return None
        return f"{shastra_nk}:{suffix}"
    # legacy
    n = parsed_fields.get("गाथा") or parsed_fields.get("श्लोक") or parsed_fields.get("सूत्र")
    if not n:
        return None
    return f"{shastra_nk}:गाथा:{n}"
```

Apply the same pattern to GathaTeeka / GathaTeekaBhaavarth / Kalash /
KalashBhaavarth NK builders (insert trailing label using the same
`_insert_trailing_label` helper introduced in phase 3 — move it to
`jain_kb_common.shastra_identifiers` so both NJ envelope and JK reference
parser share it).

## 3. Range-expansion citations

JainKosh references can be range citations, e.g. `(प.प्र./मू./1/19-21)`.
Today the parser already expands these into N separate `Reference` objects,
each with a single `गाथा`/`परमात्मप्रकाशगाथा` value. No additional logic needed
in this phase — the per-reference NK builder picks the right value.

Add an integration test covering one range-citation fixture page.

## 4. Stub-node hierarchy emission

When a reference resolves to a perm-prakash gatha that has not yet been
ingested, the envelope emits a lazy `Gatha` stub node. Update
`workers/ingestion/jainkosh/envelope.py` to thread `identifier_values` (the
`parsed_fields` dict) into the lazy stub props so the resulting `Gatha`
stub node carries the structured form. Reuse the stub-props allowlist update
from phase 3.

`_derive_hierarchy_nodes` for JK already produces `Shastra` ancestor stubs;
those need no change (compound is gatha-side only). Confirm the `Shastra`
stub's NK is the bare `परमात्मप्रकाश` (no compound suffix at the Shastra
level — only at Gatha and below).

## 5. Tests

**File** (extend): `workers/ingestion/jainkosh/tests/unit/test_reference_*.py`

| Test | Asserts |
|---|---|
| `test_compound_gatha_nk_for_परमात्मप्रकाश_single_ref` | `(प.प्र./मू./1/19)` → `परमात्मप्रकाश:अधिकार:1:गाथा:19` |
| `test_compound_gatha_nk_range_expansion` | `(प.प्र./मू./1/19-21)` → three NKs, one per gatha |
| `test_legacy_gatha_nk_unchanged_for_समयसार` | `(स.सा./मू./8)` still → `समयसार:गाथा:8` |
| `test_gatha_teeka_nk_compound` | reference resolving to teeka layer produces `…:टीका:अधिकार:1:गाथा:टीका:19` |
| `test_missing_field_returns_no_edge` | malformed `(प.प्र./मू./19)` (no अधिकार) → reference dropped + warning logged |

Plus full JK suite green, plus NJ suite green. Cross-source idempotency test:

```bash
# 1) ingest a परमात्मप्रकाश envelope from NJ → creates real Gatha node with compound NK
# 2) ingest a JK keyword whose page cites that gatha → MENTIONS_TOPIC edge lands on the SAME node
# 3) assert Neo4j has exactly 1 Gatha node with that NK, is_stub=false, and 1 MENTIONS_TOPIC edge from the Keyword
```

Add as `tests/ingestion/test_cross_source_compound_id.py`.

## 6. Implementation notes / done-checklist

- [ ] Reference-NK builder switched to `get_identifier_fields` / `build_compound_suffix`
- [ ] `_insert_trailing_label` lifted to `jain_kb_common.shastra_identifiers`
      (called from both NJ envelope and JK reference parser)
- [ ] Lazy stub props carry `identifier_values` JSON
- [ ] Missing-field references emit a `parser.reference.compound.missing_field` warning,
      reference dropped (no edge), no crash
- [ ] Cross-source integration test green: NJ and JK land on the same Neo4j Gatha node
- [ ] Update authoritative docs:
      - `docs/design/data_sources/jainkosh/parser.md` — § Reference Parser:
        add a compound-identifier subsection.
      - `docs/design/data_sources/jainkosh/ingestion.md` — note that compound
        gathas use the same MERGE pattern; no apply-layer change.
      - Mark phase 4 ✓ in [`00_compound_identifiers_overview.md`](./00_compound_identifiers_overview.md).

## 7. Out of scope

- API / UI (phase 5).
- Editing the `format` strings in shastra.json — they remain
  `अधिकार/परमात्मप्रकाशगाथा/...`; only `gatha_identifier` is the NK driver.
