"""add table_type to tables (index|general)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-10
"""

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tables "
        "ADD COLUMN table_type TEXT NOT NULL DEFAULT 'general'"
    )
    op.execute(
        "ALTER TABLE tables "
        "ADD CONSTRAINT tables_table_type_check "
        "CHECK (table_type IN ('index','general'))"
    )
    op.execute("CREATE INDEX idx_tables_type ON tables(table_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tables_type")
    op.execute("ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_table_type_check")
    op.execute("ALTER TABLE tables DROP COLUMN IF EXISTS table_type")
