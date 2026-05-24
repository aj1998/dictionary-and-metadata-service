# Correction: Remove `topic_mentions` Postgres Table

## Decision

Drop the `topic_mentions` Postgres table. It is redundant with Neo4j and was never populated by the ingestion pipeline.

## Rationale

`topic_mentions` was designed to track which gathas/teekas/books/pravachans cite a topic. That relationship is already fully modelled in Neo4j:

| What `topic_mentions` tracked | Neo4j equivalent |
|---|---|
| Gatha → Topic | `(Gatha)-[:MENTIONS_TOPIC]->(Topic)` |
| Teeka content → Topic | `(GathaTeeka)-[:MENTIONS_TOPIC]->(Topic)` |
| Topic definition → Topic | `(Topic)-[:CONTAINS_DEFINITION]->(Keyword)` (reverse path) |
| `cataloguesearch_chunk_id` | `source_chunk_id` property on the Neo4j edge |

Evidence that the table was a dead placeholder:
- `packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py` has no `upsert_topic_mention`.
- `workers/ingestion/jainkosh/apply.py` has no reference to `TopicMention`.
- No test references the model.

The navigation service (direct Neo4j) is the correct authoritative source for "where is topic X mentioned". Having a Postgres copy would require a dual-write sync (Postgres + Neo4j), which adds complexity with no benefit.

## Changes Required

### 1. Postgres SQLAlchemy model

**File**: `packages/jain_kb_common/jain_kb_common/db/postgres/topics.py`

Remove the entire `TopicMention` class (lines 47–96).

### 2. Alembic migration

**New file**: `migrations/versions/0014_drop_topic_mentions.py`

```python
"""Drop topic_mentions table (redundant with Neo4j MENTIONS_TOPIC edges)."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("topic_mentions")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE topic_mentions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            teeka_id UUID REFERENCES teekas(id),
            gatha_id UUID REFERENCES gathas(id),
            book_id UUID REFERENCES books(id),
            pravachan_id UUID REFERENCES pravachans(id),
            page INT,
            cataloguesearch_chunk_id TEXT,
            mongo_doc_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_topic_mention_single_source CHECK (
                (teeka_id IS NOT NULL)::int +
                (gatha_id IS NOT NULL)::int +
                (book_id IS NOT NULL)::int +
                (pravachan_id IS NOT NULL)::int = 1
            )
        )
    """)
    op.execute("CREATE INDEX idx_topic_mentions_topic ON topic_mentions(topic_id)")
    op.execute("CREATE INDEX idx_topic_mentions_chunk ON topic_mentions(cataloguesearch_chunk_id)")
```

### 3. `apply.py`

No changes needed — `apply.py` never wrote to `topic_mentions`.

### 4. Tests

No changes needed — no test references `TopicMention`.

### 5. Design docs

- Remove the `topic_mentions` section from `docs/design/data_model_postgres.md`.
- The data service topic detail response does **not** include a `mentions` field. Callers that need topic→gatha/teeka mention links query the navigation service.

## Impact on API Responses

The old `dictionary-service` spec included a `mentions` array in the topic detail response, sourced from `topic_mentions`. In the new design:

- **`GET /v1/topics/{id}`** (data service): returns Postgres row + Mongo extracts only. No `mentions` field.
- Topic mention context is available via `GET /v1/topics/{natural_key}/neighbors` in the navigation service, which reads directly from Neo4j `MENTIONS_TOPIC` edges.
