"""Create keywords and keyword_aliases tables."""

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE keywords (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key        TEXT NOT NULL UNIQUE,
            display_text       TEXT NOT NULL,
            source_url         TEXT,
            definition_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            graph_node_id      TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX idx_keywords_text_trgm ON keywords USING gin (display_text gin_trgm_ops)
    """)
    op.execute("""
        CREATE TRIGGER trg_keywords_updated_at
        BEFORE UPDATE ON keywords
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE keyword_aliases (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alias_text   TEXT NOT NULL,
            keyword_id   UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
            source       TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (alias_text)
        )
    """)
    op.execute("CREATE INDEX idx_keyword_aliases_keyword ON keyword_aliases(keyword_id)")
    op.execute("""
        CREATE INDEX idx_keyword_aliases_alias_trgm ON keyword_aliases USING gin (alias_text gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS keyword_aliases")
    op.execute("DROP TABLE IF EXISTS keywords")
