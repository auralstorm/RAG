"""Pin the product's fixed role matrix independently of mutable database assignments."""

from app.modules.iam.domain.rbac import DELEGABLE_PERMISSIONS, PERMISSION_CODES, SYSTEM_ROLE_PERMISSIONS


def test_fixed_role_matrix_matches_v1_product_rules() -> None:
    assert SYSTEM_ROLE_PERMISSIONS["SUPER_ADMIN"] == frozenset(PERMISSION_CODES)
    assert SYSTEM_ROLE_PERMISSIONS["KB_ADMIN"] == {"dashboard.read", "kb.read", "document.read"}
    assert SYSTEM_ROLE_PERMISSIONS["AUDIT_READONLY"] == {
        "dashboard.read",
        "provider.read",
        "model.read",
        "kb.read",
        "document.read",
        "trace.read",
        "user.read",
        "role.read",
        "permission.read",
        "employee.read",
        "audit.read",
        "config.read",
        "acl.read",
    }
    assert DELEGABLE_PERMISSIONS == SYSTEM_ROLE_PERMISSIONS["AUDIT_READONLY"]
    assert (
        not {
            "role.manage",
            "user.manage",
            "acl.manage",
            "kb.manage",
            "provider.manage",
            "config.manage",
            "trace.reveal_identity",
        }
        & DELEGABLE_PERMISSIONS
    )
