"""
私域运营Agent - Private Domain Operations Agent

基于《智链OS私域运营Agent模块设计方案v2.0》实现
核心功能：
1. 信号感知引擎（Signal Radar）- 6类信号监听
2. 三维用户分层（RFM × 门店象限 × 动态标签）
3. 门店潜力四象限模型（本地化SPA）
4. 智能旅程引擎（Journey Automation）
5. 舆情监控（Reputation Guard）
6. 私域运营看板
"""

import os
import asyncio
import structlog
from datetime import datetime, timedelta, date
from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any, Tuple
from statistics import mean
from collections import defaultdict
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


# ─────────────────────────── Enums ───────────────────────────

class RFMLevel(str, Enum):
    S1 = "S1"  # 高价值
    S2 = "S2"  # 潜力
    S3 = "S3"  # 沉睡
    S4 = "S4"  # 流失预警
    S5 = "S5"  # 流失


class StoreQuadrant(str, Enum):
    BENCHMARK = "benchmark"    # 标杆：高渗透+低竞争
    DEFENSIVE = "defensive"    # 防守：高渗透+高竞争
    POTENTIAL = "potential"    # 潜力：低渗透+低竞争
    BREAKTHROUGH = "breakthrough"  # 突围：低渗透+高竞争


class SignalType(str, Enum):
    CONSUMPTION = "consumption"    # 消费信号
    CHURN_RISK = "churn_risk"      # 流失预警
    BAD_REVIEW = "bad_review"      # 差评信号
    HOLIDAY = "holiday"            # 节气/节日
    COMPETITOR = "competitor"      # 竞品动态
    VIRAL = "viral"                # 裂变触发


class JourneyType(str, Enum):
    NEW_CUSTOMER = "new_customer"      # 新客激活（7天4触点）
    VIP_RETENTION = "vip_retention"    # VIP保鲜
    REACTIVATION = "reactivation"      # 沉睡唤醒
    REVIEW_REPAIR = "review_repair"    # 差评修复


class JourneyStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ─────────────────────────── TypedDicts ───────────────────────────

class UserSegment(TypedDict):
    customer_id: str
    rfm_level: str          # S1-S5
    store_quadrant: str     # benchmark/defensive/potential/breakthrough
    dynamic_tags: List[str] # 动态标签
    recency_days: int       # 最近消费距今天数
    frequency: int          # 消费频次（近30天）
    monetary: int           # 消费金额（近30天，分）
    last_visit: str
    risk_score: float       # 流失风险分 0-1


class SignalEvent(TypedDict):
    signal_id: str
    signal_type: str
    customer_id: Optional[str]
    store_id: str
    description: str
    severity: str           # low/medium/high/critical
    triggered_at: str
    action_taken: Optional[str]


class JourneyRecord(TypedDict):
    journey_id: str
    journey_type: str
    customer_id: str
    store_id: str
    status: str
    current_step: int
    total_steps: int
    started_at: str
    next_action_at: Optional[str]
    completed_at: Optional[str]


class StoreQuadrantData(TypedDict):
    store_id: str
    store_name: str
    quadrant: str
    competition_density: float   # 竞争密度（周边1km同品类数）
    member_penetration: float    # 会员渗透率 0-1
    untapped_potential: int      # 待渗透空间（人数）
    strategy: str                # 推荐策略


class PrivateDomainDashboard(TypedDict):
    store_id: str
    total_members: int
    active_members: int          # 近30天有消费
    rfm_distribution: Dict[str, int]  # S1-S5各层人数
    pending_signals: int
    running_journeys: int
    monthly_repurchase_rate: float
    churn_risk_count: int        # 流失预警人数
    bad_review_count: int        # 近7天差评数
    store_quadrant: str
    roi_estimate: float


# ─────────────────────────── Agent ───────────────────────────

