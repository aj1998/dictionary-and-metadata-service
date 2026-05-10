"""Add topics hierarchy columns and check constraint."""

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        ALTER TABLE topics
          ADD COLUMN IF NOT EXISTS topic_path        TEXT,
          ADD COLUMN IF NOT EXISTS parent_topic_id   UUID REFERENCES topics(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS is_leaf           BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS is_synthetic      BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE topics
          ADD CONSTRAINT IF NOT EXISTS topics_natural_key_no_source_prefix
          CHECK (natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%')
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_topics_parent_topic ON topics(parent_topic_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_topics_keyword_path ON topics(parent_keyword_id, topic_path)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_topics_keyword_path")
    op.execute("DROP INDEX IF EXISTS idx_topics_parent_topic")
    op.execute("ALTER TABLE topics DROP CONSTRAINT IF EXISTS topics_natural_key_no_source_prefix")
    op.execute("ALTER TABLE topics DROP COLUMN IF EXISTS is_synthetic")
    op.execute("ALTER TABLE topics DROP COLUMN IF EXISTS is_leaf")
    op.execute("ALTER TABLE topics DROP COLUMN IF EXISTS parent_topic_id")
    op.execute("ALTER TABLE topics DROP COLUMN IF EXISTS topic_path")
