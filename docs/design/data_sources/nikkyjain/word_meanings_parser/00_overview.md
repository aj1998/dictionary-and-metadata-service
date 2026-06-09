# Feature: Bhaavarth `shortFont` Word-Meanings (Footnote Glossary)

## Motivation

Several NJ HTML pages annotate the **primary teeka bhaavarth** with inline superscript markers (e.g. `<sup>१</sup>मोक्ष-मार्ग-प्रपंच-सूचक`) and a trailing `<span class=shortFont>` block at the bottom that defines each marked word:

```
<sup>१</sup>उत्तर कर्मसंतति= बाद का कर्म प्रवाह, भावी कर्म-परम्परा ।
<sup>२</sup>पूर्व = पहले की ।
<sup>३</sup>केवली-भगवान को वेदनीय, नाम और गोत्र कर्म की स्थिति कभी स्वभाव से ही …
<sup>४</sup>मोक्ष-मार्ग-प्रपंच-सूचक = मोक्ष का विस्तार बतलाने वाली …
```

Reference HTML: `nikkyjain.github.io/jainDataBase/shastra/01_द्रव्यानुयोग/05_पञ्चास्तिकाय--कुन्दकुन्दाचार्य/html/161.html`

Today the parser leaves these superscript digits embedded as plain numbers inside the bhaavarth Markdown and discards the trailing `shortFont` block, so the reader sees text like `अब ४मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।` with no way to access the definition.

## Outcome

1. **Parser** strips inline `<sup>N</sup>` markers from the bhaavarth text, records the *char offset* of the anchor word, and extracts the `shortFont` glossary entries.
2. **Ingestion** writes a new Mongo collection `gatha_teeka_bhaavarth_shortfont` (and the kalash counterpart, if applicable) keyed off the parent bhaavarth NK.
3. **API** exposes the entries on the existing bhaavarth payload that the reader already fetches — no new endpoint.
4. **UI** underlines the anchor word in the rendered bhaavarth with a dark-yellow line; clicking it opens a small popover showing the meaning.

## Phase plan

| Phase | Doc | Scope | Touches |
|---|---|---|---|
| 1 | [`01_parser_phase.md`](01_parser_phase.md) | Extract markers + glossary, strip from text, emit `ShortFontEntry` model | `workers/ingestion/nj/` |
| 2 | [`02_data_model_phase.md`](02_data_model_phase.md) | Mongo collection, envelope, apply, indexes | `packages/jain_kb_common/db/mongo/`, `workers/ingestion/nj/envelope.py`, `apply.py`, [`data_model_mongo.md`](../../../data_model/data_model_mongo.md) |
| 3 | [`03_ui_phase.md`](03_ui_phase.md) | API hydration + `BhaavarthPanel` underline + popover | `services/core_service/`, `ui/src/components/BhaavarthPanel.tsx`, `ui/src/lib/api/`, `ui/src/lib/types.ts` |

Each phase is independently testable and ships its own goldens / unit tests. No phase should require sub-agent delegation when implemented in order.

## Cross-references

- Parser wiki: [`../nj_parser.md`](../nj_parser.md)
- Ingestion wiki: [`../nj_ingestion.md`](../nj_ingestion.md)
- Mongo data model: [`../../../data_model/data_model_mongo.md`](../../../data_model/data_model_mongo.md)
- UI dev wiki: [`../../../../../ui/README.md`](../../../../../ui/README.md)

## Resolved design decisions

1. **Scope (confirmed)**: parse `shortFont` from **all** bhaavarth-like blocks —
   - Primary teeka gatha bhaavarth (`gatha_teeka_bhaavarth_hindi`)
   - Secondary teeka gatha bhaavarth (`gatha_teeka_bhaavarth_hindi`, secondary NK)
   - Kalash hindi / kalash bhaavarth (`kalash_hindi`, `kalash_bhaavarth_hindi` if/when present)
2. **Bare narrative footnote** (no `=` separator): underline the body token the `<sup>` was attached to; popover shows the full narrative.
3. **Offsets**: indexed against the cleaned, NFC-normalised Markdown stored in the parent bhaavarth doc (`gatha_teeka_bhaavarth_md` / `kalash_*_md`). Same precedent as anyavartha offsets in `teeka_gatha_mapping`.
4. **UI**: dark-yellow underline + click-to-open `Popover`.
5. **Numbering**: `marker_number` stored as ASCII int; `marker_devanagari` kept for display.
6. **`(N)` markers inside `<span class=notes>`** (e.g. `<span class=notes>(मोक्ष)</span>`) are inline parentheticals, not glossary footnotes — left untouched.
