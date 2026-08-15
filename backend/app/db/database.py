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


def _build_engine() -> AsyncEngine:
    # An asyncpg connection belongs to the event loop that opened it. Test code
    # runs helpers in short-lived loops, so pooling there produces
    # "Event loop is closed" rather than a real failure. Pooling is a
    # production concern; disable it under test.
    if settings.environment == "test":
        return create_async_engine(settings.database_url, echo=settings.db_echo, poolclass=NullPool)

    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
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
