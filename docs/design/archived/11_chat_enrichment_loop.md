# 11 — Chat Enrichment Loop

Daily cron job that pulls AI-generated topic candidates from `cataloguesearch-chat`'s database, lands them in our `topic_candidates` table, and surfaces them in the admin UI for human approval. Approved candidates merge into the topic graph.

## Direction (per FQ4)

`cataloguesearch-chat` exposes its own database (read-only access for us). We **pull** on a cron — no push from chat to us. This keeps the integration loose.

## Required from cataloguesearch-chat side

A read-only Postgres role (or a read-replica) granting SELECT on a single view:

```sql
-- Owned by cataloguesearch-chat. We do NOT manage this view; we just consume it.
CREATE VIEW chat_topic_candidates_v1 AS
SELECT
  id                       AS source_chat_id,         -- stable across our pulls
  generated_at             AS source_generated_at,
  proposed_topic_text_hi   AS proposed_topic_text_hi,
  associated_keywords      AS associated_keywords,    -- text[] of NFC Devanagari
  user_query               AS user_query,
  llm_explanation          AS llm_explanation,
  cataloguesearch_chunk_ids AS cataloguesearch_chunk_ids
FROM ai_topic_candidates
WHERE generated_at > now() - interval '14 days';
```

(Schema owned by chat; we treat it as a contract. If chat changes the view, version it: `chat_topic_candidates_v2` etc., and we update the puller.)

Connection details supplied to us via env:

```
CHAT_DB_DSN=postgresql://reader:***@chat-db-host:5432/chat
CHAT_VIEW_NAME=chat_topic_candidates_v1
```

## Our side

### Cron worker

Celery beat schedule:

```python
# workers/enrichment/chat_candidate_puller/schedule.py
beat_schedule = {
    "chat-puller-daily": {
        "task": "workers.enrichment.chat_candidate_puller.pull_new_candidates",
        "schedule": crontab(hour=2, minute=15),    # 02:15 daily
    }
}
```

### Pull algorithm

```python
# workers/enrichment/chat_candidate_puller/__init__.py
async def pull_new_candidates():
    state = await load_chat_puller_state()
    last_id = state.last_source_id
    last_pull = state.last_pulled_at or (now() - timedelta(days=14))

    async with chat_pg.connect() as chat_conn, our_pg.session() as our_session:
        rows = await chat_conn.fetch("""
          SELECT * FROM chat_topic_candidates_v1
          WHERE source_generated_at > $1
          ORDER BY source_generated_at ASC, source_chat_id ASC
        """, last_pull)

        inserted = 0
        for r in rows:
            # idempotent insert by source_chat_id
            stmt = pg_insert(TopicCandidate).values(
                source_chat_id=r["source_chat_id"],
                proposed_topic_text=[{"lang": "hin", "script": "Deva",
                                      "text": nfc(r["proposed_topic_text_hi"])}],
                associated_keyword_texts=[nfc(k) for k in r["associated_keywords"]],
                user_query=r["user_query"],
                llm_explanation=r["llm_explanation"],
                cataloguesearch_chunk_ids=r["cataloguesearch_chunk_ids"],
                status="pending",
            ).on_conflict_do_nothing(index_elements=[TopicCandidate.source_chat_id])
            res = await our_session.execute(stmt)
            inserted += res.rowcount

        await our_session.commit()
        await save_chat_puller_state(
            last_pulled_at=now(),
            last_source_id=rows[-1]["source_chat_id"] if rows else last_id,
            last_run_status=f"ok:inserted={inserted}",
        )
        return {"pulled": len(rows), "inserted": inserted}
```

`source_chat_id` is the deduplication key. Re-running the puller is safe.

### Admin review queue

Admin UI page `/admin/topic-candidates` lists `pending` candidates with:

