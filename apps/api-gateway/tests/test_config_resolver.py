"""
ConfigResolver 单元测试
不依赖数据库：用内存 OrgNode/OrgConfig 对象直接测试解析逻辑
"""
import pytest
from src.services.config_resolver import ConfigResolver
from src.models.org_node import OrgNode, OrgNodeType
from src.models.org_config import OrgConfig, ConfigKey


def make_node(id_, name, parent_id=None, depth=0, path=None) -> OrgNode:
    path = path or id_
    node = OrgNode()
    node.id = id_
    node.name = name
    node.node_type = OrgNodeType.STORE if depth > 0 else OrgNodeType.GROUP
    node.parent_id = parent_id
    node.path = path
    node.depth = depth
    node.configs = []
    return node


def make_config(node_id, key, value, value_type="str", is_override=False) -> OrgConfig:
    cfg = OrgConfig()
    cfg.org_node_id = node_id
    cfg.config_key = key
    cfg.config_value = value
    cfg.value_type = value_type
    cfg.is_override = is_override
    return cfg


# ── 场景 1: 无配置时返回默认值 ──────────────────────────────────────────
def test_resolve_returns_default_when_no_config():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve(
        node_id="sto",
        key=ConfigKey.MAX_CONSECUTIVE_WORK_DAYS,
        default=6,
    )
    assert result == 6


# ── 场景 2: 子节点继承父节点配置 ────────────────────────────────────────
def test_resolve_inherits_from_parent():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    # 集团设置了配置，门店没有
    group.configs = [
        make_config("grp", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5", "int")
    ]
    store.configs = []

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, default=6)
    assert result == 5  # 继承自集团


# ── 场景 3: 门店配置覆盖集团配置 ────────────────────────────────────────
def test_resolve_store_overrides_group():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    group.configs = [
        make_config("grp", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5", "int")
    ]
    store.configs = [
        make_config("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "4", "int", is_override=True)
    ]

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, default=6)
    assert result == 4  # 门店自己覆盖


# ── 场景 4: 三层继承（集团→品牌→门店）────────────────────────────────
def test_resolve_three_level_chain():
    group  = make_node("grp", "集团", depth=0, path="grp")
    brand  = make_node("brd", "品牌A", parent_id="grp", depth=1, path="grp.brd")
    store  = make_node("sto", "门店A", parent_id="brd", depth=2, path="grp.brd.sto")

    group.configs = [make_config("grp", ConfigKey.PROBATION_DAYS, "90", "int")]
    brand.configs = [make_config("brd", ConfigKey.PROBATION_DAYS, "60", "int")]
    store.configs = []  # 门店没配置，继承品牌的

    node_map = {"grp": group, "brd": brand, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("sto", ConfigKey.PROBATION_DAYS, default=90)
    assert result == 60  # 最近的祖先（品牌）生效


# ── 场景 5: resolve_all 返回完整配置字典 ────────────────────────────────
def test_resolve_all_merges_chain():
    group = make_node("grp", "集团", depth=0, path="grp")
    store = make_node("sto", "门店A", parent_id="grp", depth=1, path="grp.sto")

    group.configs = [
        make_config("grp", ConfigKey.PROBATION_DAYS, "90", "int"),
        make_config("grp", ConfigKey.OVERTIME_MULTIPLIER, "1.5", "float"),
    ]
    store.configs = [
        make_config("sto", ConfigKey.OVERTIME_MULTIPLIER, "2.0", "float", is_override=True),
    ]

    node_map = {"grp": group, "sto": store}
    resolver = ConfigResolver(node_map=node_map)

    all_cfg = resolver.resolve_all("sto")
    assert all_cfg[ConfigKey.PROBATION_DAYS] == 90        # 继承集团
    assert all_cfg[ConfigKey.OVERTIME_MULTIPLIER] == 2.0  # 门店覆盖


# ── 场景 6: bool 类型正确解析 ────────────────────────────────────────────
def test_resolve_bool_type():
    group = make_node("grp", "集团", depth=0, path="grp")
    group.configs = [
        make_config("grp", ConfigKey.SPLIT_SHIFT_ALLOWED, "true", "bool")
    ]
    node_map = {"grp": group}
    resolver = ConfigResolver(node_map=node_map)

    result = resolver.resolve("grp", ConfigKey.SPLIT_SHIFT_ALLOWED, default=False)
    assert result is True
