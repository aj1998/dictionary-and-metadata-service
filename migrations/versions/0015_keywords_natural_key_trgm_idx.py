"""Add GIN trigram index on keywords.natural_key for fuzzy matching."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS keywords_natural_key_trgm_idx "
        "ON keywords USING gin (natural_key gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS keywords_natural_key_trgm_idx")
