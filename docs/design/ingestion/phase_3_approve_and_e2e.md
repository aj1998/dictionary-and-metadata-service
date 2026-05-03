# Phase 3 — Approve action, CLI, end-to-end idempotency

**Goal**: close the loop. A queue row in `pending` can be approved (or
rejected) by a Python callable / CLI; approval invokes the Phase-1
apply layer; the entire pipeline is proven idempotent end-to-end.

When this phase is done, running

```bash
# Ingest one letter
python -m workers.ingestion.jainkosh.orchestrator ingest \
  --config parser_configs/jainkosh.yaml \
  --letter अ --triggered-by admin@example.com

# Approve everything from a run
python -m workers.ingestion.jainkosh.orchestrator approve \
  --run-id <uuid> --reviewed-by admin@example.com
```

both work, twice in a row, with zero net DB changes after the second
end-to-end pass.

---

## 3.1 Approve / reject callables

New file: `workers/ingestion/jainkosh/review.py`.

```python
async def approve_review_row(
    *,
    review_id: uuid.UUID,
    reviewed_by: str,
    pg_session_factory,
    mongo_db,
    neo4j_driver,
) -> None:
    async with pg_session_factory() as s:
        row = await s.get(IngestionReviewQueue, review_id)
        if row is None:
            raise ValueError(f"review row {review_id} not found")
        if row.status == CandidateStatus.approved:
            return  # already applied; idempotent no-op
        if row.status != CandidateStatus.pending:
            raise ValueError(f"cannot approve row in status {row.status}")
        envelope = row.proposed_payload
        run_id = row.ingestion_run_id

    # Apply outside the lookup tx, but inside its own write tx.
    async with pg_session_factory() as s:
        await apply_approved_keyword_payload(
            envelope=envelope,
            pg_session=s,
            mongo_db=mongo_db,
            neo4j_driver=neo4j_driver,
            ingestion_run_id=run_id,
        )
        await s.commit()

    async with pg_session_factory() as s:
        await s.execute(update(IngestionReviewQueue).where(
            IngestionReviewQueue.id == review_id
        ).values(
            status=CandidateStatus.approved,
            reviewed_by=reviewed_by,
            reviewed_at=func.now(),
        ))
        await s.commit()


async def reject_review_row(*, review_id, reviewed_by, reason, pg_session_factory) -> None:
    """Pure status update; no apply."""


async def approve_run(*, run_id, reviewed_by, ...) -> dict:
    """Approve every pending row for a run. Returns {approved: n, errors: [...]}.
    Loops over rows; one row's failure does not abort the rest."""
```

Properties:

- Approving an already-approved row is a no-op (idempotent).
- Apply step uses `apply_approved_keyword_payload` from Phase 1; all
  underlying writes are upserts.
- Status transition is always last; if apply fails, the row remains
  `pending` and a retry can re-run safely.

---

## 3.2 CLI

`workers/ingestion/jainkosh/orchestrator.py` — make it executable as
`python -m workers.ingestion.jainkosh.orchestrator <subcommand> …`
using `argparse`:

```
ingest    --config PATH --letter L --triggered-by EMAIL [--run-id UUID]
approve   --run-id UUID --reviewed-by EMAIL [--auto] [--review-id UUID]
reject    --review-id UUID --reviewed-by EMAIL --reason TEXT
list      --run-id UUID [--status pending|approved|rejected]
```

`approve --auto` reads `config.review.auto_approve`. If set, the CLI
calls `approve_run` immediately after `ingest` finishes. Default is
manual approval.

`list` prints `(review_id, entity_natural_key, status)` rows from
`ingestion_review_queue`.

---

## 3.3 End-to-end idempotency test

`tests/ingestion/test_e2e.py`:

