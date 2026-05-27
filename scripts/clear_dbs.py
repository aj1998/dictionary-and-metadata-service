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


_POSTGRES_EXTENSION_STMTS = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
)

# All Mongo collections written by any ingestor (jainkosh + nj)
_MONGO_COLLECTIONS = (
    # jainkosh
    "keyword_definitions",
    "topic_extracts",
    "raw_html_snapshots",
    # nj
    "gatha_hindi_chhand",
    "gatha_prakrit",
    "gatha_sanskrit",
    "gatha_teeka_bhaavarth_hindi",
    "gatha_teeka_sanskrit",
    "kalash_hindi",
    "kalash_sanskrit",
    "kalash_word_meanings",
    "teeka_gatha_mapping",
)


def _load_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        print(f"Missing environment variable: {key}", file=sys.stderr)
        sys.exit(2)
    return val


async def _clear(*, neo4j_database: str) -> None:
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
        print("clearing postgres...")
        async with engine.begin() as conn:
            for stmt in _POSTGRES_EXTENSION_STMTS:
                await conn.execute(text(stmt))
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
        print(f"  truncated {len(Base.metadata.sorted_tables)} postgres tables")

        print("clearing mongo...")
        for coll in _MONGO_COLLECTIONS:
            result = await mongo_db[coll].drop()
            print(f"  dropped collection: {coll}")

        print("clearing neo4j...")
        async with neo4j_driver.session(database=neo4j_database) as session:
            result = await session.run("MATCH (n) DETACH DELETE n RETURN count(n) AS deleted")
            record = await result.single()
            deleted = record["deleted"] if record else 0
            print(f"  deleted {deleted} neo4j nodes")

        print("done")
    finally:
        await close_driver()
        await engine.dispose()
        mongo_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clear all ingestion databases (Postgres, Mongo, Neo4j)"
    )
    parser.add_argument("--neo4j-database", default="neo4j")
    args = parser.parse_args(argv)

    asyncio.run(_clear(neo4j_database=args.neo4j_database))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
