"""create tables table for Table first-class entity

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-07
"""

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tables (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key            TEXT NOT NULL UNIQUE,
            source                 ingestion_source NOT NULL,
            parent_natural_key     TEXT NOT NULL,
            parent_kind            TEXT NOT NULL,
            seq                    INT  NOT NULL,
            caption                JSONB,
            source_url             TEXT,
            raw_html_doc_id        TEXT NOT NULL,
            graph_node_id          TEXT,
            ingestion_run_id       UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (parent_natural_key, seq)
        )
    """)
    op.execute("CREATE INDEX idx_tables_parent ON tables(parent_natural_key)")
    op.execute("CREATE INDEX idx_tables_source ON tables(source)")
    op.execute("CREATE INDEX idx_tables_run    ON tables(ingestion_run_id)")
    op.execute("""
        CREATE TRIGGER trg_tables_updated_at
        BEFORE UPDATE ON tables
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tables")
