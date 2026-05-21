# 09 — Open Questions

Questions I want pinned down before / during implementation. Grouped by area; each has my best-guess default the specs already encode, marked **D:**. The spec is built around the default; answer if you disagree.

## Brand & repo topology

- **Q1.** Is **Jinvani SAAR** a new top-level brand replacing `cataloguesearch` / `cataloguesearch-chat` consumer-facing names, or just the umbrella for the new pages? **D:** new public umbrella; `cataloguesearch` and `-chat` remain backend repo names.
- **Q2.** Do all new services (auth, audio, image, model-serving, scratchpad) live in the `dictionary-and-metadata-service` repo, or as siblings under `Coding/Jinvani/`? **D:** services in this repo (`services/<name>/`), but model-serving in a sibling `Coding/Jinvani/model-serving/` because of GPU dependency.
- **Q3.** Is `cataloguesearch` itself something we modify, or do we strictly call it as a black box? **D:** call as black box; enhancements (graph-aware re-rank, A/V chunks) ride alongside via an enhancement wrapper. Confirm if we own that repo.

## Shastra reader

- **Q4.** Per-shastra layout configs: who authors them and where do they live in source? **D:** YAML under `parser_configs/shastra_layouts/<family>/<natural_key>.yaml`; authored by admin via the admin UI editor, validated by a JSON schema, version-controlled like the existing `jainkosh.yaml`.
- **Q5.** Drush-taant images: which image gen provider and what is the per-month budget? **D:** GPT-4o image (preferred for prompt fidelity) with Stable Diffusion XL as fall-back; admin sets monthly cap in env. Always admin-reviewed before publish.
- **Q6.** ElevenLabs voice selection: do we pick one Hindi voice per shastra, or per chapter? **D:** one voice per shastra, configurable in the layout config. Multi-voice (for dialogue puraans) is v2.
- **Q7.** PDF export: do we watermark with the project name + source URLs? **D:** yes for all exports; user name in watermark only if logged-in user opts in.

## Translation pipeline

- **Q8.** Vitrag-elibrary: do we have a clean dump, or do we need to scrape? Licensing? **D:** assume we can scrape and store under fair-use; admin reviewer flags before publish. Confirm.
- **Q9.** "Counters as USP" — scope is per-(keyword|topic) × (shastra, anuyoga, global). Do we also need per-author counters? **D:** not in v1; the join is cheap to add later.
- **Q10.** Hierarchy assistance: if AI proposes a parent that conflicts with an existing edge, do we *replace* or *coexist*? **D:** coexist with `RELATED_TO` (soft); never replace an admin-approved `IS_A`/`PART_OF` without explicit re-review.

## Multilingual

- **Q11.** Kannada/Gujarati dictionaries: which specific books / digital sources do we OCR? **D:** TBD — first ingest is whichever Jain Kannada / Gujarati dictionary the product owner provides. Spec is source-agnostic.
- **Q12.** Tamil: scope? **D:** out of v1; placeholder in the schema only.
- **Q13.** Sanskrit chhaaya: do we *display* it always for shastras that have it, or behind a toggle? **D:** display always between Prakrit and Hindi (matches Tier-1 in 05).

## Advanced RAG / A-V

- **Q14.** Jinswara "verified authors" — how is verification done? **D:** admin maintains an allowlist of author IDs in `parser_configs/jinswara_authors.yaml`. New authors require admin approval.
- **Q15.** YouTube ingestion: which speech-to-text? **D:** Whisper-v3 (open) for cost; AssemblyAI for higher accuracy if budget allows. Configurable.
- **Q16.** Flowchart/table scanner: which detector? **D:** Microsoft TableTransformer for tables; an off-the-shelf doc-layout model (LayoutLMv3 or YOLO-v8 fine-tuned on a small Jain-OCR set) for flowcharts/figures.

## Finetuning

- **Q17.** Base model choice for graph-understanding finetune. **D:** Qwen-2.5-7B-Instruct (good Hindi + permissive license).
- **Q18.** Base model for Jainism main model. **D:** Llama-3.1-70B (or 34B Qwen) — open-weight, multilingual, accepts long context. Heavy infra; OK to start with 13B and graduate.
- **Q19.** Training infra: rented GPUs (Lambda / RunPod / Modal) vs. owned? **D:** rented on demand; checkpoints + datasets go to a long-lived S3-compatible bucket. Spec assumes Modal because of bursty workloads.
- **Q20.** DPO / RLAIF preference data — where does it come from? **D:** v1 uses SFT only; preference data comes later from logged AI page chats with thumbs-up/down.

## User accounts

- **Q21.** Auth backend: build (FastAPI + Authlib + magic links) or buy (Auth0 / Clerk)? **D:** build (low scale, sovereignty matters for Jain study communities). Magic link + Google OAuth only.
- **Q22.** Data retention on account deletion: erase chat history fully, or anonymise and keep for retrieval improvement? **D:** anonymise by default (configurable per user at signup).

## Cross-cutting

- **Q23.** Provider strategy: do we have hard cost caps per environment? **D:** monthly env caps via env vars (`ANTHROPIC_MONTHLY_USD_CAP`, etc.); the `llm_call` abstraction enforces them and falls back to a smaller model when exceeded.
- **Q24.** Where do AI-generated artefacts (images, audio, drush-taant) get versioned for *future re-generation*? **D:** record the (model, prompt, seed, timestamp) tuple alongside the artefact so a future re-run is reproducible.
- **Q25.** Sitemap + SEO: are research tools and AI page indexed? **D:** AI page is `noindex` (queries leak intent); ShastraExplorer and Graph are indexed; Research Tools landing page indexed but per-tool sessions not.
- **Q26.** Multi-tenant or single-tenant? **D:** single-tenant (one Jinvani SAAR deployment); future federation across institutions out of scope.
- **Q27.** Data export for users (GDPR-style portability)? **D:** account download (JSON of preferences + saved-views + scratchpad + chat history) endpoint included from day one.
