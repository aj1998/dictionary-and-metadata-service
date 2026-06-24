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
| `Gatha` | `sanskrit_gatha`, `sanskrit_text` | `gatha_sanskrit` |
| `GathaTeeka` | `sanskrit_text` | `gatha_teeka_sanskrit` |
| `GathaTeekaBhaavarth` | `hindi_text` | `gatha_teeka_bhaavarth_hindi` |
| `Kalash` | `sanskrit_gatha`, `sanskrit_text` | `kalash_sanskrit` |
| `Kalash` | `hindi_gatha`, `hindi_text` | `kalash_hindi` |
| `KalashBhaavarth` | `hindi_text` | `kalash_bhaavarth_hindi` |

### Anvayartha (शब्दार्थ) second target

When a `Gatha` stub resolves to a verse collection (`gatha_prakrit` /
`gatha_sanskrit`) **and** the source block carries an absorbed
`hindi_translation`, the resolver emits a *second* target against the gatha's
Hindi अन्वयार्थ: the first `teeka_gatha_mapping` doc for that gatha (mirrors the
reading page's `primaryMapping = teekaMapping[0]`). This target is matched
against the block's `hindi_translation` (not `text_devanagari`) using the
`hindi_text` threshold, and its `char_start/end` are stored against the doc's
`full_anyavaarth` — exactly what the शब्दार्थ panel renders. So one source block
fans out to both the verse match and the अन्वयार्थ match, and the UI highlights
both panels at once. Implemented via `Target.source_text_kind` /
`Target.match_block_kind` and `_resolve_anvayartha_target` in
[target_resolver.py](../../../workers/matching/target_resolver.py). No mapping
doc → no row (we don't emit a noisy `target_missing` for anvayartha-less gathas).

### Bhaavarth (भावार्थ) for `Gatha`-primary verses (shastra-type roots)

The `GathaTeeka` bhaavarth path below only fires for shastras that *have* a
Sanskrit टीका. Shastra-type roots like **तत्त्वार्थसूत्र** have no टीका ("टीका
उपलब्ध नहीं है"): the sutra *is* the gatha, so JainKosh emits a `Gatha` stub, not
`GathaTeeka`. Their published भावार्थ (सर्वार्थसिद्धि / राजवार्तिक / …) nonetheless
lives in `gatha_teeka_bhaavarth_hindi`, and a quoting block's `hindi_translation`
*is* that भावार्थ. So when a `Gatha` verse target's block carries a
`hindi_translation`, `_resolve_gatha_bhaavarth_targets` also emits a भावार्थ
target — **fanning out one target per publication** bhaavarth doc for the gatha.
Because bhaavarth docs carry no `gatha_natural_key`, the lookup is a regex over
`gatha_teeka_natural_key` (`^{shastra}:[^:]+:{gseg}$`, with the zero-pad
alternate of `gseg` also tried). Each publication is scored independently, so
only the one actually containing the quote clears threshold. No bhaavarth doc →
no row. This mirrors the अन्वयार्थ second target and runs alongside it for every
`Gatha` verse with a Hindi translation.

### Bhaavarth (भावार्थ) second target

A `sanskrit_text` block resolves to a `GathaTeeka` stub and matches the Sanskrit
teeka (`gatha_teeka_sanskrit`) on `text_devanagari`. But such a block's
`hindi_translation` **is** the published Hindi भावार्थ — the same text the
reading page renders in the bhaavarth panel. So, exactly mirroring the
अन्वयार्थ pattern above, when the primary target is a Sanskrit teeka **and** the
source block carries a `hindi_translation`, the resolver emits a *second* target
against the gatha's `gatha_teeka_bhaavarth_hindi` doc, matched on the block's
`hindi_translation` (not `text_devanagari`) with the `hindi_text` threshold.
The bhaavarth doc is keyed with a publication index
(`प्रवचनसार:तत्त्वप्रदीपिका:0:96:भावार्थ:hi`) that the `GathaTeeka` stub does not
carry, so `_resolve_bhaavarth_target` looks it up by the doc's
`gatha_teeka_natural_key` field (`{teeka_nk}:{gseg}`, recovered by stripping the
`:टीका:san` suffix from the teeka Mongo NK) rather than re-deriving the prefixed
NK. No bhaavarth doc → no row (we don't emit a noisy `target_missing`). So one
`sanskrit_text` block fans out to both the Sanskrit-teeka match and the भावार्थ
match, and the UI highlights both panels at once. Implemented via
`_resolve_bhaavarth_target` in
[target_resolver.py](../../../workers/matching/target_resolver.py).

### Compound-identifier shastras (परमात्मप्रकाश and similar)

For shastras declared with a `gatha_identifier` in
[`shastra.json`](../../../parser_configs/_manual_configs/shastra.json) — see the
[Compound Identifiers wiki](../specs/compound_identifiers/README.md) — the Gatha
NK carries the full compound suffix
(`परमात्मप्रकाश:अधिकार:1:गाथा:001`). The resolver derives the per-gatha Mongo
segment via `_mongo_seg_from_gatha_nk`, which mirrors
`workers/ingestion/nj/envelope._gatha_mongo_segment`:

- compound shastra → strip the `{shastra_nk}:` prefix and keep the full suffix
  (`अधिकार:1:गाथा:001`)
- legacy shastra → use only the trailing numeric segment (`8`)

This affects `GathaTeeka` and `GathaTeekaBhaavarth` Mongo NK assembly —
previously they used `gatha_nk.split(":")[-1]`, which dropped the
`अधिकार:N:गाथा:` prefix for compound shastras and silently produced
`target_missing` for every compound teeka/bhaavarth row.

#### Zero-padding fallback (width-agnostic)

JainKosh's reference parser builds Neo4j Gatha stub NKs from raw citation
values (`…:गाथा:12`), but NJ ingestion zero-pads the trailing numeric to
3 digits (`…:गाथा:012`). When the resolver's primary Mongo lookup misses,
`_padded_variant_nk` re-pads (or strips padding from) the last numeric
colon-segment and retries — so both citation forms hit the same stored doc.
This mirrors the `_find_compound_gatha_fuzzy` server-side fallback in
`services/core_service/domains/data/routers/gathas.py`. The fallback applies
to any Mongo NK shape, so it also covers compound teeka/bhaavarth lookups
where the trailing number lives mid-NK (e.g. `…:गाथा:012:टीका:san`). Successful
fallbacks emit `INFO target_resolver fuzzy zero-pad match: <unpadded> → <padded>`.

`_padded_variant_nk` only tries **one** fixed width (3). But NJ pads the
gatha/sutra number to a *chapter-dependent* width — e.g. तत्त्वार्थसूत्र अध्याय 5
stores `सूत्र:01` (2 digits, the chapter's max sutra count), so neither the
exact (`सूत्र:1`) nor the 3-pad (`सूत्र:001`) lookup hit it. When both miss,
`_numeric_variant_regex` matches the trailing number by **value** regardless of
zero-padding width (`^…:सूत्र:0*1:sanskrit$`), and the resolved doc's NK (minus
its `:lang` suffix) is adopted as the metadata `gatha_natural_key` so UI
deep-links land on the stored padding. Emits `INFO target_resolver fuzzy
width-agnostic match: <derived> → <resolved>`.

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

- `original`: the **raw NFC** text — exactly the coordinate space the UI renders
  (it applies `normalizeNFC(text)` then slices by char offset). The
  length-changing canonicalizations (anusvara `ं` → class-nasal/`म्`, र्-gemination
  collapse) are **not** reflected in `original`; they happen on an internal
  working buffer whose per-character raw-NFC offsets are threaded into `n2o`.
- `normalized`: stripped + canonicalized text used for matching
- `n2o`: normalized-index → **raw-NFC**-index map. Because a single anusvara may
  expand to two characters (`ं` → `म` + `्`), `n2o` is non-decreasing (not
  strictly increasing): both injected chars share the anusvara's raw offset. This
  guarantees `char_start`/`char_end` from `locate()` land on the un-transformed
  text the UI highlights — a mismatch here drifts the highlight forward by one
  char per edit before the match.

Stripping rules currently remove:

- ZWJ / ZWNJ
- whitespace
- danda / double danda / pipe
- hyphens, dashes, underscore, tilde
- ASCII punctuation
- all digits (ASCII + Devanagari), unconditionally — verse markers like `।1।` /
  `|1|` and digits glued to a word (`गाथा9`) are always stripped on both sides
- Devanagari avagraha
- Devanagari visarga
- Devanagari chandrabindu (`ँ` U+0901) — Apabhramsha-era prints (e.g.
  परमात्मप्रकाश) emit chandrabindu inconsistently, so stripping it makes
  `सण्णाणेँ` and `सण्णाणे` collapse identically.

- **Word-final anusvara → `म्`.** In Sanskrit/Prakrit a word-final anusvara
  represents `म्` (e.g. `द्रव्यं` ≡ `द्रव्यम्`, `अहं` ≡ `अहम्`). The anusvara pass
  therefore canonicalizes any `ं` *not* followed by a consonant (string end,
  before a vowel, etc.) to `म्` + halant, space-tolerantly (`द्रव्यं इति` collapses
  to the same form as `द्रव्यम् इति`). This is the complement of the
  before-a-consonant rule below.
- **Unicode curly quotation marks stripped** (U+2018/U+2019 single, U+201C/U+201D
  double). The corpus wraps embedded quotes in these (e.g. a टीका writes
  `‘समगुणपर्यायं द्रव्यम्’`) while JainKosh extracts drop them; they are stripped
  like the ASCII quotes in strip rule 5.

A third **preprocess** pass also runs alongside the Tiryak and anusvara passes:

- **`र्`-gemination collapse.** The old Sanskrit orthographic convention of doubling a consonant after `र्` (e.g. `पर्य्याय` ↔ `पर्याय`, `धर्म्म` ↔ `धर्म`, `कर्म्म` ↔ `कर्म`) is canonicalized to the single-consonant form. Pattern: `र ् C ् C` → `र ् C` where both `C`s are the same Devanagari consonant. Scoped to "after `र्`" so legitimate same-consonant conjuncts elsewhere (e.g. `क्क` in `मक्का`) are untouched. ZWJ/ZWNJ between the doubled consonant and halant is tolerated.

In addition to stripping, two **preprocess** passes run before the strip pass to canonicalize OCR/spelling variants that would otherwise produce false negatives:

- **Vedic Sign Tiryak (U+1CED `᳭`) → halant (U+094D `्`)**. Some OCR'd shastras emit `᳭` where a real halant belongs (e.g. `तिर्यङ᳭मनुष्य` vs `तिर्यङ्मनुष्य`). The substitution makes the two forms identical and also lets the next pass fire on it.
- **Anusvara sandhi canonicalization**. Each anusvara `ं` followed by a Devanagari consonant is replaced with the sandhi-class nasal + halant + consonant:
  - `ं` + क-class (क ख ग घ ङ) → `ङ्` + consonant
  - `ं` + च-class (च छ ज झ ञ) → `ञ्` + consonant
  - `ं` + ट-class (ट ठ ड ढ ण) → `ण्` + consonant
  - `ं` + त-class (त थ द ध न) → `न्` + consonant
  - `ं` + प-class (प फ ब भ म) → `म्` + consonant
  - `ं` + semivowel/sibilant/ह → `न्` + consonant (convention varies; we pick `न्` so both forms collapse identically)

  This makes `संबंध` (anusvara form) and `संबन्ध` (spelled-out form) both canonicalize to `सम्बन्ध` → exact match. ZWJ/ZWNJ between anusvara and the consonant is tolerated.

  An earlier attempt that *stripped* anusvara and any `[ङञणनम]्`+consonant bigram was rejected because it over-collapsed legitimate conjuncts: e.g. `अभ्युपगम्य` (gerund) has a real `म्य` conjunct that is not a nasalization, and stripping it would have made `अभ्युपगम्य` look identical to `अभ्युपगम`. Sandhi canonicalization avoids this — only an actual `ं` ever triggers a rewrite, so non-nasalization conjuncts are untouched.

The `n2o` mapping is what makes UI highlighting possible.

### Locate

`locate(source, target)` does:

1. exact normalized substring search
2. ellipsis-bridged exact-with-fuzzy fallback (when the source contains a literal run of 3+ dots)
3. fallback to fixed-length character shingle Jaccard search

Return methods:

- `exact_normalized`
- `exact_normalized_ellipsis`
- `shingle_fuzzy`
- `none`

#### Ellipsis bridging

When the source's original text contains a run of `...` (three or more dots), the matcher treats the ellipsis as a **wildcard gap** and requires the segments around it to appear in order inside the target. This is needed for JainKosh extracts like:

```
भावप्रच्छन्नेषु ... सर्वेष्वपि... द्रष्टृत्वं प्रत्यक्षत्वात्
```

where the source quotes only the bookends of a longer commentary passage with `...` standing in for the elided middle.

Procedure:

1. Split `source.original` on `\.{3,}` to get segments; normalize each.
2. Search each segment sequentially in `target.normalized`, advancing a cursor after each successful match so order is enforced. Each segment first tries exact substring; if that fails, a per-segment shingle window scan with a relaxed threshold (`max(0.6, threshold - 0.15)`) is used to tolerate per-segment OCR variation.
3. If every segment is found, the returned span covers **first-segment start → last-segment end** in the target's original text, so the UI highlights the whole bridged region (including the elided middle).
4. If any segment cannot be located (even fuzzily) the method falls through to the shingle fallback (step 3 of the main pipeline).

Method name: `exact_normalized_ellipsis`. Downstream code that switches on `result.method` must accept this new value.

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

**Read-time enrichment for kalash targets.** The matcher worker leaves
`target.gatha_natural_key` null for `kalash_sanskrit` / `kalash_hindi` targets
because the Neo4j `Kalash` stub does not store the owning gatha
(`Kalash → Gatha` lives only in Postgres via `kalashes.gatha_id`). The
extract-matches service backfills this field at read-time: when the target
collection is one of `kalash_sanskrit` / `kalash_hindi` and `gatha_natural_key`
is missing, it reconstructs the Kalash natural_key from the target NK
(stripping the `:san` / `:hi` suffix), looks up `Kalash.gatha_id → Gatha` in
Postgres, and writes the result back onto the returned document. The UI's
`buildGathaHref` then prefers this field so kalash matches deep-link to the
gatha page that contains the kalash in "विशेष देखें" rather than to a non-
existent gatha numbered after the kalash. `kalash_bhaavarth_hindi` is not yet
enriched (its NK shape `{publication}:कलश:भावार्थ:{n}` lacks the
shastra/teeka prefix needed to reconstruct the Kalash NK).

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

- deep links are built as `/shastras/<shastra>/gathas/<number-or-gatha-nk>?match=<match_nk>`
  - `buildGathaHref` prefers `target.gatha_natural_key` (set directly by the
    matcher for gatha/teeka/bhaavarth targets, and backfilled at read-time for
    kalash targets — see §8.2) so kalash matches land on the owning gatha
  - falls back to the legacy heuristic (`extractGathaNumberFromTargetNk`) only
    when `gatha_natural_key` is absent
- the reading page fetches the match doc when `searchParams.match` is present
- a highlight is applied only when:
  - `match.status === 'matched'`
  - `match.target.natural_key` equals the panel text being rendered
  - `char_start` and `char_end` are in bounds
- the panel that contains the matched target also gets a red accent ring
  (`ring-2 ring-accent`) so the matched window is visually obvious; in tabbed
  panels (kalash tabs, hindi-bhaavarth tabs) the matching tab is auto-activated
  on first render and its label stays accent-coloured when not active — wired
  via the `hasMatch` flag on `TabbedPanelItem`

The same reading page supports highlights for:

- prakrit gatha
- sanskrit gatha
- sanskrit teeka
- hindi bhaavarth
- hindi anvayartha (शब्दार्थ panel — `teeka_gatha_mapping`)
- kalash sanskrit
- kalash hindi
- kalash bhaavarth

#### Multiple simultaneous highlights

A single block can produce several matched rows on the **same gatha** (e.g. the
verse + its अन्वयार्थ). The deep-link therefore carries **repeated** `?match=`
params, one per matched target (`buildGathaHref(match, extraMatchKeys)` in
[gatha-content.ts](../../../ui/src/lib/gatha-content.ts); `useMatchEntries`
groups matched keys by `target.gatha_natural_key`). The reading page accepts
`match?: string | string[]`, fetches all match docs, and `highlightFor` is
applied per panel, so every matched panel highlights and pulses.
`HighlightScrollIntoView` takes `naturalKeys: string[]`, scrolls to the first
resolved panel, and pulses all of them.

## 10. Important Invariants

- UI and Python reference selection must stay identical.
- Matching offsets are stored against NFC-normalized original text, not raw unnormalized input.
- `extract_matches` is idempotent at the natural-key level; reruns update the same row.
- One source block may fan out to multiple target rows if Neo4j returns multiple stubs.
- `target_missing` means the graph edge exists but the routed Mongo target doc does not.
- `unmatched` means the target doc exists but the matcher could not clear the threshold.

### Upstream ingestion dependency: stub label correctness

A missing or wrongly-labeled Neo4j stub will cause the resolver to drop the
edge (no `extract_matches` row at all) — the matcher never even runs. This
recently surfaced for the routing `(GathaTeeka, prakrit_text)`: when JainKosh's
`reference_edges._emit_gatha` saw a `prakrit_text` block whose shastra was
typed as `teeka` (e.g. `नियमसार`), it emitted a `GathaTeeka` stub. Because
`prakrit_text` always carries the original Prakrit verse — same content as
`prakrit_gatha` — the correct stub is `Gatha`, matching the routing already
established for `publication` shastras in [parser.md v1.11.19](../data_sources/jainkosh/parser.md).
The fix (v1.11.22) extends that rule to `teeka` type so `prakrit_text` blocks
emit `Gatha` regardless of shastra type. See parser.md §12.2 routing table.

Symptom checklist when a topic-extract / keyword-definition block has no "View in Shastra" link in the modal:

1. Is there an `extract_matches` row for the source block at all?
   - Yes, status `matched` → UI bug. Check `DefinitionModal` ref correlation.
   - Yes, status `unmatched` → matcher couldn't clear the threshold (real text divergence or normalization gap).
   - Yes, status `target_missing` → routing OK, Mongo target absent.
   - **No row at all** → resolver yielded zero targets. Inspect the stub label and block kind against `_ROUTING` in `target_resolver.py`. If the stub label is "wrong" for the block kind, the fix is in jainkosh ingestion, not in matching.
2. If the matcher runs but scores below threshold, dump `normalized_source` and `normalized_target` from the stored doc and diff them. Common culprits are anusvara/spelled-nasal divergence (now handled), U+1CED (now handled), per-word OCR variation (handled by shingle fuzzy), and ellipsis-bridged extracts (now handled).

## 11. Known Gaps

- `Page` stub matching is not implemented.
- Matching is CLI-triggered, not async-worker driven.
- The UI fetches match docs one-by-one from the client; there is no batch endpoint yet.
- `buildGathaHref` derives the reading route from `target.gatha_natural_key` (preferred) and falls back to parsing `target.natural_key`, so any future target-key format change must update that helper too.
- `kalash_bhaavarth_hindi` targets still lack `gatha_natural_key` enrichment — fix requires storing `shastra_natural_key` / `teeka_natural_key` on the KalashBhaavarth Neo4j stub at ingestion so the Kalash NK can be reconstructed.
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

## 13. Changelog

| Date | Change |
|---|---|
| 2026-06-25 | **Width-agnostic zero-padding fallback.** `तत्त्वार्थसूत्र` अध्याय 5 सूत्र 1 (`अजीव-काया-धर्माधर्माकाश-पुद्गला:`) was `target_missing` — the resolver derived `सूत्र:1:sanskrit` and the fixed-width `_padded_variant_nk` only tried `सूत्र:001`, but NJ pads to the chapter's max width (`सूत्र:01`, 2 digits). New `_numeric_variant_regex` matches the trailing number by value (`0*{n}`) regardless of padding width when both exact + 3-pad lookups miss; the resolved doc's NK (minus `:lang`) becomes the metadata `gatha_natural_key`. Files: `workers/matching/target_resolver.py`, `tests/workers/matching/test_target_resolver.py`. |
| 2026-06-25 | **Digit stripping is now unconditional.** Rule 6 previously stripped a digit run only when *both* sides were strip-chars/edges, so a digit glued to a letter (`गाथा9`, or a number abutting a word with no separating danda) survived and could break matching. `normalize()` now strips every ASCII/Devanagari digit regardless of neighbors — verse markers like `।1।` / `\|1\|` always collapse out on both source and target. Re-run the matcher to recompute stored offsets. Files: `packages/jain_kb_common/jain_kb_common/matching/normalize.py`, `packages/jain_kb_common/jain_kb_common/matching/tests/test_normalize.py`. |
| 2026-06-24 | **Highlight-offset coordinate fix + grey/brown icon for matched siblings.** Follow-up to the same गुणपर्यायवान् references. (1) **Offsets now in raw-NFC space.** `normalize()` previously reported `n2o` against the *transformed* `original` (after anusvara `ं`→`म्`/class-nasal and र्-gemination collapse, both length-changing), but the UI highlights `normalizeNFC(text)` (plain NFC). Each transform before a match shifted the rendered highlight forward by one char — visible as the भावार्थ highlight starting mid-word. `original` is now the raw NFC text and `n2o` threads each char's raw-NFC offset through the transforms (the injected `म`+`्` share the anusvara's offset, so `n2o` is non-decreasing). Re-run the matcher to recompute stored `char_start`/`char_end`. (2) **`findMatchForRef` prefers `matched`.** A block can emit several same-gatha targets (matched टीका + unmatched भावार्थ/अन्वयार्थ sibling); the modal picked the first by gatha regardless of status, rendering a grey book for a ref that does highlight. Now prefers a `matched` candidate. Files: `packages/jain_kb_common/jain_kb_common/matching/normalize.py`, `ui/src/components/ViewInShastraButton.tsx`, plus tests in `test_normalize.py` and `ui/src/__tests__/components/ViewInShastraButton.test.ts`. |
| 2026-06-24 | **Bhaavarth (भावार्थ) for `Gatha`-primary verses + two normalization fixes.** Two adjacent गुणपर्यायवान् references on द्रव्य had no working link/highlight. (1) **`Gatha`-primary भावार्थ fan-out.** Shastra-type roots (तत्त्वार्थसूत्र) emit a `Gatha` stub (no Sanskrit टीका), so the `GathaTeeka` bhaavarth path never fired and the सर्वार्थसिद्धि भावार्थ was never matched. New `_resolve_gatha_bhaavarth_targets` emits a भावार्थ target per publication bhaavarth doc for any `Gatha` verse whose block has a `hindi_translation`, looked up by regex over `gatha_teeka_natural_key` (bhaavarth docs lack `gatha_natural_key`). (2) **Word-final anusvara → `म्`.** `समगुणपर्यायं द्रव्यं इति` (extract) vs `समगुणपर्यायं द्रव्यम्’ इति` (टीका) scored 0.69 because a word-final `ं` wasn't canonicalized; `normalize()` now maps any `ं` not followed by a consonant to `म्`. (3) **Curly quotes stripped** (U+2018/U+2019/U+201C/U+201D) — the same टीका wraps the quote in `‘…’`. After (2)+(3) the quote is an exact substring (score 1.0). Files: `workers/matching/target_resolver.py`, `packages/jain_kb_common/jain_kb_common/matching/normalize.py`, plus tests in `tests/workers/matching/test_target_resolver.py` and `packages/jain_kb_common/jain_kb_common/matching/tests/test_normalize.py`. |
| 2026-06-24 | **Bhaavarth (भावार्थ) second target.** A `sanskrit_text` block resolving to a `GathaTeeka` (Sanskrit teeka) whose `hindi_translation` is the published Hindi भावार्थ now also emits a `gatha_teeka_bhaavarth_hindi` target matched against that translation (`source_text_kind="hindi_translation"`, threshold `hindi_text`), so the भावार्थ panel highlights alongside the Sanskrit teeka. Previously only the Sanskrit teeka matched and the भावार्थ panel never highlighted (e.g. द्रव्य → प्रवचनसार/तत्त्वप्रदीपिका गाथा 96). The bhaavarth doc is looked up by its `gatha_teeka_natural_key` field (`{teeka_nk}:{gseg}`), recovered by stripping `:टीका:san` from the teeka Mongo NK, because the `GathaTeeka` stub lacks the publication-prefixed NK. No UI change needed — the reading page already keys the bhaavarth panel highlight by `bh.natural_key`, and `useMatchEntries` groups the teeka + bhaavarth matches as same-gatha siblings into one repeated-`?match=` deep-link. Files: `workers/matching/target_resolver.py`, `tests/workers/matching/test_target_resolver.py`. |
| 2026-06-24 | **Anvayartha (शब्दार्थ) second target + multi-highlight.** A `Gatha` verse target whose source block has a `hindi_translation` now also emits a `teeka_gatha_mapping` (अन्वयार्थ) target matched against that translation (`Target.source_text_kind="hindi_translation"`, threshold `hindi_text`), so the शब्दार्थ panel highlights alongside the verse. UI: `buildGathaHref` accepts sibling match keys → repeated `?match=` params; the gatha reading page accepts `match: string \| string[]`, highlights every matched panel, and `HighlightScrollIntoView` pulses all of them. Files: `workers/matching/{source_iter,target_resolver,orchestrator,apply_match}.py`, `ui/src/lib/gatha-content.ts`, `ui/src/components/{ViewInShastraButton,ShabdaArthSection,HighlightScrollIntoView}.tsx`, `ui/src/app/.../gathas/[number]/page.tsx`. |
| 2026-06-24 | **`(Gatha, sanskrit_text)` routing.** Root "shastra"-type shastras whose primary verse is Sanskrit (e.g. तत्त्वार्थसूत्र) are extracted by JainKosh as a `sanskrit_text` block, but `reference_edges._emit_gatha` emits a `Gatha` stub for *every* block kind under a `shastra`-type shastra (the sutra **is** the gatha). The matcher's `_ROUTING` lacked `(Gatha, sanskrit_text)`, so the resolver dropped the edge — no `extract_matches` row at all, hence no "View in Shastra" link on e.g. द्रव्य → तत्त्वार्थसूत्र 5/29 (`सत् द्रव्यलक्षणम्`). Added `(Gatha, sanskrit_text) → gatha_sanskrit` and the matching `_derive_mongo_nk` branch (`{stub_nk}:sanskrit`). Files: `workers/matching/target_resolver.py`, `tests/workers/matching/test_target_resolver.py`. |
| 2026-06-16 | **Compound-identifier support in `target_resolver`.** Two fixes for compound shastras (परमात्मप्रकाश etc.): (a) `GathaTeeka` / `GathaTeekaBhaavarth` Mongo NK now uses the full compound suffix (`अधिकार:1:गाथा:001`) via the new `_mongo_seg_from_gatha_nk` helper, mirroring `envelope._gatha_mongo_segment` — previously `gatha_nk.split(":")[-1]` dropped the prefix and silently produced `target_missing` for every compound teeka/bhaavarth. (b) `_padded_variant_nk` zero-padding fallback retries the Mongo lookup with the alternate padding of the last numeric segment so JainKosh's raw citation NKs (`…:गाथा:12`) hit NJ's zero-padded docs (`…:गाथा:012`). Mirrors the `_find_compound_gatha_fuzzy` server-side fallback. Files: `workers/matching/target_resolver.py`, `tests/workers/matching/test_target_resolver.py`. |
| 2026-06-16 | **Chandrabindu (U+0901) stripped.** Apabhramsha-era OCR (परमात्मप्रकाश) emits chandrabindu inconsistently — e.g. target `सण्णाणेँ` vs JainKosh extract `सण्णाणे`. `_is_strip_char` rule 8b now strips chandrabindu the same way visarga / avagraha are stripped, so the two forms collapse identically. Files: `normalize.py`, `tests/test_normalize.py`. |
| 2026-06-15 | **`र्`-gemination collapse.** `normalize()` collapses the old Sanskrit orthographic doubling of a consonant after `र्` (पर्य्याय → पर्याय, धर्म्म → धर्म, कर्म्म → कर्म). Scoped to "after `र्`" so unrelated same-consonant conjuncts (क्क in मक्का, real म्य in अभ्युपगम्य) are untouched. Files: `normalize.py`, `tests/test_normalize.py`. |
| 2026-06-15 | **Ellipsis-bridged matching.** `locate()` now recognizes a literal run of 3+ dots in the source as a wildcard gap. Source is split into segments; each is located in target sequentially with per-segment exact-then-fuzzy search; the returned span covers first-segment start → last-segment end so the UI highlights the bridged region. New `MatchResult.method = "exact_normalized_ellipsis"`. Files: `locate.py`, `types.py`, `tests/test_locate.py`. |
| 2026-06-15 | **Vedic Sign Tiryak (U+1CED) → halant substitution.** `normalize()` rewrites `᳭` to `्` before any other pass, fixing OCR'd targets like `तिर्यङ᳭मनुष्य` that should equal `तिर्यङ्मनुष्य`. |
| 2026-06-15 | **Sandhi anusvara canonicalization.** `normalize()` rewrites each anusvara `ं` followed by a consonant to the sandhi-class nasal + halant + consonant (e.g. `ं`+ब → `म्`+ब). Makes the anusvara form and the spelled-out form (`संबंध` vs `संबन्ध`) match exactly, without over-collapsing real conjuncts like `म्य` in `अभ्युपगम्य`. ZWJ/ZWNJ between anusvara and consonant is tolerated. Replaced an earlier strip-based approach that was rejected for over-collapsing real conjuncts. |
| 2026-06-15 | **Stub-label correctness for `prakrit_text` blocks in `teeka`-type shastras** (upstream in jainkosh ingestion, [parser.md v1.11.22](../data_sources/jainkosh/parser.md)). `_emit_gatha` now emits a `Gatha` stub (not `GathaTeeka`) for `prakrit_text` blocks regardless of shastra type, matching the `publication` rule from v1.11.19. Unblocks deep-links for topic/keyword extracts whose Prakrit-verse blocks reference `teeka`-typed shastras (e.g. `नियमसार/28`). |
