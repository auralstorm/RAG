"""Freeze V1 role capabilities and persist purpose-bound knowledge ACL facts."""

from uuid import NAMESPACE_URL, uuid5

from alembic import op
from sqlalchemy import text

revision = "0004_rbac_policy"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None

# This historical matrix is intentionally frozen, independent of runtime catalog edits.
PERMISSIONS = (
    "dashboard.read",
    "provider.read",
    "provider.manage",
    "model.read",
    "model.manage",
    "kb.read",
    "kb.manage",
    "document.read",
    "document.manage",
    "trace.read",
    "trace.reveal_identity",
    "user.read",
    "user.manage",
    "role.read",
    "role.manage",
    "permission.read",
    "employee.read",
    "employee.manage",
    "audit.read",
    "config.read",
    "config.manage",
    "acl.read",
    "acl.manage",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE policy_state (
            singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
            version bigint NOT NULL DEFAULT 1 CHECK(version > 0)
        );
        INSERT INTO policy_state VALUES (true,1);
        CREATE TABLE system_role_permissions (
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
            PRIMARY KEY (role_id,permission_id)
        );
        CREATE TABLE kb_resource_grants (
            id uuid PRIMARY KEY,
            kb_id uuid NOT NULL,
            purpose varchar(16) NOT NULL CHECK(purpose IN ('admin','chat')),
            principal_type varchar(24) NOT NULL CHECK(principal_type IN ('USER','ROLE','ADMIN_USER','EMPLOYEE')),
            principal_id uuid NOT NULL,
            permission varchar(16) NOT NULL CHECK(permission IN ('READ','MANAGE')),
            user_ref uuid GENERATED ALWAYS AS (CASE WHEN principal_type='USER' THEN principal_id END) STORED REFERENCES users(id) ON DELETE RESTRICT,
            role_ref uuid GENERATED ALWAYS AS (CASE WHEN principal_type='ROLE' THEN principal_id END) STORED REFERENCES roles(id) ON DELETE RESTRICT,
            source_type varchar(24) GENERATED ALWAYS AS (CASE WHEN principal_type IN ('ADMIN_USER','EMPLOYEE') THEN principal_type END) STORED,
            source_id uuid GENERATED ALWAYS AS (CASE WHEN principal_type IN ('ADMIN_USER','EMPLOYEE') THEN principal_id END) STORED,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_type,source_id) REFERENCES subject_bindings(principal_type,principal_id) ON DELETE RESTRICT,
            UNIQUE(kb_id,purpose,principal_type,principal_id),
            CHECK(purpose <> 'chat' OR permission='READ')
        );
        CREATE INDEX ix_kb_grants_principal ON kb_resource_grants(purpose,principal_type,principal_id);
    """)
    connection = op.get_bind()
    for code in PERMISSIONS:
        resource, action = code.split(".")
        connection.execute(
            text(
                "INSERT INTO permissions(id,code,resource,action) VALUES (:id,:code,:resource,:action) ON CONFLICT(code) DO NOTHING"
            ),
            {
                "id": uuid5(NAMESPACE_URL, "enterprise-rag:permission:" + code),
                "code": code,
                "resource": resource,
                "action": action,
            },
        )
    matrix = {
        "SUPER_ADMIN": PERMISSIONS,
        "AUDIT_READONLY": tuple(code for code in PERMISSIONS if code.endswith(".read")),
        "KB_ADMIN": ("dashboard.read", "kb.read", "document.read"),
    }
    for role, codes in matrix.items():
        for code in codes:
            connection.execute(
                text(
                    "INSERT INTO system_role_permissions(role_id,permission_id) SELECT r.id,p.id FROM roles r,permissions p WHERE r.code=:role AND p.code=:code"
                ),
                {"role": role, "code": code},
            )
    op.execute("""
        INSERT INTO role_permissions(role_id,permission_id)
            SELECT role_id,permission_id FROM system_role_permissions ON CONFLICT DO NOTHING;
        CREATE FUNCTION guard_system_role_permissions() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' AND EXISTS (SELECT 1 FROM roles WHERE id=OLD.role_id AND is_system) THEN
                RAISE EXCEPTION 'fixed role permissions are protected' USING ERRCODE='23514';
            END IF;
            IF TG_OP <> 'DELETE' AND EXISTS (SELECT 1 FROM roles WHERE id=NEW.role_id AND is_system)
                AND NOT EXISTS (SELECT 1 FROM system_role_permissions WHERE role_id=NEW.role_id AND permission_id=NEW.permission_id) THEN
                RAISE EXCEPTION 'fixed role matrix is protected' USING ERRCODE='23514';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER fixed_role_permissions BEFORE INSERT OR UPDATE OR DELETE ON role_permissions
            FOR EACH ROW EXECUTE FUNCTION guard_system_role_permissions();
        CREATE TRIGGER fixed_role_permissions_no_truncate BEFORE TRUNCATE ON role_permissions
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_protected_mutation();
        CREATE TRIGGER fixed_matrix_no_mutation BEFORE INSERT OR UPDATE OR DELETE ON system_role_permissions
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_protected_mutation();
        CREATE TRIGGER fixed_matrix_no_truncate BEFORE TRUNCATE ON system_role_permissions
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_protected_mutation();
        CREATE FUNCTION guard_fixed_permission_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS(SELECT 1 FROM system_role_permissions WHERE permission_id=OLD.id) THEN
                IF TG_OP='DELETE' THEN
                    RAISE EXCEPTION 'fixed permission is protected' USING ERRCODE='23514';
                END IF;
                IF NEW.id IS DISTINCT FROM OLD.id OR NEW.code IS DISTINCT FROM OLD.code
                    OR NEW.resource IS DISTINCT FROM OLD.resource OR NEW.action IS DISTINCT FROM OLD.action THEN
                    RAISE EXCEPTION 'fixed permission is protected' USING ERRCODE='23514';
                END IF;
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER fixed_permission_identity BEFORE UPDATE OR DELETE ON permissions
            FOR EACH ROW EXECUTE FUNCTION guard_fixed_permission_identity();
        CREATE FUNCTION bump_policy_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE policy_state SET version=version+1 WHERE singleton;
            RETURN NULL;
        END;
        $$;
        CREATE TRIGGER roles_policy AFTER INSERT OR UPDATE OR DELETE ON roles FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
        CREATE TRIGGER permissions_policy AFTER INSERT OR UPDATE OR DELETE ON permissions FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
        CREATE TRIGGER user_roles_policy AFTER INSERT OR UPDATE OR DELETE ON user_roles FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
        CREATE TRIGGER role_permissions_policy AFTER INSERT OR UPDATE OR DELETE ON role_permissions FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
        CREATE TRIGGER grants_policy AFTER INSERT OR UPDATE OR DELETE ON kb_resource_grants FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
        CREATE TRIGGER bindings_policy AFTER INSERT OR UPDATE OR DELETE ON subject_bindings FOR EACH STATEMENT EXECUTE FUNCTION bump_policy_version();
    """)


def downgrade() -> None:
    """Restore the preceding empty matrix; custom roles/assignments remain but lose frozen catalog links."""
    op.execute("""
        DROP TRIGGER roles_policy ON roles;
        DROP TRIGGER permissions_policy ON permissions;
        DROP TRIGGER user_roles_policy ON user_roles;
        DROP TRIGGER role_permissions_policy ON role_permissions;
        DROP TRIGGER bindings_policy ON subject_bindings;
        DROP TABLE kb_resource_grants;
        DROP TRIGGER fixed_role_permissions ON role_permissions;
        DROP TRIGGER fixed_role_permissions_no_truncate ON role_permissions;
        DROP TRIGGER fixed_matrix_no_mutation ON system_role_permissions;
        DROP TRIGGER fixed_matrix_no_truncate ON system_role_permissions;
        DROP TRIGGER fixed_permission_identity ON permissions;
        DELETE FROM role_permissions WHERE (role_id,permission_id) IN (SELECT role_id,permission_id FROM system_role_permissions);
        DROP TABLE system_role_permissions;
        DROP TABLE policy_state;
        DROP FUNCTION bump_policy_version();
        DROP FUNCTION guard_system_role_permissions();
        DROP FUNCTION guard_fixed_permission_identity();
    """)
