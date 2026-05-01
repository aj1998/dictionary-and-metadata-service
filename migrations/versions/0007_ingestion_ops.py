"""Create parser_configs, ingestion_runs, and ingestion_review_queue tables."""

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE parser_configs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source       ingestion_source NOT NULL,
            config_path  TEXT NOT NULL,
            version      TEXT NOT NULL,
            checksum     TEXT NOT NULL,
            active       BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source, config_path, version)
        )
    """)

    op.execute("""
        CREATE TABLE ingestion_runs (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source            ingestion_source NOT NULL,
            parser_config_id  UUID REFERENCES parser_configs(id),
            triggered_by      TEXT NOT NULL,
            status            ingestion_run_status NOT NULL DEFAULT 'pending',
            started_at        TIMESTAMPTZ,
            finished_at       TIMESTAMPTZ,
            iterator_state    JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_html_dir      TEXT,
            stats             JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_log         TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_ingestion_runs_source_status ON ingestion_runs(source, status)")
    op.execute("""
        CREATE TRIGGER trg_ingestion_runs_updated_at
        BEFORE UPDATE ON ingestion_runs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE ingestion_review_queue (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ingestion_run_id      UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
            entity_type           TEXT NOT NULL,
            entity_natural_key    TEXT NOT NULL,
            proposed_payload      JSONB NOT NULL,
            diff_against_existing JSONB,
            status                candidate_status NOT NULL DEFAULT 'pending',
            reviewed_by           TEXT,
            reviewed_at           TIMESTAMPTZ,
            reject_reason         TEXT,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_review_queue_status ON ingestion_review_queue(status)")
    op.execute("CREATE INDEX idx_review_queue_run ON ingestion_review_queue(ingestion_run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_review_queue")
    op.execute("DROP TABLE IF EXISTS ingestion_runs")
    op.execute("DROP TABLE IF EXISTS parser_configs")
