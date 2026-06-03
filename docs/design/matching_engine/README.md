# Matching Engine Wiki

Implementation-level reference for the extract matching system. This document replaces the earlier phase-plan README and should be treated as the current source of truth for agents changing matching behavior in `workers/matching`, `services/core_service`, or `ui/`.

## 1. Purpose

The matching engine connects JainKosh definition/topic-extract blocks to the exact substring they came from in NJ shastra content.

It exists so the UI can:

- show a "View in Shastra" link next to a reference inside `DefinitionModal`
- deep-link into the reading page
- highlight the exact matched span in gatha/teeka/bhaavarth/kalash text

The output is stored in Mongo `extract_matches`.

## 2. End-to-End Flow

1. JainKosh ingestion creates source blocks in Mongo and stub-linked graph edges in Neo4j.
2. NJ ingestion populates Mongo target docs for gathas, teekas, bhaavarths, and kalash variants.
3. `scripts/match_extracts.py` runs the worker pipeline in `workers/matching/`.
4. The worker resolves each eligible source block to one or more Neo4j stub targets.
5. Each source/target pair is normalized and matched using `jain_kb_common.matching`.
6. The worker upserts one `extract_matches` row per source/target pair.
7. `core_service` hydrates `match_natural_keys` back into keyword/topic payloads.
8. The UI lazily fetches those match docs, renders shastra links, and passes `?match=<natural_key>` to the reading page.
9. The reading page fetches the match doc and highlights the stored `char_start`/`char_end` range when the status is `matched`.

## 3. Source Side

Eligible source docs:

- `keyword_definitions.page_sections[].definitions[].blocks[]`
- `topic_extracts.blocks[]`

Implemented in [source_iter.py](../../../workers/matching/source_iter.py).

Rules:

- skip block kinds `see_also` and `table`
- skip blocks with no references selected by shared `pick_refs_to_show`
- use the same reference-selection semantics as the UI
- emit one `SourceBlock` per candidate block

Important detail:

- matching eligibility is driven by `jain_kb_common.matching.pick_refs_to_show`, which is the Python port of `ui/src/components/DefinitionModal.tsx`
- if the UI changes reference-picking rules, the Python helper must change in lockstep

## 4. Target Side

Implemented in [target_resolver.py](../../../workers/matching/target_resolver.py).

The resolver:

- looks up Neo4j edges from a source block to stub nodes
- identifies the stub label
- maps `(stub_label, block_kind)` to a Mongo collection
- derives the final Mongo `natural_key`
- loads the Mongo doc and extracts target text

Current stub-to-collection routing:

| Stub label | Source block kind(s) | Target collection |
|---|---|---|
| `Gatha` | `prakrit_gatha`, `prakrit_text` | `gatha_prakrit` |
| `Gatha` | `sanskrit_gatha` | `gatha_sanskrit` |
| `GathaTeeka` | `sanskrit_text` | `gatha_teeka_sanskrit` |
| `GathaTeekaBhaavarth` | `hindi_text` | `gatha_teeka_bhaavarth_hindi` |
| `Kalash` | `sanskrit_gatha`, `sanskrit_text` | `kalash_sanskrit` |
| `Kalash` | `hindi_gatha`, `hindi_text` | `kalash_hindi` |
| `KalashBhaavarth` | `hindi_text` | `kalash_bhaavarth_hindi` |

Current non-goal:

- `Page` stubs are discovered but explicitly skipped in v1

## 5. Match Algorithm

Shared matching code lives in `packages/jain_kb_common/jain_kb_common/matching/`.

Key files:

- `normalize.py`
- `locate.py`
- `score.py`
- `ref_selection.py`

### Normalization

`normalize(text)` returns:

- `original`: NFC-normalized source text
- `normalized`: stripped text used for matching
- `n2o`: normalized-index to original-index map

Stripping rules currently remove:

- ZWJ / ZWNJ
- whitespace
- danda / double danda / pipe
- hyphens, dashes, underscore, tilde
- ASCII punctuation
- bounded digit runs
- Devanagari avagraha
- Devanagari visarga

The `n2o` mapping is what makes UI highlighting possible.

### Locate

`locate(source, target)` does:

1. exact normalized substring search
2. fallback to fixed-length character shingle Jaccard search

Return methods:

- `exact_normalized`
- `shingle_fuzzy`
- `none`

### Thresholds

Defaults from `score.py`:

- `prakrit_gatha`: `0.90`
- `sanskrit_gatha`: `0.90`
- `hindi_gatha`: `0.85`
- `prakrit_text`: `0.80`
- `sanskrit_text`: `0.80`
- `hindi_text`: `0.80`

Thresholds can be overridden with env vars like `MATCHER_THRESHOLD_PRAKRIT_GATHA`.

## 6. Stored Output

Rows are written by [apply_match.py](../../../workers/matching/apply_match.py) into Mongo `extract_matches`.

Natural key shape:

- keyword definition block:
  `match:keyword_definition:<parent_nk>:s<section>:d<definition>:b<block>:target:<target_nk>`
- topic extract block:
  `match:topic_extract:<parent_nk>:b<block>:target:<target_nk>`

Stored payload includes:

