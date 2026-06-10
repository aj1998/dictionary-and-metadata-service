# 01 — Pages and Features

The user-facing surface. Names match the brief: **Graph**, **AI**, **ShastraExplorer**, **ResearchTools**, plus auxiliary routes (Home, Login, Account). The existing `14_public_ui.md` route map (`/shastras`, `/dictionary`, `/topics`, `/search`) is implemented and stays where it is — these new pages live alongside.

## Top-level navigation

```
Home   |   ShastraExplorer   |   Graph   |   AI   |   ResearchTools   |   ▾Account
                                                                            (login / language / customisation)
```

## #Graph — knowledge graph workspace

Existing graph traversal page (see `design/ui/initial_design/03_graph_traversal_page.md`) becomes the *primary* graph UI. Additions:

- **Shastra Reader side panel.** Pin any node (keyword/topic/gatha) → open a docked reading pane on the right showing the corresponding ShastraExplorer view in a slim layout.
- **Multi-language overlay toggle.** Hindi/English always; one extra optional overlay (Kn/Gu/Sa/Pr) selectable for keyword and topic labels only.
- **Counter chips.** Each node carries occurrence count across corpus (USP).
- **Save graph view.** Authenticated user can save a particular set of expanded nodes + filters as a named view.

## #AI — Advanced RAG chat

The `cataloguesearch-chat` UI re-styled and re-mounted inside SAAR, with these enhancements:

- **GraphRAG-fused retrieval.** Vector hits → keyword resolve → graph expansion → re-rank (already implemented via query-service).
- **Structured citation tiles.** Each answer cites gathas / topics / keywords / Jinswara Q&As with click-throughs into ShastraExplorer or Graph.
- **Flowchart / table / diagram retrieval.** When an answer touches a topic that has a stored flowchart/table/graph (from `flowchart_table_graph_scanner` ingestion), render it inline.
- **Drush-taant generation toggle.** For a gatha-grounded answer, optionally trigger image generation (see [03_shastra_reader.md](./archived/03_shastra_reader.md)).
- **Model picker.** Pick between base Anthropic/OpenAI and finetuned in-house models (graph-understanding model, Jainism main model, research-domain models).

## #ShastraExplorer — Shastra Reader

The reading core. See [03_shastra_reader.md](./archived/03_shastra_reader.md) for full feature list. Key elements:

- Organised, per-shastra layout following its native structure (e.g. samaysaar adhikaar→kalash→gatha; puraan chapter→sarga; karm-grantha chapter→shloka). Configurable per shastra.
- Keyword hover/click expansion (popover; deep-link to `/dictionary/[nk]` or Graph).
- Optional topic-relations expansion alongside gatha/bhaavarth.
- AI-generated drush-taant image per gatha (cached, admin-approved).
- ElevenLabs audio reader.
- PDF export of a chapter / shastra / custom selection.
- JainKosh-highlighted Hindi text with hyperlinks (color-coded by topic / keyword category).
- Extended-definition highlights with hover-popover.

## #ResearchTools — topic-wise tools

A catalog page listing self-contained research workspaces. Initial entries:

- **Siri Bhoovalay decoder** — see [07_siri_bhoovalay_and_research_models.md](./07_siri_bhoovalay_and_research_models.md).
- **Jain Maths** — calculator + reference panel powered by the finetuned Jain+Modern Maths model.
- **Jain Sciences** (Physics / Chemistry / Biology) — Q/A workbenches, each pinned to a finetuned model.
- **Jain Astronomy / Teenlok** — 3D viewer + finetuned model.
- **Comparative Philosophy** — ShatDarshan ↔ Jain Darshan comparison workbench.
- **Ethics & Practical Life** — situational Q/A workbench.
- **Translation Workbench** — Hin/En ↔ Sa/Pr/Kn/Gu keyword/phrase lookup.

Each tool has the same shell: model picker, scratch pad, citations panel, export button.

## Auxiliary pages

| Page | Purpose |
|---|---|
| `/` Home | Hero + four feature cards + recent ingestion + featured shastra of the week. |
| `/login`, `/signup` | Email/OTP or Google OAuth (see [08_user_accounts.md](./08_user_accounts.md)). |
| `/account` | Profile, language preference, saved views, saved highlights, export history. |
| `/admin/...` | Existing admin UI (`admin_ui.md`) — gated routes for ingestion review, finetune jobs, model registry. |

## Layout primitives shared across pages

- **Devanagari fonts:** Noto Serif Devanagari (body), Noto Sans Devanagari (UI).
- **Language toggle:** persistent top-right; selecting EN also re-fetches with `lang=en` where translations exist (graceful fall-back to Hindi).
- **Citation badge:** uniform component showing source (shastra:gatha or url) used everywhere a quote appears.
- **Counter badge:** small chip showing topic/keyword mention count; clickable → opens occurrence list panel.
- **Provenance footer:** every AI-generated text block carries a "AI-generated, admin-approved on YYYY-MM-DD" badge or "AI-generated, unreviewed — read with care" warning.

## Page → service dependencies

| Page | Reads | Writes |
|---|---|---|
| Graph | navigation-service, data-service | (auth) saved-view-service |
| AI | query-service, cataloguesearch-chat, model-serving | query_logs |
| ShastraExplorer | data-service, metadata-service, audio-service, image-service, pdf-service | (auth) saved-highlight-service |
| ResearchTools | model-serving, query-service, data-service | (auth) scratchpad-service |
| Account | auth-service, user-prefs-service | user-prefs-service |
