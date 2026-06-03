# Phase 1 — Matcher Core Library

Pure-Python library. No DB writes. No Mongo / Postgres / Neo4j clients.
Just deterministic functions and dataclasses. Other phases depend on it.

## Goal

Given a `(source_text, target_text, block_kind)`, return:

```python
@dataclass
class MatchResult:
    matched: bool
    method: Literal["exact_normalized", "shingle_fuzzy", "none"]
    score: float                     # 0.0–1.0; 1.0 for exact
    char_start: int | None           # offset into ORIGINAL NFC target_text
    char_end: int | None             # exclusive
    normalized_source: str
    normalized_target: str
```

The lib is consumed in Phase 2 by the orchestrator and must be importable
without any service deps.

## Location

```
packages/jain_kb_common/matching/
├── __init__.py
├── normalize.py          # NFC + strip rules + offset map
├── locate.py             # exact substring + shingle fallback
├── score.py              # Jaccard, per-kind thresholds
├── ref_selection.py      # Python port of pickRefsToShow / pickHiddenRefs
├── types.py              # MatchResult, NormalizedText dataclasses
└── tests/
    ├── test_normalize.py
    ├── test_locate.py
    ├── test_score.py
    └── test_ref_selection.py
```

Tests run with `pytest packages/jain_kb_common/matching/tests/` — no DB
required.

## 1. `normalize.py`

```python
def normalize(text: str) -> NormalizedText: ...

@dataclass
class NormalizedText:
    original: str                    # input as given (after NFC)
    normalized: str                  # stripped form used for matching
    n2o: list[int]                   # n2o[i] = original index of normalized[i]
```

**Strip rules** (apply in order, after `unicodedata.normalize('NFC', s)`):

1. ZWJ (`‍`) and ZWNJ (`‌`).
2. ASCII whitespace, U+00A0, and Devanagari space variants.
3. Danda `।`, double-danda `॥`, ASCII pipe `|`.
4. Hyphens (`-`, `‐`–`―`), underscores, tildes.
5. ASCII punctuation `, . ; : ! ? " ' ( ) [ ] { } / \ * + = < > & %`.
6. Devanagari digits `०–९` and ASCII digits `0–9` **when surrounded by
   punctuation/whitespace** (verse-number markers like `।39।`); standalone
   digits inside words are kept.
7. Devanagari avagraha `ऽ`.

`n2o` is built incrementally during the pass so callers can map a
normalized-form match range back to the original. **This is the only way
char offsets stay correct against the un-stripped text the UI renders.**

Unit tests: identity on already-normalized text; round-trip
`original[n2o[i]] == normalized[i]` (where defined); sample with mixed
ZWJ + danda + digits.

## 2. `locate.py`

```python
def locate(
    source: NormalizedText,
    target: NormalizedText,
    *,
    shingle_n: int = 3,
) -> MatchResult: ...
```

Steps:

1. **Exact normalized substring**: `target.normalized.find(source.normalized)`.
   If `>= 0`, map back via `target.n2o` → `(char_start, char_end)`,
   `method="exact_normalized"`, `score=1.0`.
2. **Shingle fallback**: split `source.normalized` and `target.normalized`
   into character n-grams (size `shingle_n`). Slide a window of
   `len(source.normalized)` over `target.normalized`; for each window
   compute Jaccard of n-gram sets vs source. Pick the best window.
   Map window bounds back via `target.n2o`. `method="shingle_fuzzy"`.
3. If no candidate scores above the threshold, return
   `matched=False, method="none", char_start=None, char_end=None`.

Performance: skip the shingle pass when `len(target.normalized) >
50 * len(source.normalized)` to bound cost on long teeka bodies; in that
case use a sliding rolling-hash to find the best 5 candidate windows
before computing Jaccard. Keep the implementation small — premature
optimization is out of scope; document this as a follow-up if a real
slow case shows up.

Unit tests:
- exact substring at start/middle/end of target
- whitespace + danda variants between source and target → still exact
- partial overlap below threshold → `none`
- shingle-fuzzy win when target has 1–2 extra characters interspersed

## 3. `score.py`

```python
DEFAULT_THRESHOLD = 0.80
KIND_THRESHOLDS: dict[BlockKind, float] = {
    "prakrit_gatha": 0.90,
    "sanskrit_gatha": 0.90,
    "hindi_gatha": 0.85,
    "prakrit_text": 0.80,
    "sanskrit_text": 0.80,
    "hindi_text": 0.80,
}

def threshold_for(kind: BlockKind) -> float: ...
def jaccard(a: set, b: set) -> float: ...
```

