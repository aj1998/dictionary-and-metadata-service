"""Create publications table."""

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key   TEXT NOT NULL UNIQUE,
            teeka_id      UUID NOT NULL REFERENCES teekas(id) ON DELETE CASCADE,
            publisher_id  TEXT NOT NULL,
            publisher     JSONB,
            public_url    TEXT,
            publisher_url TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_publications_teeka ON publications(teeka_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_publications_teeka")
    op.execute("DROP TABLE IF EXISTS publications")
