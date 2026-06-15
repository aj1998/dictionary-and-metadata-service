# Compound Identifiers — Wiki & Implementation Reference

> **Status**: ✅ Implemented & live for **परमात्मप्रकाश** (phases 1–5 + bugfix pass).
> **Audience**: anyone touching the parser / envelope / API / UI gatha paths.
> **Scope**: A consolidated wiki for the compound-identifier feature — covers
> the design rationale, the per-phase spec links, the end-to-end data flow, and
> every bug we hit (with fix locations) while bringing परमात्मप्रकाश fully
> end-to-end through ingestion → reader.

---

## 1. Why compound identifiers exist

Most shastras identify a gatha by a single integer (`समयसार:गाथा:8`). A handful —
starting with **परमात्मप्रकाश** — partition gathas across multiple top-level
sections (e.g. `अधिकार`) so that *adhikaar-1 गाथा 1* and *adhikaar-2 गाथा 1* are
distinct nodes. Without compound IDs they collide, and every downstream artifact
(Postgres row, Neo4j node, Mongo doc, jainkosh citation, API path, UI URL,
breadcrumb) silently merges or breaks.

The feature threads a single, declarative source-of-truth — `gatha_identifier`
in `parser_configs/_manual_configs/shastra.json` — through every layer:

```
shastra.json  →  jain_kb_common.shastra_identifiers
                ↓
       NJ parser (parse_myitem, parse_page, extract → identifier_values)
                ↓
       NJ envelope (compound NK suffix everywhere)
                ↓
       Ingestion apply (Postgres adhikaar JSONB, Neo4j NKs, Mongo NKs)
                ↓
       Jainkosh reference parser (resolved_fields → compound NK)
                ↓
       Core service API (/v1/shastras/{nk}/gathas/{raw}, /adjacent)
                ↓
       UI (compact URL, breadcrumb, tiles, search-jump, modal)
```

If the shastra has no `gatha_identifier`, every layer falls back to legacy
behaviour — no regressions for the existing corpus.

---

## 2. Phase index (specs, in order)

| Phase | Spec | What it adds |
|---|---|---|
| 1 | [`01_shastra_json_and_config_loader.md`](./01_shastra_json_and_config_loader.md) | `gatha_identifier` / `kalash_identifier` in `shastra.json`; reader utilities in `jain_kb_common.shastra_identifiers` (`get_identifier_fields`, `build_compound_suffix`, `extract_identifier_values_from_suffix`, `canonical_segment_name`). |
| 2 | [`02_nj_parser_compound_id_support.md`](./02_nj_parser_compound_id_support.md) | NJ `parse_myitem.py` handles no-`<optgroup>` form, expands multi-gatha ranges, and emits `identifier_values` per `GathaExtract` / `KalashExtract`. |
| 3 | [`03_envelope_and_apply_compound_nk.md`](./03_envelope_and_apply_compound_nk.md) | Envelope emits compound NK suffix for Gatha / Kalash / GathaTeeka / GathaTeekaBhaavarth / KalashBhaavarth. Postgres `gathas.adhikaar` JSONB stores `identifier_values`. Mongo docs use the same compound suffix in `gatha_teeka_natural_key`. |
| 4 | [`04_jainkosh_reference_compound_nk.md`](./04_jainkosh_reference_compound_nk.md) | Jainkosh reference parser reads `gatha_identifier` at resolve time and assembles the compound NK so jainkosh citations land on the same node as NJ-emitted ones. |
| 5 | [`05_api_and_ui_compound_routes.md`](./05_api_and_ui_compound_routes.md) | Core service `/v1/shastras/{nk}/gathas/{raw_id}` + `/adjacent` endpoints. UI reading route, breadcrumb per-field chips, search-jump dropdown, compound-aware modal links. |

---

## 3. Canonical forms

### 3.1 Identifier declaration (`shastra.json`)
```json
{
  "shastra_name": "परमात्मप्रकाश",
  "gatha_identifier": "अधिकार,परमात्मप्रकाशगाथा",
  "kalash_identifier": null
}
```
The field name `परमात्मप्रकाशगाथा` is the jainkosh-grammar form. At NK-emit time
the shastra-name prefix is stripped → canonical segment `गाथा`.

### 3.2 Natural keys

