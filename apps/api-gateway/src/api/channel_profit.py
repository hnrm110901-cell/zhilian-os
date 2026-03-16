"""
渠道毛利 API

端点：
  GET /api/v1/channel-profit/{store_id}
      → 门店所有菜品渠道毛利报告

  GET /api/v1/channel-profit/{store_id}/dish/{dish_id}?channel=meituan
      → 单菜品在指定渠道的毛利详情

  GET /api/v1/channel-profit/{store_id}/labels?label=亏钱|勉强|赚钱
      → 按标注过滤菜品渠道毛利
"""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.menu_profit_engine import DishChannelProfit, MenuProfitEngine

router = APIRouter(prefix="/api/v1/channel-profit", tags=["channel_profit"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class DishChannelProfitResponse(BaseModel):
    """渠道毛利响应（分 → 元转换）"""

    dish_id: str
    dish_name: str
    channel: str
    store_id: str
    price_yuan: float
    revenue_yuan: float  # 扣佣后到手金额（元）
    bom_cost_yuan: float  # BOM 食材成本（元）
    packaging_cost_yuan: float  # 包材费（元）
    delivery_cost_yuan: float  # 配送费（元）
    total_cost_yuan: float  # 总成本（元）
    gross_profit_yuan: float  # 毛利（元）
    gross_margin_pct: float  # 毛利率（0~1 float）
    label: str  # 赚钱 / 勉强 / 亏钱
    bom_source_ids: List[str]

    @classmethod
    def from_dataclass(cls, d: DishChannelProfit) -> "DishChannelProfitResponse":
        def _to_yuan(v) -> float:
            return round(float(v) / 100, 2)

        return cls(
            dish_id=d.dish_id,
            dish_name=d.dish_name,
            channel=d.channel,
            store_id=d.store_id,
            price_yuan=_to_yuan(d.price_fen),
            revenue_yuan=_to_yuan(d.revenue_fen),
            bom_cost_yuan=_to_yuan(d.bom_cost_fen),
            packaging_cost_yuan=_to_yuan(d.packaging_cost_fen),
            delivery_cost_yuan=_to_yuan(d.delivery_cost_fen),
            total_cost_yuan=_to_yuan(d.total_cost_fen),
            gross_profit_yuan=_to_yuan(d.gross_profit_fen),
            gross_margin_pct=d.gross_margin_pct,
            label=d.label,
            bom_source_ids=d.bom_source_ids,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/{store_id}", response_model=List[DishChannelProfitResponse])
async def get_store_channel_report(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """门店所有上架菜品 × 渠道的实时毛利看板"""
    results = await MenuProfitEngine.get_store_channel_report(db, store_id)
    return [DishChannelProfitResponse.from_dataclass(r) for r in results]


@router.get("/{store_id}/dish/{dish_id}", response_model=DishChannelProfitResponse)
async def get_dish_channel_profit(
    store_id: str,
    dish_id: str,
    channel: str = Query(..., description="渠道标识，如 meituan / eleme / 堂食"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单菜品在指定渠道的毛利详情"""
    result = await MenuProfitEngine.get_dish_channel_profit(db, dish_id, channel, store_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到菜品 {dish_id} 在渠道 {channel} 的定价配置")
    return DishChannelProfitResponse.from_dataclass(result)


@router.get("/{store_id}/labels", response_model=List[DishChannelProfitResponse])
async def get_by_label(
    store_id: str,
    label: str = Query(..., description="标注过滤：亏钱|勉强|赚钱"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按利润标注过滤门店菜品渠道毛利"""
    valid_labels = {"亏钱", "勉强", "赚钱"}
    if label not in valid_labels:
        raise HTTPException(status_code=400, detail=f"label 必须是 {valid_labels} 之一")

    results = await MenuProfitEngine.get_store_channel_report(db, store_id)
    filtered = [r for r in results if r.label == label]
    return [DishChannelProfitResponse.from_dataclass(r) for r in filtered]
