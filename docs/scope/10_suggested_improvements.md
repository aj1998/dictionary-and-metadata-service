# 10 — Suggested Improvements

Additions to the SAAR vision I'd recommend including, grouped by where they fit.

## Reading experience

1. **"Read across teekas" mode.** A side-by-side panel showing the same gatha's bhaavarth from multiple teekakaars (Amritchandra vs. Jaisen vs. Pandit Kunthusagar). Already supported by your data model (`teekas`, `teeka_mapping_doc_ids`), just exposed in the reader.
2. **Inline anumaan / anvayartha quiz.** For students: hide the word-by-word and let the reader test recall, revealing one word at a time. Tracked per user.
3. **Citation collector.** Selecting any text adds it to a personal "swadhyay clipboard" with auto-formatted citation. Exports to BibTeX, markdown, or a PDF essay template.
4. **Per-gatha "topic map" thumbnail.** A tiny 8-node graph visualisation on every gatha card on the listing page (`/shastras/[nk]`) — preview of what the gatha touches. Generated from `MENTIONS_TOPIC`.
5. **Reading streaks and progress.** Per-user "you have read 47/415 gathas of समयसार". Optional, opt-in. Strong retention lever.
6. **Adhikaar-level audio with bookmarks.** Audio reader saves position per user, lets them resume across devices.
7. **Right-rail "ask the AI"** scoped to the gatha currently in view — pre-seeded with this gatha's context so questions get high-precision answers.

## Graph

8. **Graph diff view.** Show which nodes/edges were added in the last N enrichment runs. Useful for power users and for admins reviewing pipeline quality.
9. **Path-explainer.** "Why is keyword A connected to topic B?" — render the shortest path with annotations on each edge ("this edge came from JainKosh page X").
10. **Filterable layouts.** Switch between force-directed, hierarchical (anuyoga as root), radial (one keyword centred). The graph already has the data to drive any of these.

## AI page

11. **"Strict citations only" toggle.** Default mode (off) lets the model paraphrase. Strict mode refuses to answer without ≥ 1 graph-grounded citation, and renders the model's confidence per claim.
12. **Multi-shastra comparison shortcut.** "Compare what Samaysaar gatha 39 and Pravachansaar gatha 93 say about पर्याय" — pre-built UI pattern instead of free-form prompt.
13. **Counterfactual cards.** When the model uses a topic, render a small "but X says otherwise" card pulled from related-author teekas if a disagreement signal exists.
14. **Conversation export.** One-click "save this thread as a study PDF" with all citations resolved.

## Translation / enrichment

15. **Reverse-direction quality probe.** When the pipeline outputs an English keyword from Hindi, occasionally feed it back through a separate model to translate to Hindi and check round-trip stability. Surfaces translation drift cheaply.
16. **"Suggestion mode" for power users.** Logged-in researchers can propose corrections to AI translations / extractions inline; suggestions land in the review queue. Crowd-sources quality.
17. **Active-learning sampler.** The enrichment pipeline preferentially queues for human review the *spans the model was uncertain on* (low confidence + high disagreement across passes), rather than uniform sampling. Same labelling budget, much better coverage of failure modes.

## Multilingual

18. **Mantra romanisation channel.** For Sanskrit/Prakrit mantras, expose IAST + ISO 15919 romanisations alongside Devanagari. Useful for non-Hindi readers and ML training corpora alike.
19. **Phonetic search.** "Type in romanised text and find the keyword." Already partly free from `pg_trgm`; add a transliteration index.

## Finetuning / models

20. **Open the eval harness.** Publish the eval datasets (anonymised) as a benchmark — "JaiBench". Encourages external contributors; brand boost for SAAR.
21. **Tool-use finetune.** Teach the main model to call internal tools (graph query, counter lookup, citation resolver) as function calls. Cheaper than re-training when a knowledge slice changes; the model just queries the live graph.
22. **Distillation cascade.** Train a tiny model (1–3B) that mimics the main model's answers for common queries. Serves cheaply, falls back to the main model on low confidence.

## Operations

23. **Provenance everywhere.** Every text block in the UI carries: source, ingestion run ID, reviewer (if any), reviewed date. Already in tables; add a hover-to-see provenance ribbon.
24. **A "weekly digest" newsletter.** Auto-summarises the week's newly-added gathas, topics, drush-taants, audios, and approved translations. Strong community-building lever.
25. **Public open-data dumps.** Quarterly JSONL exports of the public graph and Mongo extracts under a CC-BY-NC-SA-like licence (with original-source attribution preserved). Aligns with the project's spirit.
26. **Sponsor-acknowledgement pipeline.** Some shastras / pravachans are sponsored by publishers; build a clean "thank-you" footer that pulls from `teekas.publisher` etc.

## Community & longevity

27. **Discussion threads anchored to gathas / topics / Q&As.** Light-touch — markdown, slow moderation. Many readers want to discuss without standing up Slack/Discord. Could be Discourse-as-a-service rather than build.
28. **Reading groups.** Multiple users sharing a saved-view + scratchpad. Slightly beyond co-editing but valuable.
29. **API access for researchers.** Read-only API tokens with rate limits, gated by reviewer-approval. The data has academic value; structured access is a public good.

## What I'd consciously *not* add

- Co-editing of gathas (high risk, scope creep).
- A user-submitted shastra ingest pipeline (quality control nightmare).
- Real-time translation (cost vs. value for an asynchronous study product is poor).
- NFTs / on-chain provenance — provenance lives in Postgres + S3, that's enough.
