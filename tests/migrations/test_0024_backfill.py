"""Test the backfill logic introduced in migration 0024.

Rather than running the full Alembic migration chain (which requires a
throw-away DB at revision 0023), this test simulates the backfill SQL against
the live test schema (post-0024) to verify the heuristic queries produce the
expected results.

To run:
    DATABASE_URL=postgresql+asyncpg://<user>@localhost/jain_kb_test \
        python -m pytest tests/migrations/test_0024_backfill.py -v
"""

import os
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "packages", "jain_kb_common"),
)

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))
skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="DATABASE_URL not set")


@skip_no_db
async def test_backfill_keywords_stamped_jainkosh(async_session: AsyncSession):
    """keywords rows should be stamped with ['jainkosh'] by the backfill SQL."""
    kw_id = str(uuid.uuid4())
    await async_session.execute(
        text(
            "INSERT INTO keywords (id, natural_key, display_text, definition_doc_ids, sources) "
            "VALUES (:id, :nk, :dt, '[]'::jsonb, '{}'::text[])"
        ),
        {"id": kw_id, "nk": f"backfill-kw-{kw_id}", "dt": "test"},
    )
    await async_session.commit()

    # Run the backfill SQL for keywords
    await async_session.execute(
        text("UPDATE keywords SET sources = ARRAY['jainkosh'] WHERE sources = '{}'::text[]")
    )
    await async_session.commit()

    row = await async_session.execute(
        text("SELECT sources FROM keywords WHERE id = :id"), {"id": kw_id}
    )
    result = row.scalar_one()
    assert result == ["jainkosh"]


@skip_no_db
async def test_backfill_gathas_stamped_nj(async_session: AsyncSession):
    """gathas rows should be stamped with ['nj'] by the backfill SQL."""
    # Insert a minimal author and shastra first (FK constraints)
    author_id = str(uuid.uuid4())
    shastra_id = str(uuid.uuid4())
    gatha_id = str(uuid.uuid4())
    nk_prefix = gatha_id[:8]

    await async_session.execute(
        text(
            "INSERT INTO authors (id, natural_key, display_name, kind, sources) "
            "VALUES (:id, :nk, '[]'::jsonb, 'acharya', '{}'::text[])"
        ),
        {"id": author_id, "nk": f"bf-author-{nk_prefix}"},
    )
    await async_session.execute(
        text(
            "INSERT INTO shastras (id, natural_key, title, author_id, sources) "
            "VALUES (:id, :nk, '[]'::jsonb, :aid, '{}'::text[])"
        ),
        {"id": shastra_id, "nk": f"bf-shastra-{nk_prefix}", "aid": author_id},
    )
    await async_session.execute(
        text(
            "INSERT INTO gathas (id, natural_key, shastra_id, gatha_number, "
            "hindi_chhand_doc_ids, teeka_mapping_doc_ids, keyword_ids, topic_ids, sources) "
            "VALUES (:id, :nk, :sid, '001', '[]'::jsonb, '[]'::jsonb, "
            "'[]'::jsonb, '[]'::jsonb, '{}'::text[])"
        ),
        {"id": gatha_id, "nk": f"bf-gatha-{nk_prefix}", "sid": shastra_id},
    )
    await async_session.commit()

    # Run the backfill SQL for gathas
    await async_session.execute(
        text("UPDATE gathas SET sources = ARRAY['nj'] WHERE sources = '{}'::text[]")
    )
    await async_session.commit()

    row = await async_session.execute(
        text("SELECT sources FROM gathas WHERE id = :id"), {"id": gatha_id}
    )
    result = row.scalar_one()
    assert result == ["nj"]


@skip_no_db
async def test_backfill_coowned_with_ingestion_runs(async_session: AsyncSession):
    """shastras/teekas/authors backfill uses ingestion_runs to stamp co-owned rows."""
    run_id = str(uuid.uuid4())
    # Seed an ingestion_run for jainkosh
    await async_session.execute(
        text(
            "INSERT INTO ingestion_runs (id, source, triggered_by, status, iterator_state, stats) "
            "VALUES (:id, 'jainkosh', 'test', 'success', '{}'::jsonb, '{}'::jsonb)"
        ),
        {"id": run_id},
    )
    await async_session.commit()

    author_id = str(uuid.uuid4())
    nk_prefix = author_id[:8]
    await async_session.execute(
        text(
            "INSERT INTO authors (id, natural_key, display_name, kind, sources) "
            "VALUES (:id, :nk, '[]'::jsonb, 'acharya', '{}'::text[])"
        ),
        {"id": author_id, "nk": f"bf2-author-{nk_prefix}"},
    )
    await async_session.commit()

    # Run the co-owned backfill SQL
    await async_session.execute(
        text("""
            UPDATE authors SET sources = COALESCE(
                (SELECT array_agg(DISTINCT source::text)
                 FROM ingestion_runs WHERE source IN ('jainkosh', 'nj')),
                '{}'::text[]
            ) WHERE sources = '{}'::text[]
        """)
    )
    await async_session.commit()

    row = await async_session.execute(
        text("SELECT sources FROM authors WHERE id = :id"), {"id": author_id}
    )
    result = row.scalar_one()
    assert "jainkosh" in result
