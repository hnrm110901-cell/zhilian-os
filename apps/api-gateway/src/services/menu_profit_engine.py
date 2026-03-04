"""
Task4: MenuProfitEngine — 菜品渠道毛利分析引擎

计算公式：
  revenue_fen   = price_fen × (1 - platform_commission_pct)
  total_cost    = bom_cost_fen + packaging_cost_fen + delivery_cost_fen
  gross_profit  = revenue_fen - total_cost
  gross_margin  = gross_profit / revenue_fen  (revenue_fen > 0 时)
  label         = 赚钱 (>30%) / 勉强 (>0%) / 亏钱 (≤0%)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dish import Dish
from src.models.dish_channel import DishChannelConfig
from src.models.channel_config import SalesChannelConfig
from src.models.store import Store
from src.services.bom_resolver import BOMResolverService

logger = structlog.get_logger()


@dataclass
class DishChannelProfit:
    """单道菜 × 单渠道的毛利分析结果"""
    dish_id: str
    dish_name: str
    channel: str
    store_id: str
    price_fen: int
    revenue_fen: Decimal                # 扣佣后到手金额
    bom_cost_fen: Decimal               # BOM 食材成本
    packaging_cost_fen: int             # 包材费
    delivery_cost_fen: int              # 配送费
    total_cost_fen: Decimal             # 总成本
    gross_profit_fen: Decimal           # 毛利
    gross_margin_pct: float             # 毛利率（0~1 float）
    label: str                          # 赚钱 / 勉强 / 亏钱
    bom_source_ids: List[str] = field(default_factory=list)


def _resolve_channel_config(
    brand_configs: List[SalesChannelConfig],
    default_configs: List[SalesChannelConfig],
    channel: str,
) -> Optional[SalesChannelConfig]:
    """品牌级优先，fallback 集团默认（brand_id=None）"""
    for cfg in brand_configs:
        if cfg.channel == channel and cfg.is_active:
            return cfg
    for cfg in default_configs:
        if cfg.channel == channel and cfg.is_active:
            return cfg
    return None


class MenuProfitEngine:
    """
    菜品渠道毛利分析引擎（全静态方法，无状态）

    调用示例：
        result = await MenuProfitEngine.get_dish_channel_profit(
            session, dish_id, "meituan", store_id
        )
    """

    @staticmethod
    async def get_dish_channel_profit(
        session: AsyncSession,
        dish_id: str,
        channel: str,
        store_id: str,
    ) -> Optional[DishChannelProfit]:
        """
        计算单道菜在指定渠道的毛利。

        步骤：
        1. 查 DishChannelConfig(dish_id, channel) → price_fen；无记录 return None
        2. 查 Store.brand_id
        3. 查 SalesChannelConfig（品牌级优先，fallback brand_id=None）→ commission/costs
        4. BOMResolverService.resolve() → bom_cost_fen
        5. 计算各项指标
        """
        # 1. 渠道定价
        dcc_result = await session.execute(
            select(DishChannelConfig).where(
                DishChannelConfig.dish_id == dish_id,
                DishChannelConfig.channel == channel,
                DishChannelConfig.is_available == True,  # noqa: E712
            )
        )
        dcc: Optional[DishChannelConfig] = dcc_result.scalar_one_or_none()
        if dcc is None:
            return None

        # 取菜品名称
        dish_result = await session.execute(
            select(Dish).where(Dish.id == dish_id)
        )
        dish: Optional[Dish] = dish_result.scalar_one_or_none()
        dish_name = dish.name if dish else str(dish_id)

        # 2. 门店 brand_id
        store_result = await session.execute(
            select(Store).where(Store.id == store_id)
        )
        store: Optional[Store] = store_result.scalar_one_or_none()
        brand_id = store.brand_id if store else None

        # 3. 渠道成本配置
        channel_cfgs_result = await session.execute(
            select(SalesChannelConfig).where(
                SalesChannelConfig.channel == channel,
                SalesChannelConfig.is_active == True,  # noqa: E712
            )
        )
        all_cfgs: List[SalesChannelConfig] = list(channel_cfgs_result.scalars().all())
        brand_cfgs = [c for c in all_cfgs if c.brand_id == brand_id] if brand_id else []
        default_cfgs = [c for c in all_cfgs if c.brand_id is None]

        ch_cfg = _resolve_channel_config(brand_cfgs, default_cfgs, channel)
        commission_pct = Decimal(str(ch_cfg.platform_commission_pct)) if ch_cfg else Decimal("0")
        packaging_cost = ch_cfg.packaging_cost_fen if ch_cfg else 0
        delivery_cost = ch_cfg.delivery_cost_fen if ch_cfg else 0

        # 4. BOM 成本
        resolved = await BOMResolverService.resolve(session, dish_id, store_id, channel)
        bom_cost = resolved.total_bom_cost_fen

        # 5. 毛利计算
        price = Decimal(str(dcc.price_fen))
        revenue = price * (Decimal("1") - commission_pct)
        total_cost = bom_cost + Decimal(str(packaging_cost)) + Decimal(str(delivery_cost))
        gross_profit = revenue - total_cost

        if revenue > 0:
            margin_pct = float(gross_profit / revenue)
        else:
            margin_pct = 0.0

        if margin_pct > 0.30:
            label = "赚钱"
        elif margin_pct > 0:
            label = "勉强"
        else:
            label = "亏钱"

        return DishChannelProfit(
            dish_id=str(dish_id),
            dish_name=dish_name,
            channel=channel,
            store_id=store_id,
            price_fen=dcc.price_fen,
            revenue_fen=revenue,
            bom_cost_fen=bom_cost,
            packaging_cost_fen=packaging_cost,
            delivery_cost_fen=delivery_cost,
            total_cost_fen=total_cost,
            gross_profit_fen=gross_profit,
            gross_margin_pct=margin_pct,
            label=label,
            bom_source_ids=resolved.source_bom_ids,
        )

    @staticmethod
    async def get_store_channel_report(
        session: AsyncSession,
        store_id: str,
    ) -> List[DishChannelProfit]:
        """
        批量计算门店所有上架菜品 × 渠道的毛利报告。
        """
        # 取门店所有 is_available DishChannelConfig（关联 dish 存在）
        dccs_result = await session.execute(
            select(DishChannelConfig)
            .join(Dish, DishChannelConfig.dish_id == Dish.id)
            .where(
                Dish.store_id == store_id,
                DishChannelConfig.is_available == True,  # noqa: E712
            )
        )
        dccs: List[DishChannelConfig] = list(dccs_result.scalars().all())

        results: List[DishChannelProfit] = []
        for dcc in dccs:
            profit = await MenuProfitEngine.get_dish_channel_profit(
                session, str(dcc.dish_id), dcc.channel, store_id
            )
            if profit is not None:
                results.append(profit)

        return results
