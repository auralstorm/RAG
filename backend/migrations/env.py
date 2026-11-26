"""Configure Alembic on the connection owned by the migration runner."""

from alembic import context
from sqlalchemy.engine import Connection

connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    raise RuntimeError("Use the repository database migration command")

context.configure(connection=connection, version_table_schema="public")
with context.begin_transaction():
    context.run_migrations()
