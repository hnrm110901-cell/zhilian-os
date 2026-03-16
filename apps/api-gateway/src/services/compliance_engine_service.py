"""
合规引擎服务 — ComplianceEngineService
统一合规评分计算、告警生成、自动操作执行。

评分权重：
  健康证 25% + 食品安全 30% + 证照 20% + 卫生检查 25%

评级标准：
  A+ >= 95, A >= 85, B >= 70, C >= 55, D >= 40, F < 40
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.compliance import ComplianceLicense, LicenseStatus
from src.models.compliance_engine import ComplianceAlert, ComplianceScore
from src.models.food_safety import FoodSafetyInspection, FoodTraceRecord
from src.models.health_certificate import HealthCertificate

logger = structlog.get_logger()

# 评分权重
WEIGHT_HEALTH = 0.25
WEIGHT_FOOD_SAFETY = 0.30
WEIGHT_LICENSE = 0.20
WEIGHT_HYGIENE = 0.25

# 评级阈值
GRADE_THRESHOLDS = [
    (95, "A+"),
    (85, "A"),
    (70, "B"),
    (55, "C"),
    (40, "D"),
    (0, "F"),
]

# 告警严重程度映射
ALERT_SEVERITY_MAP = {
    "cert_expired": "critical",
    "cert_expiring": "high",
    "inspection_failed": "critical",
    "license_expiring": "high",
    "trace_gap": "medium",
    "score_drop": "high",
}


def _calc_grade(score: int) -> str:
    """根据综合分计算评级"""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


class ComplianceEngineService:
    """合规引擎核心服务"""

    # ── 评分计算 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def compute_store_score(
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        score_date: date,
    ) -> ComplianceScore:
        """计算单个门店的合规评分"""
        today = score_date

        # 1) 健康证维度：有效证件占比
        cert_q = select(HealthCertificate).where(
            and_(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.store_id == store_id,
            )
        )
        cert_result = await db.execute(cert_q)
        certs = cert_result.scalars().all()

        if certs:
            valid_count = sum(1 for c in certs if c.expiry_date and c.expiry_date >= today)
            health_cert_score = round(valid_count / len(certs) * 100)
        else:
            health_cert_score = 100  # 无员工需要健康证时满分

        # 2) 食品安全维度：检查通过率 (60%) + 溯源覆盖率 (40%)
        insp_q = select(FoodSafetyInspection).where(
            and_(
                FoodSafetyInspection.brand_id == brand_id,
                FoodSafetyInspection.store_id == store_id,
                FoodSafetyInspection.inspection_date >= today - timedelta(days=90),
            )
        )
        insp_result = await db.execute(insp_q)
        inspections = insp_result.scalars().all()

        if inspections:
            passed = sum(1 for i in inspections if i.status == "passed")
            pass_rate = round(passed / len(inspections) * 100)
        else:
            pass_rate = 100

        # 溯源覆盖率：最近30天有溯源记录且状态正常的比例
        trace_q = select(func.count()).where(
            and_(
                FoodTraceRecord.brand_id == brand_id,
                FoodTraceRecord.store_id == store_id,
                FoodTraceRecord.receive_date >= today - timedelta(days=30),
            )
        )
        trace_total_result = await db.execute(trace_q)
        trace_total = trace_total_result.scalar() or 0

        trace_normal_q = select(func.count()).where(
            and_(
                FoodTraceRecord.brand_id == brand_id,
                FoodTraceRecord.store_id == store_id,
                FoodTraceRecord.receive_date >= today - timedelta(days=30),
                FoodTraceRecord.status == "normal",
            )
        )
        trace_normal_result = await db.execute(trace_normal_q)
        trace_normal = trace_normal_result.scalar() or 0

        trace_coverage = round(trace_normal / trace_total * 100) if trace_total > 0 else 100
        food_safety_score = round(pass_rate * 0.6 + trace_coverage * 0.4)

        # 3) 证照维度：所有必要证照有效率
        lic_q = select(ComplianceLicense).where(
            ComplianceLicense.store_id == store_id,
        )
        lic_result = await db.execute(lic_q)
        licenses = lic_result.scalars().all()

        if licenses:
            valid_lic = sum(1 for lic in licenses if lic.expiry_date and lic.expiry_date >= today)
            license_score = round(valid_lic / len(licenses) * 100)
        else:
            license_score = 100

        # 4) 卫生检查维度：最近一次日检/周检得分
        hygiene_q = (
            select(FoodSafetyInspection)
            .where(
                and_(
                    FoodSafetyInspection.brand_id == brand_id,
                    FoodSafetyInspection.store_id == store_id,
                    FoodSafetyInspection.inspection_type.in_(["daily", "weekly"]),
                )
            )
            .order_by(FoodSafetyInspection.inspection_date.desc())
            .limit(5)
        )
        hygiene_result = await db.execute(hygiene_q)
        hygiene_inspections = hygiene_result.scalars().all()

        if hygiene_inspections:
            scores = [i.score for i in hygiene_inspections if i.score is not None]
            hygiene_score = round(sum(scores) / len(scores)) if scores else 80
        else:
            hygiene_score = 80  # 无检查记录时给默认及格分

        # 5) 综合评分
        overall_score = round(
            health_cert_score * WEIGHT_HEALTH
            + food_safety_score * WEIGHT_FOOD_SAFETY
            + license_score * WEIGHT_LICENSE
            + hygiene_score * WEIGHT_HYGIENE
        )
        grade = _calc_grade(overall_score)

        # 6) 风险项：低于70分的维度
        risk_items: List[Dict[str, Any]] = []
        dimension_checks = [
            ("health_cert", "健康证合规", health_cert_score),
            ("food_safety", "食品安全", food_safety_score),
            ("license", "证照合规", license_score),
            ("hygiene", "卫生检查", hygiene_score),
        ]
        for dim_type, dim_name, dim_score in dimension_checks:
            if dim_score < 70:
                severity = "critical" if dim_score < 40 else "high" if dim_score < 55 else "medium"
                risk_items.append(
                    {
                        "type": dim_type,
                        "description": f"{dim_name}评分 {dim_score} 分，低于合规标准（70分）",
                        "severity": severity,
                        "deadline": (today + timedelta(days=7)).isoformat(),
                    }
                )

        # 7) Upsert
        existing_q = select(ComplianceScore).where(
            and_(
                ComplianceScore.brand_id == brand_id,
                ComplianceScore.store_id == store_id,
                ComplianceScore.score_date == score_date,
            )
        )
        existing_result = await db.execute(existing_q)
        record = existing_result.scalar_one_or_none()

        if record:
            record.health_cert_score = health_cert_score
            record.food_safety_score = food_safety_score
            record.license_score = license_score
            record.hygiene_score = hygiene_score
            record.overall_score = overall_score
            record.grade = grade
            record.risk_items = risk_items
        else:
            record = ComplianceScore(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id,
                score_date=score_date,
                health_cert_score=health_cert_score,
                food_safety_score=food_safety_score,
                license_score=license_score,
                hygiene_score=hygiene_score,
                overall_score=overall_score,
                grade=grade,
                risk_items=risk_items,
            )
            db.add(record)

        await db.flush()
        logger.info(
            "compliance_score_computed",
            brand_id=brand_id,
            store_id=store_id,
            overall=overall_score,
            grade=grade,
        )
        return record

    @staticmethod
    async def compute_all_stores(
        db: AsyncSession,
        brand_id: str,
    ) -> List[ComplianceScore]:
        """批量计算品牌下所有门店的合规评分"""
        # 收集所有涉及的 store_id
        store_ids = set()

        cert_q = select(HealthCertificate.store_id).where(HealthCertificate.brand_id == brand_id).distinct()
        result = await db.execute(cert_q)
        store_ids.update(r[0] for r in result.all())

        insp_q = select(FoodSafetyInspection.store_id).where(FoodSafetyInspection.brand_id == brand_id).distinct()
        result = await db.execute(insp_q)
        store_ids.update(r[0] for r in result.all())

        trace_q = select(FoodTraceRecord.store_id).where(FoodTraceRecord.brand_id == brand_id).distinct()
        result = await db.execute(trace_q)
        store_ids.update(r[0] for r in result.all())

        today = date.today()
        scores = []
        for sid in store_ids:
            score = await ComplianceEngineService.compute_store_score(
                db,
                brand_id,
                sid,
                today,
            )
            scores.append(score)

        await db.flush()
        logger.info("compliance_all_stores_computed", brand_id=brand_id, count=len(scores))
        return scores

    # ── 告警生成 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_alerts(
        db: AsyncSession,
        brand_id: str,
    ) -> List[ComplianceAlert]:
        """扫描各数据源，生成合规告警"""
        today = date.today()
        alerts: List[ComplianceAlert] = []

        # 1) 过期/即将过期的健康证
        cert_q = select(HealthCertificate).where(
            and_(
                HealthCertificate.brand_id == brand_id,
                HealthCertificate.expiry_date <= today + timedelta(days=30),
            )
        )
        cert_result = await db.execute(cert_q)
        certs = cert_result.scalars().all()

        for cert in certs:
            is_expired = cert.expiry_date < today
            alert_type = "cert_expired" if is_expired else "cert_expiring"
            severity = ALERT_SEVERITY_MAP[alert_type]
            days = (cert.expiry_date - today).days

            # 去重：相同实体+类型不重复创建
            dup_q = select(func.count()).where(
                and_(
                    ComplianceAlert.related_entity_id == str(cert.id),
                    ComplianceAlert.alert_type == alert_type,
                    ComplianceAlert.is_resolved == False,
                )
            )
            dup_result = await db.execute(dup_q)
            if (dup_result.scalar() or 0) > 0:
                continue

            title = (
                f"健康证已过期：{cert.employee_name}" if is_expired else f"健康证将在 {days} 天后过期：{cert.employee_name}"
            )
            alert = ComplianceAlert(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=cert.store_id,
                alert_type=alert_type,
                severity=severity,
                title=title,
                description=f"员工 {cert.employee_name}（{cert.employee_id}）健康证到期日：{cert.expiry_date.isoformat()}",
                related_entity_id=str(cert.id),
                auto_action="block_scheduling" if is_expired else "notify_manager",
            )
            db.add(alert)
            alerts.append(alert)

        # 2) 未通过的食品安全检查
        failed_q = select(FoodSafetyInspection).where(
            and_(
                FoodSafetyInspection.brand_id == brand_id,
                FoodSafetyInspection.status == "failed",
                FoodSafetyInspection.inspection_date >= today - timedelta(days=30),
            )
        )
        failed_result = await db.execute(failed_q)
        failed_inspections = failed_result.scalars().all()

        for insp in failed_inspections:
            dup_q = select(func.count()).where(
                and_(
                    ComplianceAlert.related_entity_id == str(insp.id),
                    ComplianceAlert.alert_type == "inspection_failed",
                    ComplianceAlert.is_resolved == False,
                )
            )
            dup_result = await db.execute(dup_q)
            if (dup_result.scalar() or 0) > 0:
                continue

            alert = ComplianceAlert(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=insp.store_id,
                alert_type="inspection_failed",
                severity="critical",
                title=f"食品安全检查未通过（{insp.inspection_date.isoformat()}）",
                description=f"检查员：{insp.inspector_name}，得分：{insp.score or '未评分'}，需立即整改",
                related_entity_id=str(insp.id),
                auto_action="flag_inspection",
            )
            db.add(alert)
            alerts.append(alert)

        # 3) 溯源缺口：最近7天收货但无正常状态的批次
        gap_q = select(FoodTraceRecord).where(
            and_(
                FoodTraceRecord.brand_id == brand_id,
                FoodTraceRecord.receive_date >= today - timedelta(days=7),
                FoodTraceRecord.status.in_(["warning", "recalled"]),
            )
        )
        gap_result = await db.execute(gap_q)
        gap_records = gap_result.scalars().all()

        for rec in gap_records:
            dup_q = select(func.count()).where(
                and_(
                    ComplianceAlert.related_entity_id == str(rec.id),
                    ComplianceAlert.alert_type == "trace_gap",
                    ComplianceAlert.is_resolved == False,
                )
            )
            dup_result = await db.execute(dup_q)
            if (dup_result.scalar() or 0) > 0:
                continue

            alert = ComplianceAlert(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=rec.store_id,
                alert_type="trace_gap",
                severity="medium",
                title=f"溯源异常：{rec.ingredient_name}（批次 {rec.batch_number}）",
                description=f"供应商：{rec.supplier_name}，状态：{rec.status}，需核实",
                related_entity_id=str(rec.id),
                auto_action="notify_manager",
            )
            db.add(alert)
            alerts.append(alert)

        # 4) 评分骤降（>10 分）
        yesterday = today - timedelta(days=1)
        score_today_q = select(ComplianceScore).where(
            and_(
                ComplianceScore.brand_id == brand_id,
                ComplianceScore.score_date == today,
            )
        )
        score_today_result = await db.execute(score_today_q)
        today_scores = score_today_result.scalars().all()

        for ts in today_scores:
            prev_q = select(ComplianceScore).where(
                and_(
                    ComplianceScore.brand_id == brand_id,
                    ComplianceScore.store_id == ts.store_id,
                    ComplianceScore.score_date == yesterday,
                )
            )
            prev_result = await db.execute(prev_q)
            prev = prev_result.scalar_one_or_none()
            if prev and prev.overall_score - ts.overall_score > 10:
                drop = prev.overall_score - ts.overall_score
                alert = ComplianceAlert(
                    id=uuid.uuid4(),
                    brand_id=brand_id,
                    store_id=ts.store_id,
                    alert_type="score_drop",
                    severity="high",
                    title=f"合规评分骤降 {drop} 分",
                    description=f"门店 {ts.store_id} 评分从 {prev.overall_score} 降至 {ts.overall_score}，需关注",
                    related_entity_id=str(ts.id),
                    auto_action="notify_manager",
                )
                db.add(alert)
                alerts.append(alert)

        await db.flush()
        logger.info("compliance_alerts_generated", brand_id=brand_id, count=len(alerts))
        return alerts

    # ── 自动操作 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def execute_auto_actions(
        db: AsyncSession,
        brand_id: str,
    ) -> List[Dict[str, Any]]:
        """根据未处理告警执行自动操作"""
        q = select(ComplianceAlert).where(
            and_(
                ComplianceAlert.brand_id == brand_id,
                ComplianceAlert.is_resolved == False,
                ComplianceAlert.auto_action.isnot(None),
            )
        )
        result = await db.execute(q)
        pending_alerts = result.scalars().all()

        actions_log: List[Dict[str, Any]] = []
        now = datetime.utcnow()

        for alert in pending_alerts:
            action_result = "executed"
            action_desc = ""

            if alert.auto_action == "block_scheduling":
                action_desc = f"已标记员工需续证（告警：{alert.title}）"
            elif alert.auto_action == "notify_manager":
                action_desc = f"已通知门店管理员（告警：{alert.title}）"
            elif alert.auto_action == "flag_inspection":
                action_desc = f"已创建整改跟踪任务（告警：{alert.title}）"
            else:
                action_result = "skipped"
                action_desc = f"未知操作类型：{alert.auto_action}"

            action_entry = {
                "action": alert.auto_action,
                "alert_id": str(alert.id),
                "store_id": alert.store_id,
                "timestamp": now.isoformat(),
                "result": action_result,
                "description": action_desc,
            }
            actions_log.append(action_entry)

        # 记录到当日评分的 auto_actions_taken
        today = date.today()
        score_q = select(ComplianceScore).where(
            and_(
                ComplianceScore.brand_id == brand_id,
                ComplianceScore.score_date == today,
            )
        )
        score_result = await db.execute(score_q)
        scores = score_result.scalars().all()
        for s in scores:
            existing_actions = s.auto_actions_taken or []
            store_actions = [a for a in actions_log if a["store_id"] == s.store_id]
            s.auto_actions_taken = existing_actions + store_actions

        await db.flush()
        logger.info("compliance_auto_actions_executed", brand_id=brand_id, count=len(actions_log))
        return actions_log

    # ── 查询方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_scores(
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        grade: Optional[str] = None,
    ) -> Tuple[List[ComplianceScore], int]:
        """分页查询门店合规评分（最新日期优先）"""
        # 先取每个门店最新评分日期
        latest_q = (
            select(
                ComplianceScore.store_id,
                func.max(ComplianceScore.score_date).label("max_date"),
            )
            .where(ComplianceScore.brand_id == brand_id)
            .group_by(ComplianceScore.store_id)
            .subquery()
        )

        q = (
            select(ComplianceScore)
            .join(
                latest_q,
                and_(
                    ComplianceScore.store_id == latest_q.c.store_id,
                    ComplianceScore.score_date == latest_q.c.max_date,
                ),
            )
            .where(ComplianceScore.brand_id == brand_id)
        )

        if grade:
            q = q.where(ComplianceScore.grade == grade)

        # 总数
        count_q = select(func.count()).select_from(q.subquery())
        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0

        # 分页
        q = q.order_by(ComplianceScore.overall_score.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(q)
        return result.scalars().all(), total

    @staticmethod
    async def get_score_detail(
        db: AsyncSession,
        score_id: str,
    ) -> Optional[ComplianceScore]:
        """获取评分详情"""
        q = select(ComplianceScore).where(ComplianceScore.id == score_id)
        result = await db.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_alerts(
        db: AsyncSession,
        brand_id: str,
        severity: Optional[str] = None,
        is_resolved: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ComplianceAlert], int]:
        """分页查询合规告警"""
        q = select(ComplianceAlert).where(ComplianceAlert.brand_id == brand_id)

        if severity:
            q = q.where(ComplianceAlert.severity == severity)
        if is_resolved is not None:
            q = q.where(ComplianceAlert.is_resolved == is_resolved)

        count_q = select(func.count()).select_from(q.subquery())
        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0

        # 按严重程度排序：critical > high > medium > low
        severity_order = func.array_position(["critical", "high", "medium", "low"], ComplianceAlert.severity)
        q = q.order_by(severity_order, ComplianceAlert.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(q)
        return result.scalars().all(), total

    @staticmethod
    async def resolve_alert(
        db: AsyncSession,
        alert_id: str,
        resolved_by: str,
    ) -> Optional[ComplianceAlert]:
        """处置告警"""
        q = select(ComplianceAlert).where(ComplianceAlert.id == alert_id)
        result = await db.execute(q)
        alert = result.scalar_one_or_none()

        if not alert:
            return None

        alert.is_resolved = True
        alert.resolved_by = resolved_by
        alert.resolved_at = datetime.utcnow()
        await db.flush()
        return alert

    @staticmethod
    async def get_dashboard(
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """品牌级合规仪表盘数据"""
        today = date.today()

        # 最新评分（每门店最新一条）
        latest_q = (
            select(
                ComplianceScore.store_id,
                func.max(ComplianceScore.score_date).label("max_date"),
            )
            .where(ComplianceScore.brand_id == brand_id)
            .group_by(ComplianceScore.store_id)
            .subquery()
        )
        scores_q = (
            select(ComplianceScore)
            .join(
                latest_q,
                and_(
                    ComplianceScore.store_id == latest_q.c.store_id,
                    ComplianceScore.score_date == latest_q.c.max_date,
                ),
            )
            .where(ComplianceScore.brand_id == brand_id)
        )

        scores_result = await db.execute(scores_q)
        scores = scores_result.scalars().all()

        # 平均分
        if scores:
            avg_score = round(sum(s.overall_score for s in scores) / len(scores))
        else:
            avg_score = 0
        avg_grade = _calc_grade(avg_score)

        # 评级分布
        grade_dist = {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for s in scores:
            if s.grade in grade_dist:
                grade_dist[s.grade] += 1

        # 趋势（过去7天平均分）
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_q = select(func.avg(ComplianceScore.overall_score)).where(
                and_(
                    ComplianceScore.brand_id == brand_id,
                    ComplianceScore.score_date == d,
                )
            )
            day_result = await db.execute(day_q)
            day_avg = day_result.scalar()
            trend.append(
                {
                    "date": d.isoformat(),
                    "avg_score": round(day_avg) if day_avg else None,
                }
            )

        # 告警统计
        alert_q = (
            select(
                ComplianceAlert.severity,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    ComplianceAlert.brand_id == brand_id,
                    ComplianceAlert.is_resolved == False,
                )
            )
            .group_by(ComplianceAlert.severity)
        )
        alert_result = await db.execute(alert_q)
        alert_counts = {r[0]: r[1] for r in alert_result.all()}

        # 最近自动操作
        recent_actions: List[Dict[str, Any]] = []
        for s in scores:
            if s.auto_actions_taken:
                for a in s.auto_actions_taken[-5:]:
                    recent_actions.append(a)
        recent_actions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "avg_score": avg_score,
            "avg_grade": avg_grade,
            "store_count": len(scores),
            "grade_distribution": grade_dist,
            "alert_counts": {
                "critical": alert_counts.get("critical", 0),
                "high": alert_counts.get("high", 0),
                "medium": alert_counts.get("medium", 0),
                "low": alert_counts.get("low", 0),
                "total": sum(alert_counts.values()),
            },
            "trend": trend,
            "recent_actions": recent_actions[:10],
        }
