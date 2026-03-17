# apps/api-gateway/tests/test_org_scope_middleware.py
from src.models.org_permission import OrgPermission, OrgPermissionLevel
from src.models.user import User


def test_org_permission_levels():
    assert OrgPermissionLevel.READ_ONLY.value == "read_only"
    assert OrgPermissionLevel.READ_WRITE.value == "read_write"
    assert OrgPermissionLevel.ADMIN.value == "admin"


def test_org_permission_instantiation():
    perm = OrgPermission(
        user_id="usr-001",
        org_node_id="reg-south",
        permission_level=OrgPermissionLevel.READ_WRITE,
    )
    assert perm.org_node_id == "reg-south"
    assert perm.permission_level == OrgPermissionLevel.READ_WRITE


def test_user_has_org_node_id():
    from sqlalchemy.inspection import inspect
    cols = {c.key for c in User.__table__.columns}
    assert "org_node_id" in cols
