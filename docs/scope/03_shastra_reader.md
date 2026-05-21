# 03 — Shastra Reader (ShastraExplorer)

The reading core. Mirrors how a serious Jain student already studies a shastra (kalash → gatha → bhaavarth → notes), but layers the graph + AI on top.

## Per-shastra organised layout

Different shastra families have different native structures. The reader respects each:

| Shastra family | Native structure |
|---|---|
| Samaysaar / Pravachansaar / Niyamsaar | adhikaar → kalash (sometimes) → gatha → harigeet → bhaavarth (teeka) |
| Karm-grantha / Gommatsaar | chapter → shloka → vivran |
| Tatvarth-sutra | adhyaay → sutra → bhashya |
| Puraan (Padma, Harivansha, etc.) | parva → sarga → shloka |
| Mantra-shastra (Sahasranaam etc.) | shloka with mantra-meta |
| Siri Bhoovalay | chakra → ank/grid (special viewer, see [07](./07_siri_bhoovalay_and_research_models.md)) |

Each shastra ships with a small layout config (YAML/JSON) declaring its structure and how to render it. New shastras only need a new config — code stays the same. Spec: `design/scope/02_shastra_layout_configs_spec.md`.

Reference shastra used as the canonical example: `nikkyjain.github.io/jainDataBase/shastra/01_द्रव्यानुयोग/01_समयसार--कुन्दकुन्दाचार्य/html/001.html`.

## Keyword expansion (hover / click)

Any word in the rendered Hindi/Prakrit text that the indexer matched to a `Keyword` or `Topic` is wrapped in an inline tag. Behaviour:

- **Hover** → small popover with short definition (first 2–3 lines of `keyword_definitions` Mongo doc) + counter chip ("उल्लेख: 47 बार समयसार में, 312 बार कुल").
- **Click** → side-panel expansion: full JainKosh definition, related topics, "open in Graph", "open in dictionary".

Color coding (also drives the JainKosh-highlight overlay):

- Indigo: keyword (definition exists).
- Purple: topic.
- Amber: keyword with alias only (no definition yet).
- Slate (dotted underline): candidate from AI pipeline, unreviewed.

## Topic-relations expansion (optional, per gatha)

A collapsible "इस गाथा से संबंधित विषय" block under each gatha. Pulls from graph: `Gatha -[:MENTIONS_TOPIC]- Topic`, then `Topic -[:IS_A|PART_OF|RELATED_TO]-` neighbours. Default collapsed; opens a mini-graph view embedded.

## Drush-taant (illustration) generation

A drush-taant in Jain teekas is a worldly analogy. For every gatha that has a bhaavarth, we can generate an illustrative image:

- Prompt is constructed from gatha translation + bhaavarth (LLM rewrites into image-prompt).
- Image generated via DALL-E 3 / Imagen 3 / Stable Diffusion XL (configurable).
- Stored under `drushtaant_images` Mongo collection + S3 blob.
- Always admin-reviewed (low-risk filter for any depiction that violates aniconic norms).
- Cached forever once approved.

Spec: `design/scope/05_drushtaant_image_gen_spec.md`.

## Audio reader

ElevenLabs (or Murf/PlayHT as alt) per-chapter narration in Hindi (later EN, Sa, Pr). Pre-generated at admin approval, streamed via signed URL. Highest value for Puraan and long bhaavarth-heavy shastras. Spec: `design/scope/06_audio_reader_elevenlabs_spec.md`.

## PDF export

Server-side render (Puppeteer + print stylesheet) of:

- Single gatha (with all panels).
- Adhikaar.
- Whole shastra.
- A user's saved selection (auth required).

Includes citations, footnotes for AI-generated material, and a TOC. Spec: `design/scope/07_pdf_export_spec.md`.

## JainKosh-highlight overlay

When a user toggles "JainKosh mode", every span we identified during the enrichment pipeline (topic + keyword indexes per gatha) gets a colour-coded highlight with a hyperlink. This is the visible payoff of the enrichment pipeline. Spec: `design/scope/12_jainkosh_highlight_overlay_spec.md`.

## Extended-definitions / extracts highlights

For words that have a long-form extract in the keyword's JainKosh page, the popover also shows a "+" to expand into a side-panel showing the relevant subsection (using `topics.extract_doc_ids`). This is the same data the existing `/dictionary/[nk]` page exposes, but rendered alongside the gatha.

## Page anatomy

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [breadcrumb]  समयसार › अधिकार 1: जीव-अजीव अधिकार › गाथा 1                     │
│  [adhikaar selector ▾]   [gatha pager ◄ ►]   [lang: हि | En | +Kn]            │
├──────────────────────────────────────────────────────────────────────────────┤
│  [Prakrit panel — large, original]                                           │
│  [Sanskrit chhaaya panel]                                                    │
│  [Hindi harigeet panel]                                                      │
│  [Anvayartha — word-by-word, hover-able]                                     │
│  [Bhaavarth teeka — with JainKosh highlights on]                             │
│  [Drush-taant image panel — generated, expandable]                           │
│  [Related topics — collapsed by default]                                     │
│  [Audio strip — play/pause, chapter, speed]                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│  Right rail: keyword popover stack | mini graph | export menu | save mark    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Definition of done

- [ ] Layout config schema validated; samaysaar, pravachansaar, niyamsaar, gommatsaar, tatvarth-sutra, one puraan all configured.
- [ ] Hover/click expansion works against existing keyword + topic indexes; popover under 200 ms p95.
- [ ] Drush-taant pipeline (admin trigger → image → review → publish) E2E.
- [ ] Audio reader plays Hindi narration of at least one full adhikaar.
- [ ] PDF export round-trips one whole shastra cleanly.
- [ ] JainKosh-highlight overlay toggle works without page reload.