- Proposed topic heading (Hindi)
- Associated keywords (chips, each linkable to existing keyword node if found)
- User query + LLM explanation (collapsible)
- Cataloguesearch chunk IDs (each rendered with a fetch-on-click preview hitting cataloguesearch's chunk-by-id API)
- "Existing topic match?" — server-computed: any topic with the same NFC heading + same parent keyword. If a fuzzy match exists, surface as a "merge with existing" option.

Actions per row:
- **Approve as new topic** → see merge logic below
- **Merge into existing topic** (pick from search) → just adds `topic_mentions` rows
- **Reject** with reason → updates `status=rejected, reject_reason=...`

### Merge logic on approval

```python
async def approve_topic_candidate(candidate_id: UUID, *, mode: Literal["new", "merge"],
                                  merge_target_id: UUID | None = None,
                                  reviewer: str):
    cand = await get_candidate(candidate_id)
    async with our_pg.transaction() as tx:
        if mode == "new":
            topic_natural_key = build_topic_natural_key(
                source="chat",
                parent_keyword=guess_parent_keyword(cand.associated_keyword_texts),
                heading=pick_hindi(cand.proposed_topic_text),
            )
            topic = await pg.upsert_topic(
                tx,
                natural_key=topic_natural_key,
                display_text=cand.proposed_topic_text,
                source="chat_candidate",
                parent_keyword_id=resolve_parent_keyword_id(...),
            )
            mongo_doc_id = await mongo.upsert_topic_extract(
                natural_key=topic_natural_key,
                doc=build_extract_doc(cand),
            )
            await pg.set_topic_extract_doc_ids(tx, topic.id, [str(mongo_doc_id)])
        else:
            topic = await pg.get_topic(tx, merge_target_id)

        # Mentions: link to cataloguesearch chunks
        for chunk_id in cand.cataloguesearch_chunk_ids:
            await pg.upsert_topic_mention(
                tx, topic_id=topic.id,
                cataloguesearch_chunk_id=chunk_id,
            )

        # Mentioned keywords -> graph edges
        for kw_text in cand.associated_keyword_texts:
            kw = await pg.get_keyword_by_natural_key(tx, kw_text)
            if kw is None:
                # candidate references a keyword we don't have. Two options:
                # 1. auto-create a 'pending' keyword stub (recommended for v1)
                # 2. flag for admin to scrape from JainKosh
                kw = await pg.create_keyword_stub(tx, natural_key=kw_text,
                                                  display_text=kw_text,
                                                  source_url=None)
            await pg.attach_keyword_to_topic(tx, topic_id=topic.id, keyword_id=kw.id)

        await pg.update_candidate(tx, candidate_id,
                                  status="merged",
                                  merged_into_topic_id=topic.id,
                                  reviewed_by=reviewer)

    # post-commit: graph sync (Celery)
    graph_sync.delay(topic_id=str(topic.id))
```

### `pending` keyword stubs

Keywords arriving via chat candidates that we don't yet have are created as stubs (no JainKosh definition, no aliases). They appear in admin UI tagged `unscraped` with a one-click "Scrape from JainKosh" action that triggers a single-keyword JainKosh fetch.

## Failure handling

- DB connectivity errors → puller retries with exponential backoff (3 attempts). On final failure, writes `last_run_status="error: ..."` to `chat_puller_state` and raises a Sentry/log event.
- Schema drift on the chat-side view → if a column is missing, fail the run with a clear error and notify admin. Don't silently coerce.
- Empty pulls (no new rows in 14d) → log `pulled=0` and continue.

## Env vars

```
CHAT_DB_DSN=postgresql://reader:***@chat-db:5432/chat
CHAT_VIEW_NAME=chat_topic_candidates_v1
PULLER_LOOKBACK_DAYS=14
PULLER_MAX_ROWS_PER_RUN=5000
```

## Module layout

```
workers/enrichment/chat_candidate_puller/
├── __init__.py            # pull_new_candidates Celery task
├── schedule.py            # Celery beat schedule entry
├── chat_db.py             # asyncpg connection pool to chat DB
├── merge.py               # approve_topic_candidate, build_topic_natural_key, etc.
└── tests/
    ├── fixtures/
    │   └── chat_topic_candidates_sample.json
    └── test_pull_idempotent.py
```

## Definition of Done

- [ ] `chat_puller_state` row created on first run.
- [ ] Pulling the same fixture twice produces zero net inserts (idempotent on `source_chat_id`).
- [ ] Admin UI page lists pending candidates with all fields visible.
- [ ] Approving as new topic → topic + mentions + keyword edges + graph sync, and the candidate moves to `merged` status.
- [ ] Approving as merge into existing topic → only mentions + keyword edges added; no new topic row.
- [ ] Rejection captures `reject_reason`.
- [ ] Schema-drift test: a mock chat view missing a column produces a clean error with `last_run_status` describing the drift.
