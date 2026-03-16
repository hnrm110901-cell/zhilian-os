"""
Unified Brain API — 每日1决策

端点：
  GET  /today        — 今日最重要的1个决策
  GET  /push-preview — 推送预览文案
"""

from datetime import date

from fastapi import APIRouter, Query
from src.services.unified_brain import BrainInput, format_push_message, pick_top_decision

router = APIRouter(prefix="/api/v1/brain", tags=["unified-brain"])


def _demo_context(store_id: str, d: date) -> BrainInput:
    """演示上下文，生产环境替换为真实DB聚合"""
    return BrainInput(
        store_id=store_id,
        date=d.isoformat(),
        # 食材成本
        cost_actual_pct=34.2,
        cost_target_pct=32.0,
        cost_variance_pct=2.8,
        cost_top_factor="usage_overrun",
        cost_top_action="酸菜鱼鱼片克重 380g→350g，通知厨师长调整切配标准",
        cost_saving_yuan=12800,
        # 人力
        labor_cost_rate=26.5,
        labor_target_rate=25.0,
        labor_saving_yuan=3200,
        labor_suggestion="明日周一客流预测偏低，建议减排1人（前厅）",
        # 库存
        critical_inventory_count=0,
        # 损耗
        waste_rate_pct=4.2,
        waste_target_pct=3.0,
        waste_top_item="鲈鱼",
        waste_saving_yuan=5600,
        waste_action="鲈鱼损耗率12%（行业P10=6%），建议引入切配称重抽检",
        # 营收
        revenue_yesterday_yuan=28560,
        revenue_change_pct=12.0,
        # 历史
        last_advice_adopted=True,
        last_advice_saving_yuan=2100,
    )


@router.get("/stores/{store_id}/today")
async def get_today_decision(
    store_id: str,
    target_date: date = Query(default=None),
):
    """今日最重要的1个决策"""
    d = target_date or date.today()
    ctx = _demo_context(store_id, d)
    card = pick_top_decision(ctx)

    if card is None:
        return {
            "store_id": store_id,
            "date": d.isoformat(),
            "has_decision": False,
            "message": "今日经营状况良好，暂无需要立即处理的事项",
        }

    return {
        "store_id": store_id,
        "date": d.isoformat(),
        "has_decision": True,
        "decision": {
            "title": card.title,
            "action": card.action,
            "expected_saving_yuan": card.expected_saving_yuan,
            "confidence_pct": card.confidence_pct,
            "severity": card.severity,
            "detail": card.detail,
            "executor": card.executor,
            "deadline_hours": card.deadline_hours,
            "category": card.category,
            "source": card.source,
        },
        "cumulative_saving_yuan": ctx.last_advice_saving_yuan if ctx.last_advice_adopted else 0,
    }


@router.get("/stores/{store_id}/push-preview")
async def get_push_preview(
    store_id: str,
    target_date: date = Query(default=None),
):
    """推送消息预览"""
    d = target_date or date.today()
    ctx = _demo_context(store_id, d)
    card = pick_top_decision(ctx)

    if card is None:
        return {"store_id": store_id, "message": "无需推送"}

    cumulative = ctx.last_advice_saving_yuan if ctx.last_advice_adopted else 0
    return {
        "store_id": store_id,
        "push_text": format_push_message(card, cumulative),
    }
