"""Alembic environment configuration.

Reads DATABASE_URL_SYNC from app settings and runs migrations
against the sync engine (both online and offline modes).
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.config import settings  # noqa: E402
from backend.database import Base  # noqa: E402

# Import ALL models so Base.metadata is populated
from backend.models import (  # noqa: E402, F401
    Company,
    Person,
    CompanyWebsiteIntel,
    CompanyIntentSignal,
    OutreachDraft,
    PipelineStage,
    Activity,
    ABTestResult,
    LeadRating,
)

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
