"""RadAI — Async SQLAlchemy database session.

Engine and session factory are created lazily so that:
  - Tests can override DATABASE_URL before the engine is created.
  - Importing this module doesn't fail when asyncpg isn't installed
    (e.g., unit-test environments using SQLite+aiosqlite).
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    """Create the async engine lazily on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
        # SQLite doesn't support pool_size/max_overflow
        engine_kwargs: dict = {"echo": settings.environment == "development"}
        if not db_url.startswith("sqlite"):
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20
        _engine = create_async_engine(db_url, **engine_kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory, creating it lazily."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


def AsyncSessionLocal() -> AsyncSession:
    """Backward-compatible callable that returns a session context.

    Usage::
        async with AsyncSessionLocal() as session:
            ...
    """
    return get_session_factory()()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
