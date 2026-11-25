"""PostgreSQL connection and transaction ownership for persistence adapters."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from math import ceil

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import TupleRow

from app.core.config import Settings
from app.core.observability import observe_operation


def postgres_conninfo(settings: Settings) -> str:
    return make_conninfo(
        host=settings.postgres_host,
        port=str(settings.postgres_port),
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_database,
        connect_timeout=str(ceil(settings.dependency_timeout)),
    )


@asynccontextmanager
async def postgres_transaction(settings: Settings) -> AsyncGenerator[AsyncConnection[TupleRow]]:
    """Own a connection and commit on success or roll back on exceptional exit.

    Repositories share the supplied connection within one use case and leave completion to its owner.
    """
    with observe_operation("postgres.transaction"):
        async with await AsyncConnection.connect(postgres_conninfo(settings)) as connection:
            yield connection
