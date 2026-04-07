"""Database engine and session factory.

Connection params loaded from .env via python-dotenv:
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

_engine = None
_session_factory = None


def build_database_url(driver: str = "asyncpg") -> str:
    """Build database URL from individual DB_* env vars.

    Args:
        driver: 'asyncpg' for async (default), 'psycopg2' or '' for sync.
    """
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "azurecn_calc")
    user = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASSWORD", "")

    if not user:
        raise RuntimeError("DB_USER environment variable is not set")

    scheme = f"postgresql+{driver}" if driver else "postgresql"
    return f"{scheme}://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(build_database_url("asyncpg"), echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def get_session() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