| Node | Legacy NK | Compound NK |
|---|---|---|
| `Gatha` (Postgres + Neo4j) | `समयसार:गाथा:8` | `परमात्मप्रकाश:अधिकार:1:गाथा:001` |
| `gatha_teeka_natural_key` (Mongo) | `समयसार:टीका:8` | `परमात्मप्रकाश:टीका:अधिकार:1:गाथा:001` |
| Bhaavarth shortfont NK | `…:गाथा:टीका:भावार्थ:8` | `…:अधिकार:1:गाथा:टीका:भावार्थ:001` |

Postgres detail: `gathas.gatha_number` stores the full compound suffix
(`"अधिकार:1:गाथा:001"`) while `gathas.adhikaar` (JSONB) holds the
`identifier_values` dict.

### 3.3 URL / API compact form

The compact form is the values, in declaration order, joined by `,`:
`/shastras/परमात्मप्रकाश/gathas/1,001`. Legacy shastras use the bare number:
`/shastras/समयसार/gathas/8`.

### 3.4 Mongo per-gatha segment (`mongo_seg`)

Computed by `_gatha_mongo_segment` (`workers/ingestion/nj/envelope.py:304`):
- Compound: full compound suffix (`अधिकार:1:गाथा:001`).
- Legacy: zero-stripped bare number (`8`).

