"""Clear all databases (Postgres, Mongo, Neo4j) used by the ingestion pipeline."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "jain_kb_common"))
sys.path.insert(0, str(REPO_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from jain_kb_common.db.neo4j import close_driver, get_driver
from jain_kb_common.db.neo4j.clear import clear_source as neo4j_clear_source
from jain_kb_common.db.postgres.base import Base
import jain_kb_common.db.postgres.authors  # noqa: F401
import jain_kb_common.db.postgres.shastras  # noqa: F401
import jain_kb_common.db.postgres.anuyogas  # noqa: F401
import jain_kb_common.db.postgres.teekas  # noqa: F401
import jain_kb_common.db.postgres.books  # noqa: F401
import jain_kb_common.db.postgres.pravachans  # noqa: F401
import jain_kb_common.db.postgres.keywords  # noqa: F401
import jain_kb_common.db.postgres.gathas  # noqa: F401
import jain_kb_common.db.postgres.topics  # noqa: F401
import jain_kb_common.db.postgres.publications  # noqa: F401
import jain_kb_common.db.postgres.kalashas  # noqa: F401
import jain_kb_common.db.postgres.ingestion  # noqa: F401
import jain_kb_common.db.postgres.enrichment  # noqa: F401
import jain_kb_common.db.postgres.query_logs  # noqa: F401
import jain_kb_common.db.postgres.teeka_chapters  # noqa: F401
import jain_kb_common.db.postgres.tables  # noqa: F401


_POSTGRES_EXTENSION_STMTS = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
)

# Mongo collections split by which ingestor writes them
_JK_MONGO = (
    "keyword_definitions",
    "topic_extracts",
    "raw_html_snapshots",
    "ocr_pages",
    "tables",
)
_NJ_MONGO = (
    "gatha_hindi_chhand",
    "gatha_prakrit",
    "gatha_sanskrit",
    "gatha_teeka_hindi",
    "gatha_word_meanings",
    "gatha_teeka_bhaavarth_hindi",
    "gatha_teeka_bhaavarth_shortfont",
    "gatha_teeka_sanskrit",
    "kalash_bhaavarth_hindi",
    "kalash_bhaavarth_shortfont",
    "kalash_hindi",
    "kalash_sanskrit",
    "kalash_word_meanings",
    "teeka_gatha_mapping",
)
_SHARED_MONGO = ("extract_matches",)

# All collections combined (for --source all)
_MONGO_COLLECTIONS = _JK_MONGO + _NJ_MONGO + _SHARED_MONGO


def _load_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        print(f"Missing environment variable: {key}", file=sys.stderr)
        sys.exit(2)
    return val


async def _clear_mongo_collections(mongo_db, collections: tuple[str, ...]) -> None:
    for coll in collections:
        await mongo_db[coll].drop()
        print(f"  dropped collection: {coll}")


async def _clear_postgres_by_source(conn, src: str) -> None:
    """Delete/shrink Postgres rows belonging to *src* in FK-safe order."""
    # keyword_aliases cascade from keywords — delete by source column
    await conn.execute(text(
        "DELETE FROM keyword_aliases WHERE source = :src"
    ), {"src": src})
    print("  deleted keyword_aliases")

    # topic_candidates are jainkosh-adjacent enrichment only
    if src == "jainkosh":
        await conn.execute(text("DELETE FROM topic_candidates"))
        print("  deleted topic_candidates")

    # ingestion_review_queue: children of ingestion_runs
    await conn.execute(text(
        "DELETE FROM ingestion_review_queue WHERE ingestion_run_id IN "
        "(SELECT id FROM ingestion_runs WHERE source = :src)"
    ), {"src": src})
    print("  deleted ingestion_review_queue rows")

    # tables has single source column
    await conn.execute(text("DELETE FROM tables WHERE source = :src"), {"src": src})
    print("  deleted tables")

    # topics has single source column
    await conn.execute(text("DELETE FROM topics WHERE source = :src"), {"src": src})
    print("  deleted topics")

    # Shared tables: delete exclusively-owned rows, shrink co-owned arrays
    _shared_tables = (
        "gathas",
        "kalashas",
        "teeka_chapters",
        "publications",
        "teekas",
        "keywords",
        "shastras",
        "authors",
        "books",
        "pravachans",
    )
    for tbl in _shared_tables:
        await conn.execute(text(
            f"DELETE FROM {tbl} WHERE :src = ANY(sources) AND sources <@ ARRAY[:src]::text[]"
        ), {"src": src})
        await conn.execute(text(
            f"UPDATE {tbl} SET sources = array_remove(sources, :src) "
            f"WHERE :src = ANY(sources) AND cardinality(sources) > 1"
        ), {"src": src})
        print(f"  cleared {tbl}")

    # ingestion_runs / parser_configs: own source column
    await conn.execute(text("DELETE FROM ingestion_runs WHERE source = :src"), {"src": src})
    print("  deleted ingestion_runs")
    await conn.execute(text("DELETE FROM parser_configs WHERE source = :src"), {"src": src})
    print("  deleted parser_configs")


async def _clear(*, source: str, neo4j_database: str) -> None:
    database_url = _load_env("DATABASE_URL")
    mongo_url = _load_env("MONGO_URL", "mongodb://localhost:27017")
    mongo_db_name = _load_env("MONGO_DB_NAME", "jain_kb")
    neo4j_url = _load_env("NEO4J_URL")
    neo4j_user = _load_env("NEO4J_USER", "neo4j")
    neo4j_password = _load_env("NEO4J_PASSWORD")

    engine = create_async_engine(database_url, echo=False)
    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[mongo_db_name]
    neo4j_driver = get_driver(url=neo4j_url, user=neo4j_user, password=neo4j_password)

    try:
        # ── Postgres ──────────────────────────────────────────────────────────
        print("clearing postgres...")
        if source == "all":
            async with engine.begin() as conn:
                for stmt in _POSTGRES_EXTENSION_STMTS:
                    await conn.execute(text(stmt))
                await conn.run_sync(Base.metadata.create_all)
            async with engine.begin() as conn:
                for table in reversed(Base.metadata.sorted_tables):
                    await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
            print(f"  truncated {len(Base.metadata.sorted_tables)} postgres tables")
        else:
            async with engine.begin() as conn:
                await _clear_postgres_by_source(conn, source)
            print(f"  finished per-source postgres clear for '{source}'")

        # ── Mongo ─────────────────────────────────────────────────────────────
        print("clearing mongo...")
        if source == "all":
            collections = _MONGO_COLLECTIONS
        elif source == "jainkosh":
            collections = _JK_MONGO + _SHARED_MONGO
        else:  # nj
            collections = _NJ_MONGO + _SHARED_MONGO
        await _clear_mongo_collections(mongo_db, collections)

        # ── Neo4j ─────────────────────────────────────────────────────────────
        print("clearing neo4j...")
        if source == "all":
            async with neo4j_driver.session(database=neo4j_database) as session:
                result = await session.run(
                    "MATCH (n) DETACH DELETE n RETURN count(n) AS deleted"
                )
                record = await result.single()
                deleted = record["deleted"] if record else 0
                print(f"  deleted {deleted} neo4j nodes")
        else:
            counts = await neo4j_clear_source(
                neo4j_driver, source=source, database=neo4j_database
            )
            print(
                f"  neo4j: deleted {counts['deleted']} exclusive, "
                f"shrunk {counts['updated']} co-owned nodes"
            )

        print("done")
    finally:
        await close_driver()
        await engine.dispose()
        mongo_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clear all ingestion databases (Postgres, Mongo, Neo4j)"
    )
    parser.add_argument(
        "--source",
        choices=["all", "jainkosh", "nj"],
        default="all",
        help="Which source's data to remove (default: all)",
    )
    parser.add_argument("--neo4j-database", default="neo4j")
    args = parser.parse_args(argv)

    asyncio.run(_clear(source=args.source, neo4j_database=args.neo4j_database))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