class PrivateDomainAgent(BaseAgent):
    """
    私域运营Agent

    负责餐饮连锁门店的私域用户运营，实现「防损防跑单」核心价值：
    - 防跑单：实时监控高价值用户流失信号，提前14天预警并自动挽回
    - 防损耗：差评48小时内自动处理，避免口碑坏损扩大化
    - 防竞品：门店象限监测，竞品新开店自动触发防守策略
    - 增营收：精准旅程拉动复购和客单价提升
    """

    def __init__(self, store_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.store_id = store_id
        self.logger = logger.bind(agent="private_domain", store_id=store_id)
        self._db_engine = None

        # 配置参数
        self.churn_threshold_days = int(os.getenv("PD_CHURN_THRESHOLD_DAYS", "14"))
        self.s1_min_frequency = int(os.getenv("PD_S1_MIN_FREQUENCY", "2"))
        self.s1_min_monetary = int(os.getenv("PD_S1_MIN_MONETARY", "10000"))  # 分
        self.penetration_threshold = float(os.getenv("PD_PENETRATION_THRESHOLD", "0.3"))
        self.competition_threshold = int(os.getenv("PD_COMPETITION_THRESHOLD", "5"))
        self.bad_review_threshold = int(os.getenv("PD_BAD_REVIEW_THRESHOLD", "3"))

    def get_supported_actions(self) -> List[str]:
        return [
            "get_dashboard",
            "analyze_rfm",
            "detect_signals",
            "calculate_store_quadrant",
            "trigger_journey",
            "get_journeys",
            "get_signals",
            "segment_users",
            "get_churn_risks",
            "process_bad_review",
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        self.logger.info("executing_action", action=action, params=params)
        try:
            if action == "get_dashboard":
                result = await self.get_dashboard()
            elif action == "analyze_rfm":
                result = await self.analyze_rfm(params.get("days", 30))
            elif action == "detect_signals":
                result = await self.detect_signals()
            elif action == "calculate_store_quadrant":
                result = await self.calculate_store_quadrant(
                    params.get("competition_density", 0),
                    params.get("member_count", 0),
                    params.get("estimated_population", 1000),
                )
            elif action == "trigger_journey":
                result = await self.trigger_journey(
                    params["journey_type"],
                    params["customer_id"],
                )
            elif action == "get_journeys":
                result = await self.get_journeys(params.get("status"))
            elif action == "get_signals":
                result = await self.get_signals(params.get("signal_type"), params.get("limit", 50))
            elif action == "segment_users":
                result = await self.segment_users(params.get("days", 30))
            elif action == "get_churn_risks":
                result = await self.get_churn_risks()
            elif action == "process_bad_review":
                result = await self.process_bad_review(
                    params["review_id"],
                    params.get("customer_id"),
                    params.get("rating", 2),
                    params.get("content", ""),
                )
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}",
                    execution_time=0.0,
                    metadata=None,
                )
            return AgentResponse(success=True, data=result, error=None, execution_time=0.0, metadata=None)
        except Exception as e:
            self.logger.error("action_failed", action=action, error=str(e))
            return AgentResponse(success=False, data=None, error=str(e), execution_time=0.0, metadata=None)

    # ─────────────────────────── Core Methods ───────────────────────────

    async def get_dashboard(self) -> PrivateDomainDashboard:
        """获取私域运营看板数据"""
        self.logger.info("getting_dashboard")
        rfm_data = await self.analyze_rfm(30)
        signals = await self.get_signals(limit=100)
        journeys = await self.get_journeys(status="running")
        churn_risks = await self.get_churn_risks()

        rfm_dist = defaultdict(int)
        total_members = len(rfm_data)
        active_members = 0
        for u in rfm_data:
            rfm_dist[u["rfm_level"]] += 1
            if u["recency_days"] <= 30:
                active_members += 1

        repurchase_rate = active_members / total_members if total_members > 0 else 0.0
        bad_reviews = [s for s in signals if s["signal_type"] == SignalType.BAD_REVIEW]

        # 估算ROI（基于文档公式）
        s1_count = rfm_dist.get("S1", 0)
        roi_estimate = round(s1_count * 0.12 * 200 / 3980, 2)  # 简化估算

        quadrant_data = await self.calculate_store_quadrant(
            competition_density=4.0,
            member_count=total_members,
            estimated_population=max(total_members * 3, 1000),
        )

        return PrivateDomainDashboard(
            store_id=self.store_id,
            total_members=total_members,
            active_members=active_members,
            rfm_distribution=dict(rfm_dist),
            pending_signals=len([s for s in signals if not s.get("action_taken")]),
            running_journeys=len(journeys),
            monthly_repurchase_rate=round(repurchase_rate, 3),
            churn_risk_count=len(churn_risks),
            bad_review_count=len(bad_reviews),
            store_quadrant=quadrant_data["quadrant"],
            roi_estimate=roi_estimate,
        )

    async def analyze_rfm(self, days: int = 30) -> List[UserSegment]:
        """
        RFM三维分层分析
        S1: 高价值（近30天消费≥2次 且 金额≥100元）
        S2: 潜力（近30天消费1-2次）
        S3: 沉睡（31-60天无消费）
        S4: 流失预警（61-90天无消费）
        S5: 流失（>90天无消费）
        """
        self.logger.info("analyzing_rfm", days=days)
        # 模拟数据（实际应从DB查询 orders 表）
        mock_customers = self._generate_mock_customers(50)
        segments = []
        for c in mock_customers:
            rfm_level = self._classify_rfm(c["recency_days"], c["frequency"], c["monetary"])
            risk_score = self._calculate_churn_risk(c["recency_days"], c["frequency"])
            dynamic_tags = self._infer_dynamic_tags(c)
            segments.append(UserSegment(
                customer_id=c["customer_id"],
                rfm_level=rfm_level,
                store_quadrant=StoreQuadrant.POTENTIAL.value,
                dynamic_tags=dynamic_tags,
                recency_days=c["recency_days"],
                frequency=c["frequency"],
                monetary=c["monetary"],
                last_visit=c["last_visit"],
                risk_score=risk_score,
            ))
        return segments

    async def detect_signals(self) -> List[SignalEvent]:
        """检测6类信号"""
        self.logger.info("detecting_signals")
        signals = []
        now = datetime.utcnow().isoformat()

        # 模拟信号检测（实际应查询DB + 外部API）
        mock_customers = self._generate_mock_customers(50)
        for c in mock_customers:
            # 流失预警信号
            if c["recency_days"] >= self.churn_threshold_days:
                signals.append(SignalEvent(
                    signal_id=f"SIG_CHURN_{c['customer_id']}_{date.today().isoformat()}",
                    signal_type=SignalType.CHURN_RISK.value,
                    customer_id=c["customer_id"],
                    store_id=self.store_id,
                    description=f"高价值用户 {c['customer_id']} 已 {c['recency_days']} 天未消费",
                    severity="high" if c["recency_days"] >= 30 else "medium",
                    triggered_at=now,
                    action_taken=None,
                ))
            # 高消费信号
            if c["monetary"] >= self.s1_min_monetary * 1.5:
                signals.append(SignalEvent(
                    signal_id=f"SIG_CONS_{c['customer_id']}_{date.today().isoformat()}",
                    signal_type=SignalType.CONSUMPTION.value,
                    customer_id=c["customer_id"],
                    store_id=self.store_id,
                    description=f"用户 {c['customer_id']} 本月消费 ¥{c['monetary']//100}，超均值1.5倍",
                    severity="low",
                    triggered_at=now,
                    action_taken=None,
                ))
        return signals[:20]  # 返回最新20条

    async def calculate_store_quadrant(
        self,
        competition_density: float,
        member_count: int,
        estimated_population: int,
    ) -> StoreQuadrantData:
        """
        计算门店四象限位置
        横轴：竞争密度（周边1km同品类数）
        纵轴：会员渗透率（会员数/估算消费人口）
        """
        self.logger.info("calculating_store_quadrant")
        penetration = member_count / max(estimated_population, 1)
        high_penetration = penetration >= self.penetration_threshold
        high_competition = competition_density >= self.competition_threshold

        if high_penetration and not high_competition:
            quadrant = StoreQuadrant.BENCHMARK
            strategy = "重点投放S1 VIP个性化触达，启动老带新裂变，警惕周边新竞品"
        elif high_penetration and high_competition:
            quadrant = StoreQuadrant.DEFENSIVE
            strategy = "自动触发沉睡预警，优惠券对标竞品节点推送，差评24h内自动补偿"
        elif not high_penetration and not high_competition:
            quadrant = StoreQuadrant.POTENTIAL
            strategy = "引流活码密度最高，新客激活SOP（7天4触点），LBS区域定向推送"
        else:
            quadrant = StoreQuadrant.BREAKTHROUGH
            strategy = "限时高折扣首单券定向推送，异业联名换量，朋友圈广告精准本地投放"

        return StoreQuadrantData(
            store_id=self.store_id,
            store_name=f"门店 {self.store_id}",
            quadrant=quadrant.value,
            competition_density=competition_density,
            member_penetration=round(penetration, 3),
            untapped_potential=max(0, estimated_population - member_count),
            strategy=strategy,
        )

    async def trigger_journey(self, journey_type: str, customer_id: str) -> JourneyRecord:
        """触发用户旅程"""
        self.logger.info("triggering_journey", journey_type=journey_type, customer_id=customer_id)
        journey_steps = {
            JourneyType.NEW_CUSTOMER.value: 4,      # Day0/2/5/7
            JourneyType.VIP_RETENTION.value: 4,     # 月/季/生日/年
            JourneyType.REACTIVATION.value: 3,      # 第1/2/3触
            JourneyType.REVIEW_REPAIR.value: 4,     # 30min/4h/补偿/追踪
        }
        total_steps = journey_steps.get(journey_type, 3)
        now = datetime.utcnow()
        return JourneyRecord(
            journey_id=f"JRN_{journey_type.upper()}_{customer_id}_{now.strftime('%Y%m%d%H%M%S')}",
            journey_type=journey_type,
            customer_id=customer_id,
            store_id=self.store_id,
            status=JourneyStatus.RUNNING.value,
            current_step=1,
            total_steps=total_steps,
            started_at=now.isoformat(),
            next_action_at=(now + timedelta(days=2)).isoformat(),
            completed_at=None,
        )

    async def get_journeys(self, status: Optional[str] = None) -> List[JourneyRecord]:
        """获取旅程列表"""
        self.logger.info("getting_journeys", status=status)
        # 模拟数据
        journeys = [
            JourneyRecord(
                journey_id=f"JRN_NEW_CUSTOMER_C00{i}_20260225",
                journey_type=JourneyType.NEW_CUSTOMER.value,
                customer_id=f"C00{i}",
                store_id=self.store_id,
                status=JourneyStatus.RUNNING.value if i % 3 != 0 else JourneyStatus.COMPLETED.value,
                current_step=min(i % 4 + 1, 4),
                total_steps=4,
                started_at=(datetime.utcnow() - timedelta(days=i)).isoformat(),
                next_action_at=(datetime.utcnow() + timedelta(days=1)).isoformat(),
                completed_at=None,
            )
            for i in range(1, 11)
        ]
        if status:
            journeys = [j for j in journeys if j["status"] == status]
        return journeys

    async def get_signals(
        self,
        signal_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[SignalEvent]:
        """获取信号列表"""
        signals = await self.detect_signals()
        if signal_type:
            signals = [s for s in signals if s["signal_type"] == signal_type]
        return signals[:limit]

    async def get_churn_risks(self) -> List[UserSegment]:
        """获取流失风险用户列表"""
        segments = await self.analyze_rfm(30)
        return [s for s in segments if s["rfm_level"] in ("S3", "S4", "S5") or s["risk_score"] >= 0.6]

    async def process_bad_review(
        self,
        review_id: str,
        customer_id: Optional[str],
        rating: int,
        content: str,
    ) -> Dict[str, Any]:
        """处理差评（差评修复旅程）"""
        self.logger.info("processing_bad_review", review_id=review_id, rating=rating)
        journey = None
        if customer_id:
            journey = await self.trigger_journey(JourneyType.REVIEW_REPAIR.value, customer_id)
        return {
            "review_id": review_id,
            "handled": True,
            "response_time_minutes": 28,
            "compensation_issued": rating <= 2,
            "journey_triggered": journey is not None,
            "journey_id": journey["journey_id"] if journey else None,
            "handled_at": datetime.utcnow().isoformat(),
        }

    # ─────────────────────────── Private Helpers ───────────────────────────

    def _classify_rfm(self, recency_days: int, frequency: int, monetary: int) -> str:
        if recency_days <= 30 and frequency >= self.s1_min_frequency and monetary >= self.s1_min_monetary:
            return RFMLevel.S1.value
        elif recency_days <= 30 and (frequency >= 1 or monetary >= self.s1_min_monetary // 2):
            return RFMLevel.S2.value
        elif recency_days <= 60:
            return RFMLevel.S3.value
        elif recency_days <= 90:
            return RFMLevel.S4.value
        else:
            return RFMLevel.S5.value

    def _calculate_churn_risk(self, recency_days: int, frequency: int) -> float:
        base_risk = min(recency_days / 90, 1.0)
        freq_factor = max(0, 1 - frequency * 0.1)
        return round(min(base_risk * 0.7 + freq_factor * 0.3, 1.0), 3)

    def _infer_dynamic_tags(self, customer: Dict[str, Any]) -> List[str]:
        tags = []
        if customer["monetary"] >= self.s1_min_monetary * 2:
            tags.append("高消费")
        if customer["frequency"] >= 4:
            tags.append("高频")
        if customer["recency_days"] <= 7:
            tags.append("近期活跃")
        if customer.get("avg_order_time", 12) in range(11, 14):
            tags.append("午餐偏好")
        if customer.get("avg_order_time", 12) in range(17, 21):
            tags.append("晚餐偏好")
        return tags or ["普通用户"]

    def _generate_mock_customers(self, count: int) -> List[Dict[str, Any]]:
        """生成模拟客户数据（实际应从DB查询）"""
        import random
        random.seed(42)
        customers = []
        for i in range(count):
            recency = random.randint(1, 120)
            freq = random.randint(0, 8)
            monetary = random.randint(2000, 50000)
            customers.append({
                "customer_id": f"C{str(i+1).zfill(4)}",
                "recency_days": recency,
                "frequency": freq,
                "monetary": monetary,
                "last_visit": (datetime.utcnow() - timedelta(days=recency)).strftime("%Y-%m-%d"),
                "avg_order_time": random.choice([12, 13, 18, 19, 20]),
            })
        return customers
