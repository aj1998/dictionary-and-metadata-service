import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: AsyncIOMotorClient | None = None


def get_mongo_client(url: str | None = None) -> AsyncIOMotorClient:
    global _client
    if _client is None:
        url = url or os.environ["MONGO_URL"]
        _client = AsyncIOMotorClient(url)
    return _client


def get_db(url: str | None = None, db_name: str = "jain_kb") -> AsyncIOMotorDatabase:
    return get_mongo_client(url)[db_name]
