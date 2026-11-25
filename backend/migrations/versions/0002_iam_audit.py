"""Persist canonical subjects, exact identity mappings, RBAC facts and append-only audit."""

from alembic import op

revision = "0002_iam_audit"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the first business tables without renaming or inferring legacy subjects."""
    op.execute(r"""
        CREATE TABLE users (
            id uuid PRIMARY KEY,
            display_name varchar(128) NOT NULL CHECK (display_name ~ '\S'),
            status varchar(24) NOT NULL CHECK (
                status IN ('ACTIVE', 'DISABLED', 'LOCKED', 'PENDING_DEPARTURE', 'DEPARTED')
            ),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at timestamptz,
            CHECK (updated_at >= created_at),
            CHECK (deleted_at IS NULL OR (deleted_at >= created_at AND status <> 'ACTIVE'))
        );
        CREATE INDEX ix_users_status ON users (status) WHERE deleted_at IS NULL;

        CREATE TABLE identities (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            provider_key varchar(64) COLLATE "C" NOT NULL
                CHECK (provider_key ~ '^[a-z][a-z0-9_.-]*$'),
            issuer varchar(2048) COLLATE "C" NOT NULL CHECK (issuer ~ '\S'),
            subject varchar(256) COLLATE "C" NOT NULL CHECK (subject ~ '\S'),
            status varchar(24) NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at timestamptz,
            CHECK (updated_at >= created_at),
            CHECK (deleted_at IS NULL OR (deleted_at >= created_at AND status = 'DISABLED'))
        );
        -- Fixed UTF-8 conversion is deterministic. Bounded digests avoid PostgreSQL's
        -- B-tree tuple limit for valid long Unicode keys. Readers still match raw keys;
        -- a digest collision refuses registration rather than merging two identities.
        CREATE FUNCTION identity_key_digest(value text) RETURNS bytea
            LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
            RETURN sha256(convert_to(value, 'UTF8'));
        CREATE UNIQUE INDEX uq_identities_provider_issuer_subject ON identities (
            provider_key, identity_key_digest(issuer), identity_key_digest(subject)
        );
        CREATE INDEX ix_identities_user ON identities (user_id);

        CREATE TABLE subject_bindings (
            principal_type varchar(24) NOT NULL CHECK (principal_type IN ('ADMIN_USER', 'EMPLOYEE')),
            principal_id uuid NOT NULL,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (principal_type, principal_id)
        );
        CREATE INDEX ix_subject_bindings_user ON subject_bindings (user_id);

        CREATE TABLE roles (
            id uuid PRIMARY KEY,
            code varchar(64) COLLATE "C" NOT NULL UNIQUE CHECK (code ~ '^[A-Z][A-Z0-9_]*$'),
            name varchar(128) NOT NULL CHECK (name ~ '\S'),
            is_system boolean NOT NULL DEFAULT false,
            protected boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at timestamptz,
            CHECK (updated_at >= created_at),
            CHECK (deleted_at IS NULL OR deleted_at >= created_at),
            CHECK (
                (code IN ('SUPER_ADMIN', 'KB_ADMIN', 'AUDIT_READONLY')
                    AND is_system AND protected AND deleted_at IS NULL)
                OR (code NOT IN ('SUPER_ADMIN', 'KB_ADMIN', 'AUDIT_READONLY') AND NOT is_system)
            )
        );
        INSERT INTO roles (id, code, name, is_system, protected) VALUES
            ('e73b5820-f27e-5eca-a9a9-b38a23d7c933', 'SUPER_ADMIN', '超级管理员', true, true),
            ('ae8d8418-5e90-582b-8281-c1e841918d65', 'KB_ADMIN', '知识库管理员', true, true),
            ('16198e77-3079-5a1f-863f-d8006d65d007', 'AUDIT_READONLY', '只读审计员', true, true);

        CREATE TABLE permissions (
            id uuid PRIMARY KEY,
            code varchar(128) COLLATE "C" NOT NULL UNIQUE,
            resource varchar(64) NOT NULL CHECK (resource ~ '^[a-z][a-z0-9_]*$'),
            action varchar(64) NOT NULL CHECK (action ~ '^[a-z][a-z0-9_]*$'),
            description varchar(512) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (code = resource || '.' || action),
            CHECK (updated_at >= created_at)
        );
        CREATE TABLE user_roles (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, role_id)
        );
        CREATE INDEX ix_user_roles_role ON user_roles (role_id);
        CREATE TABLE role_permissions (
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (role_id, permission_id)
        );
        CREATE INDEX ix_role_permissions_permission ON role_permissions (permission_id);

        CREATE TABLE audit_events (
            id uuid PRIMARY KEY,
            schema_version varchar(16) NOT NULL DEFAULT '1.0' CHECK (schema_version = '1.0'),
            occurred_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            action varchar(64) NOT NULL CHECK (action IN (
                'iam.login', 'iam.role_change', 'iam.permission_change', 'provider.change',
                'model.change', 'kb.change', 'rag.config_publish', 'trace.reveal_identity', 'lifecycle.change'
            )),
            result varchar(24) NOT NULL CHECK (result IN ('SUCCEEDED', 'DENIED', 'FAILED')),
            risk varchar(24) NOT NULL CHECK (risk IN ('LOW', 'MEDIUM', 'HIGH')),
            request_id uuid NOT NULL,
            trace_id varchar(32) CHECK (trace_id ~ '^[0-9a-f]{32}$' AND trace_id <> repeat('0', 32)),
            actor_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
            actor_system_roles text[] NOT NULL DEFAULT '{}',
            actor_role_ids uuid[] NOT NULL DEFAULT '{}',
            ip_address inet,
            object_id uuid,
            target_trace_id varchar(32) CHECK (
                target_trace_id ~ '^[0-9a-f]{32}$' AND target_trace_id <> repeat('0', 32)
            ),
            before_snapshot jsonb CHECK (jsonb_typeof(before_snapshot) = 'object'),
            after_snapshot jsonb CHECK (jsonb_typeof(after_snapshot) = 'object'),
            protected_reason_ref uuid,
            CHECK (actor_system_roles <@ ARRAY['SUPER_ADMIN', 'KB_ADMIN', 'AUDIT_READONLY']::text[]),
            CHECK (cardinality(actor_role_ids) <= 100),
            CHECK (actor_user_id IS NOT NULL OR
                (cardinality(actor_system_roles) = 0 AND cardinality(actor_role_ids) = 0)),
            CHECK (result = 'SUCCEEDED' OR after_snapshot IS NULL),
            CHECK (
                (action = 'trace.reveal_identity' AND risk = 'HIGH' AND object_id IS NULL
                    AND before_snapshot IS NULL AND after_snapshot IS NULL
                    AND (result <> 'SUCCEEDED' OR
                        (actor_user_id IS NOT NULL AND target_trace_id IS NOT NULL AND protected_reason_ref IS NOT NULL)))
                OR (action <> 'trace.reveal_identity' AND target_trace_id IS NULL)
            )
        );
        CREATE INDEX ix_audit_occurred ON audit_events (occurred_at, id);
        CREATE INDEX ix_audit_actor_occurred ON audit_events (actor_user_id, occurred_at);
        CREATE INDEX ix_audit_action_occurred ON audit_events (action, occurred_at);
        CREATE INDEX ix_audit_request ON audit_events (request_id);
        CREATE INDEX ix_audit_trace ON audit_events (trace_id) WHERE trace_id IS NOT NULL;

        CREATE FUNCTION set_iam_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER users_updated BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION set_iam_updated_at();
        CREATE TRIGGER identities_updated BEFORE UPDATE ON identities
            FOR EACH ROW EXECUTE FUNCTION set_iam_updated_at();
        CREATE TRIGGER roles_updated BEFORE UPDATE ON roles
            FOR EACH ROW EXECUTE FUNCTION set_iam_updated_at();
        CREATE TRIGGER permissions_updated BEFORE UPDATE ON permissions
            FOR EACH ROW EXECUTE FUNCTION set_iam_updated_at();

        CREATE FUNCTION protect_iam_role() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.protected THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'protected role' USING ERRCODE = '23514';
                END IF;
                IF NEW.id IS DISTINCT FROM OLD.id OR NEW.code IS DISTINCT FROM OLD.code
                    OR NOT NEW.protected OR NEW.is_system IS DISTINCT FROM OLD.is_system
                    OR NEW.deleted_at IS NOT NULL THEN
                    RAISE EXCEPTION 'protected role' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER roles_protected BEFORE UPDATE OR DELETE ON roles
            FOR EACH ROW EXECUTE FUNCTION protect_iam_role();

        CREATE FUNCTION refuse_protected_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'protected append-only data' USING ERRCODE = '23514';
        END;
        $$;
        CREATE TRIGGER roles_no_truncate BEFORE TRUNCATE ON roles
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_protected_mutation();
        CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION refuse_protected_mutation();
        CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_events
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_protected_mutation();
        REVOKE ALL ON audit_events FROM PUBLIC;
    """)


def downgrade() -> None:
    """Destructive development rollback; populated installations require a verified backup."""
    op.execute("""
        DROP TABLE audit_events;
        DROP TABLE role_permissions;
        DROP TABLE user_roles;
        DROP TABLE permissions;
        DROP TABLE roles;
        DROP TABLE subject_bindings;
        DROP TABLE identities;
        DROP TABLE users;
        DROP FUNCTION refuse_protected_mutation();
        DROP FUNCTION protect_iam_role();
        DROP FUNCTION set_iam_updated_at();
        DROP FUNCTION identity_key_digest(text);
    """)
