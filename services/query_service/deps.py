from __future__ import annotations

from collections.abc import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

_engine = None
_session_factory: async_sessionmaker | None = None
_mongo_client: AsyncIOMotorClient | None = None
_neo4j_driver = None


def _get_factory() -> async_sessionmaker:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(settings.DATABASE_URL, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_factory()
    async with factory() as session:
        yield session


def _get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
    return _mongo_client


async def get_mongo_db() -> AsyncIOMotorDatabase:  # type: ignore[return]
    client = _get_mongo_client()
    return client[settings.MONGO_DB_NAME]


def get_neo4j_driver() -> object:
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import AsyncGraphDatabase  # type: ignore[import]
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URL,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _neo4j_driver
