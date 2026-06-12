from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app import migrations


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    raise RuntimeError(
        "Use `python -m app.migrations upgrade|stamp|status`; "
        f"current baseline is {migrations.BASELINE_REVISION}."
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
