import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _build_engine():  # type: ignore[no-untyped-def]
    return create_async_engine(os.environ["DATABASE_URL"], echo=False)


def _build_session_factory(engine):  # type: ignore[no-untyped-def]
    return async_sessionmaker(engine, expire_on_commit=False)


class _LazyEngine:
    """Proxy that creates the async engine on first attribute access."""

    _engine = None

    def _get(self):  # type: ignore[no-untyped-def]
        if self._engine is None:
            self._engine = _build_engine()
        return self._engine

    def __getattr__(self, name: str):  # type: ignore[override]
        return getattr(self._get(), name)


class _LazySessionFactory:
    """Proxy that creates the session factory on first call."""

    _factory = None

    def _get(self):  # type: ignore[no-untyped-def]
        if self._factory is None:
            self._factory = _build_session_factory(_build_engine())
        return self._factory

    def __call__(self, **kwargs):  # type: ignore[override]
        return self._get()(**kwargs)

    def __getattr__(self, name: str):  # type: ignore[override]
        return getattr(self._get(), name)


async_engine = _LazyEngine()
AsyncSessionLocal = _LazySessionFactory()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _LazySessionFactory()
    async with factory() as session:
        yield session
