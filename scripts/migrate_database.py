"""Run repository Alembic migrations as an explicit PostgreSQL maintenance command."""

import argparse
import sys
from collections.abc import Sequence
from contextlib import closing
from io import StringIO
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.util import CommandError
from app.adapters.postgres import postgres_conninfo
from app.core.config import Settings, load_settings
from psycopg import Connection, Error
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "backend/migrations"
MigrationAction = Literal["upgrade", "current", "downgrade"]


def run_migration(settings: Settings, action: MigrationAction, revision: str = "head") -> str:
    if not settings.postgres_password.get_secret_value():
        raise ValueError("PostgreSQL credentials are required for migrations")

    def connect() -> Connection[tuple[object, ...]]:
        return Connection.connect(postgres_conninfo(settings))

    engine = create_engine("postgresql+psycopg://", creator=connect, poolclass=NullPool, hide_parameters=True)
    with closing(StringIO()) as output:
        config = Config(stdout=output)
        config.set_main_option("script_location", str(MIGRATION_DIR).replace("%", "%%"))
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                if action == "current":
                    command.current(config)
                else:
                    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
                    connection.execute(text("SELECT pg_advisory_xact_lock(1282080839, 1)"))
                    if action == "upgrade":
                        command.upgrade(config, revision)
                    else:
                        command.downgrade(config, revision)
            return output.getvalue().strip()
        finally:
            engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("upgrade").add_argument("revision", nargs="?", default="head")
    commands.add_parser("current")
    commands.add_parser("downgrade").add_argument("revision")
    args = parser.parse_args(argv)
    try:
        output = run_migration(load_settings(), args.action, getattr(args, "revision", "head"))
    except (CommandError, Error, SQLAlchemyError, ValidationError, ValueError) as error:
        print(
            f"Database migration failed ({type(error).__name__}). Check the database profile and revision.",
            file=sys.stderr,
        )
        return 1
    print(output or ("No applied revision." if args.action == "current" else "Database migration completed."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
