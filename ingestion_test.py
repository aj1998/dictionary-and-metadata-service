import asyncio, os
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.apply import apply_approved_keyword_payload

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from jain_kb_common.db.neo4j import get_driver, close_driver
from jain_kb_common.db.neo4j.constraints import ensure_constraints

async def main():
    # --- Parse ---
    config = load_config()
    html = open("workers/ingestion/jainkosh/tests/fixtures/आत्मा.html", encoding="utf-8").read()
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
    envelope = build_envelope(result).model_dump()
    print("Topics in envelope:", len(envelope["would_write"]["postgres"]["topics"]))

    # --- DB connections ---
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    mongo = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["jain_kb_manual"]
    driver = get_driver(os.environ["NEO4J_URL"], os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    await ensure_constraints(driver, database="neo4j")

    # --- Apply (twice to verify idempotency) ---
    async with Session() as session:
        await apply_approved_keyword_payload(
            envelope=envelope, pg_session=session,
            mongo_db=mongo, neo4j_driver=driver, neo4j_database="neo4j",
        )
        print("First apply done.")
        await apply_approved_keyword_payload(
            envelope=envelope, pg_session=session,
            mongo_db=mongo, neo4j_driver=driver, neo4j_database="neo4j",
        )
        print("Second apply done — no errors means idempotent.")

    await close_driver()
    await engine.dispose()
    mongo.client.close()

asyncio.run(main())