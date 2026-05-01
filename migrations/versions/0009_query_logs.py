"""Create query_logs table."""

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE query_logs (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            query_text          TEXT NOT NULL,
            normalized_tokens   JSONB NOT NULL,
            matched_keyword_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            topic_ids_returned  JSONB NOT NULL DEFAULT '[]'::jsonb,
            num_results         INT NOT NULL DEFAULT 0,
            latency_ms          INT,
            caller              TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_query_logs_created ON query_logs(created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_logs")
