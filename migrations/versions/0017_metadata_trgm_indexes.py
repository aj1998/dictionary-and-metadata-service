"""Add GIN trigram indexes on shastras, authors, teekas for fuzzy metadata search."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # shastras — natural_key (Latin) + title JSONB cast (Devanagari / English)
    op.execute(
        "CREATE INDEX IF NOT EXISTS shastras_nk_trgm "
        "ON shastras USING gin (natural_key gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS shastras_title_trgm "
        "ON shastras USING gin ((title::text) gin_trgm_ops)"
    )
    # authors — natural_key + display_name JSONB cast
    op.execute(
        "CREATE INDEX IF NOT EXISTS authors_nk_trgm "
        "ON authors USING gin (natural_key gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS authors_display_name_trgm "
        "ON authors USING gin ((display_name::text) gin_trgm_ops)"
    )
    # teekas — natural_key only (no dedicated name column)
    op.execute(
        "CREATE INDEX IF NOT EXISTS teekas_nk_trgm "
        "ON teekas USING gin (natural_key gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS teekas_nk_trgm")
    op.execute("DROP INDEX IF EXISTS authors_display_name_trgm")
    op.execute("DROP INDEX IF EXISTS authors_nk_trgm")
    op.execute("DROP INDEX IF EXISTS shastras_title_trgm")
    op.execute("DROP INDEX IF EXISTS shastras_nk_trgm")
