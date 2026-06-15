# Phase 2 — NJ parser: parse परमात्मप्रकाश + emit compound identifier values

> **Read first**: [`00_compound_identifiers_overview.md`](./00_compound_identifiers_overview.md),
> [`01_shastra_json_and_config_loader.md`](./01_shastra_json_and_config_loader.md).
>
> **Today's failure**: every परमात्मप्रकाश page logs `unclassified page`
> because `parse_myitem._OPTION_RE` only matches `$optgrp.append(...)`. The
> परमात्मप्रकाश `myItem.js` has no `<optgroup>` — options are appended directly
> via `mySel.append(...)`. The gatha-number values are also adhikaar-prefixed
> (`1-001`, `1-019-021`, `2-001`).
>
> **Goal**: NJ parser correctly classifies, splits, and emits per-gatha extracts
> for any shastra whose `gatha_identifier` is declared in shastra.json, carrying
> a structured `identifier_values: dict[field, str]` through `GathaExtract` /
> `KalashExtract`. This phase does **not** build natural keys — that lives in
> phase 3 (envelope).

---

## 1. Extend `parse_myitem.py`

**File**: `workers/ingestion/nj/parse_myitem.py`

### 1.1 Add a no-optgroup option regex

```python
# Existing (keep): $optgrp.append("<option …>")
_OPTION_RE = re.compile(
    r"""\$optgrp\.append\("<option value='([^']+)'><b>([^<]+)</b>\s*-\s*﻿?(.*?)</option>"\)"""
)

# NEW: mySel.append("<option …>") — no optgroup wrapper
_OPTION_BARE_RE = re.compile(
    r"""mySel\.append\("<option value='([^']+)'><b>([^<]+)</b>\s*-\s*﻿?(.*?)</option>"\)"""
)
```

In `_parse_block`:
- After the existing `_OPTGRP_RE` / `_OPTION_RE` matchers, add:
  ```python
  m = _OPTION_BARE_RE.search(stripped)
  if m:
      html_filename = m.group(1).strip()
      gatha_number = m.group(2).strip()
      heading_hi = _strip_bom(m.group(3))
      # adhikaar carried from leading "N-" prefix when no optgroup is present
      adh_num, gatha_canonical = _split_leading_adhikaar(gatha_number)
      result[html_filename] = GathaIndexEntry(
          html_filename=html_filename,
          gatha_number=gatha_canonical,            # "001" or "019-021"
          heading_hi=heading_hi,
          adhikaar_hi=current_adhikaar,             # may be empty
          adhikaar_number=adh_num or current_adhikaar_number or None,
      )
  ```
- Add helper `_split_leading_adhikaar(value: str) -> (int | None, str)`:
  - If value matches `^(\d+)-(\d+.*)$` AND the trailing part contains at least
    one digit, return `(int(prefix), trailing)`.
  - Else return `(None, value)`.
- Make sure the `_OPTGRP_RE` / `_OPTION_RE` code path also calls
  `_split_leading_adhikaar` defensively so values like `1-019-021` still
  classify when wrapped in an optgroup.

### 1.2 Adhikaar names from YAML

Update `workers/ingestion/nj/config.py` to accept an optional list:

```python
class NJShastra(BaseModel):
    ...
    adhikaars: list[NJAdhikaar] = []

class NJAdhikaar(BaseModel):
    number: int
    name_hi: str
```

After `parse_myitem` returns its indexes, the orchestrator looks up
`adhikaar_hi` from the config when the index didn't carry one:
```python
adh_name = next((a.name_hi for a in cfg.shastra.adhikaars if a.number == entry.adhikaar_number), "")
if not entry.adhikaar_hi:
    entry.adhikaar_hi = adh_name
```

For परमात्मप्रकाश, add to `parser_configs/nj/parmatmaprakash.yaml`:
```yaml
shastra:
  natural_key: परमात्मप्रकाश
  ...
  adhikaars:
    - { number: 1, name_hi: "परमात्म-अधिकार" }
    - { number: 2, name_hi: "मोक्ष-अधिकार" }   # confirm name from source
```
(Confirm exact names by inspecting the html headings on pages `1-001.html` and
`2-001.html`. Leave empty strings if uncertain — they can be added later.)

## 2. Multi-gatha range expansion: `_expand_gatha_numbers`

**File**: `workers/ingestion/nj/orchestrator.py` (current home of
`_expand_gatha_numbers`).

The current rule treats 2-part hyphenated values as inclusive ranges and 3+ parts
as explicit lists. With compound shastras, that still applies, but the caller now
passes the **canonical** `gatha_number` (adhikaar prefix already stripped by
`_split_leading_adhikaar`). No further change is required if `gatha_canonical`
matches `019-021` for the page `1-019-021.html`.

Add a unit test (see §6) covering this path explicitly.

## 3. Emit `identifier_values` from extracts

**File**: `workers/ingestion/nj/models.py`

