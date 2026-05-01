"""Create authors, shastras, anuyogas, shastra_anuyogas tables."""

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE authors (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key  TEXT NOT NULL UNIQUE,
            display_name JSONB NOT NULL,
            kind         author_kind NOT NULL,
            bio          JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_authors_updated_at
        BEFORE UPDATE ON authors
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE anuyogas (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind         anuyoga_kind NOT NULL UNIQUE,
            display_name JSONB NOT NULL,
            description  JSONB
        )
    """)

    op.execute("""
        CREATE TABLE shastras (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key  TEXT NOT NULL UNIQUE,
            title        JSONB NOT NULL,
            author_id    UUID NOT NULL REFERENCES authors(id) ON DELETE RESTRICT,
            source_url   TEXT,
            description  JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_shastras_author ON shastras(author_id)")
    op.execute("""
        CREATE TRIGGER trg_shastras_updated_at
        BEFORE UPDATE ON shastras
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE shastra_anuyogas (
            shastra_id  UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
            anuyoga_id  UUID NOT NULL REFERENCES anuyogas(id) ON DELETE RESTRICT,
            PRIMARY KEY (shastra_id, anuyoga_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shastra_anuyogas")
    op.execute("DROP TABLE IF EXISTS shastras")
    op.execute("DROP TABLE IF EXISTS anuyogas")
    op.execute("DROP TABLE IF EXISTS authors")