```python
async def test_ingest_then_approve_twice_is_zero_net_diff(...):
    # Stub fetcher + discover with 2 saved keyword HTMLs.
    run_id_1 = await run_letter_async(...)
    await approve_run(run_id=run_id_1, reviewed_by="t@x", ...)

    snap_1 = await capture_db_snapshot(pg, mongo, neo4j)

    run_id_2 = await run_letter_async(...)   # second ingest — new run row
    await approve_run(run_id=run_id_2, reviewed_by="t@x", ...)

    snap_2 = await capture_db_snapshot(pg, mongo, neo4j)

    assert snap_1.row_counts == snap_2.row_counts
    assert snap_1.content_hashes == snap_2.content_hashes
```

`capture_db_snapshot` returns:

- Row counts for: `keywords`, `topics`, `keyword_aliases`,
  `ingestion_review_queue` (exclude `ingestion_runs` — these grow per run by design).
- Mongo: `count_documents({})` for `keyword_definitions` and `topic_extracts`.
- Neo4j: `MATCH (n:Keyword) RETURN count(n)`, same for `Topic`,
  `MATCH ()-[r:PART_OF]->() RETURN count(r)`, same for `RELATED_TO`.
- Content hashes: SHA-256 of stably-sorted `(natural_key, display_text,
  topic_path, is_leaf, is_synthetic)` tuples from `topics`, of the
  Mongo `keyword_definitions` doc bodies, and of Neo4j topic
  properties.

The two snapshots must be byte-equal except for `updated_at`
timestamps (strip them before hashing).

---

## 3.4 Auxiliary tests

`tests/ingestion/test_review.py`:

1. `test_approve_pending_then_already_approved_is_noop`.
2. `test_reject_does_not_apply` — apply layer is never called; DB rows
   not created.
3. `test_apply_failure_keeps_row_pending` — monkeypatch
   `apply_approved_keyword_payload` to raise once; assert row still
   `pending`, error surfaced; second call (no monkeypatch) succeeds.

`tests/ingestion/test_cli.py`:

1. Smoke-test each subcommand via `subprocess.run([...,'-m',
   'workers.ingestion.jainkosh.orchestrator', 'list', '--run-id',
   uuid])` against a populated test DB.

---

## 3.5 Manual testing doc

`docs/manual_testing/jainkosh_orchestrator.md` — a short runbook:

1. `alembic upgrade head` (gets you `0010` from Phase 1).
2. Ensure Postgres + Mongo + Neo4j running.
3. `python -m workers.ingestion.jainkosh.orchestrator ingest --letter अ --config parser_configs/jainkosh.yaml --triggered-by you@you`.
4. `python -m … list --run-id <uuid>`.
5. `python -m … approve --run-id <uuid> --reviewed-by you@you`.
6. Verify a row in `keywords`, `topics`, `keyword_aliases`; a doc in
   Mongo `keyword_definitions`; a node in Neo4j with
   `(:Keyword {natural_key: "आत्मा"})`.

---

## 3.6 Definition of Done — Phase 3

This is the **orchestrator-stage** Definition of Done from
`08_ingestion_jainkosh.md`, restated and made testable:

- [ ] `approve_review_row` / `approve_run` / `reject_review_row` exist
      and behave per §3.1.
- [ ] CLI subcommands `ingest`, `approve`, `reject`, `list` all work
      and are documented in `docs/manual_testing/jainkosh_orchestrator.md`.
- [ ] `test_ingest_then_approve_twice_is_zero_net_diff` passes — the
      headline idempotency guarantee.
- [ ] All auxiliary tests in `test_review.py` and `test_cli.py` pass.
- [ ] `data/raw/jainkosh/<run_ts>/` is populated by every ingest run.
- [ ] Rate limit honored (Phase 2 test still passes).
- [ ] Aliases mined for at least one keyword in the test fixture
      (verify a row in `keyword_aliases` after approve).
- [ ] Label-seed topics (`is_synthetic=True`) in the fixture are upserted
      with their own `natural_key` and do not collide with numeric-tree
      topics (assert via row count).
- [ ] Re-running the orchestrator twice with identical inputs produces
      zero net DB changes after second approval (the e2e test).

When this list is green, the orchestrator-stage of
`08_ingestion_jainkosh.md` is done. Admin UI (`13`) and any future
auto-approve / scheduled-letter cron are out of scope here.