```python
class GathaExtract(BaseModel):
    ...
    identifier_values: dict[str, str] = {}   # NEW
    # Pre-existing scalar fields stay for backwards-compatibility:
    adhikaar_number: int | None = None
    adhikaar_hi: str = ""

class KalashExtract(BaseModel):
    ...
    identifier_values: dict[str, str] = {}   # NEW
```

**File**: `workers/ingestion/nj/orchestrator.py` (per-extract builder):

```python
from jain_kb_common.shastra_identifiers import get_identifier_fields

def _build_identifier_values(cfg, entry, gatha_number_str):
    fields = get_identifier_fields(cfg.shastra.natural_key, "gatha") or []
    if not fields:
        return {}
    # Convention: the LAST field in gatha_identifier is the gatha number itself.
    # Earlier fields come from the GathaIndexEntry (adhikaar_number today; extend
    # via the same _split_leading_adhikaar path for any future N-N-... prefixes).
    values: dict[str, str] = {}
    for f in fields[:-1]:
        if f == "अधिकार" and entry.adhikaar_number is not None:
            values[f] = str(entry.adhikaar_number)
    values[fields[-1]] = gatha_number_str
    return values
```

Wire it into the gatha-expansion loop so every expanded `GathaExtract` carries
its own `identifier_values` (the last-field value differs per expanded gatha).
Same wiring for `parse_secondary_kalash_page` → `KalashExtract`.

When `get_identifier_fields` returns `None` (single-identifier shastra), leave
`identifier_values` as `{}` — phase 3 treats empty dict as "use legacy
single-field NK".

## 4. Logging

Add `INFO` log lines:
- `myItem.js parsed: %d primary entries (compound=%s)` — where compound is
  the boolean `bool(get_identifier_fields(...))`.
- When `_split_leading_adhikaar` strips a prefix, log at DEBUG.

## 5. Run

```bash
export NIKKYJAIN_LOCAL_PATH=/path/to/nikkyjain.github.io
python -m workers.ingestion.nj.cli parse \
  --config parser_configs/nj/parmatmaprakash.yaml \
  --batch-offset 0 --batch-limit 5 --format golden
```

Verify the output JSON:
- `shastra_parse_result.warnings` no longer contains `unclassified page` for
  the first 5 files.
- Each `gathas[i].identifier_values` has `{"अधिकार":"1","परमात्मप्रकाशगाथा":"001"}` etc.
- For `1-019-021.html` three entries appear with `परमात्मप्रकाशगाथा` = `019`, `020`, `021`.

## 6. Tests

**File** (extend): `tests/workers/nj/test_parse_myitem_unit.py`
- `test_bare_mysel_append_no_optgroup`: feed a minimal `myItem.js` string with
  the परमात्मप्रकाश layout; assert 2 entries, correct `adhikaar_number`.
- `test_split_leading_adhikaar_2part`: `"1-001"` → `(1, "001")`.
- `test_split_leading_adhikaar_3part`: `"1-019-021"` → `(1, "019-021")`.
- `test_split_leading_adhikaar_no_prefix`: `"019"` → `(None, "019")`.

**File** (extend): `tests/workers/nj/test_orchestrator_unit.py`
- `test_identifier_values_populated_for_compound_shastra`: monkeypatch
  `shastra.json` path (use the kwarg) and assert each `GathaExtract.identifier_values`.
- `test_identifier_values_empty_for_single_identifier`: समयसार fixture stays
  `{}`.

**File** (extend, optional): add a golden fixture under
`workers/ingestion/nj/tests/fixtures/parmatmaprakash/` covering 2–3 sample
html pages + a stub `myItem.js`. Run as an integration unit test.

Run:
```bash
python -m pytest tests/workers/nj/ -v
```

Full NJ suite **must remain green** (currently ~105 tests).

## 7. Implementation notes / done-checklist

- [ ] `parse_myitem.py` accepts both optgroup and bare forms; tests added
- [ ] `_split_leading_adhikaar` covers 2-part / 3-part / no-prefix cases
- [ ] `_expand_gatha_numbers` confirmed working on canonical (stripped) numbers
- [ ] `GathaExtract.identifier_values` / `KalashExtract.identifier_values` added
- [ ] `NJShastra.adhikaars` config wired; parmatmaprakash.yaml updated
- [ ] CLI golden run produces non-empty `gathas[]` with zero `unclassified` warnings
- [ ] Update `docs/design/data_sources/nikkyjain/nj_parser.md`:
      add a top-level **Compound identifier** section explaining the
      `identifier_values` field and the bare-`mySel.append` regex; update the
      "Known edge cases" table; mark phase 2 ✓ in
      [`00_compound_identifiers_overview.md`](./00_compound_identifiers_overview.md).

## 8. Out of scope

- No envelope changes (phase 3).
- No NK strings emitted from the parser — extracts carry only
  `identifier_values` + the legacy scalars; the envelope assembles the NK.
- No graph / Postgres / Mongo writes.