- `source`
- `target`
- `match`
- `matcher_version`
- `ingestion_run_id`

`match.status` values:

- `matched`
- `unmatched`
- `target_missing`

Behavioral detail:

- rows are still written for `unmatched` and `target_missing`
- that is intentional so the UI can still expose a grey deep-link when the target exists but text matching failed

## 7. Worker Entry Points

CLI lives in [scripts/match_extracts.py](../../../scripts/match_extracts.py).

Modes:

- `--mode all`
- `--mode jainkosh-keyword --nk <keyword_nk>`
- `--mode jainkosh-topic --nk <topic_nk>`
- `--mode nj-shastra --nk <shastra_nk>`

Useful flags:

- `--dry-run`
- `--limit <n>`

Examples:

```bash
python scripts/match_extracts.py --mode all
python scripts/match_extracts.py --mode nj-shastra --nk samaysar
python scripts/match_extracts.py --mode jainkosh-keyword --nk आत्मा --dry-run
```

Exit behavior:

- exit `1` when any `target_missing` rows were encountered
- exit `1` when unmatched ratio is at least `50%`

## 8. Core Service Integration

The matching engine is exposed in `services/core_service` in two ways.

### 8.1 Hydration into keyword/topic payloads

Implemented in:

- [keywords.py](../../../services/core_service/domains/data/services/keywords.py)
- [topics.py](../../../services/core_service/domains/data/services/topics.py)

Behavior:

- keyword definition blocks receive `match_natural_keys?: string[]`
- topic extract blocks receive `match_natural_keys?: string[]`
- all statuses are included: `matched`, `unmatched`, `target_missing`

This means the UI does not need to compute matches itself. It only receives block-level foreign keys.

### 8.2 Extract-match fetch endpoint

Implemented in:

- [extract_matches router](../../../services/core_service/domains/data/routers/extract_matches.py)
- [extract_matches service](../../../services/core_service/domains/data/services/extract_matches.py)

Route:

- `GET /v1/extract-matches/{natural_key}`

Returns the stored match doc, minus Mongo `_id`.

## 9. UI Integration

### Definition modal

Relevant files:

- [DefinitionModal.tsx](../../../ui/src/components/DefinitionModal.tsx)
- [ViewInShastraButton.tsx](../../../ui/src/components/ViewInShastraButton.tsx)

Behavior:

- blocks receive `match_natural_keys`
- the modal calls `useMatchEntries(match_natural_keys)`
- each key is fetched via `getExtractMatch`
- matches are correlated back to visible refs primarily by `shastra_name`, and secondarily by resolved gatha field
- `target_missing` links are hidden
- `matched` links render in blue
- `unmatched` links still render, but in muted grey

This is why unmatched rows still matter operationally.

### Reading page

Relevant files:

- [page.tsx](../../../ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx)
- [gatha-content.ts](../../../ui/src/lib/gatha-content.ts)

Behavior:

- deep links are built as `/shastras/<shastra>/gathas/<number>?match=<match_nk>`
- the reading page fetches the match doc when `searchParams.match` is present
- a highlight is applied only when:
  - `match.status === 'matched'`
  - `match.target.natural_key` equals the panel text being rendered
  - `char_start` and `char_end` are in bounds

The same reading page supports highlights for:

- prakrit gatha
- sanskrit gatha
- sanskrit teeka
- hindi bhaavarth
- kalash sanskrit
- kalash hindi
- kalash bhaavarth

## 10. Important Invariants

- UI and Python reference selection must stay identical.
- Matching offsets are stored against NFC-normalized original text, not raw unnormalized input.
- `extract_matches` is idempotent at the natural-key level; reruns update the same row.
- One source block may fan out to multiple target rows if Neo4j returns multiple stubs.
- `target_missing` means the graph edge exists but the routed Mongo target doc does not.
- `unmatched` means the target doc exists but the matcher could not clear the threshold.

## 11. Known Gaps

- `Page` stub matching is not implemented.
- Matching is CLI-triggered, not async-worker driven.
- The UI fetches match docs one-by-one from the client; there is no batch endpoint yet.
- `buildGathaHref` derives the reading route from `target.natural_key`, so any future target-key format change must update that helper too.
- The UI TypeScript `ExtractMatch` type is a trimmed client view of the backend document, not a full schema mirror.

## 12. Change Checklist For Agents

When changing matching behavior, check all of these:

1. `packages/jain_kb_common/jain_kb_common/matching/*`
2. `workers/matching/source_iter.py`
3. `workers/matching/target_resolver.py`
4. `workers/matching/apply_match.py`
5. `scripts/match_extracts.py`
6. `services/core_service/domains/data/services/keywords.py`
7. `services/core_service/domains/data/services/topics.py`
8. `services/core_service/domains/data/routers/extract_matches.py`
9. `ui/src/components/DefinitionModal.tsx`
10. `ui/src/components/ViewInShastraButton.tsx`
11. `ui/src/lib/gatha-content.ts`
12. `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`

At minimum, also review:

- matching unit tests under `packages/jain_kb_common/jain_kb_common/matching/tests/`
- worker tests under `tests/workers/matching/`
- UI tests around `DefinitionModal` and `gatha-content`
