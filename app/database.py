"""Database connection for the scheduled pipelines.

Deliberately NOT a copy of the app's database module. The app owns the
schema: its `init_db()` runs `create_all` plus a block of
`ALTER TABLE … ADD COLUMN IF NOT EXISTS` statements on every boot. If
this repo ran the same thing against a model set that had drifted
behind the app's, it could create tables or columns that don't match
what production actually expects.

So `init_db()` here only proves the connection works. Every DDL
decision stays in the main repo, and these jobs are pure readers and
row-writers.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # Scheduled jobs run for minutes at a time against a connection
    # that may have gone stale between batches; recycling below the
    # typical idle timeout avoids "server closed the connection".
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Verify connectivity. Intentionally performs no DDL.

    Scripts call this at startup out of habit inherited from the main
    repo; keeping the name means they need no edits, while the body
    stays a no-op beyond a round-trip that fails loudly if
    DATABASE_URL is wrong.
    """
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
