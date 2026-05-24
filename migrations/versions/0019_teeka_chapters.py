"""create teeka_chapters table for chapter metadata per primary teeka

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-25
"""

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE teeka_chapters (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key           TEXT NOT NULL UNIQUE,
            teeka_id              UUID NOT NULL REFERENCES teekas(id) ON DELETE CASCADE,
            chapter_number        INTEGER NOT NULL,
            name                  JSONB NOT NULL DEFAULT '[]',
            start_gatha_id        UUID NOT NULL REFERENCES gathas(id),
            end_gatha_id          UUID REFERENCES gathas(id),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (teeka_id, chapter_number)
        )
    """)
    op.execute("CREATE INDEX idx_teeka_chapters_teeka ON teeka_chapters(teeka_id)")
    op.execute("CREATE INDEX idx_teeka_chapters_start_gatha ON teeka_chapters(start_gatha_id)")
    op.execute("""
        CREATE TRIGGER trg_teeka_chapters_updated_at
        BEFORE UPDATE ON teeka_chapters
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS teeka_chapters")
