"""Add sources TEXT[] to ten core tables for per-source attribution."""

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Add sources column with NOT NULL DEFAULT '{}' to all ten tables
    for table in (
        "authors",
        "shastras",
        "teekas",
        "gathas",
        "kalashas",
        "publications",
        "teeka_chapters",
        "books",
        "pravachans",
        "keywords",
    ):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN sources TEXT[] NOT NULL DEFAULT '{{}}'::text[]"
        )

    # GIN indexes for efficient ANY(sources) queries
    op.execute("CREATE INDEX idx_authors_sources        ON authors        USING gin (sources)")
    op.execute("CREATE INDEX idx_shastras_sources       ON shastras       USING gin (sources)")
    op.execute("CREATE INDEX idx_teekas_sources         ON teekas         USING gin (sources)")
    op.execute("CREATE INDEX idx_gathas_sources         ON gathas         USING gin (sources)")
    op.execute("CREATE INDEX idx_kalashas_sources       ON kalashas       USING gin (sources)")
    op.execute("CREATE INDEX idx_publications_sources   ON publications   USING gin (sources)")
    op.execute("CREATE INDEX idx_teeka_chapters_sources ON teeka_chapters USING gin (sources)")
    op.execute("CREATE INDEX idx_books_sources          ON books          USING gin (sources)")
    op.execute("CREATE INDEX idx_pravachans_sources     ON pravachans     USING gin (sources)")
    op.execute("CREATE INDEX idx_keywords_sources       ON keywords       USING gin (sources)")

    # Best-effort backfill: stamp rows that obviously belong to one ingestor

    # jainkosh-only: keywords always come from jainkosh
    op.execute("UPDATE keywords SET sources = ARRAY['jainkosh']")

    # nj-only: gathas, kalashas, teeka_chapters, publications are nj-exclusive
    op.execute("UPDATE gathas         SET sources = ARRAY['nj']")
    op.execute("UPDATE kalashas       SET sources = ARRAY['nj']")
    op.execute("UPDATE teeka_chapters SET sources = ARRAY['nj']")
    op.execute("UPDATE publications   SET sources = ARRAY['nj']")

    # Co-owned: shastras / teekas / authors — stamp with all ingestion sources present.
    # COALESCE protects against array_agg returning NULL when ingestion_runs is empty.
    op.execute("""
        UPDATE shastras SET sources = COALESCE(
            (SELECT array_agg(DISTINCT source::text)
             FROM ingestion_runs WHERE source IN ('jainkosh', 'nj')),
            '{}'::text[]
        )
    """)
    op.execute("""
        UPDATE teekas SET sources = COALESCE(
            (SELECT array_agg(DISTINCT source::text)
             FROM ingestion_runs WHERE source IN ('jainkosh', 'nj')),
            '{}'::text[]
        )
    """)
    op.execute("""
        UPDATE authors SET sources = COALESCE(
            (SELECT array_agg(DISTINCT source::text)
             FROM ingestion_runs WHERE source IN ('jainkosh', 'nj')),
            '{}'::text[]
        )
    """)
    # books and pravachans are left with '{}' (no production rows yet)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_authors_sources")
    op.execute("DROP INDEX IF EXISTS idx_shastras_sources")
    op.execute("DROP INDEX IF EXISTS idx_teekas_sources")
    op.execute("DROP INDEX IF EXISTS idx_gathas_sources")
    op.execute("DROP INDEX IF EXISTS idx_kalashas_sources")
    op.execute("DROP INDEX IF EXISTS idx_publications_sources")
    op.execute("DROP INDEX IF EXISTS idx_teeka_chapters_sources")
    op.execute("DROP INDEX IF EXISTS idx_books_sources")
    op.execute("DROP INDEX IF EXISTS idx_pravachans_sources")
    op.execute("DROP INDEX IF EXISTS idx_keywords_sources")

    for table in (
        "authors",
        "shastras",
        "teekas",
        "gathas",
        "kalashas",
        "publications",
        "teeka_chapters",
        "books",
        "pravachans",
        "keywords",
    ):
        op.execute(f"ALTER TABLE {table} DROP COLUMN sources")
