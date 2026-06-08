"""add role column to teekas table

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-08
"""

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE teekas ADD COLUMN IF NOT EXISTS role TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE teekas DROP COLUMN IF EXISTS role")
