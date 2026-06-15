# Phase 3 — NJ envelope + apply: compound natural keys end-to-end

> **Read first**: phases [`00`](../00_compound_identifiers_overview.md),
> [`01`](../01_shastra_json_and_config_loader.md),
> [`02`](../02_nj_parser_compound_id_support.md).
>
> **Goal**: produce compound NKs for `Gatha`, `GathaTeeka`, `GathaTeekaBhaavarth`,
> `Kalash`, `KalashBhaavarth` in NJ's `would_write` envelope, and persist them
> idempotently in Postgres + Mongo + Neo4j without breaking existing single-id
> shastras (समयसार, प्रवचनसार, …).
>
> **Touch surface**: `workers/ingestion/nj/envelope.py` (the big one),
> `workers/ingestion/jainkosh/apply.py` (no logic change — NK is opaque),
> `packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py`
> (use compound `gatha_number`), one Alembic migration is **NOT** needed
> because `gatha_number` is already `TEXT` and `adhikaar` is already `JSONB`.

---

## 1. Envelope NK builder

**File**: `workers/ingestion/nj/envelope.py`

### 1.1 Replace `_gatha_nk` and friends

Today:
```python
def _gatha_nk(shastra_nk: str, gatha_number: str) -> str:
    return f"{shastra_nk}:{_GATHA}:{_norm_num(gatha_number)}"
```

Add a new helper that uses `identifier_values` when present:

```python
from jain_kb_common.shastra_identifiers import (
    get_identifier_fields, build_compound_suffix, canonical_segment_name,
)

def _gatha_suffix(shastra_nk: str, gatha: "GathaExtract") -> str:
    """Return the NK suffix that follows the shastra prefix.

    Compound shastras → `अधिकार:1:गाथा:2`.
    Legacy shastras   → `गाथा:8`.
    """
    if gatha.identifier_values:
        s = build_compound_suffix(shastra_nk, gatha.identifier_values, kind="gatha")
        if s:
            return s
    # Legacy fallback — identical to today's behaviour
    return f"{_GATHA}:{_norm_num(gatha.gatha_number)}"


def _gatha_nk(shastra_nk: str, gatha: "GathaExtract") -> str:
    return f"{shastra_nk}:{_gatha_suffix(shastra_nk, gatha)}"
```

**Update every call site** to pass the `GathaExtract` (not just the number
string). Callers currently include: gatha node emission, teeka-doc gatha
linkage, kalash-page parent linkage, table emission, NJ mention edges.

### 1.2 GathaTeeka / GathaTeekaBhaavarth / Kalash / KalashBhaavarth NKs

Today (data_model_graph.md §"Natural-key format conventions"):
```
GathaTeeka           {shastra}:{teeka}:गाथा:टीका:{n}
GathaTeekaBhaavarth  {shastra}:{teeka}:{publisher_id}:गाथा:टीका:भावार्थ:{n}
Kalash               {shastra}:{teeka}:कलश:{k}
KalashBhaavarth      {shastra}:{teeka}:{publisher_id}:कलश:भावार्थ:{k}
```

New shape — the **gatha suffix replaces `गाथा:{n}`** wherever it appears, and
the kalash suffix replaces `कलश:{k}`:

```
GathaTeeka            compound:  {shastra}:{teeka}:अधिकार:1:गाथा:टीका:2
                      legacy:    {shastra}:{teeka}:गाथा:टीका:8
GathaTeekaBhaavarth   compound:  {shastra}:{teeka}:{pubid}:अधिकार:1:गाथा:टीका:भावार्थ:2
                      legacy:    {shastra}:{teeka}:{pubid}:गाथा:टीका:भावार्थ:8
Kalash                compound:  {shastra}:{teeka}:अधिकार:1:कलश:7      (when kalash_identifier set)
                      legacy:    {shastra}:{teeka}:कलश:7
KalashBhaavarth       compound:  {shastra}:{teeka}:{pubid}:अधिकार:1:कलश:भावार्थ:7
                      legacy:    {shastra}:{teeka}:{pubid}:कलश:भावार्थ:7
```

Implementation: in each NK builder, compose
```
nk = f"{teeka_nk}:{suffix_with_inserted_label}"
```
where `suffix_with_inserted_label` is built by taking the gatha/kalash suffix
and **inserting the trailing label** (`टीका`, `टीका:भावार्थ`, `भावार्थ`) before
the **last value**.

```python
def _insert_trailing_label(suffix: str, label: str) -> str:
    # "अधिकार:1:गाथा:2" + "टीका" → "अधिकार:1:गाथा:टीका:2"
    head, _, tail = suffix.rpartition(":")
    if not head:
        return f"{label}:{suffix}"
    return f"{head}:{label}:{tail}"
```

### 1.3 Hierarchy emission (`shastra_hierarchy.enabled`)

`_derive_hierarchy_nodes(label, key)` in envelope.py parses the structured key
to extract `shastra_natural_key`, `teeka_natural_key`, `publisher_id`. Update
the parser to recognise compound suffixes:

