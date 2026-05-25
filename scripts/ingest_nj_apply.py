"""Apply NikkYJain shastra envelopes to Postgres + Mongo + Neo4j."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
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
import jain_kb_common.db.postgres.teekas  # noqa: F401
import jain_kb_common.db.postgres.publications  # noqa: F401
import jain_kb_common.db.postgres.gathas  # noqa: F401
import jain_kb_common.db.postgres.kalashas  # noqa: F401
import jain_kb_common.db.postgres.teeka_chapters  # noqa: F401
import jain_kb_common.db.postgres.keywords  # noqa: F401
import jain_kb_common.db.postgres.topics  # noqa: F401
import jain_kb_common.db.postgres.anuyogas  # noqa: F401
import jain_kb_common.db.postgres.books  # noqa: F401
import jain_kb_common.db.postgres.pravachans  # noqa: F401
import jain_kb_common.db.postgres.ingestion  # noqa: F401
import jain_kb_common.db.postgres.enrichment  # noqa: F401
import jain_kb_common.db.postgres.query_logs  # noqa: F401

from workers.ingestion.nj.apply import apply_nj_shastra_payload
from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.envelope import build_envelope
from workers.ingestion.nj.orchestrator import parse_shastra


_POSTGRES_EXTENSION_STMTS = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS btree_gin",
)


async def _ensure_postgres_extensions(conn) -> None:
    for stmt in _POSTGRES_EXTENSION_STMTS:
        await conn.execute(text(stmt))


def _load_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        print(f"Missing environment variable: {key}", file=sys.stderr)
        sys.exit(2)
    return val


def _print_summary(ww: dict, shastra_nk: str) -> None:
    gathas = ww["postgres"].get("gathas", [])
    kalashes = ww["postgres"].get("kalashas", [])
    primary_kalashes = [k for k in kalashes if "तात्पर्यवृत्ति" not in k["natural_key"]]
    secondary_kalashes = [k for k in kalashes if k not in primary_kalashes]
    chhand_docs = ww["mongo"].get("gatha_hindi_chhand", [])
    anyavartha_docs = ww["mongo"].get("teeka_gatha_mapping", [])
    san_docs = ww["mongo"].get("gatha_sanskrit", [])
    chapters = ww["postgres"].get("teeka_chapters", [])

    print(f"[{shastra_nk}] {len(gathas)} gathas, {len(secondary_kalashes)} secondary kalashes")
    print(f"primary kalashes total: {len(primary_kalashes)}")
    print(f"gathas with Sanskrit: {len(san_docs)}")
    print(f"gathas with Hindi chhand: {len(set(d['gatha_natural_key'] for d in chhand_docs))}")
    print(f"teeka_gatha_mapping docs: {len(anyavartha_docs)}")
    print(f"teeka chapters: {len(chapters)}")
    print(f"would apply {len(gathas)} gatha(s)")


async def _run(args: argparse.Namespace) -> None:
    config_path = args.config or os.environ.get("NJ_CONFIG")
    if not config_path:
        print("Missing --config or NJ_CONFIG env var", file=sys.stderr)
        sys.exit(2)
    cfg = load_config_for_shastra(Path(config_path).stem)
    shastra_nk = cfg.shastra.natural_key

    parse_result = parse_shastra(cfg)
    envelope = build_envelope(parse_result, cfg)
    ww = envelope["would_write"]

    if args.dry_run:
        _print_summary(ww, shastra_nk)
        return

    database_url = _load_env("DATABASE_URL")
    mongo_url = _load_env("MONGO_URL", "mongodb://localhost:27017")
    mongo_db_name = _load_env("MONGO_DB_NAME", "jain_kb")
    neo4j_url = _load_env("NEO4J_URL")
    neo4j_user = _load_env("NEO4J_USER", "neo4j")
    neo4j_password = _load_env("NEO4J_PASSWORD")

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db_obj = mongo_client[mongo_db_name]
    neo4j_driver = get_driver(url=neo4j_url, user=neo4j_user, password=neo4j_password)

    try:
        async with engine.begin() as conn:
            await _ensure_postgres_extensions(conn)
            await conn.run_sync(Base.metadata.create_all)
        await ensure_constraints(neo4j_driver, database=args.neo4j_database)

        ingestion_run_id = uuid.UUID(args.ingestion_run_id) if args.ingestion_run_id else None

        # Filter to single gatha if requested
        if args.gatha:
            from workers.ingestion.nj.envelope import _norm_num, build_envelope as _be
            target = _norm_num(args.gatha)
            parse_result_filtered = parse_result.model_copy(update={
                "gathas": [g for g in parse_result.gathas if _norm_num(g.gatha_number) == target],
                "secondary_kalashes": [],
            })
            envelope = _be(parse_result_filtered, cfg)

        async with session_factory() as pg_session:
            await apply_nj_shastra_payload(
                envelope=envelope,
                pg_session=pg_session,
                mongo_db=mongo_db_obj,
                neo4j_driver=neo4j_driver,
                ingestion_run_id=ingestion_run_id,
                neo4j_database=args.neo4j_database,
            )

        print(f"done: {shastra_nk}")
    finally:
        await close_driver()
        await engine.dispose()
        mongo_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply NikkYJain shastra to databases")
    parser.add_argument("--config", default=None, help="Path to parser_configs/nj/<shastra>.yaml (or set NJ_CONFIG env var)")
    parser.add_argument("--dry-run", action="store_true", help="Parse + summarize; no DB writes")
    parser.add_argument("--gatha", default=None, help="Apply only this gatha number (e.g. 001)")
    parser.add_argument("--neo4j-database", default="neo4j")
    parser.add_argument("--ingestion-run-id", default=None, help="Optional UUID for Mongo stamp")
    args = parser.parse_args(argv)

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
