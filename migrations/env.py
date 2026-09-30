import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Registers every model on Base.metadata so autogenerate sees the whole
# schema — platform tables AND product tables — regardless of which module
# is imported first. This file lives here, outside both src/eklabs_platform
# and src/products, specifically so it's free to import from both: it's the
# one place in the repo where importing from `products` is required, not
# forbidden — the "platform/ never imports products/" rule is about
# platform/ *code*, and a root-level migration runner isn't that.
from eklabs_platform.core.db import models as _platform_models  # noqa: F401
from eklabs_platform.core.db.base import Base
from products.ectd.db import models as _ectd_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migrator_database_url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "ALEMBIC_DATABASE_URL is not set — needs the eklabs_migrator connection "
            "string (Supabase's direct/session connection, not the transaction "
            "pooler used by the app)."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_migrator_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _migrator_database_url()
    connectable = engine_from_config(
        configuration,
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
