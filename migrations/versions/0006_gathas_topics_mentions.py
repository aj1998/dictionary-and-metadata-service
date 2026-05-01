"""Create gathas, topics, and topic_mentions tables."""

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gathas (
            id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key                   TEXT NOT NULL UNIQUE,
            shastra_id                    UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
            gatha_number                  TEXT NOT NULL,
            adhikaar                      JSONB,
            heading                       JSONB,
            prakrit_doc_id                TEXT,
            sanskrit_doc_id               TEXT,
            hindi_chhand_doc_ids          JSONB NOT NULL DEFAULT '[]'::jsonb,
            prakrit_word_meanings_doc_id  TEXT,
            sanskrit_word_meanings_doc_id TEXT,
            teeka_mapping_doc_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
            keyword_ids                   JSONB NOT NULL DEFAULT '[]'::jsonb,
            topic_ids                     JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_gathas_shastra ON gathas(shastra_id)")
    op.execute("CREATE INDEX idx_gathas_keyword_ids ON gathas USING gin (keyword_ids jsonb_path_ops)")
    op.execute("CREATE INDEX idx_gathas_topic_ids ON gathas USING gin (topic_ids jsonb_path_ops)")
    op.execute("""
        CREATE TRIGGER trg_gathas_updated_at
        BEFORE UPDATE ON gathas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE topics (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key       TEXT NOT NULL UNIQUE,
            display_text      JSONB NOT NULL,
            source            ingestion_source NOT NULL,
            parent_keyword_id UUID REFERENCES keywords(id) ON DELETE SET NULL,
            extract_doc_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
            graph_node_id     TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_topics_parent_keyword ON topics(parent_keyword_id)")
    op.execute("""
        CREATE TRIGGER trg_topics_updated_at
        BEFORE UPDATE ON topics
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE topic_mentions (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id                 UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            teeka_id                 UUID REFERENCES teekas(id),
            gatha_id                 UUID REFERENCES gathas(id),
            book_id                  UUID REFERENCES books(id),
            pravachan_id             UUID REFERENCES pravachans(id),
            page                     INT,
            cataloguesearch_chunk_id TEXT,
            mongo_doc_id             TEXT,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (
                (teeka_id IS NOT NULL)::int +
                (gatha_id IS NOT NULL)::int +
                (book_id IS NOT NULL)::int +
                (pravachan_id IS NOT NULL)::int = 1
            )
        )
    """)
    op.execute("CREATE INDEX idx_topic_mentions_topic ON topic_mentions(topic_id)")
    op.execute("CREATE INDEX idx_topic_mentions_chunk ON topic_mentions(cataloguesearch_chunk_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS topic_mentions")
    op.execute("DROP TABLE IF EXISTS topics")
    op.execute("DROP TABLE IF EXISTS gathas")
