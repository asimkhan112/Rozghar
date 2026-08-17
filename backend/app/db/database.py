"""Engine, session factory and the request-scoped session dependency.

The session is the unit of work. Repositories flush through it but never
commit; the service layer owns the transaction boundary, which is what lets a
single business operation span several repositories atomically.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _connect_args() -> dict:
    """asyncpg connection arguments derived from the configured URL.

    Two hosted-Postgres facts drive this:

    * **TLS is requested here, not in the URL.** asyncpg does not accept
      libpq's `sslmode`, so `_as_driver_url` strips it and the intent arrives
      as this flag instead.
    * **Prepared statements have to be off behind a transaction pooler.**
      Neon's pooled endpoint and Railway's PgBouncer both hand a different
      backend to each transaction, so a statement prepared on one is missing
      on the next — surfacing as an intermittent `prepared statement "__asyncpg_..."
      does not exist` under load rather than a clean failure at boot. Disabling
      the cache is the supported way to run asyncpg through a transaction
      pooler; it costs a re-parse per statement, which is far cheaper than the
      bug it prevents.
    """
    args: dict = {}
    if settings.database_requires_ssl:
        args["ssl"] = "require"
    if settings.database_pooled:
        args["statement_cache_size"] = 0
        args["prepared_statement_cache_size"] = 0
    return args


def _build_engine() -> AsyncEngine:
    # An asyncpg connection belongs to the event loop that opened it. Test code
    # runs helpers in short-lived loops, so pooling there produces
    # "Event loop is closed" rather than a real failure. Pooling is a
    # production concern; disable it under test.
    if settings.environment == "test":
        return create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            poolclass=NullPool,
            connect_args=_connect_args(),
        )

    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        connect_args=_connect_args(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        # Recycle below typical proxy and firewall idle timeouts so a pooled
        # connection is never handed out already dead.
        pool_recycle=1800,
        pool_pre_ping=True,
    )


engine: AsyncEngine = _build_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # attributes stay readable after commit
    autoflush=False,  # flushes are explicit, so query timing is predictable
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session per request.

    Commit is the caller's responsibility. Any exception rolls the transaction
    back before the connection returns to the pool.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close every pooled connection. Called from the application lifespan."""
    await engine.dispose()
