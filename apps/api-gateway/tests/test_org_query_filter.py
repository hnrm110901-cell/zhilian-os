# apps/api-gateway/tests/test_org_query_filter.py
import pytest
from sqlalchemy import select
from src.core.org_query_filter import OrgQueryFilter
from src.core.org_scope import OrgScope
from src.models.order import Order   # 现有模型，有 store_id 字段


def make_scope(store_ids: list[str], is_admin=False) -> OrgScope:
    return OrgScope(
        home_node_id="test-node",
        accessible_store_ids=store_ids,
        accessible_node_ids=[],
        permission_level="read_write",
        is_global_admin=is_admin,
    )


def test_filter_adds_store_id_in_clause():
    """普通 scope 应在查询上追加 store_id IN (...) 过滤"""
    scope = make_scope(["sto-gz-001", "sto-sz-001"])
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)

    # 检查 SQL 包含 IN 子句
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "IN" in compiled.upper()
    assert "sto-gz-001" in compiled


def test_filter_skips_for_global_admin():
    """全局 Admin 不加过滤条件"""
    scope = make_scope([], is_admin=True)
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)
    compiled_original = str(select(Order).compile(compile_kwargs={"literal_binds": True}))
    compiled_filtered = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    # Admin scope 不应该改变查询
    assert "WHERE" not in compiled_filtered or compiled_filtered == compiled_original


def test_filter_empty_scope_returns_nothing():
    """空 scope（非 admin）应返回 1=0 条件（零结果）"""
    scope = make_scope([])  # 无权限但非 admin
    q = select(Order)
    filtered = OrgQueryFilter.apply(q, Order, scope)
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "1 != 1" in compiled or "false" in compiled.lower() or "1=0" in compiled


def test_filter_brand_scoped_model():
    """有 brand_id 但无 store_id 的模型，使用 brand_id scope_field → 不过滤"""
    scope = OrgScope(
        home_node_id="brd-001",
        accessible_store_ids=["sto-a", "sto-b"],
        accessible_node_ids=["brd-001", "sto-a", "sto-b"],
        permission_level="read_write",
    )
    from src.models.dish_master import DishMaster  # 只有 brand_id
    q = select(DishMaster)
    # brand_scoped 模式：不过滤（品牌级数据在子树内通用）
    filtered = OrgQueryFilter.apply(q, DishMaster, scope, scope_field="brand_id")
    # 只要不崩溃即可，具体行为取决于 brand_id 是否在 scope 中
    assert filtered is not None
