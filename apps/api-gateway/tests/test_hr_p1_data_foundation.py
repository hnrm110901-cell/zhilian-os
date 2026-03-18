"""P1 Data Foundation tests — org seed, employee seed, Excel import, authoritative flip, z62."""
import json
import os
import uuid
from datetime import date, datetime, time
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_DATA_DIR = Path(__file__).parent.parent / "src" / "data"


# ── P1-A: Org Seed ──────────────────────────────────────────────────


def test_xuji_org_seed_count_43():
    """org seed JSON 应有 43 个节点"""
    with open(_DATA_DIR / "xuji_org_seed.json", encoding="utf-8") as f:
        nodes = json.load(f)
    assert len(nodes) == 43


def test_xuji_org_seed_depth_correct():
    """depth 约定: group=0, brand=1, region=2, store=3, department=4"""
    with open(_DATA_DIR / "xuji_org_seed.json", encoding="utf-8") as f:
        nodes = json.load(f)

    by_type = {}
    for n in nodes:
        by_type.setdefault(n["node_type"], set()).add(n["depth"])

    assert by_type["group"] == {0}
    assert by_type["brand"] == {1}
    assert by_type["region"] == {2}
    assert by_type["store"] == {3}
    assert by_type["department"] == {4}


def test_xuji_org_seed_path_consistency():
    """每个节点的 path 应以其 id 结尾且包含 parent 的 path"""
    with open(_DATA_DIR / "xuji_org_seed.json", encoding="utf-8") as f:
        nodes = json.load(f)

    id_to_node = {n["id"]: n for n in nodes}
    for n in nodes:
        assert n["path"].endswith(n["id"]), f"{n['id']} path should end with its own id"
        if n["parent_id"]:
            parent = id_to_node[n["parent_id"]]
            assert n["path"].startswith(parent["path"] + "."), (
                f"{n['id']} path should start with parent path"
            )


# ── P1-B: Employee Seed ─────────────────────────────────────────────


def test_xuji_employees_seed_count_100():
    """employee seed JSON 应有 100 个员工"""
    with open(_DATA_DIR / "xuji_employees_seed.json", encoding="utf-8") as f:
        employees = json.load(f)
    assert len(employees) == 100


def test_xuji_employees_pay_scheme_4_types():
    """应包含全部 4 种薪酬类型: fixed_monthly, hourly, base_plus_commission, piecework"""
    with open(_DATA_DIR / "xuji_employees_seed.json", encoding="utf-8") as f:
        employees = json.load(f)

    pay_types = {emp["pay_scheme"]["type"] for emp in employees}
    assert pay_types == {"fixed_monthly", "hourly", "base_plus_commission", "piecework"}


def test_xuji_employees_10_stores():
    """员工应分布在 10 个门店"""
    with open(_DATA_DIR / "xuji_employees_seed.json", encoding="utf-8") as f:
        employees = json.load(f)

    # org_node_id 形如 xj-sXX-ft, 提取门店部分
    stores = set()
    for emp in employees:
        parts = emp["org_node_id"].rsplit("-", 1)
        stores.add(parts[0])  # xj-s01, xj-s02, etc.
    assert len(stores) == 10


# ── P1-D: Excel Import ──────────────────────────────────────────────


