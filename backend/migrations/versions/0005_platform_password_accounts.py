"""Persist first-party platform password credentials separately from identities."""

from alembic import op

revision = "0005_platform_password_accounts"
down_revision = "0004_rbac_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE TABLE platform_password_credentials (
            identity_id uuid PRIMARY KEY REFERENCES identities(id) ON DELETE RESTRICT,
            username varchar(128) COLLATE "C" NOT NULL CHECK (username ~ '\S'),
            password_hash varchar(512) NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (updated_at >= created_at)
        );
        CREATE UNIQUE INDEX uq_platform_password_username
            ON platform_password_credentials (lower(username));
        CREATE TRIGGER platform_password_credentials_updated
            BEFORE UPDATE ON platform_password_credentials
            FOR EACH ROW EXECUTE FUNCTION set_iam_updated_at();
    """)


def downgrade() -> None:
    """Dropping this table removes all platform password credentials."""
    op.execute("DROP TABLE platform_password_credentials;")
