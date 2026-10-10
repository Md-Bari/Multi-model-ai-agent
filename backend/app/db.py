"""Database engine and session. Accepts the URL formats hosted providers hand out
(postgres://, postgresql://, ?sslmode=require as used by Neon) and adapts them for asyncpg."""

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def engine_args(raw_url: str) -> tuple[str, dict]:
    url = make_url(raw_url)
    if url.drivername in ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        url = url.set(drivername="postgresql+asyncpg")

    kwargs: dict = {"pool_pre_ping": True}
    if url.drivername == "postgresql+asyncpg":
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)  # libpq-only option asyncpg doesn't know
        connect_args: dict = {}
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = sslmode
        if "pooler" in (url.host or ""):
            # PgBouncer in transaction mode can't keep prepared statements.
            connect_args["statement_cache_size"] = 0
        url = url.set(query=query)
        kwargs |= {"connect_args": connect_args, "pool_size": 5, "max_overflow": 5, "pool_recycle": 300}
    return url.render_as_string(hide_password=False), kwargs


_url, _kwargs = engine_args(settings.database_url)
engine = create_async_engine(_url, **_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


DB = AsyncSession
