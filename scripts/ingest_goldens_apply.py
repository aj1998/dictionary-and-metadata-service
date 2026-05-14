"""Apply JainKosh golden envelopes to the configured databases."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "jain_kb_common"))
sys.path.insert(0, str(REPO_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jain_kb_common.db.neo4j import close_driver, get_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints
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

from workers.ingestion.jainkosh.apply import apply_approved_keyword_payload
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "workers" / "ingestion" / "jainkosh" / "tests" / "fixtures"
_POSTGRES_EXTENSION_STMTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
)


@dataclass(frozen=True)
class GoldenSpec:
    keyword: str
    url: str


GOLDENS: tuple[GoldenSpec, ...] = (
    GoldenSpec("आत्मा", "https://jainkosh.org/wiki/आत्मा"),
    GoldenSpec("द्रव्य", "https://jainkosh.org/wiki/द्रव्य"),
    GoldenSpec("पर्याय", "https://jainkosh.org/wiki/पर्याय"),
    GoldenSpec("वस्तु", "https://jainkosh.org/wiki/वस्तु"),
)


def _load_envelope(spec: GoldenSpec) -> dict:
    config = load_config()
    html = (FIXTURE_DIR / f"{spec.keyword}.html").read_text(encoding="utf-8")
    result = parse_keyword_html(html, spec.url, config)
    return build_envelope(result).model_dump()


def _selected_goldens(keyword: str | None) -> tuple[GoldenSpec, ...]:
    if keyword is None:
        return GOLDENS
    return tuple(spec for spec in GOLDENS if spec.keyword == keyword)


async def _ensure_postgres_extensions(conn) -> None:
    for stmt in _POSTGRES_EXTENSION_STMTS:
        await conn.execute(text(stmt))


async def _run_apply(selected: tuple[GoldenSpec, ...], *, neo4j_database: str, ingestion_run_id: uuid.UUID | None) -> None:
    database_url = os.environ["DATABASE_URL"]
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    mongo_db_name = os.environ.get("MONGO_DB", "jain_kb_manual")
    neo4j_url = os.environ["NEO4J_URL"]
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ["NEO4J_PASSWORD"]

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[mongo_db_name]
    neo4j_driver = get_driver(url=neo4j_url, user=neo4j_user, password=neo4j_password)

    try:
        async with engine.begin() as conn:
            await _ensure_postgres_extensions(conn)
            await conn.run_sync(Base.metadata.create_all)
        await ensure_constraints(neo4j_driver, database=neo4j_database)
        async with session_factory() as pg_session:
            for spec in selected:
                envelope = _load_envelope(spec)
                await apply_approved_keyword_payload(
                    envelope=envelope,
                    pg_session=pg_session,
                    mongo_db=mongo_db,
                    neo4j_driver=neo4j_driver,
                    ingestion_run_id=ingestion_run_id,
                    neo4j_database=neo4j_database,
                )
                print(f"applied {spec.keyword}")
    finally:
        await close_driver()
        await engine.dispose()
        mongo_client.close()


async def _clear_existing_data(*, database_url: str, mongo_url: str, mongo_db_name: str, neo4j_url: str, neo4j_user: str, neo4j_password: str, neo4j_database: str) -> None:
    engine = create_async_engine(database_url, echo=False)
    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[mongo_db_name]
    neo4j_driver = get_driver(url=neo4j_url, user=neo4j_user, password=neo4j_password)

    try:
        async with engine.begin() as conn:
            await _ensure_postgres_extensions(conn)
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))

        for coll in ("keyword_definitions", "topic_extracts", "raw_html_snapshots"):
            await mongo_db[coll].drop()

        async with neo4j_driver.session(database=neo4j_database) as session:
            await session.run("MATCH (n) DETACH DELETE n")
    finally:
        await close_driver()
        await engine.dispose()
        mongo_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply JainKosh golden envelopes to databases")
    parser.add_argument("--keyword", choices=[spec.keyword for spec in GOLDENS], default=None)
    parser.add_argument("--neo4j-database", default="neo4j")
    parser.add_argument("--ingestion-run-id", default=None, help="Optional UUID to stamp on Mongo documents")
    parser.add_argument("--dry-run", action="store_true", help="Load and summarize goldens without touching databases")
    parser.add_argument("--clear-first", action="store_true", help="Clear Postgres, Mongo, and Neo4j before applying")
    args = parser.parse_args(argv)

    selected = _selected_goldens(args.keyword)
    if not selected:
        print("No matching goldens found.", file=sys.stderr)
        return 2

    if args.dry_run:
        for spec in selected:
            envelope = _load_envelope(spec)
            ww = envelope["would_write"]
            print(
                f"{spec.keyword}: "
                f"{len(ww['postgres'].get('topics', []))} topics, "
                f"{len(ww['postgres'].get('keyword_aliases', []))} aliases, "
                f"{len(ww['mongo'].get('topic_extracts', []))} topic extracts"
            )
        print(f"would apply {len(selected)} golden(s)")
        return 0

    try:
        if args.clear_first:
            try:
                database_url = os.environ["DATABASE_URL"]
                mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
                mongo_db_name = os.environ.get("MONGO_DB", "jain_kb_manual")
                neo4j_url = os.environ["NEO4J_URL"]
                neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
                neo4j_password = os.environ["NEO4J_PASSWORD"]
            except KeyError as exc:
                print(f"Missing environment variable: {exc.args[0]}", file=sys.stderr)
                return 2

            asyncio.run(
                _clear_existing_data(
                    database_url=database_url,
                    mongo_url=mongo_url,
                    mongo_db_name=mongo_db_name,
                    neo4j_url=neo4j_url,
                    neo4j_user=neo4j_user,
                    neo4j_password=neo4j_password,
                    neo4j_database=args.neo4j_database,
                )
            )
            print("cleared existing data")

        ingestion_run_id = uuid.UUID(args.ingestion_run_id) if args.ingestion_run_id else None
    except ValueError as exc:
        print(f"Invalid --ingestion-run-id: {exc}", file=sys.stderr)
        return 2

    try:
        asyncio.run(_run_apply(selected, neo4j_database=args.neo4j_database, ingestion_run_id=ingestion_run_id))
    except KeyError as exc:
        print(f"Missing environment variable: {exc.args[0]}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
