"""Add GIN trigram index on topics natural_key (slash-replaced) for parent-aware similarity search."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS topics_natural_key_trgm_idx "
        "ON topics USING gin (REPLACE(natural_key, '/', ' ') gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS topics_natural_key_trgm_idx")
