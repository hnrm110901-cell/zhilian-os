"""
Integration tests for WasteGuardService (B3)

Covers:
1. check_and_alert: 空 variances → 返回空列表
2. check_and_alert: |diff_pct| ≤ 10% → 不触发告警
3. check_and_alert: |diff_pct| > 10% → 触发告警，返回 event_id
4. check_and_alert: 推理超时 → 静默忽略，不抛异常
5. check_and_alert: 企微推送失败 → 静默忽略
6. generate_monthly_report: 正常返回四维字段
7. generate_monthly_report: DB 无数据 → 返回空列表各维度
8. cross_store_bom_drift_alert: 无 BOM 记录 → 返回空列表
9. cross_store_bom_drift_alert: 同菜品跨店偏差 > 阈值 → 触发告警
10. check_and_alert: 多个 variance 中部分超阈值 → 只有超阈值的被触发
"""
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Module stubs ──────────────────────────────────────────────────────────────
sys.modules.setdefault("structlog", MagicMock(get_logger=MagicMock(return_value=MagicMock(
    info=MagicMock(), warning=MagicMock(), error=MagicMock(), debug=MagicMock()
))))
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())
sys.modules.setdefault("src.ontology", MagicMock())

for mod in [
    "src.models", "src.models.waste_event", "src.models.order",
    "src.models.bom", "src.models.dish_master",
    "src.services.waste_reasoning_service",
    "src.services.wechat_work_message_service",
]:
    sys.modules.setdefault(mod, MagicMock())

from src.services.waste_guard_service import WasteGuardService  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session():
    session = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_reasoning_result(top3=None):
    return {
        "top3_root_causes": top3 or [
            {"dimension": "staff", "reason": "员工操作不规范", "score": 80},
            {"dimension": "supplier", "reason": "供应商批次问题", "score": 60},
        ]
    }


# ── Tests: check_and_alert ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_and_alert_empty_variances():
    """空 variances → 直接返回空列表，不调用推理或企微"""
    session = _make_session()
    result = await WasteGuardService.check_and_alert(
        session=session,
        store_id="S001",
        tenant_id="T001",
        variances=[],
    )
    assert result == []


@pytest.mark.asyncio
async def test_check_and_alert_below_threshold():
    """|diff_pct| = 9.5% ≤ 10% → 不触发"""
    session = _make_session()
    variances = [
        {"ingredient_id": "ING001", "diff_rate_pct": 9.5, "ingredient_name": "猪肉"},
        {"ingredient_id": "ING002", "diff_rate_pct": -8.0, "ingredient_name": "鸡蛋"},
    ]
    result = await WasteGuardService.check_and_alert(
        session=session,
        store_id="S001",
        tenant_id="T001",
        variances=variances,
    )
    assert result == []


@pytest.mark.asyncio
async def test_check_and_alert_above_threshold_triggers_alert():
    """|diff_pct| = 25% > 10% → 触发告警，返回非空 event_id 列表"""
    session = _make_session()
    variances = [
        {"ingredient_id": "ING001", "diff_rate_pct": 25.0, "ingredient_name": "猪肉"},
    ]

    mock_reasoning = AsyncMock(return_value=_make_reasoning_result())
    mock_send_card = AsyncMock(return_value={"success": True})

    async def _pass_through(coro, timeout):
        return await coro

    import src.services.waste_guard_service as _wgs_mod
    import src.services.waste_reasoning_service as _wrs_mod

    with patch.object(_wgs_mod.asyncio, "wait_for", side_effect=_pass_through), \
         patch.object(_wrs_mod, "run_waste_reasoning", mock_reasoning), \
         patch("src.services.wechat_work_message_service.wechat_work_message_service", MagicMock(send_card_message=mock_send_card)):
        result = await WasteGuardService.check_and_alert(
            session=session,
            store_id="S001",
            tenant_id="T001",
            variances=variances,
        )

    assert len(result) == 1
    assert result[0].startswith("WG-")


