"""Create teekas, books, book_anuyogas, pravachans tables."""

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE teekas (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key                 TEXT NOT NULL UNIQUE,
            shastra_id                  UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
            teekakar_id                 UUID REFERENCES authors(id),
            publisher                   JSONB,
            translator                  JSONB,
            editor                      JSONB,
            cataloguesearch_shastra_id  TEXT,
            public_url                  TEXT,
            publisher_url               TEXT,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_teekas_shastra ON teekas(shastra_id)")
    op.execute("CREATE INDEX idx_teekas_teekakar ON teekas(teekakar_id)")
    op.execute("""
        CREATE TRIGGER trg_teekas_updated_at
        BEFORE UPDATE ON teekas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE books (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key   TEXT NOT NULL UNIQUE,
            title         JSONB NOT NULL,
            shastra_id    UUID REFERENCES shastras(id) ON DELETE SET NULL,
            publisher     JSONB,
            translator    JSONB,
            editor        JSONB,
            public_url    TEXT,
            publisher_url TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_books_shastra ON books(shastra_id)")
    op.execute("""
        CREATE TRIGGER trg_books_updated_at
        BEFORE UPDATE ON books
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE book_anuyogas (
            book_id     UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            anuyoga_id  UUID NOT NULL REFERENCES anuyogas(id) ON DELETE RESTRICT,
            PRIMARY KEY (book_id, anuyoga_id)
        )
    """)

    op.execute("""
        CREATE TABLE pravachans (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            natural_key   TEXT NOT NULL UNIQUE,
            title         JSONB NOT NULL,
            shastra_id    UUID REFERENCES shastras(id) ON DELETE SET NULL,
            speaker_id    UUID REFERENCES authors(id),
            publisher     JSONB,
            translator    JSONB,
            editor        JSONB,
            public_url    TEXT,
            publisher_url TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_pravachans_updated_at
        BEFORE UPDATE ON pravachans
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pravachans")
    op.execute("DROP TABLE IF EXISTS book_anuyogas")
    op.execute("DROP TABLE IF EXISTS books")
    op.execute("DROP TABLE IF EXISTS teekas")
