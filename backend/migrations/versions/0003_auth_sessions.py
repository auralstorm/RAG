"""Persist purpose-bound platform sessions, refresh rotation and login budgets."""

from alembic import op

revision = "0003_auth_sessions"
down_revision = "0002_iam_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE identities ADD CONSTRAINT uq_identity_subject UNIQUE (id, user_id);
        CREATE TABLE identity_applications (
            identity_id uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            application varchar(16) NOT NULL CHECK (application IN ('chat', 'admin')),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (identity_id, application)
        );
        CREATE TABLE auth_sessions (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL,
            identity_id uuid NOT NULL,
            application varchar(16) NOT NULL CHECK (application IN ('chat', 'admin')),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            FOREIGN KEY (identity_id, user_id) REFERENCES identities(id, user_id) ON DELETE RESTRICT,
            CHECK (expires_at > created_at)
        );
        CREATE INDEX ix_auth_sessions_subject ON auth_sessions(user_id);
        CREATE INDEX ix_auth_sessions_expiry ON auth_sessions(expires_at);
        CREATE TABLE auth_refresh_tokens (
            token_hash char(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            session_id uuid NOT NULL REFERENCES auth_sessions(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consumed_at timestamptz
        );
        CREATE INDEX ix_auth_refresh_session ON auth_refresh_tokens(session_id);
        CREATE TABLE auth_login_budgets (
            bucket char(64) PRIMARY KEY CHECK (bucket ~ '^[0-9a-f]{64}$'),
            window_start timestamptz NOT NULL,
            attempts integer NOT NULL CHECK (attempts > 0)
        );
    """)


def downgrade() -> None:
    """Development rollback invalidates every platform session; never restores old tokens."""
    op.execute("""
        DROP TABLE auth_login_budgets;
        DROP TABLE auth_refresh_tokens;
        DROP TABLE auth_sessions;
        DROP TABLE identity_applications;
        ALTER TABLE identities DROP CONSTRAINT uq_identity_subject;
    """)
