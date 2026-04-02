import asyncio
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── Load app config and models ───────────────────────────────────────────────
# Import settings to get the DATABASE_URL from .env
from app.config import settings

# Import Base so Alembic can detect all models for autogenerate
from app.database import Base

# Import all models — required for autogenerate to detect them
import app.models  # noqa: F401 — triggers all model imports via models/__init__.py

# ─── Alembic Config ───────────────────────────────────────────────────────────
config = context.config

# Override sqlalchemy.url with the value from .env
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate (--autogenerate flag)
target_metadata = Base.metadata


# ─── Offline Migrations ───────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL without a live DB connection.
    Useful for generating migration scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,           # Detect column type changes
        compare_server_default=True, # Detect server default changes
    )
    with context.begin_transaction():
        context.run_migrations()


# ─── Online Migrations (Async) ────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with an async SQLAlchemy engine.
    This is the standard mode when running: alembic upgrade head
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ─── Entry Point ──────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
