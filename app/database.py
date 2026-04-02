from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# ─── Async Engine ─────────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,           # Logs all SQL queries in debug mode
    pool_size=10,                  # Number of persistent connections
    max_overflow=20,               # Extra connections allowed above pool_size
    pool_pre_ping=True,            # Verify connections before use (handles DB restarts)
    pool_recycle=3600,             # Recycle connections every 1 hour
)

# ─── Async Session Factory ────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ─── Declarative Base ─────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    All models in app/models/ must inherit from this class.
    """
    pass


# ─── Dependency: DB Session ───────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides an async DB session per request.
    Rolls back on exception. Commit ownership is intentionally left to the
    service layer to keep transaction boundaries explicit and consistent.

    Usage in routes:
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
