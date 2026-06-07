import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

_engine: AsyncEngine | None = None
_session_factory = None


def get_settings():
    """
    Import application settings lazily.
    """
    from core.settings import get_settings

    settings = get_settings()

    return settings


def get_database_url() -> str:
    """
    Resolve database URL from settings or environment.
    """
    settings = get_settings()

    database_url = getattr(settings, "DATABASE_URL", None)

    if database_url:
        return database_url

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "postgres")

    return f"postgresql+asyncpg://" f"{user}:{password}@{host}:{port}/{database}"


def get_engine() -> AsyncEngine:
    """
    Singleton SQLAlchemy engine.
    """
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            echo=False,
            pool_pre_ping=True,
        )

    return _engine


def get_session_factory():
    """
    Singleton session factory.
    """
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


@asynccontextmanager
async def get_session():
    """
    Usage:

        async with get_session() as session:
            ...
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """
    Gracefully close database connections.
    """
    global _engine

    if _engine is not None:
        await _engine.dispose()
        _engine = None
