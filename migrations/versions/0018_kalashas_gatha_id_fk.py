"""add gatha_id FK to kalashas

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kalashas",
        sa.Column("gatha_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_kalashas_gatha_id",
        "kalashas", "gathas",
        ["gatha_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_kalashas_gatha", "kalashas", ["gatha_id"])


def downgrade() -> None:
    op.drop_index("idx_kalashas_gatha", table_name="kalashas")
    op.drop_constraint("fk_kalashas_gatha_id", "kalashas", type_="foreignkey")
    op.drop_column("kalashas", "gatha_id")
