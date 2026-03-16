"""
供应商智能评分服务
融合 B2B采购单、食品安全溯源、供应商档案，计算四维度评分卡
"""

import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, asc, case, desc, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.food_safety import FoodTraceRecord
from src.models.supplier_agent import SupplierProfile
from src.models.supplier_b2b import B2BPurchaseItem, B2BPurchaseOrder
from src.models.supplier_intelligence import SupplierScorecard


class SupplierIntelligenceService:
    """供应商智能评分服务"""

    # 综合评分权重
    WEIGHT_DELIVERY = 0.30
    WEIGHT_QUALITY = 0.35
    WEIGHT_PRICE = 0.20
    WEIGHT_SERVICE = 0.15

    # 评级阈值
    TIER_THRESHOLDS = {"A": 85, "B": 70, "C": 50}

    # ── 评分卡计算 ───────────────────────────────────────────────

    async def compute_scorecard(
        self,
        db: AsyncSession,
        brand_id: str,
        supplier_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """
        为单个供应商计算月度评分卡。
        period 格式: "2026-03"
        """
        year, month = int(period[:4]), int(period[5:7])

        # 1) 查询 B2B 采购单数据
        delivery_data = await self._query_delivery_data(db, brand_id, supplier_id, year, month)

        # 2) 查询食品安全溯源数据
        quality_data = await self._query_quality_data(db, brand_id, supplier_id, year, month)

        # 3) 查询价格趋势数据
        price_data = await self._query_price_data(db, brand_id, supplier_id, year, month)

        # 4) 计算四维度得分
        delivery_score = self._calc_delivery_score(delivery_data)
        quality_score = self._calc_quality_score(quality_data)
        price_score = self._calc_price_score(price_data)
        service_score = self._calc_service_score(delivery_data, quality_data)

        # 5) 加权综合分
        overall_score = int(
            delivery_score * self.WEIGHT_DELIVERY
            + quality_score * self.WEIGHT_QUALITY
            + price_score * self.WEIGHT_PRICE
            + service_score * self.WEIGHT_SERVICE
        )

        # 6) 评级
        tier = self._determine_tier(overall_score)

        # 7) 价格趋势
        price_trend = price_data.get("trend", "stable")

        # 8) 推荐动作
        recommendations = self._generate_recommendations(
            delivery_score, quality_score, price_score, service_score, delivery_data, quality_data
        )

        # 9) 获取供应商名称
        supplier_name = delivery_data.get("supplier_name") or quality_data.get("supplier_name") or supplier_id

        # 10) Upsert 评分卡
        scorecard = await self._upsert_scorecard(
            db,
            brand_id=brand_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            period=period,
            delivery_score=delivery_score,
            quality_score=quality_score,
            price_score=price_score,
            service_score=service_score,
            overall_score=overall_score,
            tier=tier,
            order_count=delivery_data.get("order_count", 0),
            total_amount_fen=delivery_data.get("total_amount_fen", 0),
            defect_count=quality_data.get("defect_count", 0),
            late_delivery_count=delivery_data.get("late_count", 0),
            price_trend=price_trend,
            recommendations=recommendations,
        )

        return scorecard.to_dict()

    async def compute_all_scorecards(
        self,
        db: AsyncSession,
        brand_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """批量计算所有活跃供应商的评分卡"""
        year, month = int(period[:4]), int(period[5:7])

        # 从采购单和溯源记录中收集所有供应商
        supplier_ids = set()

        # 从 B2B 采购单获取供应商
        po_result = await db.execute(
            select(B2BPurchaseOrder.supplier_id)
            .where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    extract("year", B2BPurchaseOrder.created_at) == year,
                    extract("month", B2BPurchaseOrder.created_at) == month,
                )
            )
            .distinct()
        )
        for row in po_result.scalars().all():
            supplier_ids.add(row)

        # 从溯源记录获取供应商
        trace_result = await db.execute(
            select(FoodTraceRecord.supplier_id)
            .where(
                and_(
                    FoodTraceRecord.brand_id == brand_id,
                    extract("year", FoodTraceRecord.receive_date) == year,
                    extract("month", FoodTraceRecord.receive_date) == month,
                    FoodTraceRecord.supplier_id.isnot(None),
                )
            )
            .distinct()
        )
        for row in trace_result.scalars().all():
            if row:
                supplier_ids.add(row)

        # 逐个计算
        results = []
        for sid in supplier_ids:
            card = await self.compute_scorecard(db, brand_id, sid, period)
            results.append(card)

        return {
            "period": period,
            "supplier_count": len(results),
            "scorecards": results,
        }

    # ── 查询接口 ─────────────────────────────────────────────────

    async def get_scorecards(
        self,
        db: AsyncSession,
        brand_id: str,
        period: Optional[str] = None,
        tier: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页查询评分卡列表"""
        conditions = [SupplierScorecard.brand_id == brand_id]
        if period:
            conditions.append(SupplierScorecard.score_period == period)
        if tier:
            conditions.append(SupplierScorecard.tier == tier.upper())

        # 总数
        count_q = select(func.count()).select_from(SupplierScorecard).where(and_(*conditions))
        total = (await db.execute(count_q)).scalar_one()

        # 分页数据
        offset = (page - 1) * page_size
        data_q = (
            select(SupplierScorecard)
            .where(and_(*conditions))
            .order_by(desc(SupplierScorecard.overall_score))
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(data_q)).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [r.to_dict() for r in rows],
        }

    async def get_scorecard_detail(
        self,
        db: AsyncSession,
        scorecard_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取评分卡详情"""
        result = await db.execute(select(SupplierScorecard).where(SupplierScorecard.id == scorecard_id))
        card = result.scalar_one_or_none()
        return card.to_dict() if card else None

    async def get_price_trends(
        self,
        db: AsyncSession,
        brand_id: str,
        supplier_id: str,
        months: int = 6,
    ) -> List[Dict[str, Any]]:
        """获取供应商最近 N 个月的食材价格趋势（来自 B2B 采购单明细）"""
        today = date.today()
        start_year = today.year
        start_month = today.month - months
        if start_month <= 0:
            start_year -= 1
            start_month += 12

        start_date = date(start_year, start_month, 1)

        # 按月份 + 食材聚合平均单价
        result = await db.execute(
            select(
                extract("year", B2BPurchaseOrder.created_at).label("yr"),
                extract("month", B2BPurchaseOrder.created_at).label("mo"),
                B2BPurchaseItem.ingredient_name,
                func.avg(B2BPurchaseItem.unit_price_fen).label("avg_price_fen"),
                func.sum(B2BPurchaseItem.amount_fen).label("total_fen"),
            )
            .join(B2BPurchaseItem, B2BPurchaseItem.order_id == B2BPurchaseOrder.id)
            .where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    B2BPurchaseOrder.supplier_id == supplier_id,
                    B2BPurchaseOrder.created_at >= start_date,
                    B2BPurchaseOrder.status.in_(["received", "completed"]),
                )
            )
            .group_by("yr", "mo", B2BPurchaseItem.ingredient_name)
            .order_by("yr", "mo")
        )

        trends: List[Dict[str, Any]] = []
        for row in result.all():
            trends.append(
                {
                    "period": f"{int(row.yr):04d}-{int(row.mo):02d}",
                    "ingredient_name": row.ingredient_name,
                    "avg_price_yuan": round(float(row.avg_price_fen) / 100, 2),
                    "total_yuan": round(float(row.total_fen) / 100, 2),
                }
            )

        return trends

    async def get_ranking(
        self,
        db: AsyncSession,
        brand_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """供应商排名及评级分布"""
        conditions = [
            SupplierScorecard.brand_id == brand_id,
            SupplierScorecard.score_period == period,
        ]

        # 排名列表
        result = await db.execute(
            select(SupplierScorecard).where(and_(*conditions)).order_by(desc(SupplierScorecard.overall_score))
        )
        cards = result.scalars().all()

        # 评级分布
        tier_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
        ranking = []
        for idx, card in enumerate(cards, 1):
            tier_dist[card.tier] = tier_dist.get(card.tier, 0) + 1
            ranking.append(
                {
                    "rank": idx,
                    **card.to_dict(),
                }
            )

        return {
            "period": period,
            "total_suppliers": len(cards),
            "tier_distribution": tier_dist,
            "ranking": ranking,
        }

    async def get_risk_alerts(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> List[Dict[str, Any]]:
        """
        识别高风险供应商：
        - D 级供应商
        - 缺陷率高（defect_count >= 3）
        - 延迟交付多（late_delivery_count >= 3）
        - 食安问题（recalled 状态的溯源记录）
        """
        alerts: List[Dict[str, Any]] = []

        # 最新周期的 D 级或低分供应商
        latest_period_q = select(func.max(SupplierScorecard.score_period)).where(SupplierScorecard.brand_id == brand_id)
        latest_period = (await db.execute(latest_period_q)).scalar_one_or_none()

        if not latest_period:
            return alerts

        result = await db.execute(
            select(SupplierScorecard).where(
                and_(
                    SupplierScorecard.brand_id == brand_id,
                    SupplierScorecard.score_period == latest_period,
                )
            )
        )
        cards = result.scalars().all()

        for card in cards:
            reasons = []
            if card.tier == "D":
                reasons.append(f"综合评级D（{card.overall_score}分），远低于合格线")
            if card.defect_count >= 3:
                reasons.append(f"本月缺陷{card.defect_count}次，食安风险较高")
            if card.late_delivery_count >= 3:
                reasons.append(f"迟交{card.late_delivery_count}次，交付可靠性不足")
            if card.delivery_score < 50:
                reasons.append(f"交付评分仅{card.delivery_score}分")
            if card.quality_score < 50:
                reasons.append(f"质量评分仅{card.quality_score}分")

            if reasons:
                recommended_action = self._risk_action(card)
                alerts.append(
                    {
                        "scorecard_id": str(card.id),
                        "supplier_id": card.supplier_id,
                        "supplier_name": card.supplier_name,
                        "tier": card.tier,
                        "overall_score": card.overall_score,
                        "reasons": reasons,
                        "recommended_action": recommended_action,
                        "total_amount_yuan": round(card.total_amount_fen / 100, 2),
                        "period": card.score_period,
                    }
                )

        # 按风险严重度排序（综合分越低越靠前）
        alerts.sort(key=lambda a: a["overall_score"])
        return alerts

    # ── 内部计算方法 ─────────────────────────────────────────────

    async def _query_delivery_data(
        self, db: AsyncSession, brand_id: str, supplier_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """从 B2B 采购单提取交付数据"""
        result = await db.execute(
            select(
                func.count(B2BPurchaseOrder.id).label("order_count"),
                func.sum(B2BPurchaseOrder.total_amount_fen).label("total_fen"),
                func.max(B2BPurchaseOrder.supplier_name).label("supplier_name"),
                # 已完成/已收货的订单
                func.sum(
                    case(
                        (B2BPurchaseOrder.status.in_(["received", "completed"]), 1),
                        else_=0,
                    )
                ).label("completed_count"),
                # 准时交付（实际 <= 预期）
                func.sum(
                    case(
                        (
                            and_(
                                B2BPurchaseOrder.actual_delivery_date.isnot(None),
                                B2BPurchaseOrder.expected_delivery_date.isnot(None),
                                B2BPurchaseOrder.actual_delivery_date <= B2BPurchaseOrder.expected_delivery_date,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("on_time_count"),
                # 迟交
                func.sum(
                    case(
                        (
                            and_(
                                B2BPurchaseOrder.actual_delivery_date.isnot(None),
                                B2BPurchaseOrder.expected_delivery_date.isnot(None),
                                B2BPurchaseOrder.actual_delivery_date > B2BPurchaseOrder.expected_delivery_date,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("late_count"),
            ).where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    B2BPurchaseOrder.supplier_id == supplier_id,
                    extract("year", B2BPurchaseOrder.created_at) == year,
                    extract("month", B2BPurchaseOrder.created_at) == month,
                )
            )
        )
        row = result.one()
        return {
            "order_count": row.order_count or 0,
            "total_amount_fen": int(row.total_fen or 0),
            "supplier_name": row.supplier_name,
            "completed_count": int(row.completed_count or 0),
            "on_time_count": int(row.on_time_count or 0),
            "late_count": int(row.late_count or 0),
        }

    async def _query_quality_data(
        self, db: AsyncSession, brand_id: str, supplier_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """从食品安全溯源记录提取质量数据"""
        result = await db.execute(
            select(
                func.count(FoodTraceRecord.id).label("total_records"),
                func.max(FoodTraceRecord.supplier_name).label("supplier_name"),
                # 正常状态
                func.sum(case((FoodTraceRecord.status == "normal", 1), else_=0)).label("normal_count"),
                # 召回
                func.sum(case((FoodTraceRecord.status == "recalled", 1), else_=0)).label("recalled_count"),
                # 预警
                func.sum(case((FoodTraceRecord.status == "warning", 1), else_=0)).label("warning_count"),
                # 有证书
                func.sum(case((FoodTraceRecord.certificate_url.isnot(None), 1), else_=0)).label("cert_count"),
                # 温控达标（冷链 0-8 度范围内视为达标）
                func.sum(
                    case(
                        (
                            and_(
                                FoodTraceRecord.temperature_on_receive.isnot(None),
                                FoodTraceRecord.temperature_on_receive >= 0,
                                FoodTraceRecord.temperature_on_receive <= 8,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("temp_ok_count"),
                # 有温度记录
                func.sum(case((FoodTraceRecord.temperature_on_receive.isnot(None), 1), else_=0)).label("temp_recorded_count"),
            ).where(
                and_(
                    FoodTraceRecord.brand_id == brand_id,
                    FoodTraceRecord.supplier_id == supplier_id,
                    extract("year", FoodTraceRecord.receive_date) == year,
                    extract("month", FoodTraceRecord.receive_date) == month,
                )
            )
        )
        row = result.one()
        defect_count = int(row.recalled_count or 0) + int(row.warning_count or 0)
        return {
            "total_records": int(row.total_records or 0),
            "supplier_name": row.supplier_name,
            "normal_count": int(row.normal_count or 0),
            "recalled_count": int(row.recalled_count or 0),
            "warning_count": int(row.warning_count or 0),
            "cert_count": int(row.cert_count or 0),
            "temp_ok_count": int(row.temp_ok_count or 0),
            "temp_recorded_count": int(row.temp_recorded_count or 0),
            "defect_count": defect_count,
        }

    async def _query_price_data(
        self, db: AsyncSession, brand_id: str, supplier_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """从 B2B 采购明细提取价格数据，判断趋势"""
        # 本月平均单价
        current_q = await db.execute(
            select(func.avg(B2BPurchaseItem.unit_price_fen).label("avg_price"))
            .join(B2BPurchaseItem, B2BPurchaseItem.order_id == B2BPurchaseOrder.id)
            .where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    B2BPurchaseOrder.supplier_id == supplier_id,
                    extract("year", B2BPurchaseOrder.created_at) == year,
                    extract("month", B2BPurchaseOrder.created_at) == month,
                )
            )
        )
        current_avg = current_q.scalar_one_or_none()

        # 上月平均单价
        prev_month = month - 1
        prev_year = year
        if prev_month <= 0:
            prev_month = 12
            prev_year -= 1

        prev_q = await db.execute(
            select(func.avg(B2BPurchaseItem.unit_price_fen).label("avg_price"))
            .join(B2BPurchaseItem, B2BPurchaseItem.order_id == B2BPurchaseOrder.id)
            .where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    B2BPurchaseOrder.supplier_id == supplier_id,
                    extract("year", B2BPurchaseOrder.created_at) == prev_year,
                    extract("month", B2BPurchaseOrder.created_at) == prev_month,
                )
            )
        )
        prev_avg = prev_q.scalar_one_or_none()

        trend = "stable"
        change_pct = 0.0
        if current_avg and prev_avg and float(prev_avg) > 0:
            change_pct = (float(current_avg) - float(prev_avg)) / float(prev_avg) * 100
            if change_pct > 5:
                trend = "up"
            elif change_pct < -5:
                trend = "down"

        return {
            "current_avg_fen": float(current_avg) if current_avg else 0,
            "prev_avg_fen": float(prev_avg) if prev_avg else 0,
            "change_pct": round(change_pct, 2),
            "trend": trend,
        }

    def _calc_delivery_score(self, data: Dict[str, Any]) -> int:
        """交付评分：准时率为主"""
        order_count = data.get("order_count", 0)
        if order_count == 0:
            return 70  # 无数据给基准分

        completed = data.get("completed_count", 0)
        on_time = data.get("on_time_count", 0)

        # 完成率权重 40%，准时率权重 60%
        completion_rate = completed / order_count if order_count > 0 else 0
        on_time_rate = on_time / completed if completed > 0 else 0

        score = int(completion_rate * 40 + on_time_rate * 60)
        return max(0, min(100, score))

    def _calc_quality_score(self, data: Dict[str, Any]) -> int:
        """质量评分：食安合格率 + 温控达标 + 证书齐全"""
        total = data.get("total_records", 0)
        if total == 0:
            return 70  # 无数据给基准分

        normal = data.get("normal_count", 0)
        recalled = data.get("recalled_count", 0)
        cert_count = data.get("cert_count", 0)
        temp_ok = data.get("temp_ok_count", 0)
        temp_recorded = data.get("temp_recorded_count", 0)

        # 合格率 50% 权重
        pass_rate = normal / total
        pass_score = pass_rate * 50

        # 温控达标 30% 权重
        temp_rate = temp_ok / temp_recorded if temp_recorded > 0 else 1.0
        temp_score = temp_rate * 30

        # 证书齐全 20% 权重
        cert_rate = cert_count / total
        cert_score = cert_rate * 20

        # 召回严重扣分
        recall_penalty = recalled * 10

        score = int(pass_score + temp_score + cert_score - recall_penalty)
        return max(0, min(100, score))

    def _calc_price_score(self, data: Dict[str, Any]) -> int:
        """价格评分：稳定性和竞争力"""
        change_pct = abs(data.get("change_pct", 0))

        # 波动越小分越高
        if change_pct <= 2:
            score = 95
        elif change_pct <= 5:
            score = 85
        elif change_pct <= 10:
            score = 70
        elif change_pct <= 20:
            score = 55
        else:
            score = 35

        # 价格下降额外加分
        if data.get("change_pct", 0) < -2:
            score = min(100, score + 5)

        return score

    def _calc_service_score(self, delivery_data: Dict, quality_data: Dict) -> int:
        """服务评分：综合响应度（基于交付和质量表现推算）"""
        order_count = delivery_data.get("order_count", 0)
        total_records = quality_data.get("total_records", 0)

        if order_count == 0 and total_records == 0:
            return 70

        score = 80  # 基准分

        # 迟交次数扣分
        late = delivery_data.get("late_count", 0)
        if late > 0:
            score -= late * 8

        # 缺陷扣分
        defects = quality_data.get("defect_count", 0)
        if defects > 0:
            score -= defects * 6

        # 订单量多加分（活跃度）
        if order_count >= 10:
            score += 5
        elif order_count >= 5:
            score += 3

        return max(0, min(100, score))

    def _determine_tier(self, overall_score: int) -> str:
        """根据综合分确定评级"""
        if overall_score >= self.TIER_THRESHOLDS["A"]:
            return "A"
        elif overall_score >= self.TIER_THRESHOLDS["B"]:
            return "B"
        elif overall_score >= self.TIER_THRESHOLDS["C"]:
            return "C"
        return "D"

    def _generate_recommendations(
        self,
        delivery_score: int,
        quality_score: int,
        price_score: int,
        service_score: int,
        delivery_data: Dict,
        quality_data: Dict,
    ) -> List[str]:
        """基于弱项维度生成改进建议"""
        recs = []

        if delivery_score < 60:
            late = delivery_data.get("late_count", 0)
            recs.append(f"交付准时率偏低（迟交{late}次），建议约谈供应商优化物流方案")

        if quality_score < 60:
            recalled = quality_data.get("recalled_count", 0)
            if recalled > 0:
                recs.append(f"存在{recalled}次食材召回记录，建议加强进货检验并考虑暂停合作")
            else:
                recs.append("食安合格率不达标，建议加强温控监管和证书审核")

        if price_score < 60:
            recs.append("价格波动较大，建议签订锁价合同或引入备选供应商竞价")

        if service_score < 60:
            recs.append("服务响应度低，建议设置SLA考核机制并定期评估")

        # 综合建议
        overall = int(
            delivery_score * self.WEIGHT_DELIVERY
            + quality_score * self.WEIGHT_QUALITY
            + price_score * self.WEIGHT_PRICE
            + service_score * self.WEIGHT_SERVICE
        )
        if overall < 50:
            recs.append("综合评分过低，建议启动供应商淘汰流程，优先寻找替代来源")
        elif overall >= 85:
            recs.append("表现优秀，建议提升为战略供应商，协商年度框架协议以锁定优惠")

        return recs if recs else ["当前各项指标正常，保持监控"]

    def _risk_action(self, card: SupplierScorecard) -> str:
        """根据风险类型生成推荐行动"""
        if card.tier == "D":
            return f"建议在7天内约谈{card.supplier_name}并启动替代供应商寻源，预估涉及金额 ¥{round(card.total_amount_fen / 100, 2)}"
        if card.defect_count >= 3:
            return f"食安缺陷{card.defect_count}次，建议暂停接收该供应商食材并安排第三方检测"
        if card.late_delivery_count >= 3:
            return f"交付延迟{card.late_delivery_count}次，建议启用备选供应商分担订单"
        return "建议加强监控，下月重新评估"

    async def _upsert_scorecard(
        self,
        db: AsyncSession,
        brand_id: str,
        supplier_id: str,
        supplier_name: str,
        period: str,
        **kwargs,
    ) -> SupplierScorecard:
        """创建或更新评分卡"""
        result = await db.execute(
            select(SupplierScorecard).where(
                and_(
                    SupplierScorecard.brand_id == brand_id,
                    SupplierScorecard.supplier_id == supplier_id,
                    SupplierScorecard.score_period == period,
                )
            )
        )
        card = result.scalar_one_or_none()

        if card:
            # 更新
            for key, val in kwargs.items():
                setattr(card, key, val)
            card.supplier_name = supplier_name
        else:
            # 新建
            card = SupplierScorecard(
                id=uuid.uuid4(),
                brand_id=brand_id,
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                score_period=period,
                **kwargs,
            )
            db.add(card)

        await db.flush()
        return card
