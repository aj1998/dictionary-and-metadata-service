import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "packages", "jain_kb_common"),
)

from jain_kb_common.db.postgres.base import Base  # noqa: E402

import jain_kb_common.db.postgres.authors  # noqa: E402, F401
import jain_kb_common.db.postgres.shastras  # noqa: E402, F401
import jain_kb_common.db.postgres.anuyogas  # noqa: E402, F401
import jain_kb_common.db.postgres.teekas  # noqa: E402, F401
import jain_kb_common.db.postgres.books  # noqa: E402, F401
import jain_kb_common.db.postgres.pravachans  # noqa: E402, F401
import jain_kb_common.db.postgres.keywords  # noqa: E402, F401
import jain_kb_common.db.postgres.gathas  # noqa: E402, F401
import jain_kb_common.db.postgres.topics  # noqa: E402, F401
import jain_kb_common.db.postgres.ingestion  # noqa: E402, F401
import jain_kb_common.db.postgres.enrichment  # noqa: E402, F401
import jain_kb_common.db.postgres.query_logs  # noqa: E402, F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    config.get_main_option("sqlalchemy.url") or "",
)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(DATABASE_URL, echo=False)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
