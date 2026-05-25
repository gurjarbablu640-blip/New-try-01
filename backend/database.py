"""Database connection and session management.

Provides:
  - Async engine + session for FastAPI endpoints
  - Sync engine + session for Celery workers and services
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from config import settings

# ============================================================
# Async engine (FastAPI endpoints)
# ============================================================
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_db():
    """FastAPI dependency — yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ============================================================
# Sync engine (Celery workers, services)
# ============================================================
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def get_db():
    """Sync dependency — yields a database session (for Celery/services)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# Declarative Base (shared by all models)
# ============================================================
Base = declarative_base()
