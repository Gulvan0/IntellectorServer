import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import net.core  # noqa: F401  # imports every model module, which registers the tables in SQLModel.metadata
from common.field_types import PreciseUtcDateTime, UtcDateTime
from config.loader import load
from config.models import SecretConfig
from log.models import LOG_SCHEMA


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def database_name() -> str | None:
    """`alembic -x db=<name> ...` targets another database than the configured one, e.g. a scratch one for rehearsals"""
    return context.get_x_argument(as_dictionary=True).get("db")


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Only the main database (the connection's default schema) and the logs one are managed"""
    if type_ == "schema":
        return name in (None, LOG_SCHEMA)
    return True


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    if type_ == "type" and isinstance(obj, UtcDateTime):
        autogen_context.imports.add("import common.field_types")
        if isinstance(obj, PreciseUtcDateTime):
            return "common.field_types.PreciseUtcDateTime()"
        return f"common.field_types.UtcDateTime({obj.fsp!r})"
    return False


def run_migrations_offline() -> None:
    raise RuntimeError("Offline mode is not supported: the URL comes from SecretConfig")


def run_migrations_online() -> None:
    if os.getenv("STAGE") is None:
        raise RuntimeError("Set the STAGE environment variable, same as for the server")

    secret_config = load("secret", SecretConfig)
    connectable = create_engine(secret_config.db.sync_url(database_name()), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_name=include_name,
            render_item=render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
