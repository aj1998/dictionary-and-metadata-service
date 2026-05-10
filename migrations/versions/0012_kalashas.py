"""Create kalashas table."""

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS kalashas (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key       TEXT NOT NULL UNIQUE,
            teeka_id          UUID NOT NULL REFERENCES teekas(id) ON DELETE CASCADE,
            kalash_number     TEXT NOT NULL,
            sanskrit_doc_id   TEXT,
            hindi_doc_id      TEXT,
            bhaavarth_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_kalashas_teeka ON kalashas(teeka_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_kalashas_teeka")
    op.execute("DROP TABLE IF EXISTS kalashas")
