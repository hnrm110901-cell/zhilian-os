"""
DailyMetricService — 门店日经营数据服务
负责日经营指标的查询、汇总、预警计算。
"""
import uuid
from datetime import date, datetime
from typing import Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.daily_metric import StoreDailyMetric
from src.models.warning_rule import WarningRule
from src.models.warning_record import WarningRecord

logger = structlog.get_logger()

# 菜品成本率预警阈值（×10000 存储，即 3300=33%）
FOOD_COST_YELLOW = 3300
FOOD_COST_RED = 3500
# 折扣率预警阈值
DISCOUNT_YELLOW = 1000
DISCOUNT_RED = 1200
# 人工率预警阈值
LABOR_YELLOW = 1800
LABOR_RED = 2000
# 净利率预警阈值（红灯 < 0%，黄灯 < 8%）
NET_PROFIT_RED = 0
NET_PROFIT_YELLOW = 800


class DailyMetricService:
    """门店日经营数据服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_date(self, store_id: str, biz_date: date) -> Optional[StoreDailyMetric]:
        """查询门店某日经营数据"""
        result = await self.db.execute(
            select(StoreDailyMetric).where(
                and_(
                    StoreDailyMetric.store_id == store_id,
                    StoreDailyMetric.biz_date == biz_date,
                )
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, store_id: str, biz_date: date, data: dict) -> StoreDailyMetric:
        """新增或更新日经营数据（幂等写入）"""
        existing = await self.get_by_date(store_id, biz_date)
        if existing:
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.data_version = (existing.data_version or 1) + 1
            metric = existing
        else:
            metric = StoreDailyMetric(
                id=uuid.uuid4(),
                store_id=store_id,
                biz_date=biz_date,
                **{k: v for k, v in data.items() if hasattr(StoreDailyMetric, k)},
            )
            self.db.add(metric)

        # 自动计算派生率值（×10000 存储）
        self._compute_rates(metric)
        # 判断综合预警等级
        metric.warning_level = self._calc_warning_level(metric)

        await self.db.commit()
        await self.db.refresh(metric)
        return metric

    def _compute_rates(self, m: StoreDailyMetric) -> None:
        """计算成本率、折扣率、利润率等派生字段"""
        sales = m.total_sales_amount or 0
        if sales <= 0:
            return
        if m.food_cost_amount is not None:
            m.food_cost_rate = int(m.food_cost_amount * 10000 / sales)
        if m.labor_cost_amount is not None:
            m.labor_cost_rate = int(m.labor_cost_amount * 10000 / sales)
        if m.total_discount_amount is not None:
            m.discount_rate = int(m.total_discount_amount * 10000 / sales)
        if m.gross_profit_amount is not None:
            m.gross_profit_rate = int(m.gross_profit_amount * 10000 / sales)
        if m.net_profit_amount is not None:
            m.net_profit_rate = int(m.net_profit_amount * 10000 / sales)
        if m.dine_in_sales_amount is not None:
            m.dine_in_sales_rate = int(m.dine_in_sales_amount * 10000 / sales)
        if m.delivery_sales_amount is not None:
            m.delivery_sales_rate = int(m.delivery_sales_amount * 10000 / sales)

    def _calc_warning_level(self, m: StoreDailyMetric) -> str:
        """根据各率值判断综合预警等级"""
        # 任意一个指标超红线 → 红灯
        if (
            (m.food_cost_rate or 0) > FOOD_COST_RED
            or (m.discount_rate or 0) > DISCOUNT_RED
            or (m.labor_cost_rate or 0) > LABOR_RED
            or (m.net_profit_rate or 0) < NET_PROFIT_RED
        ):
            return "red"
        # 任意一个指标超黄线 → 黄灯
        if (
            (m.food_cost_rate or 0) > FOOD_COST_YELLOW
            or (m.discount_rate or 0) > DISCOUNT_YELLOW
            or (m.labor_cost_rate or 0) > LABOR_YELLOW
            or (0 < (m.net_profit_rate or 999) < NET_PROFIT_YELLOW)
        ):
            return "yellow"
        return "green"

    def to_api_dict(self, m: StoreDailyMetric) -> dict:
        """转换为 API 响应格式（金额 /100 转元，率 /10000 转小数）"""
        def fen_to_yuan(v): return round(v / 100, 2) if v is not None else None
        def rate(v): return round(v / 10000, 4) if v is not None else None

        return {
            "storeId": m.store_id,
            "storeName": m.store_name,
            "bizDate": str(m.biz_date),
            "warningLevel": m.warning_level,
            "totalSalesAmount": fen_to_yuan(m.total_sales_amount),
            "actualReceiptsAmount": fen_to_yuan(m.actual_receipts_amount),
            "dineInSalesAmount": fen_to_yuan(m.dine_in_sales_amount),
            "deliverySalesAmount": fen_to_yuan(m.delivery_sales_amount),
            "foodSalesAmount": fen_to_yuan(m.food_sales_amount),
            "beverageSalesAmount": fen_to_yuan(m.beverage_sales_amount),
            "otherSalesAmount": fen_to_yuan(m.other_sales_amount),
            "orderCount": m.order_count,
            "tableCount": m.table_count,
            "guestCount": m.guest_count,
            "foodCostAmount": fen_to_yuan(m.food_cost_amount),
            "laborCostAmount": fen_to_yuan(m.labor_cost_amount),
            "totalDiscountAmount": fen_to_yuan(m.total_discount_amount),
            "grossProfitAmount": fen_to_yuan(m.gross_profit_amount),
            "grossProfitRate": rate(m.gross_profit_rate),
            "netProfitAmount": fen_to_yuan(m.net_profit_amount),
            "netProfitRate": rate(m.net_profit_rate),
            "foodCostRate": rate(m.food_cost_rate),
            "laborCostRate": rate(m.labor_cost_rate),
            "discountRate": rate(m.discount_rate),
            "dineInSalesRate": rate(m.dine_in_sales_rate),
            "deliverySalesRate": rate(m.delivery_sales_rate),
            "frontStaffCount": m.front_staff_count,
            "kitchenStaffCount": m.kitchen_staff_count,
            "totalStaffCount": m.total_staff_count,
        }

    async def get_summary(self, store_id: str, biz_date: date) -> dict:
        """生成经营摘要（含自动预警描述）"""
        m = await self.get_by_date(store_id, biz_date)
        if not m:
            return {
                "storeId": store_id,
                "bizDate": str(biz_date),
                "summary": "暂无经营数据，请先同步 POS 数据。",
                "warningCount": 0,
                "warningLevel": "green",
                "majorIssueTypes": [],
            }

        issues = []
        food_rate = m.food_cost_rate or 0
        discount_rate = m.discount_rate or 0
        labor_rate = m.labor_cost_rate or 0
        net_rate = m.net_profit_rate if m.net_profit_rate is not None else 9999

        if food_rate > FOOD_COST_RED:
            issues.append("food_cost_high")
        if discount_rate > DISCOUNT_RED:
            issues.append("discount_high")
        if labor_rate > LABOR_RED:
            issues.append("labor_high")
        if net_rate < NET_PROFIT_RED:
            issues.append("sales_drop")

        warning_level = m.warning_level or "green"
        if warning_level == "red":
            summary = f"今日存在 {len(issues)} 项红灯异常，净利{'为负' if net_rate < 0 else '偏低'}，请立即复盘。"
        elif warning_level == "yellow":
            summary = "今日部分指标接近预警阈值，请关注并提前预防。"
        else:
            summary = "今日经营整体正常，请关注明日营业准备。"

        return {
            "storeId": store_id,
            "bizDate": str(biz_date),
            "summary": summary,
            "warningCount": len(issues),
            "warningLevel": warning_level,
            "majorIssueTypes": issues,
        }
