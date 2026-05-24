# JainKosh Ingestion Orchestration — Implementation Spec

This spec covers the **non-parser** flows of `08_ingestion_jainkosh.md`. The
parser (`workers/ingestion/jainkosh/`) is already implemented at v1.2.0 and
emits a `WouldWriteEnvelope` from saved HTML. What is missing is everything
that wraps the parser:

1. Schema deltas required by the parser's output (topics hierarchy, Mongo
   shapes, Neo4j props/edges) and an idempotent **apply layer** that can
   take a `WouldWriteEnvelope` and write it to all three stores.
2. The **fetch / discover / queue** loop: Celery task that walks the
   dictionary index → category pages → keyword pages, rate-limits, writes
   raw HTML snapshots, mines aliases, and inserts envelopes into
   `ingestion_review_queue`.
3. **Approve action + end-to-end idempotency + tests + CLI**: wiring the
   queue review approval to the apply layer, full Celery + CLI runners, and
   the idempotency guarantee from the orchestrator-stage Definition of
   Done in `08_ingestion_jainkosh.md`.

## Phases

| Phase | Doc | Dep | What ships |
|---|---|---|---|
| 1 | [`phase_1_schema_and_apply.md`](./phase_1_schema_and_apply.md) | parser v1.2.0 | Migration `0010_topics_hierarchy`, Mongo `keyword_definitions`/`topic_extracts` shape rewrite + indexes, Neo4j `topic_path`/`is_leaf` + `topic_kw_path` index + `PART_OF` wiring, `apply_approved_keyword_payload(envelope)` function. Deterministic given an envelope; no HTTP. |
| 2 | [`phase_2_fetch_and_queue.md`](./phase_2_fetch_and_queue.md) | Phase 1 | `discover.py`, `fetch.py` (rate-limited httpx), `alias_mining.py`, `orchestrator.py` Celery task, snapshot writer, `ingestion_runs` row, queue-insert path. End-to-end ingest **up to** queue-with-pending. |
| 3 | [`phase_3_approve_and_e2e.md`](./phase_3_approve_and_e2e.md) | Phases 1+2 | Approve action calls Phase-1 apply; reject path; CLI (`python -m workers.ingestion.jainkosh.orchestrator …`); idempotency e2e test (run twice → zero net DB diff after second approve); rate-limit honor test; alias-mining test; fixture-based golden run. |

Each phase has its own Definition of Done. A lower-reasoning model should
implement one phase top-to-bottom, run the listed tests, and stop.

## Conventions (apply to every phase)

- Re-use existing `jain_kb_common` upserts where possible
  (`upsert_keyword`, `upsert_topic`, Mongo `upsert_keyword_definition`,
  `upsert_topic_extract`, `upsert_raw_html_snapshot`, Neo4j `sync_keyword`,
  `sync_topic`). Do **not** duplicate them in `workers/`.
- Add new helper signatures (e.g., `upsert_keyword_alias`) inside
  `jain_kb_common` rather than `workers/`.
- Every write path must be safe to call twice with the same envelope
  (`ON CONFLICT DO UPDATE` / `MERGE`) — this is enforced by the Phase-3
  idempotency test.
- All Devanagari strings are NFC-normalized at the entry point (already
  guaranteed by parser; re-assert at `apply_approved_keyword_payload`).
- Postgres is the source of truth for IDs. Mongo `_id` derives from
  `stable_id(natural_key)`; Neo4j references `natural_key`.
- Topic upsert order in apply: **walk parents first** (root → leaves)
  so `parent_topic_id` resolves. Use the `topic_path` length as a sort
  key (shorter path first).
- Idempotency contracts: the envelope's
  `would_write.idempotency_contracts` map is informational for v1; the
  apply layer hard-codes the conflict keys per table. Future versions
  can read the map.

## Out of scope for this spec

- nikkyjain ingestion (`09_ingestion_nikkyjain.md`).
- Admin UI review pages (`13_admin_ui.md`) — Phase 3 only exposes the
  approve function as a Python callable + CLI, not an HTTP endpoint.
- Public APIs.
- Vyakaran OCR (`10`).
