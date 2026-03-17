import pytest
from src.models.org_node import OrgNode, OrgNodeType, StoreType, OperationMode
from src.models.org_config import OrgConfig


def test_org_node_enums_exist():
    assert OrgNodeType.GROUP.value == "group"
    assert OrgNodeType.BRAND.value == "brand"
    assert OrgNodeType.REGION.value == "region"
    assert OrgNodeType.CITY.value == "city"
    assert OrgNodeType.STORE.value == "store"
    assert OrgNodeType.DEPARTMENT.value == "department"


def test_store_type_enums_exist():
    assert StoreType.FLAGSHIP.value == "flagship"
    assert StoreType.STANDARD.value == "standard"
    assert StoreType.MALL.value == "mall"
    assert StoreType.DARK_KITCHEN.value == "dark_kitchen"
    assert StoreType.FRANCHISE.value == "franchise"
    assert StoreType.KIOSK.value == "kiosk"


def test_operation_mode_enums_exist():
    assert OperationMode.DIRECT.value == "direct"
    assert OperationMode.FRANCHISE.value == "franchise"
    assert OperationMode.JOINT.value == "joint"
    assert OperationMode.MANAGED.value == "managed"


def test_org_node_instantiation():
    node = OrgNode(
        id="group-001",
        name="徐记集团",
        node_type=OrgNodeType.GROUP,
        path="group-001",
        depth=0,
    )
    assert node.name == "徐记集团"
    assert node.node_type == OrgNodeType.GROUP
    assert node.parent_id is None


def test_org_config_instantiation():
    cfg = OrgConfig(
        org_node_id="store-001",
        config_key="max_consecutive_work_days",
        config_value="6",
        value_type="int",
        is_override=False,
    )
    assert cfg.config_key == "max_consecutive_work_days"
    assert cfg.typed_value() == 6


def test_org_config_override_flag():
    cfg = OrgConfig(
        org_node_id="store-001",
        config_key="split_shift_allowed",
        config_value="false",
        value_type="bool",
        is_override=True,
    )
    assert cfg.typed_value() is False
    assert cfg.is_override is True


from src.models.store import Store


def test_store_has_org_node_id():
    """Store 必须有 org_node_id 和 operation_mode 字段"""
    cols = {c.key for c in Store.__table__.columns}
    assert "org_node_id" in cols
    assert "store_type" in cols
    assert "operation_mode" in cols


from src.models.employee import Employee


def test_employee_has_dept_node_id():
    cols = {c.key for c in Employee.__table__.columns}
    assert "dept_node_id" in cols
