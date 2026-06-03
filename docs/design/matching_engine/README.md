# Matching Engine — Spec Index

The Matching Engine locates the **exact character offset** of each
JainKosh-sourced extract block inside its corresponding NikkYJain (NJ)
shastra Mongo document, so the UI can deep-link from a definition / topic
block to the precise position inside the gatha page where that text
appears (highlighted).

## Why we need it

- JainKosh ingestion ([`data_sources/jainkosh/parser.md`](../data_sources/jainkosh/parser.md))
  already emits Neo4j edges from every block to a **stub** node
  (`Gatha` / `GathaTeeka` / `GathaTeekaBhaavarth` / `Kalash` /
  `KalashBhaavarth` / `Page`) using the GRef reference parser.
- NJ ingestion ([`../wiki/nj_ingestion.md`](../wiki/nj_ingestion.md))
  later fills those stub nodes with real Mongo bodies
  (`gatha_prakrit`, `gatha_sanskrit`, `gatha_teeka_sanskrit`,
  `gatha_teeka_bhaavarth_hindi`, `kalash_sanskrit`, `kalash_hindi`,
  `kalash_bhaavarth_hindi`).
- The matcher closes the loop: for every (block, stub-target) edge,
  it locates the substring of the block inside the now-populated NJ
  doc and stores `(target_doc_natural_key, char_start, char_end)`.

The UI then renders a **"View in Shastra"** link per block; clicking
opens a new tab to the gatha reading page with the matched range
highlighted (Sanskrit teeka, Hindi bhaavarth, Prakrit/Sanskrit gatha,
kalash variants).

## Inputs

| Side | Source | Block kinds matched |
|---|---|---|
| JainKosh | `topic_extracts.blocks`, `keyword_definitions.page_sections[].definitions[].blocks` | `prakrit_gatha`, `prakrit_text`, `sanskrit_gatha`, `sanskrit_text`, `hindi_text`, `hindi_gatha`. `see_also` and `table` are skipped. Only blocks whose **primary shown reference** (per [`pickRefsToShow`](../../ui/src/components/DefinitionModal.tsx) logic) resolves to a stub target are considered. |
| NJ | Mongo collections | `gatha_prakrit`, `gatha_sanskrit`, `gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`, `kalash_sanskrit`, `kalash_hindi`, `kalash_bhaavarth_hindi`. |

## Match algorithm (summary)

1. **Resolve target**: walk Neo4j edges from the block to its stub
   node (using only the references chosen by the same `pickRefsToShow`
   rule applied in [`DefinitionModal`](../../ui/src/components/DefinitionModal.tsx)
   — extract this rule into a shared helper). Map stub → NJ Mongo
   doc(s) by `natural_key`.
2. **Normalize both sides**: NFC; strip ZWJ/ZWNJ; strip ASCII + Devanagari
   whitespace, danda (`।`), double-danda (`॥`), pipe, hyphen, en-/em-dash,
   numbers in parentheses, ASCII punctuation, common verse-end markers.
3. **Locate**: search the normalized source block as a substring of the
   normalized target text; if no exact substring, fall back to
   word-shingle Jaccard over n-grams (default `n=3`).
4. **Score**: single global threshold (default Jaccard ≥ `0.80`), with
   per-`BlockKind` overrides (e.g. `prakrit_gatha = 0.90`).
5. **Map back to original offsets**: keep an index from normalized
   character positions to original NFC positions while normalizing the
   target, so we can produce `char_start / char_end` against the
   un-stripped Mongo text the UI actually renders.

## Phase plan

| # | Doc | Scope |
|---|---|---|
| 1 | [`phase_1_matcher_core_lib.md`](phase_1_matcher_core_lib.md) | Shared normalization + offset-preserving locate + scoring; pure Python lib, no DB. Extract `pickRefsToShow` logic into a Python equivalent. |
| 2 | [`phase_2_storage_and_cli.md`](phase_2_storage_and_cli.md) | Mongo `extract_matches` collection + orchestrator that walks Neo4j edges + `scripts/match_extracts.py` CLI with three modes. |
| 3 | [`phase_3_ui_gatha_page.md`](phase_3_ui_gatha_page.md) | Add Sanskrit teeka section; move Hindi bhaavarth into its own window; highlight rendering driven by `?match=<id>` query param. |
| 4 | [`phase_4_ui_definition_modal_link.md`](phase_4_ui_definition_modal_link.md) | Add "View in Shastra" CTA per block in `DefinitionModal` when a match exists; deep-links into the gatha page. |

## Out of scope (defer)

- Celery / async worker orchestration — manual CLI only for v1.
- Re-ranking with embeddings — pure normalized substring + shingle.
- Cross-shastra matches (extract cites Shastra A but text is found in
  Shastra B) — only the edge-resolved target is searched.
- Admin review queue for low-confidence matches — stored with
  `status='unmatched'` for future review.
