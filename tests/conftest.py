import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from app.main import app
from app.database import Base, get_db
from app.config import settings

# ─── Engine ───────────────────────────────────────────────────────────────────
# Uses your main development database (sports_platform).
# Tables are dropped + recreated before tests, and dropped again after.
# Run `alembic upgrade head` after testing to restore tables for dev use.
test_engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Use NullPool so each session gets a fresh connection.
    # This prevents asyncpg "another operation is in progress" errors
    # that happen when a connection is shared across concurrent test sessions.
    poolclass=__import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Prevents lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ─── Session-scoped: create & drop tables once ───────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Runs ONCE for the whole test session.

    Before: drops all tables and recreates them clean.
    After:  drops all tables — DB is left empty.

    To restore for development after testing:
        alembic upgrade head
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


# ─── Per-test: fresh session, rolled back after each test ────────────────────

@pytest_asyncio.fixture()
async def db_session():
    """
    Provides a fresh AsyncSession for each test.

    How it works:
    - Opens a connection and begins an outer SAVEPOINT transaction.
    - Yields the session to the test.
    - After the test, rolls back to the SAVEPOINT — undoing ALL changes.
    - The DB is left exactly as it was before the test started.

    This is the correct pattern for async SQLAlchemy + asyncpg to avoid
    the "another operation is in progress" InterfaceError.
    """
    async with test_engine.connect() as conn:
        # Begin an outer transaction that we will NEVER commit
        await conn.begin()

        # Create a session bound to this specific connection
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        try:
            yield session
        finally:
            await session.close()
            # Roll back the outer transaction — undoes everything the test did
            await conn.rollback()


# ─── Per-test: HTTP client wired to the same session ─────────────────────────

@pytest_asyncio.fixture()
async def client(db_session: AsyncSession):
    """
    Provides an async HTTP test client.

    The app's get_db dependency is overridden to use the SAME session
    as db_session. This is critical — if the app creates its own session
    on a different connection, you get the "another operation is in progress"
    InterfaceError because asyncpg connections are not thread/coroutine safe
    for concurrent operations.

    With this override, the test helper AND the route handler both use
    the same connection, and everything stays within the same transaction.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
