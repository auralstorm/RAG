"""Add the provider registry and encrypted provider credential storage."""

from alembic import op

revision = "0006_provider_registry"
down_revision = "0005_platform_password_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE TABLE provider_secrets (
            secret_id uuid NOT NULL,
            version integer NOT NULL CHECK (version > 0),
            environment varchar(16) NOT NULL CHECK (environment IN ('development','test','production')),
            key_version varchar(64) NOT NULL CHECK (key_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
            ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 28 AND 32768),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (secret_id,version,environment)
        );

        CREATE TABLE provider_proxy_configs (
            proxy_id uuid PRIMARY KEY,
            secret_id uuid NOT NULL,
            secret_version integer NOT NULL,
            secret_environment varchar(16) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (secret_id,secret_version,secret_environment),
            FOREIGN KEY (secret_id,secret_version,secret_environment)
                REFERENCES provider_secrets(secret_id,version,environment) ON DELETE RESTRICT
        );

        CREATE TABLE providers (
            id uuid PRIMARY KEY,
            name varchar(128) NOT NULL CHECK (name ~ '\S'),
            provider_type varchar(64) NOT NULL CHECK (provider_type ~ '^[a-z][a-z0-9_]*$'),
            base_url text NOT NULL CHECK (base_url ~ '^https?://[^[:space:]]+$'),
            proxy_ref uuid REFERENCES provider_proxy_configs(proxy_id) ON DELETE RESTRICT,
            timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 300),
            status varchar(24) NOT NULL CHECK (status IN ('ACTIVE','DISABLED')),
            config_version varchar(128) NOT NULL CHECK (config_version ~ '^[0-9a-f-]{36}$'),
            credential_secret_id uuid,
            credential_version integer,
            credential_environment varchar(16),
            remarks varchar(1000) NOT NULL DEFAULT '',
            deleted_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (updated_at >= created_at),
            CHECK (
                (credential_secret_id IS NULL AND credential_version IS NULL AND credential_environment IS NULL)
                OR (credential_secret_id IS NOT NULL AND credential_version IS NOT NULL
                    AND credential_version > 0 AND credential_environment IS NOT NULL
                    AND credential_environment IN ('development','test','production'))
            ),
            FOREIGN KEY (credential_secret_id,credential_version,credential_environment)
                REFERENCES provider_secrets(secret_id,version,environment) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX uq_providers_name ON providers(lower(name)) WHERE deleted_at IS NULL;
        CREATE INDEX ix_providers_status_type ON providers(status,provider_type,id);
        CREATE TABLE provider_config_versions (
            provider_id uuid NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
            config_version varchar(128) NOT NULL,
            configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration)='object'),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (provider_id,config_version)
        );
        CREATE FUNCTION reject_provider_version_changes() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Provider configuration versions are immutable';
        END;
        $$;
        CREATE TRIGGER immutable_provider_versions BEFORE UPDATE OR DELETE ON provider_config_versions
            FOR EACH ROW EXECUTE FUNCTION reject_provider_version_changes();
    """)


def downgrade() -> None:
    """Remove Provider metadata, proxy references and encrypted credentials."""
    op.execute(
        "DROP TABLE provider_config_versions; DROP FUNCTION reject_provider_version_changes(); "
        "DROP TABLE providers; DROP TABLE provider_proxy_configs; DROP TABLE provider_secrets;"
    )
