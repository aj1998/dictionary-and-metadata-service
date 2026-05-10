"""Fix keyword_aliases unique constraint: alias_text → (keyword_id, alias_text)."""

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE keyword_aliases DROP CONSTRAINT IF EXISTS keyword_aliases_alias_text_key")
    op.execute("""
        ALTER TABLE keyword_aliases
          ADD CONSTRAINT uq_keyword_aliases_kw_alias UNIQUE (keyword_id, alias_text)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE keyword_aliases DROP CONSTRAINT IF EXISTS uq_keyword_aliases_kw_alias")
    op.execute("ALTER TABLE keyword_aliases ADD CONSTRAINT keyword_aliases_alias_text_key UNIQUE (alias_text)")
