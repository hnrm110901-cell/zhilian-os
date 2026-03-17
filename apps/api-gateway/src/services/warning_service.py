"""
WarningService — 预警规则引擎 + 预警记录服务
负责规则配置管理和每日指标预警评估。
"""
import uuid
from datetime import date
from typing import List, Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.warning_rule import WarningRule
from src.models.warning_record import WarningRecord
from src.models.daily_metric import StoreDailyMetric

logger = structlog.get_logger()


class WarningService:
    """预警服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_rules(self, enabled_only: bool = True) -> List[WarningRule]:
        stmt = select(WarningRule)
        if enabled_only:
            stmt = stmt.where(WarningRule.enabled == True)
        result = await self.db.execute(stmt.order_by(WarningRule.priority.desc()))
        return list(result.scalars().all())

    async def get_rule_by_code(self, rule_code: str) -> Optional[WarningRule]:
        result = await self.db.execute(
            select(WarningRule).where(WarningRule.rule_code == rule_code)
        )
        return result.scalar_one_or_none()

    async def upsert_rule(self, data: dict) -> WarningRule:
        """新增或更新预警规则"""
        existing = await self.get_rule_by_code(data.get("rule_code", ""))
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            rule = existing
        else:
            rule = WarningRule(id=uuid.uuid4(), **{k: v for k, v in data.items() if hasattr(WarningRule, k)})
            self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def evaluate_daily_metrics(
        self, store_id: str, biz_date: date, metric: StoreDailyMetric
    ) -> List[WarningRecord]:
        """对某门店某日经营数据执行全量规则评估，返回命中的预警记录"""
        rules = await self.list_rules()
        records: List[WarningRecord] = []

        for rule in rules:
            record = self._evaluate_rule(store_id, biz_date, metric, rule)
            if record and record.warning_level in ("yellow", "red"):
                self.db.add(record)
                records.append(record)

        if records:
            await self.db.commit()
        return records

    def _evaluate_rule(
        self, store_id: str, biz_date: date, m: StoreDailyMetric, rule: WarningRule
    ) -> Optional[WarningRecord]:
        """单条规则评估"""
        # 根据 metric_code 取对应字段值（×10000 存储的率，直接比较）
        metric_map = {
            "food_cost_rate": m.food_cost_rate,
            "labor_cost_rate": m.labor_cost_rate,
            "discount_rate": m.discount_rate,
            "net_profit_rate": m.net_profit_rate,
            "gross_profit_rate": m.gross_profit_rate,
        }
        actual = metric_map.get(rule.metric_code)
        if actual is None:
            return None

        # 阈值字符串 → 整数×10000（支持小数如 "0.35" → 3500）
        def parse_threshold(t: str) -> Optional[int]:
            if t is None:
                return None
            try:
                v = float(t)
                return int(v * 10000) if v <= 1.0 else int(v)
            except (ValueError, TypeError):
                return None

        yellow_t = parse_threshold(rule.yellow_threshold)
        red_t = parse_threshold(rule.red_threshold)

        level = "green"
        op = rule.compare_operator

        def _exceeds(val, threshold, operator) -> bool:
            if threshold is None:
                return False
            if operator == "gt":
                return val > threshold
            if operator == "gte":
                return val >= threshold
            if operator == "lt":
                return val < threshold
            if operator == "lte":
                return val <= threshold
            return False

        if red_t is not None and _exceeds(actual, red_t, op):
            level = "red"
        elif yellow_t is not None and _exceeds(actual, yellow_t, op):
            level = "yellow"

        if level == "green":
            return None

        return WarningRecord(
            id=uuid.uuid4(),
            store_id=store_id,
            biz_date=str(biz_date),
            rule_id=rule.id,
            rule_code=rule.rule_code,
            rule_name=rule.rule_name,
            warning_type=rule.metric_code,
            metric_code=rule.metric_code,
            actual_value=actual,
            yellow_threshold_value=rule.yellow_threshold,
            red_threshold_value=rule.red_threshold,
            warning_level=level,
            status="active",
        )

    async def list_by_date(self, store_id: str, biz_date: date) -> List[WarningRecord]:
        result = await self.db.execute(
            select(WarningRecord).where(
                and_(
                    WarningRecord.store_id == store_id,
                    WarningRecord.biz_date == str(biz_date),
                )
            ).order_by(WarningRecord.warning_level.desc())
        )
        return list(result.scalars().all())

    def record_to_dict(self, r: WarningRecord) -> dict:
        def rate(v): return round(v / 10000, 4) if v is not None else None
        return {
            "id": str(r.id),
            "ruleCode": r.rule_code,
            "ruleName": r.rule_name,
            "warningType": r.warning_type,
            "metricCode": r.metric_code,
            "actualValue": rate(r.actual_value),
            "yellowThresholdValue": r.yellow_threshold_value,
            "redThresholdValue": r.red_threshold_value,
            "warningLevel": r.warning_level,
            "status": r.status,
        }
