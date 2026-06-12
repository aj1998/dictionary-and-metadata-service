"""Add prakrit_verse_marker to gathas (per-page source verse number)."""

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE gathas ADD COLUMN prakrit_verse_marker TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE gathas DROP COLUMN prakrit_verse_marker")
