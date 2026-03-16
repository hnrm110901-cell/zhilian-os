"""
全渠道营收分析 Service — OmniChannel Revenue Dashboard

聚合所有销售渠道（堂食/饿了么/美团/抖音团购/自提/企业团餐）的营收数据，
提供渠道分解、趋势、对比、利润瀑布、渠道混合、峰时分析等能力。

金额说明：
  - Order.total_amount  → Numeric(10,2)，单位 yuan
  - Order.final_amount  → Integer，单位 fen
  - SalesChannelConfig.delivery_cost_fen / packaging_cost_fen → Integer，单位 fen
  - SalesChannelConfig.platform_commission_pct → Numeric(6,4)，0.1800 = 18%
  - 本 Service 对外返回统一使用「元」，保留 2 位小数
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.channel_config import SalesChannelConfig
from src.models.order import Order, OrderStatus

logger = structlog.get_logger()

# 渠道中文名映射
CHANNEL_LABELS: Dict[str, str] = {
    "dine_in": "堂食",
    "eleme": "外卖饿了么",
    "meituan": "外卖美团",
    "douyin": "抖音团购",
    "pickup": "自提",
    "corporate": "企业团餐",
}

ALL_CHANNELS = list(CHANNEL_LABELS.keys())


def _fen_to_yuan(fen: int) -> float:
    """分 → 元，保留 2 位小数"""
    return round(fen / 100, 2) if fen else 0.00


def _decimal_to_float(val: Any) -> float:
    """Decimal / None → float"""
    if val is None:
        return 0.00
    return round(float(val), 2)


class OmniChannelService:
    """全渠道营收分析"""

    # ──────────────────────────────────────────────────────────────────
    # 1. 渠道营收分解
    # ──────────────────────────────────────────────────────────────────
    async def get_channel_revenue(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        各渠道营收分解：订单量、毛收入、佣金、配送费、净收入。
        同时返回全渠道合计。
        """
        # 查询每渠道的订单量 & 毛收入（final_amount 单位 fen）
        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start_date,
            func.date(Order.order_time) <= end_date,
        ]
        # brand_id 通过 store 关联；这里暂用 store_id 级别
        if store_id:
            filters.append(Order.store_id == store_id)

        order_q = (
            select(
                Order.sales_channel,
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("gross_fen"),
            )
            .where(and_(*filters))
            .group_by(Order.sales_channel)
        )
        result = await db.execute(order_q)
        rows = result.all()

        # 渠道成本配置
        config_map = await self._load_channel_configs(db, brand_id)

        channels: List[Dict[str, Any]] = []
        total_orders = 0
        total_gross_fen = 0
        total_commission_fen = 0
        total_delivery_fen = 0
        total_net_fen = 0

        for row in rows:
            ch = row.sales_channel or "dine_in"
            order_count = row.order_count
            gross_fen = int(row.gross_fen)

            cfg = config_map.get(ch)
            commission_pct = float(cfg.platform_commission_pct) if cfg else 0.0
            delivery_per_order = int(cfg.delivery_cost_fen) if cfg else 0
            packaging_per_order = int(cfg.packaging_cost_fen) if cfg else 0

            commission_fen = int(gross_fen * commission_pct)
            delivery_fen = delivery_per_order * order_count
            packaging_fen = packaging_per_order * order_count
            net_fen = gross_fen - commission_fen - delivery_fen - packaging_fen

            channels.append(
                {
                    "channel": ch,
                    "channel_label": CHANNEL_LABELS.get(ch, ch),
                    "order_count": order_count,
                    "gross_revenue_yuan": _fen_to_yuan(gross_fen),
                    "commission_yuan": _fen_to_yuan(commission_fen),
                    "commission_rate": round(commission_pct * 100, 2),
                    "delivery_cost_yuan": _fen_to_yuan(delivery_fen),
                    "packaging_cost_yuan": _fen_to_yuan(packaging_fen),
                    "net_revenue_yuan": _fen_to_yuan(net_fen),
                }
            )

            total_orders += order_count
            total_gross_fen += gross_fen
            total_commission_fen += commission_fen
            total_delivery_fen += delivery_fen
            total_net_fen += net_fen

        # 计算各渠道占比
        for ch in channels:
            ch["share_pct"] = (
                round(ch["gross_revenue_yuan"] / _fen_to_yuan(total_gross_fen) * 100, 1) if total_gross_fen > 0 else 0.0
            )

        channels.sort(key=lambda c: c["gross_revenue_yuan"], reverse=True)

        return {
            "period": f"{start_date} ~ {end_date}",
            "store_id": store_id,
            "total": {
                "order_count": total_orders,
                "gross_revenue_yuan": _fen_to_yuan(total_gross_fen),
                "commission_yuan": _fen_to_yuan(total_commission_fen),
                "delivery_cost_yuan": _fen_to_yuan(total_delivery_fen),
                "net_revenue_yuan": _fen_to_yuan(total_net_fen),
            },
            "channels": channels,
        }

    # ──────────────────────────────────────────────────────────────────
    # 2. 每日营收趋势（按渠道）
    # ──────────────────────────────────────────────────────────────────
    async def get_revenue_trend(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str],
        days: int = 30,
    ) -> Dict[str, Any]:
        """最近 N 天每日各渠道营收趋势，用于堆叠柱状图"""
        end = date.today()
        start = end - timedelta(days=days - 1)

        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start,
            func.date(Order.order_time) <= end,
        ]
        if store_id:
            filters.append(Order.store_id == store_id)

        q = (
            select(
                func.date(Order.order_time).label("day"),
                Order.sales_channel,
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("revenue_fen"),
            )
            .where(and_(*filters))
            .group_by(func.date(Order.order_time), Order.sales_channel)
            .order_by(func.date(Order.order_time))
        )
        result = await db.execute(q)
        rows = result.all()

        # 构建日期 → 渠道 → 数值 映射
        trend_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            day_str = str(row.day)
            ch = row.sales_channel or "dine_in"
            if day_str not in trend_map:
                trend_map[day_str] = {}
            trend_map[day_str][ch] = {
                "order_count": row.order_count,
                "revenue_yuan": _fen_to_yuan(int(row.revenue_fen)),
            }

        # 填充所有日期和渠道确保前端无空洞
        trend: List[Dict[str, Any]] = []
        current = start
        while current <= end:
            day_str = str(current)
            day_data: Dict[str, Any] = {"date": day_str, "channels": {}}
            day_total = 0.0
            for ch in ALL_CHANNELS:
                ch_data = trend_map.get(day_str, {}).get(
                    ch,
                    {
                        "order_count": 0,
                        "revenue_yuan": 0.00,
                    },
                )
                day_data["channels"][ch] = ch_data
                day_total += ch_data["revenue_yuan"]
            day_data["total_revenue_yuan"] = round(day_total, 2)
            trend.append(day_data)
            current += timedelta(days=1)

        return {
            "days": days,
            "start_date": str(start),
            "end_date": str(end),
            "store_id": store_id,
            "trend": trend,
        }

    # ──────────────────────────────────────────────────────────────────
    # 3. 渠道对比（客单价、频率、峰值时段）
    # ──────────────────────────────────────────────────────────────────
    async def get_channel_comparison(
        self,
        db: AsyncSession,
        brand_id: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """各渠道对比：客单价、订单量、峰值小时"""
        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start_date,
            func.date(Order.order_time) <= end_date,
        ]

        # 基础聚合
        base_q = (
            select(
                Order.sales_channel,
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("total_fen"),
                func.coalesce(func.avg(Order.final_amount), 0).label("avg_fen"),
            )
            .where(and_(*filters))
            .group_by(Order.sales_channel)
        )
        base_result = await db.execute(base_q)
        base_rows = base_result.all()

        # 各渠道峰值小时
        peak_q = (
            select(
                Order.sales_channel,
                extract("hour", Order.order_time).label("hour"),
                func.count().label("cnt"),
            )
            .where(and_(*filters))
            .group_by(Order.sales_channel, extract("hour", Order.order_time))
        )
        peak_result = await db.execute(peak_q)
        peak_rows = peak_result.all()

        # 找每渠道订单量最高的小时
        peak_map: Dict[str, int] = {}
        peak_counts: Dict[str, int] = {}
        for row in peak_rows:
            ch = row.sales_channel or "dine_in"
            if ch not in peak_counts or row.cnt > peak_counts[ch]:
                peak_counts[ch] = row.cnt
                peak_map[ch] = int(row.hour)

        config_map = await self._load_channel_configs(db, brand_id)

        comparisons: List[Dict[str, Any]] = []
        for row in base_rows:
            ch = row.sales_channel or "dine_in"
            cfg = config_map.get(ch)
            commission_rate = float(cfg.platform_commission_pct) * 100 if cfg else 0.0
            gross_fen = int(row.total_fen)
            commission_fen = int(gross_fen * (commission_rate / 100))
            net_fen = gross_fen - commission_fen

            comparisons.append(
                {
                    "channel": ch,
                    "channel_label": CHANNEL_LABELS.get(ch, ch),
                    "order_count": row.order_count,
                    "total_revenue_yuan": _fen_to_yuan(gross_fen),
                    "avg_order_yuan": _fen_to_yuan(int(row.avg_fen)),
                    "commission_rate_pct": round(commission_rate, 2),
                    "net_revenue_yuan": _fen_to_yuan(net_fen),
                    "peak_hour": peak_map.get(ch),
                }
            )

        comparisons.sort(key=lambda c: c["total_revenue_yuan"], reverse=True)

        # 计算占比
        grand_total = sum(c["total_revenue_yuan"] for c in comparisons)
        for c in comparisons:
            c["share_pct"] = round(c["total_revenue_yuan"] / grand_total * 100, 1) if grand_total > 0 else 0.0

        return {
            "period": f"{start_date} ~ {end_date}",
            "comparisons": comparisons,
        }

    # ──────────────────────────────────────────────────────────────────
    # 4. 渠道利润（净利润 = 毛收入 - 佣金 - 配送 - 包材）
    # ──────────────────────────────────────────────────────────────────
    async def get_profit_by_channel(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        利润瀑布：毛收入 → 扣佣金 → 扣配送 → 扣包材 → 净利润
        """
        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start_date,
            func.date(Order.order_time) <= end_date,
        ]
        if store_id:
            filters.append(Order.store_id == store_id)

        q = (
            select(
                Order.sales_channel,
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("gross_fen"),
            )
            .where(and_(*filters))
            .group_by(Order.sales_channel)
        )
        result = await db.execute(q)
        rows = result.all()

        config_map = await self._load_channel_configs(db, brand_id)

        waterfall: List[Dict[str, Any]] = []
        total_gross = 0
        total_commission = 0
        total_delivery = 0
        total_packaging = 0
        total_net = 0

        for row in rows:
            ch = row.sales_channel or "dine_in"
            order_count = row.order_count
            gross_fen = int(row.gross_fen)

            cfg = config_map.get(ch)
            comm_pct = float(cfg.platform_commission_pct) if cfg else 0.0
            dlv_per = int(cfg.delivery_cost_fen) if cfg else 0
            pkg_per = int(cfg.packaging_cost_fen) if cfg else 0

            comm_fen = int(gross_fen * comm_pct)
            dlv_fen = dlv_per * order_count
            pkg_fen = pkg_per * order_count
            net_fen = gross_fen - comm_fen - dlv_fen - pkg_fen

            waterfall.append(
                {
                    "channel": ch,
                    "channel_label": CHANNEL_LABELS.get(ch, ch),
                    "order_count": order_count,
                    "gross_revenue_yuan": _fen_to_yuan(gross_fen),
                    "commission_yuan": _fen_to_yuan(comm_fen),
                    "delivery_cost_yuan": _fen_to_yuan(dlv_fen),
                    "packaging_cost_yuan": _fen_to_yuan(pkg_fen),
                    "net_profit_yuan": _fen_to_yuan(net_fen),
                    "margin_pct": round(net_fen / gross_fen * 100, 1) if gross_fen > 0 else 0.0,
                }
            )

            total_gross += gross_fen
            total_commission += comm_fen
            total_delivery += dlv_fen
            total_packaging += pkg_fen
            total_net += net_fen

        waterfall.sort(key=lambda w: w["net_profit_yuan"], reverse=True)

        return {
            "period": f"{start_date} ~ {end_date}",
            "store_id": store_id,
            "summary": {
                "gross_revenue_yuan": _fen_to_yuan(total_gross),
                "commission_yuan": _fen_to_yuan(total_commission),
                "delivery_cost_yuan": _fen_to_yuan(total_delivery),
                "packaging_cost_yuan": _fen_to_yuan(total_packaging),
                "net_profit_yuan": _fen_to_yuan(total_net),
                "overall_margin_pct": round(total_net / total_gross * 100, 1) if total_gross > 0 else 0.0,
            },
            "channels": waterfall,
        }

    # ──────────────────────────────────────────────────────────────────
    # 5. 渠道混合（百分比饼图）
    # ──────────────────────────────────────────────────────────────────
    async def get_channel_mix(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """最近 30 天各渠道营收占比，用于饼图"""
        end = date.today()
        start = end - timedelta(days=29)

        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start,
            func.date(Order.order_time) <= end,
        ]

        q = (
            select(
                Order.sales_channel,
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("revenue_fen"),
            )
            .where(and_(*filters))
            .group_by(Order.sales_channel)
            .order_by(func.sum(Order.final_amount).desc())
        )
        result = await db.execute(q)
        rows = result.all()

        total_fen = sum(int(r.revenue_fen) for r in rows)
        mix: List[Dict[str, Any]] = []
        for row in rows:
            ch = row.sales_channel or "dine_in"
            rev_fen = int(row.revenue_fen)
            mix.append(
                {
                    "channel": ch,
                    "channel_label": CHANNEL_LABELS.get(ch, ch),
                    "order_count": row.order_count,
                    "revenue_yuan": _fen_to_yuan(rev_fen),
                    "share_pct": round(rev_fen / total_fen * 100, 1) if total_fen > 0 else 0.0,
                }
            )

        return {
            "period": f"{start} ~ {end}",
            "total_revenue_yuan": _fen_to_yuan(total_fen),
            "mix": mix,
        }

    # ──────────────────────────────────────────────────────────────────
    # 6. 峰时分析（每小时 × 每渠道 订单量）
    # ──────────────────────────────────────────────────────────────────
    async def get_peak_analysis(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str],
    ) -> Dict[str, Any]:
        """最近 7 天每小时各渠道订单分布，用于热力图"""
        end = date.today()
        start = end - timedelta(days=6)

        filters = [
            Order.status == OrderStatus.COMPLETED.value,
            func.date(Order.order_time) >= start,
            func.date(Order.order_time) <= end,
        ]
        if store_id:
            filters.append(Order.store_id == store_id)

        q = (
            select(
                extract("hour", Order.order_time).label("hour"),
                Order.sales_channel,
                func.count().label("order_count"),
            )
            .where(and_(*filters))
            .group_by(extract("hour", Order.order_time), Order.sales_channel)
            .order_by(extract("hour", Order.order_time))
        )
        result = await db.execute(q)
        rows = result.all()

        # 构建 hour → channel → count 矩阵
        matrix: Dict[int, Dict[str, int]] = {}
        for hour in range(24):
            matrix[hour] = {ch: 0 for ch in ALL_CHANNELS}

        for row in rows:
            h = int(row.hour)
            ch = row.sales_channel or "dine_in"
            if ch in matrix.get(h, {}):
                matrix[h][ch] = row.order_count

        # 转为前端友好格式
        heatmap: List[Dict[str, Any]] = []
        for hour in range(24):
            entry: Dict[str, Any] = {"hour": hour}
            for ch in ALL_CHANNELS:
                entry[ch] = matrix[hour][ch]
            entry["total"] = sum(matrix[hour].values())
            heatmap.append(entry)

        return {
            "period": f"{start} ~ {end}",
            "store_id": store_id,
            "channels": ALL_CHANNELS,
            "channel_labels": CHANNEL_LABELS,
            "heatmap": heatmap,
        }

    # ──────────────────────────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────────────────────────
    async def _load_channel_configs(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, SalesChannelConfig]:
        """加载渠道成本配置，品牌级优先，集团默认兜底"""
        q = (
            select(SalesChannelConfig)
            .where(
                and_(
                    SalesChannelConfig.is_active.is_(True),
                    SalesChannelConfig.brand_id.in_([brand_id, None]),
                )
            )
            .order_by(SalesChannelConfig.brand_id.desc())  # 品牌级排前面
        )
        result = await db.execute(q)
        configs = result.scalars().all()

        # 品牌级覆盖集团默认
        config_map: Dict[str, SalesChannelConfig] = {}
        for cfg in configs:
            ch = cfg.channel
            if ch not in config_map:
                config_map[ch] = cfg
        return config_map


omni_channel_service = OmniChannelService()