Constants are tweakable via env (`MATCHER_THRESHOLD_<KIND>`) — read
once at import time.

## 4. `ref_selection.py`

Port of UI [`pickRefsToShow` / `pickHiddenRefs`](../../../ui/src/components/DefinitionModal.tsx).

```python
def pick_refs_to_show(block_references: list[dict]) -> list[dict]: ...
def pick_hidden_refs(block_references: list[dict]) -> list[dict]: ...
```

The UI helpers operate on the same `references` schema written by the
JainKosh parser (`{text, raw_html, inline_reference, resolved_fields,
shastra_name, teeka_name, …}`). Mirror the exact selection logic:

- Prefer non-inline references with resolved `shastra_name`.
- Fall back to the first qualifying inline reference if no non-inline
  exists.
- Hidden = matched references not surfaced by `pick_refs_to_show`.

Phase 1 owns the spec. After this lib lands, follow-up work can swap
the TS helpers in `DefinitionModal.tsx` to import a single source of
truth (e.g. via codegen or by keeping the JS as the spec and porting
only here) — but **do not change the TS helpers in this phase**.

Unit tests: feed identical fixtures used by
[`DefinitionModal.test.ts`](../../../ui/src/__tests__/components/DefinitionModal.test.ts);
assert identical outputs.

## 5. Public surface

```python
# packages/jain_kb_common/matching/__init__.py
from .normalize import normalize, NormalizedText
from .locate import locate
from .score import threshold_for, KIND_THRESHOLDS
from .ref_selection import pick_refs_to_show, pick_hidden_refs
from .types import MatchResult, BlockKind
```

## Logging

Use `logging.getLogger("jain_kb.matching")`. INFO for matcher entry,
DEBUG for per-window scores. No prints.

## Acceptance / DoD

- [ ] All unit tests pass: `pytest packages/jain_kb_common/matching/`.
- [ ] `locate` deterministic across runs (no random tiebreakers).
- [ ] Offset round-trip property test: for a known
      `(source, target)` pair, the returned `target[char_start:char_end]`
      contains exactly the original NFC slice corresponding to the
      matched normalized region.
- [ ] `pick_refs_to_show` outputs match the TS test fixtures byte-for-byte.

## Manual verification

```bash
source .venv/bin/activate
pip install -e packages/jain_kb_common
python -c "from jain_kb_common.matching import normalize, locate; \
  s = normalize('आत्मा द्वादशांगम् आत्मपरिणामत्वात।'); \
  t = normalize('... आत्मा द्वादशांगम् आत्मपरिणामत्वात ...'); \
  r = locate(s, t); print(r)"
```

## Implementation Notes / Diversions

- All files placed at `packages/jain_kb_common/jain_kb_common/matching/` (importable as `jain_kb_common.matching`). The spec path `packages/jain_kb_common/matching/` was a shorthand; the full path preserves the package hierarchy.

- **`locate` signature**: added an optional `threshold: float = DEFAULT_THRESHOLD` parameter so Phase 2 can pass per-`BlockKind` thresholds without a separate call site. Not in original spec but required for the function to set `matched` correctly.

- **Digit rule (rule 6)**: implemented as a two-pass approach — first pass marks whitespace/punctuation/etc., second pass finds digit runs and checks if both left and right neighbors (or string edge) are already marked as stripped. This correctly handles multi-digit runs like `।39।`.

- **Shingle guard**: when `len(target) > 50 × len(source)`, falls back to strided window sampling (every `n_windows / (50×5)` positions). Rolling-hash replacement documented as a TODO in `locate.py`.

- **`score.py` env override**: reads `os.environ` on each `threshold_for()` call (not cached at import time). Makes the env override testable without import-order constraints, with negligible perf cost.

- **`ref_selection.py`**: uses `id(r)` for identity comparison, mirroring JS `Set` reference semantics. The `pick_refs_to_show` fallback to inline occurs only when zero non-inline refs exist (even unresolved ones), exactly matching the TS `if (nonInline.length > 0)` branch.

- **Tests**: 87 tests, all pass. Run with `pytest packages/jain_kb_common/jain_kb_common/matching/tests/ -v`.
