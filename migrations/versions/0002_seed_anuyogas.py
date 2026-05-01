"""Seed the four anuyoga rows with multilingual labels."""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

from alembic import op

_ANUYOGA_SEEDS = [
    (
        "prathmanuyoga",
        '[{"lang": "hi", "script": "devanagari", "text": "प्रथमानुयोग"}, '
        '{"lang": "en", "script": "latin", "text": "Prathmanuyoga"}]',
    ),
    (
        "karananuyoga",
        '[{"lang": "hi", "script": "devanagari", "text": "करणानुयोग"}, '
        '{"lang": "en", "script": "latin", "text": "Karananuyoga"}]',
    ),
    (
        "charananuyoga",
        '[{"lang": "hi", "script": "devanagari", "text": "चरणानुयोग"}, '
        '{"lang": "en", "script": "latin", "text": "Charananuyoga"}]',
    ),
    (
        "dravyanuyoga",
        '[{"lang": "hi", "script": "devanagari", "text": "द्रव्यानुयोग"}, '
        '{"lang": "en", "script": "latin", "text": "Dravyanuyoga"}]',
    ),
]


def upgrade() -> None:
    for kind, display_name_json in _ANUYOGA_SEEDS:
        op.execute(
            f"INSERT INTO anuyogas (kind, display_name) "
            f"VALUES ('{kind}'::anuyoga_kind, '{display_name_json}'::jsonb) "
            f"ON CONFLICT (kind) DO NOTHING"
        )


def downgrade() -> None:
    for kind, _ in _ANUYOGA_SEEDS:
        op.execute(f"DELETE FROM anuyogas WHERE kind = '{kind}'::anuyoga_kind")