@pytest.mark.asyncio
async def test_check_and_alert_timeout_silently_ignored():
    """推理超时 → 静默忽略，返回空列表（不抛异常）"""
    session = _make_session()
    variances = [
        {"ingredient_id": "ING001", "diff_rate_pct": 30.0, "ingredient_name": "猪肉"},
    ]

    async def _timeout_coro(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("src.services.waste_guard_service.asyncio.wait_for", new=AsyncMock(side_effect=_timeout_coro)):
        result = await WasteGuardService.check_and_alert(
            session=session,
            store_id="S001",
            tenant_id="T001",
            variances=variances,
        )

    # 超时被静默处理，返回空列表
    assert result == []


@pytest.mark.asyncio
async def test_check_and_alert_wechat_failure_silently_ignored():
    """企微推送失败 → 静默忽略"""
    session = _make_session()
    variances = [
        {"ingredient_id": "ING001", "diff_rate_pct": 20.0, "ingredient_name": "猪肉"},
    ]

    call_count = 0

    async def _side_effect(coro, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 推理成功
            return _make_reasoning_result()
        else:
            # 企微失败
            raise Exception("微信接口超时")

    with patch("src.services.waste_guard_service.asyncio.wait_for", new=AsyncMock(side_effect=_side_effect)):
        with patch.dict(sys.modules, {
            "src.services.waste_reasoning_service": MagicMock(
                run_waste_reasoning=AsyncMock(return_value=_make_reasoning_result())
            ),
        }):
            # 不抛异常即可
            result = await WasteGuardService.check_and_alert(
                session=session,
                store_id="S001",
                tenant_id="T001",
                variances=variances,
            )
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_check_and_alert_partial_threshold():
    """多 variances 中只有超阈值的被触发"""
    session = _make_session()
    variances = [
        {"ingredient_id": "ING001", "diff_rate_pct": 5.0,  "ingredient_name": "葱"},   # below
        {"ingredient_id": "ING002", "diff_rate_pct": 15.0, "ingredient_name": "猪肉"}, # above
        {"ingredient_id": "ING003", "diff_rate_pct": -12.0, "ingredient_name": "鸡蛋"},# above (abs)
    ]

    triggered_ingredients = []

    async def _fake_wait_for(coro, timeout):
        return await coro

    mock_reasoning = AsyncMock(return_value=_make_reasoning_result())

    async def _fake_send_card(user_id, title, description, url, btntxt):
        triggered_ingredients.append(title)
        return {"success": True}

    import src.services.waste_guard_service as _wgs_mod
    import src.services.waste_reasoning_service as _wrs_mod

    with patch.object(_wgs_mod.asyncio, "wait_for", new=_fake_wait_for), \
         patch.object(_wrs_mod, "run_waste_reasoning", mock_reasoning), \
         patch("src.services.wechat_work_message_service.wechat_work_message_service", MagicMock(send_card_message=AsyncMock(side_effect=_fake_send_card))):
        result = await WasteGuardService.check_and_alert(
            session=session,
            store_id="S001",
            tenant_id="T001",
            variances=variances,
        )

    # 只有 ING002 和 ING003 超阈值
    assert len(result) == 2


# ── Tests: generate_monthly_report ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_monthly_report_structure():
    """返回 by_ingredient / by_staff / by_shift / by_channel / period 五个字段"""
    empty_rows = MagicMock()
    empty_rows.all = MagicMock(return_value=[])
    empty_rows.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    session = _make_session()
    session.execute = AsyncMock(return_value=empty_rows)

    # Patch sqlalchemy.select + func to bypass Column validation with mocked models
    chainable = MagicMock()
    chainable.where = MagicMock(return_value=chainable)
    chainable.group_by = MagicMock(return_value=chainable)
    chainable.order_by = MagicMock(return_value=chainable)
    chainable.limit = MagicMock(return_value=chainable)
    chainable.offset = MagicMock(return_value=chainable)
    chainable.join = MagicMock(return_value=chainable)

    with patch("sqlalchemy.select", return_value=chainable), \
         patch("sqlalchemy.func", MagicMock(
             sum=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
             count=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
             avg=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
         )):
        result = await WasteGuardService.generate_monthly_report(
            session=session,
            store_id="S001",
            year=2026,
            month=2,
        )

    assert "period" in result
    assert "by_ingredient" in result
    assert "by_staff" in result
    assert "by_shift" in result
    assert "by_channel" in result
    assert result["period"]["year"] == 2026
    assert result["period"]["month"] == 2


@pytest.mark.asyncio
async def test_generate_monthly_report_empty_db():
    """DB 无数据 → 各维度均为空列表"""
    empty_rows = MagicMock()
    empty_rows.all = MagicMock(return_value=[])

    session = _make_session()
    session.execute = AsyncMock(return_value=empty_rows)

    chainable = MagicMock()
    chainable.where = MagicMock(return_value=chainable)
    chainable.group_by = MagicMock(return_value=chainable)
    chainable.order_by = MagicMock(return_value=chainable)
    chainable.limit = MagicMock(return_value=chainable)
    chainable.join = MagicMock(return_value=chainable)

    with patch("sqlalchemy.select", return_value=chainable), \
         patch("sqlalchemy.func", MagicMock(
             sum=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
             count=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
             avg=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
         )):
        result = await WasteGuardService.generate_monthly_report(
            session=session,
            store_id="S001",
            year=2026,
            month=1,
        )

    assert result["by_ingredient"] == []
    assert result["by_staff"] == []
    assert result["by_shift"] == []


# ── Tests: cross_store_bom_drift_alert ───────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_store_bom_drift_no_records():
    """无 BOM 记录 → 返回空列表"""
    session = _make_session()

    empty_result = MagicMock()
    empty_result.all = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty_result)

    with patch.dict(sys.modules, {
        "src.models.bom": MagicMock(BOMTemplate=MagicMock(), BOMItem=MagicMock()),
        "src.models.dish_master": MagicMock(DishMaster=MagicMock()),
    }):
        result = await WasteGuardService.cross_store_bom_drift_alert(
            session=session,
            tenant_id="T001",
            threshold_pct=20.0,
        )

    assert result == []


@pytest.mark.asyncio
async def test_cross_store_bom_drift_above_threshold():
    """同菜品两门店BOM偏差 > 20% → 触发告警"""
    dish_id = str(uuid4())
    session = _make_session()

    row1 = MagicMock()
    row1.dish_id = dish_id
    row1.store_id = "STORE001"
    row1.total_qty = 100.0

    row2 = MagicMock()
    row2.dish_id = dish_id
    row2.store_id = "STORE002"
    row2.total_qty = 200.0  # avg=150, each drifts >20%

    query_result = MagicMock()
    query_result.all = MagicMock(return_value=[row1, row2])
    session.execute = AsyncMock(return_value=query_result)

    # Chainable mock to bypass SQLAlchemy select() column validation
    chainable = MagicMock()
    chainable.join = MagicMock(return_value=chainable)
    chainable.where = MagicMock(return_value=chainable)
    chainable.group_by = MagicMock(return_value=chainable)

    with patch("sqlalchemy.select", return_value=chainable), \
         patch("sqlalchemy.func", MagicMock(
             sum=MagicMock(return_value=MagicMock(label=MagicMock(return_value=MagicMock()))),
         )):
        with patch.dict(sys.modules, {
            "src.services.wechat_work_message_service": MagicMock(
                wechat_work_message_service=MagicMock(
                    send_card_message=AsyncMock(return_value={"success": True})
                )
            ),
        }):
            with patch("src.services.waste_guard_service.asyncio.wait_for",
                       side_effect=lambda coro, timeout: coro):
                result = await WasteGuardService.cross_store_bom_drift_alert(
                    session=session,
                    tenant_id="T001",
                    threshold_pct=20.0,
                )

    # 均值150，两个都偏差>20%，应触发2条告警
    assert len(result) >= 1
    for alert in result:
        assert "dish_id" in alert
        assert "drift_pct" in alert
        assert alert["drift_pct"] > 20.0
