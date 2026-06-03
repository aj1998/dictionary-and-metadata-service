"""CLI for the extract-matching pipeline.

Usage:
    python scripts/match_extracts.py --mode all
    python scripts/match_extracts.py --mode jainkosh-keyword --nk आत्मा
    python scripts/match_extracts.py --mode jainkosh-topic --nk आत्मा:बहिरात्मादि-3-भेद
    python scripts/match_extracts.py --mode nj-shastra --nk samaysar
    python scripts/match_extracts.py --mode all --dry-run
    python scripts/match_extracts.py --mode all --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "jain_kb_common"))
sys.path.insert(0, str(REPO_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from jain_kb_common.db.mongo.indexes import ensure_indexes
from jain_kb_common.db.neo4j import close_driver, get_driver
from workers.matching.orchestrator import (
    Stats,
    match_all,
    match_for_jainkosh_keyword,
    match_for_jainkosh_topic,
    match_for_nj_shastra,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jain_kb.match_extracts")


def _load_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        print(f"Missing environment variable: {key}", file=sys.stderr)
        sys.exit(2)
    return val


async def _run(args: argparse.Namespace) -> int:
    mongo_url = _load_env("MONGO_URL", "mongodb://localhost:27017")
    mongo_db_name = _load_env("MONGO_DB_NAME", "jain_kb")
    neo4j_url = _load_env("NEO4J_URL")
    neo4j_user = _load_env("NEO4J_USER", "neo4j")
    neo4j_password = _load_env("NEO4J_PASSWORD")
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    run_id = uuid4()
    logger.info("starting match run_id=%s mode=%s", run_id, args.mode)

    client = AsyncIOMotorClient(mongo_url)
    mongo = client[mongo_db_name]
    neo4j = get_driver(url=neo4j_url, user=neo4j_user, password=neo4j_password)

    try:
        await ensure_indexes(mongo)

        kwargs: dict = {
            "mongo": mongo,
            "neo4j": neo4j,
            "run_id": run_id,
            "dry_run": args.dry_run,
            "database": neo4j_database,
        }

        if args.mode == "all":
            if args.limit:
                kwargs["limit"] = args.limit
            stats: Stats = await match_all(**kwargs)

        elif args.mode == "jainkosh-keyword":
            if not args.nk:
                print("--nk required for jainkosh-keyword mode", file=sys.stderr)
                return 2
            stats = await match_for_jainkosh_keyword(keyword_nk=args.nk, **kwargs)

        elif args.mode == "jainkosh-topic":
            if not args.nk:
                print("--nk required for jainkosh-topic mode", file=sys.stderr)
                return 2
            stats = await match_for_jainkosh_topic(topic_nk=args.nk, **kwargs)

        elif args.mode == "nj-shastra":
            if not args.nk:
                print("--nk required for nj-shastra mode", file=sys.stderr)
                return 2
            stats = await match_for_nj_shastra(shastra_nk=args.nk, **kwargs)

        else:
            print(f"Unknown mode: {args.mode}", file=sys.stderr)
            return 2

    finally:
        await close_driver()
        client.close()

    print(json.dumps({
        "run_id": str(run_id),
        "mode": args.mode,
        "dry_run": args.dry_run,
        "blocks_processed": stats.blocks_processed,
        "edges_attempted": stats.edges_attempted,
        "matched": stats.matched,
        "unmatched": stats.unmatched,
        "target_missing": stats.target_missing,
        "elapsed_seconds": round(stats.elapsed_seconds, 2),
    }, ensure_ascii=False, indent=2))

    # Exit code: 1 if target_missing or unmatched >= 50% of edges attempted
    if stats.target_missing > 0:
        logger.warning("non-zero target_missing count: %d", stats.target_missing)
        return 1
    if stats.edges_attempted > 0:
        unmatched_pct = stats.unmatched / stats.edges_attempted
        if unmatched_pct >= 0.5:
            logger.warning("unmatched pct %.1f%% exceeds 50%% threshold", unmatched_pct * 100)
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run extract matching pipeline")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["all", "jainkosh-keyword", "jainkosh-topic", "nj-shastra"],
        help="Matching scope",
    )
    parser.add_argument("--nk", default=None, help="Natural key for targeted modes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Locate and score but skip Mongo writes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max blocks to process (smoke-test helper)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
