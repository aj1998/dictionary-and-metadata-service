# 05 — Multilingual Strategy

What "Translations/Multilingual" actually means in SAAR. There are three tiers — each handled differently — because *full* translation of all shastras into all languages is infeasible.

## Tier 1 — Hindi + English (default, everywhere)

Both languages are always available on every page where data exists. Hindi is canonical; English is added via:

- Pre-existing translations in the source corpus (some shastras have English bhaavarths already).
- The 3-step enrichment pipeline (see [04_translation_enrichment_pipeline.md](./04_translation_enrichment_pipeline.md)) using Vitrag-elibrary as a constrained dictionary.
- AI translation of section headings, topic display text, keyword names.

Implementation: every `JSONB` multilingual field already supports `[{lang, script, text}]`; English is added as additional array entries. No schema change needed.

## Tier 2 — Per-keyword / per-topic overlay (Kn / Gu / Sa / Pr / Ta)

Full body translation is **out of scope**. We translate only the *labels* (keyword display text + topic display text + section headings). User picks one extra language at a time; UI shows the chosen language as an additional row under the Hindi label in lists, popovers, and graph nodes.

Sources:

- **Kannada / Gujarati:** Hindi → target translations from OCRed Jain dictionaries (e.g. Praakrit-Gujarati Kosh, Kannada Jain Shabdkosh). Spec: `design/scope/16_kn_gu_ocr_pipeline_spec.md`.
- **Sanskrit / Prakrit:** Finetuned models for keyword/phrase mapping. Many keywords already have a Sanskrit form (chhaaya). Prakrit is harder and is a research workstream. Spec: `design/scope/26_sanskrit_prakrit_model_spec.md`.
- **Tamil:** Research only.

Storage: new tables `keyword_translations` and `topic_translations` keyed on `(entity_id, lang, script)` with `text`, `source` (ocr|ai|manual), `confidence`, `reviewed_by`, `reviewed_at`.

Spec: `design/scope/15_multilingual_keyword_storage_spec.md`.

## Tier 3 — Siri Bhoovalay / Ancient cryptography (R&D)

Sanskrit + Prakrit + Kannada all relate to the Siri Bhoovalay text, which encodes 718 languages in a cryptographic grid. Separate research workspace; uses the language models from Tier 2. See [07_siri_bhoovalay_and_research_models.md](./07_siri_bhoovalay_and_research_models.md).

## Language selection UX

- **Persistent default:** taken from user preference if logged in (see [08_user_accounts.md](./08_user_accounts.md)), else cookie, else browser `Accept-Language` (Hindi if neither).
- **Per-page toggle:** top-right; choices: हि (always on), En (always on), one of [Kn/Gu/Sa/Pr] (optional overlay; null = off).
- **Hover-only Sanskrit chhaaya:** for shastras that have one, the Sanskrit chhaaya panel is shown next to Prakrit always.

## Pipeline reuse

The 3-step enrichment pipeline is *language-agnostic* by design. To add a new language overlay:

1. Ingest a source dictionary (OCR + cleanup) into `keyword_translations` as `source='ocr'`.
2. Run the same pipeline with `target_lang = <new>` to fill gaps from AI (`source='ai'`, low-confidence by default).
3. Admin reviews via the existing review queue, approves to `source='manual'`.

## What we do *not* do

- Full body translation of shastras into Kn/Gu/Sa/Pr/Ta.
- Auto-publishing AI translations without admin review.
- Hindi-only fallback that hides Hindi when EN exists (Hindi is canonical, always shown).

## Definition of done

- [ ] `keyword_translations` and `topic_translations` tables exist, with multi-source provenance.
- [ ] Vitrag-elibrary ingested → Hin↔En entries populated on ≥ 1K core keywords.
- [ ] Kannada or Gujarati OCR pipeline ingested ≥ 500 entries from one source dictionary.
- [ ] UI language overlay toggle works on Graph, ShastraExplorer, and Dictionary pages.
- [ ] Admin review queue handles language-tagged entries.
