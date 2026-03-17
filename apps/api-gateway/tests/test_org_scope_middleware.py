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


# APPEND to test file
from src.core.org_scope import OrgScope, build_org_scope_from_nodes
from src.models.org_node import OrgNode, OrgNodeType


def _make_store_node(id_, path, parent_id=None):
    n = OrgNode()
    n.id = id_
    n.name = id_
    n.node_type = OrgNodeType.STORE.value
    n.path = path
    n.depth = path.count(".") + 1 if "." in path else 1
    n.parent_id = parent_id
    n.store_ref_id = id_  # store_ref_id = store_id（门店节点自引）
    return n


def _make_region_node(id_, path):
    n = OrgNode()
    n.id = id_
    n.name = id_
    n.node_type = OrgNodeType.REGION.value
    n.path = path
    n.depth = 1
    n.parent_id = None
    n.store_ref_id = None
    return n


def test_org_scope_store_ids_from_subtree():
    """区域节点的 scope 应包含区域内所有门店的 store_ref_id"""
    region = _make_region_node("reg-south", "grp.reg-south")
    store1 = _make_store_node("sto-gz-001", "grp.reg-south.sto-gz-001", "reg-south")
    store2 = _make_store_node("sto-sz-001", "grp.reg-south.sto-sz-001", "reg-south")

    scope = build_org_scope_from_nodes(
        home_node_id="reg-south",
        subtree_nodes=[region, store1, store2],
        permission_level="read_write",
    )
    assert set(scope.accessible_store_ids) == {"sto-gz-001", "sto-sz-001"}
    assert scope.home_node_id == "reg-south"
    assert scope.permission_level == "read_write"


def test_org_scope_store_node_only_sees_itself():
    """门店节点的 scope 只包含自身门店"""
    store = _make_store_node("sto-gz-001", "grp.reg.sto-gz-001")
    scope = build_org_scope_from_nodes(
        home_node_id="sto-gz-001",
        subtree_nodes=[store],
        permission_level="admin",
    )
    assert scope.accessible_store_ids == ["sto-gz-001"]


def test_org_scope_admin_sees_all_stores():
    """Admin 节点（集团根）可以看所有门店"""
    group_node = OrgNode()
    group_node.id = "grp-demo"
    group_node.node_type = OrgNodeType.GROUP.value
    group_node.path = "grp-demo"
    group_node.store_ref_id = None

    store1 = _make_store_node("sto-a", "grp-demo.sto-a")
    store2 = _make_store_node("sto-b", "grp-demo.sto-b")

    scope = build_org_scope_from_nodes(
        home_node_id="grp-demo",
        subtree_nodes=[group_node, store1, store2],
        permission_level="admin",
    )
    assert set(scope.accessible_store_ids) == {"sto-a", "sto-b"}
