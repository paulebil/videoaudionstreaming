from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.settings import get_settings
from .models import Base

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_database_url() -> str:
    """Return DATABASE_URL configured for async SQLAlchemy usage."""
    database_url = get_settings().DATABASE_URL

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure it in your environment before starting the app."
        )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


def get_async_engine() -> AsyncEngine:
    """Create (once) and return the async SQLAlchemy engine."""
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            echo=False,
            pool_pre_ping=True,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create (once) and return the async session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields one async DB session per request."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        yield session


async def init_db() -> None:
    """Create database tables for imported models."""
    async with get_async_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
