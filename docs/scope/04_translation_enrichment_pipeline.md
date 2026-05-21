# 04 — Translation & Enrichment Pipeline

The engine behind multilingual reading, JainKosh highlights, counters, hierarchy, categorisation, and finetune-dataset generation. Runs as a Celery DAG triggered manually per shastra (or per adhikaar), with admin review gates between stages.

## Three core stages

### Stage A — Topic extraction with indexes

For each translated bhaavarth chunk (Hindi), an LLM extracts a list of topic mentions and where they appear (character span / sentence index). Matched against existing `topics` rows; new candidates land in `topic_candidates` for admin review. Approved candidates merge into `topics` + Neo4j.

**Inputs:** bhaavarth Mongo doc, current `topics` index (filtered to the parent keyword neighbourhood).

**Output:** `{topic_natural_key, span_start, span_end, confidence, new_candidate?}[]`.

### Stage B — Keyword extraction with indexes + Vitrag-elibrary Hin→Eng

Same as Stage A but for keywords (the JainKosh-style atomic terms). Additionally, the extractor proposes an English equivalent for each keyword using the **Vitrag-elibrary** Hindi→English dictionary (separate ingest, see [05_multilingual_strategy.md](./05_multilingual_strategy.md)) as a constrained vocabulary. The AI picks the most appropriate entry per context; admin approves.

**Inputs:** chunk text, current `keywords` index, Vitrag-elibrary dictionary view.

**Output:** `{keyword_natural_key, span_start, span_end, vitrag_en_candidate, confidence, new_candidate?}[]`.

### Stage C — Hierarchy enrichment

For each new candidate topic, an LLM proposes parent topic relations ("Is this a sub-topic of an existing topic? Of which one?"). Walks the existing topic graph for closest matches (via vector similarity over topic display text), proposes `PART_OF` / `IS_A` / `RELATED_TO` edges with confidence scores. Admin approves edges before they enter the graph.

## Counters (USP)

Persisted in `topic_keyword_counters` (Postgres). Per (entity_type ∈ {keyword, topic}, entity_id, scope ∈ {shastra, teeka, anuyoga, global}):

```
mentions_count BIGINT
distinct_gathas_count INT
last_recomputed_at TIMESTAMPTZ
```

Recomputed at end of every enrichment run via SQL aggregations over `gathas.keyword_ids`, `gathas.topic_ids`, and the new `extraction_spans` table. Exposed on every keyword/topic card and in the reader popover. Used by the ranker as a prior.

Spec: `design/scope/10_topic_keyword_counters_spec.md`.

## State machine

```
INGESTED (gathas in DB)
  │
  ▼
EXTRACTION_QUEUED ──► EXTRACTION_RUN (LLM call) ──► EXTRACTION_REVIEW (admin)
  │                                                        │
  │                                                ┌───────┴─────┐
  ▼                                                ▼             ▼
HIERARCHY_QUEUED ──► HIERARCHY_RUN ──► HIERARCHY_REVIEW    REJECTED
  │
  ▼
COUNTERS_RECOMPUTE
  │
  ▼
GRAPH_SYNC ──► PUBLISHED
```

Each stage is a Celery task; transitions are recorded in `enrichment_runs` (new table; mirror of `ingestion_runs` shape).

## Future extensions

- **Other languages.** Same pipeline runs for Kn/Gu/Sa/Pr where source text exists — out of scope for v1 but the pipeline is language-agnostic by design (uses `lang` parameter throughout).
- **Topic-extract back-feed.** New topics discovered by the pipeline are themselves indexed against future runs (compounding coverage).

## LLM prompt skeletons

See `design/scope/09_translation_pipeline_ai_flow_spec.md` for concrete prompts. Key constraints:

- Always return JSON (response_format=json_schema where supported).
- Span indices in UTF-8 code points (not bytes) into the source Mongo doc text.
- Never invent a topic that's not in the index unless `proposing_new = true` — keeps hallucinations down.
- Tag each output `confidence` ∈ {high, medium, low}; admin UI sorts low-confidence to the top of the review queue.

## Eval

A small golden set (10 chapters across 3 shastras) of human-extracted topic/keyword spans is the regression bar. Spec: `design/scope/24_finetune_eval_harness_spec.md` (the same harness evaluates extraction quality, not just finetuned models).

## Definition of done

- [ ] Pipeline DAG runs E2E on one adhikaar of samaysaar.
- [ ] Counters published on at least 100 keywords, 50 topics.
- [ ] Vitrag-elibrary dictionary ingested with ≥ 10K Hin→En entries (or whatever the source provides).
- [ ] Hierarchy review UI surfaces proposed edges; admin can approve/reject.
- [ ] Graph reflects new topic edges after publish.
- [ ] Golden-set extraction precision ≥ 0.8 on a held-out 100-span sample.
