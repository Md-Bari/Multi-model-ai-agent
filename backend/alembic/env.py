import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app import models  # noqa: F401 - registers tables on Base.metadata
from app.config import settings
from app.db import Base, engine_args

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url, _ = engine_args(settings.database_url)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url, kwargs = engine_args(settings.database_url)
    kwargs.pop("pool_size", None)
    kwargs.pop("max_overflow", None)
    engine = create_async_engine(url, **kwargs)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
