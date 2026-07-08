"""HealthBridge Platform — Database Engine & Session Management"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi import Request

from app.config import settings, DATA_DIR


# ── Database URLs ──
SQLITE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'healthbridge.db'}"
ASYNC_DB_URL = settings.DATABASE_URL if settings.DATABASE_URL.startswith("postgresql") else SQLITE_URL
SYNC_DB_URL = settings.DATABASE_SYNC_URL or ASYNC_DB_URL.replace("+aiosqlite", "").replace("+asyncpg", "")

# ── Engines (module-level, created once on import) ──
is_postgres = "postgresql" in ASYNC_DB_URL

async_engine_kw = {"echo": settings.DEBUG, "pool_pre_ping": True}
if is_postgres:
    async_engine_kw["pool_size"] = 10
    async_engine_kw["max_overflow"] = 20
async_engine = create_async_engine(ASYNC_DB_URL, **async_engine_kw)

sync_engine = create_engine(
    SYNC_DB_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# ── Session Factories ──
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)


# ── Base Model ──
class Base(DeclarativeBase):
    pass


# ── Dependency ──
async def get_db(request: Request) -> AsyncSession:
    """FastAPI dependency — singleton DB session per request."""
    if hasattr(request.state, "db_session"):
        yield request.state.db_session
        return

    session = AsyncSessionLocal()
    request.state.db_session = session
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        if hasattr(request.state, "db_session"):
            del request.state.db_session


def init_db():
    """Create all tables (synchronous, for startup)."""
    import app.models  # noqa: F401 — ensure models are loaded
    Base.metadata.create_all(bind=sync_engine)


def drop_db():
    """Drop all tables (for testing)."""
    import app.models  # noqa: F401
    Base.metadata.drop_all(bind=sync_engine)