- Split on `:` once at the shastra prefix; then again at the first `अधिकार`
  segment (or whatever the first compound field's canonical segment name is).
- Provide `_derive_props` with the compound `identifier_values` so the lazy
  stub `Gatha` node carries `gatha_number = <compound suffix without leading "अधिकार:1:गाथा:" prefix? actually keep the **suffix as-is** because Postgres `gatha_number` will store it verbatim>` (see §2).

Simpler implementation: emit the structured `identifier_values` dict as a
top-level prop on the lazy Gatha node:
```python
props = {
    "shastra_natural_key": shastra,
    "gatha_number": gatha_suffix_after_shastra,   # e.g. "अधिकार:1:गाथा:2"
    "identifier_values": json.dumps(values_dict, ensure_ascii=False),
}
```
Add `identifier_values` to the per-label stub props allowlist in
`packages/jain_kb_common/jain_kb_common/db/neo4j/stubs.py` `_STUB_PROPS_BY_LABEL`.

### 1.4 Mongo doc keys

`gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`, `kalash_sanskrit`,
`kalash_hindi` Mongo documents currently embed the legacy gatha number into
their `natural_key`. They become:

```
gatha_teeka_sanskrit
  natural_key = {teeka_nk}:{gatha_suffix_post_shastra}:टीका:san
              = "परमात्मप्रकाश:टीका:अधिकार:1:गाथा:2:टीका:san"
  gatha_teeka_natural_key = "{teeka_nk}:{gatha_suffix_post_shastra}"
```

Reuse the new helpers everywhere these strings are assembled. The "edge case"
caveat in `docs/design/data_model/data_model_graph.md` (Mongo NK ≠ Neo4j NK)
**remains true** and is intentionally unresolved by this phase.

## 2. Postgres `gathas.gatha_number`

**No schema migration.** `gatha_number` is `TEXT` today. Convention from this
phase on:

- For shastras with `gatha_identifier`, `gatha_number` stores the **full suffix
  past the shastra prefix**, e.g. `अधिकार:1:गाथा:2`.
- For shastras without `gatha_identifier`, behaviour is unchanged
  (`gatha_number = "008"`).
- `gathas.adhikaar` (JSONB) is populated with the structured
  `identifier_values` dict for compound shastras — replaces the existing
  single-field usage.

Add a unique constraint check in code (no SQL change): `(shastra_id,
gatha_number)` is already the natural identity; the wider compound string just
slots in.

Update `upsert_gatha` in
`packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py` to accept the
suffix string verbatim — it already does.

## 3. NJ apply

`workers/ingestion/nj/apply_ingest.py` (or whichever module wraps
`apply_approved_keyword_payload` for NJ envelopes) does **not** need any logic
change — it treats NKs opaquely. Verify by re-running the existing integration
test pack:

```bash
python -m pytest tests/workers/nj/test_envelope.py tests/ingestion/ -v
```

Confirm: existing samaysaar / pravachansaar fixtures still produce identical
NKs (no regressions); a new parmatmaprakash fixture produces compound NKs.

## 4. Neo4j constraints

`Gatha.natural_key` uniqueness constraint already exists. Compound NKs satisfy
it because they are still strings. No DDL change.

Optional but **recommended**: add a per-label property index on
`Gatha.shastra_natural_key` to speed up traversals by-shastra. Not blocking.

## 5. Tests

Extend `tests/workers/nj/test_envelope.py`:

| Test | Asserts |
|---|---|
| `test_gatha_nk_compound_shape` | परमात्मप्रकाश fixture → `परमात्मप्रकाश:अधिकार:1:गाथा:2` |
| `test_gatha_teeka_nk_inserts_label_before_value` | `…अधिकार:1:गाथा:टीका:2` |
| `test_gatha_teeka_bhaavarth_nk_compound` | …:टीका:0:अधिकार:1:गाथा:टीका:भावार्थ:2 |
| `test_legacy_shastra_nk_unchanged` | समयसार golden bytes identical |
| `test_mongo_natural_key_compound` | gatha_teeka_sanskrit doc carries `…:टीका:san` suffix on top of compound |
| `test_hierarchy_lazy_stub_props_carry_identifier_values` | lazy Gatha stub has `identifier_values` JSON prop |
| `test_idempotency_re_apply_compound_envelope` | apply twice → same row counts, MERGE-safe |

Plus full NJ suite green. Plus the JK suite green (proves no accidental
cross-impact).

## 6. Implementation notes / done-checklist

- [x] `_gatha_nk`, GathaTeeka NK, GathaTeekaBhaavarth NK, Kalash NK, KalashBhaavarth NK
      all routed through the compound builder via `_gatha_suffix` + `_insert_trailing_label`
- [x] Stub props allowlist extended (`identifier_values` added to `_STUB_PROPS_BY_LABEL["Gatha"]`)
- [x] Postgres `gatha_number` stores compound suffix; `adhikaar` stores `identifier_values` dict
- [x] Mongo doc NKs updated (gatha_teeka_sanskrit, gatha_teeka_bhaavarth_hindi, teeka_gatha_mapping, shortfont)
- [x] All existing (समयसार, …) tests pass byte-identical — 42 pre-existing tests green
- [ ] परमात्मप्रकाश new golden checked in (requires `NIKKYJAIN_LOCAL_PATH` — deferred)
- [x] Update authoritative docs:
      - `docs/design/data_model/data_model_graph.md` ✓
      - `docs/design/data_sources/nikkyjain/nj_ingestion.md` ✓
      - `docs/design/specs/compound_identifiers/00_compound_identifiers_overview.md` ✓ (phase 3 marked)

## 7. Out of scope

- JainKosh reference resolution still emits **legacy** NKs after this phase.
  Phase 4 closes that gap. Until phase 4 ships, JK references to
  परमात्मप्रकाश gathas land on stub `Gatha` nodes with **legacy** NKs (e.g.
  `परमात्मप्रकाश:गाथा:1`); these are inert mismatches and won't pollute the
  compound nodes. Document this temporary divergence in the phase-3 commit.
- No API/UI changes (phase 5).
