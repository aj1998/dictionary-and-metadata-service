"""Setup extensions, enums, and updated_at trigger."""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op

_TABLES_WITH_UPDATED_AT = [
    "authors",
    "shastras",
    "teekas",
    "books",
    "pravachans",
    "keywords",
    "gathas",
    "topics",
    "ingestion_runs",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TYPE author_kind AS ENUM ('acharya', 'gyaani', 'scholar', 'unknown')
    """)
    op.execute("""
        CREATE TYPE anuyoga_kind AS ENUM (
            'prathmanuyoga', 'karananuyoga', 'charananuyoga', 'dravyanuyoga'
        )
    """)
    op.execute("""
        CREATE TYPE ingestion_source AS ENUM (
            'jainkosh', 'nj', 'vyakaran_vishleshan', 'cataloguesearch', 'cataloguesearch-chat'
        )
    """)
    op.execute("""
        CREATE TYPE ingestion_run_status AS ENUM (
            'pending', 'running', 'success', 'partial', 'failed', 'cancelled'
        )
    """)
    op.execute("""
        CREATE TYPE candidate_status AS ENUM ('pending', 'approved', 'rejected', 'merged')
    """)


def downgrade() -> None:
    # Triggers are dropped with their tables; just drop the function and types here.
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
    op.execute("DROP TYPE IF EXISTS candidate_status")
    op.execute("DROP TYPE IF EXISTS ingestion_run_status")
    op.execute("DROP TYPE IF EXISTS ingestion_source")
    op.execute("DROP TYPE IF EXISTS anuyoga_kind")
    op.execute("DROP TYPE IF EXISTS author_kind")
    op.execute("DROP EXTENSION IF EXISTS btree_gin")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
