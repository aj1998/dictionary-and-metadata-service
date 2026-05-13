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