def _create_test_xlsx(rows):
    """创建测试用 Excel 文件"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "手机", "岗位", "入职日期", "薪酬类型", "基本工资"])
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_valid_excel():
    """有效 Excel 应成功导入"""
    from src.services.hr.hr_import_service import HRImportService

    xlsx = _create_test_xlsx([
        ["张三", "13900000001", "服务员", "2024-06-15", "固定月薪", 3500],
        ["李四", "13900000002", "厨师", "2024-07-01", "底薪+提成", 4000],
    ])

    # Mock session
    session = AsyncMock()
    # Person.id query returns None (no duplicate)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    # Mock flush to assign IDs to added objects
    add_calls = []
    original_add = session.add

    def mock_add(obj):
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = uuid.uuid4()
        add_calls.append(obj)

    session.add = mock_add

    svc = HRImportService()
    result = await svc.import_employee_roster(
        file_content=xlsx,
        org_node_id="xj-s01-ft",
        created_by="test",
        session=session,
    )

    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_missing_columns():
    """缺少必须列应返回错误"""
    from openpyxl import Workbook
    from src.services.hr.hr_import_service import HRImportService

    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "手机"])  # 缺少岗位、入职日期等
    ws.append(["张三", "13900000001"])
    buf = BytesIO()
    wb.save(buf)

    session = AsyncMock()
    svc = HRImportService()
    result = await svc.import_employee_roster(
        file_content=buf.getvalue(),
        org_node_id="xj-s01-ft",
        created_by="test",
        session=session,
    )

    assert result["imported"] == 0
    assert len(result["errors"]) == 1
    assert "缺少必须列" in result["errors"][0]


@pytest.mark.asyncio
async def test_import_duplicate_phone_skipped():
    """手机号已存在应跳过"""
    from src.services.hr.hr_import_service import HRImportService

    xlsx = _create_test_xlsx([
        ["张三", "13900000001", "服务员", "2024-06-15", "固定月薪", 3500],
    ])

    session = AsyncMock()
    # Simulate existing phone found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = uuid.uuid4()
    session.execute.return_value = mock_result

    svc = HRImportService()
    result = await svc.import_employee_roster(
        file_content=xlsx,
        org_node_id="xj-s01-ft",
        created_by="test",
        session=session,
    )

    assert result["imported"] == 0
    assert result["skipped"] == 1


@pytest.mark.asyncio
async def test_import_invalid_date_error():
    """无效日期应记录行错误"""
    from src.services.hr.hr_import_service import HRImportService

    xlsx = _create_test_xlsx([
        ["张三", "13900000001", "服务员", "not-a-date", "固定月薪", 3500],
    ])

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    # mock add to assign id
    def mock_add(obj):
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = uuid.uuid4()
    session.add = mock_add

    svc = HRImportService()
    result = await svc.import_employee_roster(
        file_content=xlsx,
        org_node_id="xj-s01-ft",
        created_by="test",
        session=session,
    )

    assert len(result["errors"]) >= 1
    assert "第2行" in result["errors"][0]


# ── P1-F: Authoritative Mode ────────────────────────────────────────


@pytest.mark.asyncio
async def test_authoritative_mode_raises():
    """HR_AUTHORITATIVE=true 时，HR 写入失败应抛出异常"""
    with patch.dict(os.environ, {"HR_AUTHORITATIVE": "true"}):
        # Re-import to pick up the env change
        import importlib
        import src.services.hr.double_write_service as dw_mod
        importlib.reload(dw_mod)

        try:
            svc = dw_mod.DoubleWriteService()

            # Create a mock employee that will cause _do_create to fail
            mock_emp = MagicMock()
            mock_emp.id = "emp-test-001"

            # Patch _do_create to raise
            with patch.object(svc, "_do_create", side_effect=RuntimeError("DB down")):
                with pytest.raises(RuntimeError, match="DB down"):
                    await svc.on_employee_created(mock_emp)
        finally:
            # Reset to default
            with patch.dict(os.environ, {"HR_AUTHORITATIVE": "false"}):
                importlib.reload(dw_mod)


@pytest.mark.asyncio
async def test_non_authoritative_mode_swallows():
    """默认非权威模式下，HR 写入失败应返回 False（不抛异常）"""
    with patch.dict(os.environ, {"HR_AUTHORITATIVE": "false"}):
        import importlib
        import src.services.hr.double_write_service as dw_mod
        importlib.reload(dw_mod)

        svc = dw_mod.DoubleWriteService()
        mock_emp = MagicMock()
        mock_emp.id = "emp-test-002"

        with patch.object(svc, "_do_create", side_effect=RuntimeError("DB down")):
            result = await svc.on_employee_created(mock_emp)
            assert result is False


# ── P1-E: z62 Migration — Model Check ───────────────────────────────


def test_z62_migration_columns():
    """DailyAttendance 模型应有 scheduled_start_time 和 scheduled_end_time"""
    from src.models.hr.daily_attendance import DailyAttendance

    assert hasattr(DailyAttendance, "scheduled_start_time")
    assert hasattr(DailyAttendance, "scheduled_end_time")

    # Verify column types
    col_start = DailyAttendance.__table__.columns["scheduled_start_time"]
    col_end = DailyAttendance.__table__.columns["scheduled_end_time"]
    assert col_start.nullable is True
    assert col_end.nullable is True
