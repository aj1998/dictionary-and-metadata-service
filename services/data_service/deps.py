from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

_engine = None
_session_factory: async_sessionmaker | None = None
_mongo_client: AsyncIOMotorClient | None = None


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


security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    ok = secrets.compare_digest(credentials.username, settings.ADMIN_USER) and \
         secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    if not ok:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