All teeka / bhaavarth Mongo NKs are `{publication_nk}:{mongo_seg}`. The core
service teeka query (see §5 bugfix #6) anchors on this exact suffix.

---

## 4. End-to-end data flow (परमात्मप्रकाश example)

1. **Source HTML** (NJ): `10_परमात्मप्रकाश--योगींदुदेव/html/0001_अधिकार-1_गाथा-1.html`.
2. **`parse_myitem.py`** reads `myItem.js`, recovers `(adhikaar, gatha)` pairs,
   expands multi-gatha ranges, attaches `identifier_values = {"अधिकार": "1", "परमात्मप्रकाशगाथा": "001"}` to each extract.
3. **`parse_page.py`** parses the HTML, gating teeka content on
   `_is_primary_page` (substring match of `selectors.primary_teeka_label`
   inside the `<font color=darkgreen>` label in `div#teeka0`). On mismatch it
   now emits a `WARNING` (see §5 bugfix #1).
4. **`envelope.py`** builds the compound suffix via
   `build_compound_suffix(shastra_nk, identifier_values, kind="gatha")` and uses
   it for every Postgres / Neo4j / Mongo NK. `mongo_seg` is the same suffix.
5. **`apply.py`** writes Postgres rows (compound `natural_key`, `gatha_number`,
   JSONB `adhikaar`), Neo4j nodes/edges, and Mongo docs.
6. **Jainkosh reference parser** sees a citation, looks up the shastra's
   `gatha_identifier`, assembles the same compound NK, and the citation matches
   the ingested node.
7. **Core service** routes `/v1/shastras/परमात्मप्रकाश/gathas/1,001` →
   `gatha_nk_for_request` → `परमात्मप्रकाश:अधिकार:1:गाथा:001`. The
   `/adjacent` endpoint sorts gathas numerically across the compound key.
8. **UI** renders compact URLs (`1,001`), Devanagari per-field breadcrumb chips
   (`अधिकार १ › गाथा १`), a पर्-field-aware search-jump dropdown, and
   compound-aware modal book links.

---

## 5. Bugfix log

All fixes layered on top of the original phase 1–5 implementation. Listed in
chronological order with file/line pointers.

### #1 — Parser silently skipped all teeka for परमात्मप्रकाश
- **Symptom**: zero teeka_sanskrit / teeka_bhaavarth docs in Mongo despite a
  clean ingestion run; UI showed "टीका उपलब्ध नहीं है".
- **Root cause**: `selectors.primary_teeka_label: "ब्रह्मदेव सूरि"` did not
  substring-match the HTML's darkgreen label `"श्रीब्रह्मदेव :"`, so
  `_is_primary_page` returned `False` for *every* page.
- **Fix**:
  - `parser_configs/nj/parmatmaprakash.yaml:42` — `primary_teeka_label` shortened to `"ब्रह्मदेव"`.
  - `workers/ingestion/nj/parse_page.py:_is_primary_page` — added a `logger.warning("nj.primary_teeka_label.mismatch …")` so future label drift surfaces immediately instead of silently skipping content.

### #2 — Pydantic ValidationError on `adhikaar` payload
- **Symptom**: NJ ingestion failed with
  `adhikaar.0.lang/script/text` validation errors; 0 gathas reached PG.
- **Root cause**: `gathas.adhikaar` JSONB stores the `identifier_values` dict
  (per phase-3 spec diversion); the API schema's `_coerce` previously assumed
  a list of `LangText` and tried to coerce the dict.
- **Fix**: `services/core_service/domains/data/schemas/gathas.py` — tightened
  `_coerce` to only accept dicts whose keys are exactly `{lang, script, text}`;
  everything else is dropped.

### #3 — Breadcrumb showed "गाथा NaN"
- **Symptom**: Reading page breadcrumb for compound gathas displayed `गाथा NaN`.
- **Root cause**: Legacy code called `parseInt(gatha.gatha_number)`, but for
  compound shastras `gatha_number` is the compound suffix string.
- **Fix**: `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`
  detects a full NK in the `[number]` segment, normalises it to the compact
  form, and routes through the compound `getGathaByPath` API + the
  `identifier.fields` block (rendered as per-field chips).

### #4 — Empty `chhand` panel rendered
- **Fix**: `ui/src/components/GathaVerseGroup.tsx` skips rendering the chhand
  panel when its text is empty.

### #5 — Shastra-page tile titles ("गाथा अधिकार:1:गाथा:001")
- **Symptom**: Tile cards displayed the raw compound suffix.
- **Fix**: `ui/src/lib/format/gatha-id.ts:gathaTileLabel` produces
  `"अधिकार १, गाथा १"` (Devanagari numerals, no leading "गाथा" word that would
  make `1,001` read as "one thousand and one"). Used by
  `ui/src/app/[locale]/(content)/shastras/[nk]/page.tsx`.

### #6 — "गाथा पर जाएँ" only accepted zero-padded values + had no adhikaar input
- **Symptom**: Typing `1,9` returned 404, but `1,009` worked.
- **Fix**:
  - `services/core_service/domains/data/routers/gathas.py:_find_compound_gatha_fuzzy`
    — server-side fallback that re-resolves by numeric equality of identifier
    values, so user input doesn't need to match storage zero-padding.
  - `ui/src/components/GathaSearchJump.tsx` — adhikaar rendered as a
    `<select>` dropdown pre-filled from the shastra's distinct adhikaar
    values, plus a separate gatha-number input.

### #7 — Modal book link missing for compound refs
- **Symptom**: Definition modal showed references like
  `परमात्मप्रकाश | अधिकार: 1 | परमात्मप्रकाशगाथा: 12 · पृष्ठ: 19` with no
  brown/grey book icon next to the gatha chip.
- **Root cause**: `isGathaField` exact-matched
  `f.field === 'गाथा'`, but compound fields come through as
  `परमात्मप्रकाशगाथा` (or e.g. `कषायपाहुड़-गाथा`).
- **Fix**:
  - `ui/src/lib/gatha-content.ts` — new `isGathaEntityField(field)` (suffix
    match) and `displayFieldLabel(field)` (strips the shastra-name prefix and
    any leading hyphen so the chip reads just `गाथा:`).
  - `ui/src/components/DefinitionModal.tsx` — all four ref-rendering sites
    use the new helpers for both the `isGathaField` decision and the displayed
    field label.
  - `ui/src/components/ViewInShastraButton.tsx:planRefLink` — already routes
    compound refs through `compactFromResolvedFields` to build
    `/shastras/{nk}/gathas/{val1,val2}`.

### #8 — Definition modal panels collapsed multiple adhikaars' "gatha 1" together
- **Symptom**: Three identical `परमात्मप्रकाश:टीका` tabs in the टीका panel,
  with content from gathas 1, 2 and 3 of adhikaar 1 piled together.
- **Root cause**: `get_detail` in the core service queried Mongo with
  `gatha_number="1"` and a regex `^परमात्मप्रकाश:अधिकार:1:` — but teeka NKs use
  the publication NK (`परमात्मप्रकाश:टीका:0`) which never has the adhikaar
  segment in front; the regex matched anything that *happened* to share the
  bare gatha_number across publications/adhikaars.
- **Fix**: `services/core_service/domains/data/services/gathas.py:get_detail`
  now derives the per-gatha `mongo_seg` (compound suffix or legacy bare number)
  and queries `gatha_teeka_natural_key` with a regex anchored at *that*
  suffix (`^{shastra_nk}:.*:{mongo_seg}$`). One gatha = exactly one set of
  matched teeka docs, no cross-adhikaar bleed.

### #9 — `/adjacent` 500: `TypeError: '<' not supported between instances of 'str' and 'int'`
- **Symptom**: Loading any compound gatha threw an ASGI exception from
  `get_adjacent_gathas`.
- **Root cause**: `_sort_key` mixed `int` and `str` tuple elements whenever a
  gatha's identifier value wasn't fully numeric (or a field was missing).
- **Fix**: `services/core_service/domains/data/services/gathas.py:_sort_key`
  returns uniformly numeric tuples, coercing any non-numeric / missing value to
  `float("inf")` so it sorts last without crashing.

---

## 6. Files touched (cheat-sheet)

### Backend
- `parser_configs/_manual_configs/shastra.json` — `gatha_identifier` entry for परमात्मप्रकाश.
- `parser_configs/nj/parmatmaprakash.yaml` — shastra config, including the corrected `primary_teeka_label`.
- `libs/jain_kb_common/jain_kb_common/shastra_identifiers.py` — identifier reader + suffix builder/extractor.
- `workers/ingestion/nj/parse_myitem.py` — no-`<optgroup>` form, multi-gatha expansion, identifier_values emission.
- `workers/ingestion/nj/parse_page.py` — primary-teeka label-drift warning.
- `workers/ingestion/nj/envelope.py` — compound NK + `mongo_seg` for every Mongo / Neo4j fragment.
- `workers/ingestion/nj/apply.py` — Postgres `adhikaar` JSONB write path.
- `workers/ingestion/jainkosh/…` — reference parser compound NK assembly (phase 4).
- `services/core_service/domains/data/routers/gathas.py` — `/v1/shastras/{nk}/gathas/{raw_id}` + `/adjacent`, fuzzy compound fallback.
- `services/core_service/domains/data/services/gathas.py` — compound-aware sort key, per-gatha teeka query.
- `services/core_service/domains/data/schemas/gathas.py` — `_coerce` hardened.

### UI
- `ui/src/lib/format/gatha-id.ts` — `parseGathaSuffix`, `gathaCompactFromNk`, `buildGathaPathHref`, `isFullGathaNk`, `compactFromResolvedFields`, `gathaTileLabel`, `uniqueLeadingIdValues`.
- `ui/src/lib/gatha-content.ts` — `isGathaEntityField`, `displayFieldLabel`, `getRefGathaEntity`.
- `ui/src/app/[locale]/(content)/shastras/[nk]/page.tsx` — compound tile labels, adhikaar-values for search-jump.
- `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx` — URL normalisation, compound detail fetch, per-field breadcrumb.
- `ui/src/components/GathaSearchJump.tsx` — adhikaar dropdown + gatha number input.
- `ui/src/components/GathaVerseGroup.tsx` — skip empty chhand.
- `ui/src/components/ViewInShastraButton.tsx` — compound fallback link plan.
- `ui/src/components/DefinitionModal.tsx` — uses the new gatha-field helpers everywhere.

---

## 7. Operational notes

- **Re-ingestion** for a shastra after YAML edits (e.g. fixing
  `primary_teeka_label`):
  ```
  python -m workers.ingestion.nj.cli --config parser_configs/nj/parmatmaprakash.yaml --apply
  ```
- **Verifying compound flow** for a fresh shastra:
  1. `shastra.json` has the right `gatha_identifier`.
  2. `get_identifier_fields(shastra_nk, "gatha")` returns the field list.
  3. After ingestion, spot-check a Postgres row — `natural_key` must contain the compound suffix, `adhikaar` must be the identifier_values dict, `gatha_number` is the compound suffix.
  4. UI: `/shastras/{nk}/gathas/1,1` resolves (fuzzy fallback handles zero-padding); breadcrumb shows per-field chips.
- **Logs to watch**: `nj.primary_teeka_label.mismatch` — config drift on any
  newly-added shastra.

---

## 8. Future-shastra checklist

Adding a new compound shastra is a config exercise — no code changes needed
unless a new identifier shape (>2 fields, or `kalash_identifier`) is introduced.

1. Add `gatha_identifier` (and `kalash_identifier` if relevant) to `shastra.json`.
2. Add the NJ YAML config; set `primary_teeka_label` to a unique substring of
   the actual darkgreen label.
3. Run a dry parse against a single page and confirm `identifier_values`
   appears on each extract.
4. Apply ingestion; verify Postgres + Mongo NKs use the compound suffix.
5. Smoke the UI compact URL and the search-jump dropdown.
