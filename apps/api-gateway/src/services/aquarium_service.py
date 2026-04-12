"""
活海鲜养殖管理服务（Aquarium Management Service）

核心功能：
- 鱼缸 CRUD + 状态管理
- 水质指标记录（IoT / 手动）+ 异常预警
- 活海鲜批次入缸登记
- 死亡记录（自动计算损耗¥金额，更新库存）
- 每日巡检
- 鱼缸仪表板 + 死亡率报告

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.aquarium import (
    AquariumInspection,
    AquariumTank,
    AquariumWaterMetric,
    InspectionResult,
    LiveSeafoodBatch,
    MortalityReason,
    SeafoodMortalityLog,
    TankStatus,
)

logger = structlog.get_logger()

# ── 水质安全阈值（海水标准） ─────────────────────────────────────────────────

WATER_THRESHOLDS = {
    "temperature": {"min": 16.0, "max": 22.0, "unit": "°C", "label": "水温"},
    "ph": {"min": 7.8, "max": 8.4, "unit": "", "label": "pH"},
    "dissolved_oxygen": {"min": 5.0, "max": None, "unit": "mg/L", "label": "溶解氧"},
    "salinity": {"min": 30.0, "max": 35.0, "unit": "‰", "label": "盐度"},
    "ammonia": {"min": None, "max": 0.5, "unit": "mg/L", "label": "氨氮"},
    "nitrite": {"min": None, "max": 0.1, "unit": "mg/L", "label": "亚硝酸盐"},
}


class AquariumService:
    """活海鲜养殖管理服务"""

    # ── 鱼缸管理 ─────────────────────────────────────────────────────────────

    async def create_tank(
        self,
        db: AsyncSession,
        *,
        store_id: str,
        name: str,
        tank_type: str = "saltwater",
        capacity_liters: float,
        location: Optional[str] = None,
        equipment_info: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建鱼缸"""
        tank = AquariumTank(
            id=uuid.uuid4(),
            store_id=store_id,
            name=name,
            tank_type=tank_type,
            capacity_liters=capacity_liters,
            location=location,
            status=TankStatus.EMPTY.value,
            equipment_info=equipment_info,
            notes=notes,
        )
        db.add(tank)
        await db.flush()
        logger.info("鱼缸创建成功", tank_id=str(tank.id), name=name, store_id=store_id)
        return self._tank_to_dict(tank)

    async def get_tanks(
        self,
        db: AsyncSession,
        *,
        store_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """获取鱼缸列表"""
        conditions = [AquariumTank.store_id == store_id]
        if status:
            conditions.append(AquariumTank.status == status)

        # 总数查询
        count_stmt = select(func.count()).select_from(AquariumTank).where(and_(*conditions))
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 分页查询
        stmt = (
            select(AquariumTank)
            .where(and_(*conditions))
            .order_by(AquariumTank.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        tanks = result.scalars().all()

        return {
            "items": [self._tank_to_dict(t) for t in tanks],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def get_tank_by_id(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个鱼缸"""
        stmt = select(AquariumTank).where(AquariumTank.id == tank_id)
        result = await db.execute(stmt)
        tank = result.scalar_one_or_none()
        if not tank:
            return None
        return self._tank_to_dict(tank)

    async def update_tank_status(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
        status: str,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新鱼缸状态"""
        stmt = select(AquariumTank).where(AquariumTank.id == tank_id)
        result = await db.execute(stmt)
        tank = result.scalar_one_or_none()
        if not tank:
            return None

        tank.status = status
        if notes is not None:
            tank.notes = notes
        await db.flush()
        logger.info("鱼缸状态更新", tank_id=str(tank_id), new_status=status)
        return self._tank_to_dict(tank)

    # ── 水质指标 ─────────────────────────────────────────────────────────────

    async def record_water_metrics(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
        store_id: str,
        temperature: Optional[float] = None,
        ph: Optional[float] = None,
        dissolved_oxygen: Optional[float] = None,
        salinity: Optional[float] = None,
        ammonia: Optional[float] = None,
        nitrite: Optional[float] = None,
        source: str = "manual",
        recorded_by: Optional[str] = None,
        recorded_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        记录水质指标（支持 IoT 自动采集和手动录入）

        返回包含指标数据和告警列表
        """
        if recorded_at is None:
            recorded_at = datetime.utcnow()

        metric = AquariumWaterMetric(
            id=uuid.uuid4(),
            tank_id=tank_id,
            store_id=store_id,
            temperature=temperature,
            ph=ph,
            dissolved_oxygen=dissolved_oxygen,
            salinity=salinity,
            ammonia=ammonia,
            nitrite=nitrite,
            source=source,
            recorded_by=recorded_by,
            recorded_at=recorded_at,
            notes=notes,
        )
        db.add(metric)
        await db.flush()

        # 检查水质告警
        alerts = self._check_metric_alerts(metric)

        logger.info(
            "水质指标记录成功",
            tank_id=str(tank_id),
            source=source,
            alert_count=len(alerts),
        )

        return {
            "metric": self._metric_to_dict(metric),
            "alerts": alerts,
        }

    def _check_metric_alerts(self, metric: AquariumWaterMetric) -> List[Dict[str, Any]]:
        """检查水质指标是否超标，返回告警列表"""
        alerts: List[Dict[str, Any]] = []

        metric_values = {
            "temperature": metric.temperature,
            "ph": metric.ph,
            "dissolved_oxygen": metric.dissolved_oxygen,
            "salinity": metric.salinity,
            "ammonia": metric.ammonia,
            "nitrite": metric.nitrite,
        }

        for key, value in metric_values.items():
            if value is None:
                continue
            threshold = WATER_THRESHOLDS[key]
            min_val = threshold["min"]
            max_val = threshold["max"]

            if min_val is not None and value < min_val:
                alerts.append({
                    "metric": key,
                    "label": threshold["label"],
                    "value": value,
                    "unit": threshold["unit"],
                    "threshold_min": min_val,
                    "threshold_max": max_val,
                    "level": "critical" if self._is_critical_deviation(key, value, min_val, "below") else "warning",
                    "message": f"{threshold['label']}偏低: {value}{threshold['unit']}（标准≥{min_val}{threshold['unit']}）",
                })
            elif max_val is not None and value > max_val:
                alerts.append({
                    "metric": key,
                    "label": threshold["label"],
                    "value": value,
                    "unit": threshold["unit"],
                    "threshold_min": min_val,
                    "threshold_max": max_val,
                    "level": "critical" if self._is_critical_deviation(key, value, max_val, "above") else "warning",
                    "message": f"{threshold['label']}偏高: {value}{threshold['unit']}（标准≤{max_val}{threshold['unit']}）",
                })

        return alerts

    @staticmethod
    def _is_critical_deviation(metric: str, value: float, threshold: float, direction: str) -> bool:
        """
        判断是否为严重偏差（超过阈值 20% 以上视为 critical）
        """
        if threshold == 0:
            return True
        if direction == "below":
            deviation = (threshold - value) / threshold
        else:
            deviation = (value - threshold) / threshold
        return deviation > 0.2

    async def check_water_alerts(
        self,
        db: AsyncSession,
        *,
        store_id: str,
        tank_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        水质异常预警：获取每个鱼缸最新水质指标并检查是否超标

        返回所有告警列表（按鱼缸分组）
        """
        conditions = [AquariumTank.store_id == store_id, AquariumTank.status == TankStatus.ACTIVE.value]
        if tank_id:
            conditions.append(AquariumTank.id == tank_id)

        tanks_stmt = select(AquariumTank).where(and_(*conditions))
        tanks_result = await db.execute(tanks_stmt)
        tanks = tanks_result.scalars().all()

        all_alerts: List[Dict[str, Any]] = []
        for tank in tanks:
            # 获取该鱼缸最新水质记录
            latest_stmt = (
                select(AquariumWaterMetric)
                .where(AquariumWaterMetric.tank_id == tank.id)
                .order_by(AquariumWaterMetric.recorded_at.desc())
                .limit(1)
            )
            latest_result = await db.execute(latest_stmt)
            latest_metric = latest_result.scalar_one_or_none()

            if not latest_metric:
                continue

            alerts = self._check_metric_alerts(latest_metric)
            for alert in alerts:
                alert["tank_id"] = str(tank.id)
                alert["tank_name"] = tank.name
                alert["recorded_at"] = latest_metric.recorded_at.isoformat() if latest_metric.recorded_at else None
            all_alerts.extend(alerts)

        return all_alerts

    # ── 活海鲜批次 ───────────────────────────────────────────────────────────

    async def add_seafood_batch(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
        store_id: str,
        species: str,
        category: Optional[str] = None,
        entry_date: Optional[datetime] = None,
        initial_quantity: int,
        initial_weight_g: Optional[int] = None,
        unit: str = "只",
        unit_cost_fen: int,
        cost_unit: str = "只",
        supplier_name: Optional[str] = None,
        supplier_contact: Optional[str] = None,
        purchase_order_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        入缸登记

        total_cost_fen = unit_cost_fen × initial_quantity
        """
        if entry_date is None:
            entry_date = datetime.utcnow()

        total_cost_fen = unit_cost_fen * initial_quantity

        batch = LiveSeafoodBatch(
            id=uuid.uuid4(),
            tank_id=tank_id,
            store_id=store_id,
            species=species,
            category=category,
            entry_date=entry_date,
            initial_quantity=initial_quantity,
            initial_weight_g=initial_weight_g,
            unit=unit,
            current_quantity=initial_quantity,
            current_weight_g=initial_weight_g,
            unit_cost_fen=unit_cost_fen,
            total_cost_fen=total_cost_fen,
            cost_unit=cost_unit,
            supplier_name=supplier_name,
            supplier_contact=supplier_contact,
            purchase_order_id=purchase_order_id,
            is_active="true",
            notes=notes,
        )
        db.add(batch)

        # 更新鱼缸状态为 ACTIVE，更新当前品种
        tank_stmt = select(AquariumTank).where(AquariumTank.id == tank_id)
        tank_result = await db.execute(tank_stmt)
        tank = tank_result.scalar_one_or_none()
        if tank:
            tank.status = TankStatus.ACTIVE.value
            # 更新当前品种列表
            existing_species = set(tank.current_species.split(",")) if tank.current_species else set()
            existing_species.add(species)
            # 去除空字符串
            existing_species.discard("")
            tank.current_species = ",".join(sorted(existing_species))

        await db.flush()
        logger.info(
            "活海鲜入缸登记",
            batch_id=str(batch.id),
            species=species,
            quantity=initial_quantity,
            total_cost_yuan=f"¥{total_cost_fen / 100:.2f}",
        )

        return self._batch_to_dict(batch)

    # ── 死亡记录 ─────────────────────────────────────────────────────────────

    async def record_mortality(
        self,
        db: AsyncSession,
        *,
        batch_id: uuid.UUID,
        store_id: str,
        dead_quantity: int,
        dead_weight_g: Optional[int] = None,
        reason: str = "unknown",
        disposal: str = "discard",
        recorded_by: Optional[str] = None,
        recorded_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        记录死亡（自动计算损耗¥金额，更新批次存活数量）

        损耗金额 = 批次单位成本 × 死亡数量
        """
        if recorded_at is None:
            recorded_at = datetime.utcnow()

        # 查询批次信息
        batch_stmt = select(LiveSeafoodBatch).where(LiveSeafoodBatch.id == batch_id)
        batch_result = await db.execute(batch_stmt)
        batch = batch_result.scalar_one_or_none()
        if not batch:
            raise ValueError(f"批次不存在: {batch_id}")

        if dead_quantity > batch.current_quantity:
            raise ValueError(
                f"死亡数量({dead_quantity})不能超过当前存活数量({batch.current_quantity})"
            )

        # 计算损耗金额（分）
        loss_amount_fen = batch.unit_cost_fen * dead_quantity

        mortality = SeafoodMortalityLog(
            id=uuid.uuid4(),
            batch_id=batch_id,
            tank_id=batch.tank_id,
            store_id=store_id,
            dead_quantity=dead_quantity,
            dead_weight_g=dead_weight_g,
            reason=reason,
            disposal=disposal,
            loss_amount_fen=loss_amount_fen,
            recorded_by=recorded_by,
            recorded_at=recorded_at,
            notes=notes,
        )
        db.add(mortality)

        # 更新批次存活数量
        batch.current_quantity -= dead_quantity
        if batch.current_weight_g and dead_weight_g:
            batch.current_weight_g -= dead_weight_g

        # 如果全部死亡，标记批次为非活跃
        if batch.current_quantity <= 0:
            batch.is_active = "false"

        await db.flush()
        logger.info(
            "海鲜死亡记录",
            batch_id=str(batch_id),
            species=batch.species,
            dead_quantity=dead_quantity,
            loss_yuan=f"¥{loss_amount_fen / 100:.2f}",
            remaining=batch.current_quantity,
        )

        return {
            "mortality": self._mortality_to_dict(mortality),
            "batch_remaining": batch.current_quantity,
            "loss_amount_fen": loss_amount_fen,
            "loss_amount_yuan": f"¥{loss_amount_fen / 100:.2f}",
        }

    # ── 每日巡检 ─────────────────────────────────────────────────────────────

    async def daily_inspection(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
        store_id: str,
        inspector: str,
        inspection_date: Optional[date] = None,
        result: str = "normal",
        tank_cleanliness: Optional[int] = None,
        fish_activity: Optional[int] = None,
        equipment_status: Optional[int] = None,
        abnormal_description: Optional[str] = None,
        action_taken: Optional[str] = None,
        image_urls: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """每日巡检记录"""
        if inspection_date is None:
            inspection_date = date.today()

        inspection = AquariumInspection(
            id=uuid.uuid4(),
            tank_id=tank_id,
            store_id=store_id,
            inspector=inspector,
            inspection_date=inspection_date,
            inspection_time=datetime.utcnow(),
            result=result,
            tank_cleanliness=tank_cleanliness,
            fish_activity=fish_activity,
            equipment_status=equipment_status,
            abnormal_description=abnormal_description,
            action_taken=action_taken,
            image_urls=image_urls,
            notes=notes,
        )
        db.add(inspection)
        await db.flush()

        logger.info(
            "巡检记录完成",
            tank_id=str(tank_id),
            inspector=inspector,
            result=result,
        )

        return self._inspection_to_dict(inspection)

    # ── 鱼缸仪表板 ──────────────────────────────────────────────────────────

    async def get_tank_dashboard(
        self,
        db: AsyncSession,
        *,
        tank_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        鱼缸仪表板：当前品种/数量/水质/健康度评分

        健康度评分（0-100）基于：
        - 水质指标合规程度（60%权重）
        - 死亡率（20%权重）
        - 最近巡检评分（20%权重）
        """
        # 获取鱼缸信息
        tank_stmt = select(AquariumTank).where(AquariumTank.id == tank_id)
        tank_result = await db.execute(tank_stmt)
        tank = tank_result.scalar_one_or_none()
        if not tank:
            return {"error": "鱼缸不存在"}

        # 获取活跃批次
        batches_stmt = (
            select(LiveSeafoodBatch)
            .where(and_(
                LiveSeafoodBatch.tank_id == tank_id,
                LiveSeafoodBatch.is_active == "true",
            ))
            .order_by(LiveSeafoodBatch.entry_date.desc())
        )
        batches_result = await db.execute(batches_stmt)
        batches = batches_result.scalars().all()

        # 获取最新水质
        latest_metric_stmt = (
            select(AquariumWaterMetric)
            .where(AquariumWaterMetric.tank_id == tank_id)
            .order_by(AquariumWaterMetric.recorded_at.desc())
            .limit(1)
        )
        latest_metric_result = await db.execute(latest_metric_stmt)
        latest_metric = latest_metric_result.scalar_one_or_none()

        # 获取最近巡检
        latest_inspection_stmt = (
            select(AquariumInspection)
            .where(AquariumInspection.tank_id == tank_id)
            .order_by(AquariumInspection.inspection_date.desc())
            .limit(1)
        )
        latest_inspection_result = await db.execute(latest_inspection_stmt)
        latest_inspection = latest_inspection_result.scalar_one_or_none()

        # 计算 7 天死亡率
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        mortality_stmt = select(func.sum(SeafoodMortalityLog.dead_quantity)).where(
            and_(
                SeafoodMortalityLog.tank_id == tank_id,
                SeafoodMortalityLog.recorded_at >= seven_days_ago,
            )
        )
        mortality_result = await db.execute(mortality_stmt)
        total_dead_7d = mortality_result.scalar() or 0

        # 批次汇总
        total_quantity = sum(b.current_quantity for b in batches)
        total_initial = sum(b.initial_quantity for b in batches)
        total_cost_fen = sum(b.total_cost_fen for b in batches)
        species_list = list(set(b.species for b in batches))

        # 计算健康度评分
        health_score = self._calculate_health_score(
            latest_metric=latest_metric,
            latest_inspection=latest_inspection,
            total_dead_7d=total_dead_7d,
            total_quantity=total_quantity,
            total_initial=total_initial,
        )

        # 水质告警
        water_alerts = self._check_metric_alerts(latest_metric) if latest_metric else []

        return {
            "tank": self._tank_to_dict(tank),
            "species": species_list,
            "total_quantity": total_quantity,
            "total_cost_fen": total_cost_fen,
            "total_cost_yuan": f"¥{total_cost_fen / 100:.2f}",
            "active_batches": len(batches),
            "batches": [self._batch_to_dict(b) for b in batches],
            "latest_water_metric": self._metric_to_dict(latest_metric) if latest_metric else None,
            "water_alerts": water_alerts,
            "latest_inspection": self._inspection_to_dict(latest_inspection) if latest_inspection else None,
            "mortality_7d": total_dead_7d,
            "mortality_rate_7d": round(total_dead_7d / total_initial * 100, 2) if total_initial > 0 else 0.0,
            "health_score": health_score,
        }

    def _calculate_health_score(
        self,
        latest_metric: Optional[AquariumWaterMetric],
        latest_inspection: Optional[AquariumInspection],
        total_dead_7d: int,
        total_quantity: int,
        total_initial: int,
    ) -> float:
        """
        计算健康度评分（0-100）

        权重：
        - 水质合规度：60%
        - 死亡率：20%（7天内）
        - 巡检评分：20%
        """
        # 水质评分（60分满分）
        water_score = 60.0
        if latest_metric:
            alerts = self._check_metric_alerts(latest_metric)
            critical_count = sum(1 for a in alerts if a["level"] == "critical")
            warning_count = sum(1 for a in alerts if a["level"] == "warning")
            water_score = max(0, 60.0 - critical_count * 20 - warning_count * 10)

        # 死亡率评分（20分满分）
        mortality_score = 20.0
        if total_initial > 0:
            mortality_rate = total_dead_7d / total_initial
            if mortality_rate > 0.1:
                mortality_score = 0.0
            elif mortality_rate > 0.05:
                mortality_score = 10.0
            elif mortality_rate > 0.02:
                mortality_score = 15.0

        # 巡检评分（20分满分）
        inspection_score = 20.0
        if latest_inspection:
            scores = []
            if latest_inspection.tank_cleanliness is not None:
                scores.append(latest_inspection.tank_cleanliness)
            if latest_inspection.fish_activity is not None:
                scores.append(latest_inspection.fish_activity)
            if latest_inspection.equipment_status is not None:
                scores.append(latest_inspection.equipment_status)
            if scores:
                avg_score = sum(scores) / len(scores)
                inspection_score = avg_score * 2  # 1-10 映射到 0-20

            if latest_inspection.result == InspectionResult.CRITICAL.value:
                inspection_score = max(0, inspection_score - 10)
            elif latest_inspection.result == InspectionResult.WARNING.value:
                inspection_score = max(0, inspection_score - 5)

        total = water_score + mortality_score + inspection_score
        return round(min(100.0, max(0.0, total)), 1)

    # ── 死亡率报告 ───────────────────────────────────────────────────────────

    async def get_mortality_report(
        self,
        db: AsyncSession,
        *,
        store_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        species: Optional[str] = None,
        tank_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        死亡率报告（按品种/鱼缸/时间段）

        返回：总死亡数、总损耗金额、按品种/原因统计
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        if end_date is None:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # 基础条件
        conditions = [
            SeafoodMortalityLog.store_id == store_id,
            SeafoodMortalityLog.recorded_at >= start_dt,
            SeafoodMortalityLog.recorded_at <= end_dt,
        ]
        if tank_id:
            conditions.append(SeafoodMortalityLog.tank_id == tank_id)

        # 查询所有死亡记录（含批次信息）
        stmt = (
            select(SeafoodMortalityLog, LiveSeafoodBatch.species, LiveSeafoodBatch.initial_quantity)
            .join(LiveSeafoodBatch, SeafoodMortalityLog.batch_id == LiveSeafoodBatch.id)
            .where(and_(*conditions))
        )
        if species:
            stmt = stmt.where(LiveSeafoodBatch.species == species)

        result = await db.execute(stmt)
        rows = result.all()

        # 汇总统计
        total_dead = 0
        total_loss_fen = 0
        by_species: Dict[str, Dict[str, Any]] = {}
        by_reason: Dict[str, int] = {}

        for mortality_log, sp, initial_qty in rows:
            total_dead += mortality_log.dead_quantity
            total_loss_fen += mortality_log.loss_amount_fen

            # 按品种
            if sp not in by_species:
                by_species[sp] = {"dead": 0, "loss_fen": 0, "initial_total": 0}
            by_species[sp]["dead"] += mortality_log.dead_quantity
            by_species[sp]["loss_fen"] += mortality_log.loss_amount_fen
            by_species[sp]["initial_total"] += initial_qty

            # 按原因
            reason_val = mortality_log.reason or "unknown"
            by_reason[reason_val] = by_reason.get(reason_val, 0) + mortality_log.dead_quantity

        # 计算品种死亡率
        species_report = []
        for sp, data in by_species.items():
            mortality_rate = round(data["dead"] / data["initial_total"] * 100, 2) if data["initial_total"] > 0 else 0.0
            species_report.append({
                "species": sp,
                "dead_quantity": data["dead"],
                "loss_amount_fen": data["loss_fen"],
                "loss_amount_yuan": f"¥{data['loss_fen'] / 100:.2f}",
                "mortality_rate_percent": mortality_rate,
            })

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_dead": total_dead,
            "total_loss_fen": total_loss_fen,
            "total_loss_yuan": f"¥{total_loss_fen / 100:.2f}",
            "by_species": species_report,
            "by_reason": [
                {"reason": r, "count": c} for r, c in sorted(by_reason.items(), key=lambda x: -x[1])
            ],
            "record_count": len(rows),
        }

    # ── 序列化辅助 ───────────────────────────────────────────────────────────

    @staticmethod
    def _tank_to_dict(tank: AquariumTank) -> Dict[str, Any]:
        return {
            "id": str(tank.id),
            "store_id": tank.store_id,
            "name": tank.name,
            "tank_type": tank.tank_type,
            "capacity_liters": tank.capacity_liters,
            "location": tank.location,
            "status": tank.status,
            "current_species": tank.current_species,
            "equipment_info": tank.equipment_info,
            "notes": tank.notes,
            "created_at": tank.created_at.isoformat() if tank.created_at else None,
            "updated_at": tank.updated_at.isoformat() if tank.updated_at else None,
        }

    @staticmethod
    def _metric_to_dict(metric: AquariumWaterMetric) -> Dict[str, Any]:
        return {
            "id": str(metric.id),
            "tank_id": str(metric.tank_id),
            "temperature": metric.temperature,
            "ph": metric.ph,
            "dissolved_oxygen": metric.dissolved_oxygen,
            "salinity": metric.salinity,
            "ammonia": metric.ammonia,
            "nitrite": metric.nitrite,
            "source": metric.source,
            "recorded_by": metric.recorded_by,
            "recorded_at": metric.recorded_at.isoformat() if metric.recorded_at else None,
            "notes": metric.notes,
        }

    @staticmethod
    def _batch_to_dict(batch: LiveSeafoodBatch) -> Dict[str, Any]:
        return {
            "id": str(batch.id),
            "tank_id": str(batch.tank_id),
            "store_id": batch.store_id,
            "species": batch.species,
            "category": batch.category,
            "entry_date": batch.entry_date.isoformat() if batch.entry_date else None,
            "initial_quantity": batch.initial_quantity,
            "initial_weight_g": batch.initial_weight_g,
            "unit": batch.unit,
            "current_quantity": batch.current_quantity,
            "current_weight_g": batch.current_weight_g,
            "unit_cost_fen": batch.unit_cost_fen,
            "total_cost_fen": batch.total_cost_fen,
            "total_cost_yuan": f"¥{batch.total_cost_fen / 100:.2f}",
            "cost_unit": batch.cost_unit,
            "supplier_name": batch.supplier_name,
            "is_active": batch.is_active,
            "notes": batch.notes,
        }

    @staticmethod
    def _mortality_to_dict(log: SeafoodMortalityLog) -> Dict[str, Any]:
        return {
            "id": str(log.id),
            "batch_id": str(log.batch_id),
            "tank_id": str(log.tank_id),
            "dead_quantity": log.dead_quantity,
            "dead_weight_g": log.dead_weight_g,
            "reason": log.reason,
            "disposal": log.disposal,
            "loss_amount_fen": log.loss_amount_fen,
            "loss_amount_yuan": f"¥{log.loss_amount_fen / 100:.2f}",
            "recorded_by": log.recorded_by,
            "recorded_at": log.recorded_at.isoformat() if log.recorded_at else None,
            "notes": log.notes,
        }

    @staticmethod
    def _inspection_to_dict(inspection: AquariumInspection) -> Dict[str, Any]:
        return {
            "id": str(inspection.id),
            "tank_id": str(inspection.tank_id),
            "inspector": inspection.inspector,
            "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
            "result": inspection.result,
            "tank_cleanliness": inspection.tank_cleanliness,
            "fish_activity": inspection.fish_activity,
            "equipment_status": inspection.equipment_status,
            "abnormal_description": inspection.abnormal_description,
            "action_taken": inspection.action_taken,
            "image_urls": inspection.image_urls,
            "notes": inspection.notes,
        }


# 模块级单例
aquarium_service = AquariumService()
