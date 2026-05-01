"""Create topic_candidates and chat_puller_state tables."""

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE topic_candidates (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_chat_id            TEXT NOT NULL UNIQUE,
            proposed_topic_text       JSONB NOT NULL,
            associated_keyword_texts  JSONB NOT NULL,
            user_query                TEXT,
            llm_explanation           TEXT,
            cataloguesearch_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status                    candidate_status NOT NULL DEFAULT 'pending',
            merged_into_topic_id      UUID REFERENCES topics(id),
            reviewed_by               TEXT,
            reviewed_at               TIMESTAMPTZ,
            reject_reason             TEXT,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_topic_candidates_status ON topic_candidates(status)")

    op.execute("""
        CREATE TABLE chat_puller_state (
            id               INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            last_pulled_at   TIMESTAMPTZ,
            last_source_id   TEXT,
            last_run_status  TEXT,
            last_error       TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_puller_state")
    op.execute("DROP TABLE IF EXISTS topic_candidates")
