"""Record the P1-01 migration baseline before business tables are introduced."""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the initial revision in Alembic's version ledger."""


def downgrade() -> None:
    """Remove the initial revision from Alembic's version ledger."""
