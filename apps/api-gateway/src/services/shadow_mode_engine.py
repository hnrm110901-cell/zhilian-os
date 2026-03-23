"""
影子模式引擎 + 一致性比对 + 灰度切换控制器
SaaS渐进替换的安全网

三大核心能力：
  1. ShadowModeEngine: 影子记账引擎，原SaaS与屯象OS双写对比
  2. ConsistencyChecker: 一致性比对引擎，每日自动对账
  3. CutoverController: 灰度切换控制器，按模块/门店/角色渐进切换

状态机：shadow → canary → primary → sole
任何阶段 < 30秒回退到上一状态
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ShadowCompareResult:
    """双写对比结果"""
    source_id: str
    record_type: str
    is_consistent: bool
    diff_fields: List[str] = field(default_factory=list)
    source_amount_fen: int = 0
    shadow_amount_fen: int = 0
    diff_amount_fen: int = 0


@dataclass
class ConsistencyResult:
    """一致性报告"""
    session_id: str
    store_id: str
    report_date: str
    period_type: str
    total_compared: int
    consistent_count: int
    inconsistent_count: int
    consistency_rate: float
    level: str                   # perfect / acceptable / warning / critical
    total_diff_amount_fen: int
    is_pass: bool
    order_consistency_rate: Optional[float] = None
    inventory_consistency_rate: Optional[float] = None
    payment_consistency_rate: Optional[float] = None
    top_diffs: List[Dict] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class CutoverStatus:
    """切换状态"""
    store_id: str
    module: str
    phase: str
    previous_phase: Optional[str]
    shadow_pass_days: int
    health_gate_passed: bool
    canary_percentage: int
    can_advance: bool
    can_rollback: bool


# ── 影子模式引擎 ──────────────────────────────────────────────────────────────

class ShadowModeEngine:
    """
    影子记账引擎

    工作模式：
    1. 原SaaS系统正常运行（主）
    2. 屯象OS同步接收同样的业务数据（影子）
    3. 两边独立计算结果
    4. 对比差异，生成一致性报告

    当连续N天差异率 < 0.1%，标记为"可切换"
    """

    def __init__(self):
        self._sessions: Dict[str, Dict] = {}
        self._records: Dict[str, List[Dict]] = {}  # session_id -> records

    def create_session(
        self,
        brand_id: str,
        store_id: str,
        source_system: str,
        modules: Optional[List[str]] = None,
        target_pass_days: int = 30,
    ) -> Dict:
        """创建影子运行会话"""
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "brand_id": brand_id,
            "store_id": store_id,
            "source_system": source_system,
            "status": "active",
            "modules": modules or ["order", "inventory"],
            "total_records": 0,
            "consistent_records": 0,
            "inconsistent_records": 0,
            "consistency_rate": 0.0,
            "consecutive_pass_days": 0,
            "target_pass_days": target_pass_days,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._sessions[session_id] = session
        self._records[session_id] = []

        logger.info(
            "shadow_engine.session_created",
            session_id=session_id,
            store_id=store_id,
            source_system=source_system,
        )
        return session

    def record_shadow(
        self,
        session_id: str,
        record_type: str,
        source_id: str,
        source_data: Dict,
        source_amount_fen: Optional[int] = None,
        shadow_data: Optional[Dict] = None,
        shadow_amount_fen: Optional[int] = None,
    ) -> Dict:
        """记录一条影子数据"""
        session = self._sessions.get(session_id)
        if not session or session["status"] != "active":
            return {"error": "会话不存在或已停止"}

        record = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "store_id": session["store_id"],
            "record_type": record_type,
            "source_system": session["source_system"],
            "source_id": source_id,
            "source_data": source_data,
            "source_amount_fen": source_amount_fen,
            "shadow_data": shadow_data,
            "shadow_amount_fen": shadow_amount_fen,
            "is_consistent": None,
            "diff_fields": None,
            "diff_amount_fen": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._records.setdefault(session_id, []).append(record)
        session["total_records"] += 1
        return record

    def compare_record(self, record: Dict) -> ShadowCompareResult:
        """对比单条影子记录"""
        source_data = record.get("source_data") or {}
        shadow_data = record.get("shadow_data") or {}
        source_amount = record.get("source_amount_fen") or 0
        shadow_amount = record.get("shadow_amount_fen") or 0

        diff_fields = []
        # 对比所有共有字段
        all_keys = set(source_data.keys()) | set(shadow_data.keys())
        for key in all_keys:
            sv = source_data.get(key)
            shv = shadow_data.get(key)
            if sv != shv and sv is not None and shv is not None:
                diff_fields.append(key)

        # 金额差异
        diff_amount = abs(source_amount - shadow_amount)
        is_consistent = len(diff_fields) == 0 and diff_amount == 0

        # 更新记录
        record["is_consistent"] = is_consistent
        record["diff_fields"] = diff_fields
        record["diff_amount_fen"] = diff_amount
        record["compared_at"] = datetime.utcnow().isoformat()

        return ShadowCompareResult(
            source_id=record.get("source_id", ""),
            record_type=record.get("record_type", ""),
            is_consistent=is_consistent,
            diff_fields=diff_fields,
            source_amount_fen=source_amount,
            shadow_amount_fen=shadow_amount,
            diff_amount_fen=diff_amount,
        )

    def get_session_stats(self, session_id: str) -> Optional[Dict]:
        """获取会话统计"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        records = self._records.get(session_id, [])
        compared = [r for r in records if r.get("is_consistent") is not None]
        consistent = sum(1 for r in compared if r.get("is_consistent"))
        inconsistent = len(compared) - consistent

        session["consistent_records"] = consistent
        session["inconsistent_records"] = inconsistent
        if compared:
            session["consistency_rate"] = round(consistent / len(compared), 4)

        return session


# ── 一致性比对引擎 ────────────────────────────────────────────────────────────

class ConsistencyChecker:
    """
    一致性比对引擎

    每日自动对账，生成一致性报告：
    - 订单数据一致性
    - 库存数据一致性
    - 支付数据一致性
    - 金额差异汇总
    """

    THRESHOLDS = {
        "perfect": 1.0,       # 完全一致
        "acceptable": 0.999,  # 差异率 < 0.1%
        "warning": 0.99,      # 差异率 < 1%
        # < 0.99 → critical
    }

    def check_daily(
        self,
        session_id: str,
        store_id: str,
        records: List[Dict],
        report_date: Optional[date] = None,
    ) -> ConsistencyResult:
        """
        生成每日一致性报告

        Args:
            session_id: 影子会话ID
            store_id: 门店ID
            records: 当日所有影子记录（需已对比）
            report_date: 报告日期
        """
        compared = [r for r in records if r.get("is_consistent") is not None]
        consistent = sum(1 for r in compared if r["is_consistent"])
        inconsistent = len(compared) - consistent
        total = len(compared)

        rate = consistent / max(total, 1)
        total_diff = sum(abs(r.get("diff_amount_fen", 0)) for r in compared)

        # 判断等级
        level = "critical"
        for lvl, threshold in self.THRESHOLDS.items():
            if rate >= threshold:
                level = lvl
                break

        is_pass = rate >= self.THRESHOLDS["acceptable"]

        # 分类统计
        by_type: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "consistent": 0})
        for r in compared:
            rt = r.get("record_type", "unknown")
            by_type[rt]["total"] += 1
            if r["is_consistent"]:
                by_type[rt]["consistent"] += 1

        order_rate = None
        inventory_rate = None
        payment_rate = None
        if "order" in by_type and by_type["order"]["total"] > 0:
            order_rate = round(by_type["order"]["consistent"] / by_type["order"]["total"], 4)
        if "inventory" in by_type and by_type["inventory"]["total"] > 0:
            inventory_rate = round(by_type["inventory"]["consistent"] / by_type["inventory"]["total"], 4)
        if "payment" in by_type and by_type["payment"]["total"] > 0:
            payment_rate = round(by_type["payment"]["consistent"] / by_type["payment"]["total"], 4)

        # TOP差异
        diffs = [r for r in compared if not r["is_consistent"]]
        diffs.sort(key=lambda r: abs(r.get("diff_amount_fen", 0)), reverse=True)
        top_diffs = [
            {
                "source_id": r.get("source_id"),
                "record_type": r.get("record_type"),
                "diff_fields": r.get("diff_fields"),
                "diff_amount_fen": r.get("diff_amount_fen"),
            }
            for r in diffs[:10]
        ]

        # 修复建议
        recommendations = []
        if not is_pass:
            if order_rate is not None and order_rate < 0.999:
                recommendations.append("订单数据存在差异，请检查POS同步延迟或金额计算规则")
            if inventory_rate is not None and inventory_rate < 0.999:
                recommendations.append("库存数据不一致，建议核对盘点时间和扣减逻辑")
            if total_diff > 10000:  # > ¥100
                recommendations.append(f"金额差异 ¥{total_diff / 100:.2f}，需重点排查大额差异订单")

        return ConsistencyResult(
            session_id=session_id,
            store_id=store_id,
            report_date=(report_date or date.today()).isoformat(),
            period_type="daily",
            total_compared=total,
            consistent_count=consistent,
            inconsistent_count=inconsistent,
            consistency_rate=round(rate, 4),
            level=level,
            total_diff_amount_fen=total_diff,
            is_pass=is_pass,
            order_consistency_rate=order_rate,
            inventory_consistency_rate=inventory_rate,
            payment_consistency_rate=payment_rate,
            top_diffs=top_diffs,
            recommendations=recommendations,
        )


# ── 灰度切换控制器 ────────────────────────────────────────────────────────────

class CutoverController:
    """
    灰度切换控制器

    按三个维度渐进切换：
    1. 按模块：analytics → management → operations → finance
    2. 按门店：试点店 → 扩展 → 全品牌
    3. 按角色：管理层 → 店长 → 收银员

    状态机：shadow → canary → primary → sole
    每个(门店, 模块)独立控制，任何阶段可回退
    """

    PHASE_ORDER = ["shadow", "canary", "primary", "sole"]
    MODULE_ORDER = ["analytics", "management", "operations", "finance"]

    # 每个阶段的切换条件
    ADVANCE_REQUIREMENTS = {
        "shadow_to_canary": {
            "min_pass_days": 7,
            "min_consistency_rate": 0.999,
        },
        "canary_to_primary": {
            "min_pass_days": 14,
            "min_consistency_rate": 0.999,
            "min_canary_percentage": 50,
        },
        "primary_to_sole": {
            "min_pass_days": 30,
            "min_consistency_rate": 0.9999,
        },
    }

    def __init__(self):
        self._states: Dict[str, Dict] = {}  # key: "{store_id}:{module}"

    def init_cutover(
        self,
        brand_id: str,
        store_id: str,
        module: str,
    ) -> CutoverStatus:
        """初始化切换状态（默认从shadow开始）"""
        key = f"{store_id}:{module}"
        state = {
            "id": str(uuid.uuid4()),
            "brand_id": brand_id,
            "store_id": store_id,
            "module": module,
            "phase": "shadow",
            "previous_phase": None,
            "shadow_pass_days": 0,
            "required_pass_days": 30,
            "health_gate_passed": False,
            "canary_percentage": 0,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._states[key] = state
        return self._to_status(state)

    def advance(
        self,
        store_id: str,
        module: str,
        operator: str = "system",
        reason: str = "",
    ) -> CutoverStatus:
        """
        推进到下一阶段

        前置条件检查：
        - shadow → canary: 影子模式达标天数 >= 7, 一致性 >= 99.9%
        - canary → primary: 灰度达标天数 >= 14, 灰度比例 >= 50%
        - primary → sole: 主切达标天数 >= 30, 一致性 >= 99.99%
        """
        key = f"{store_id}:{module}"
        state = self._states.get(key)
        if not state:
            raise ValueError(f"切换状态不存在: {key}")

        current = state["phase"]
        idx = self.PHASE_ORDER.index(current)
        if idx >= len(self.PHASE_ORDER) - 1:
            raise ValueError("已是最终阶段，无法继续推进")

        next_phase = self.PHASE_ORDER[idx + 1]
        transition_key = f"{current}_to_{next_phase}"
        requirements = self.ADVANCE_REQUIREMENTS.get(transition_key, {})

        # 检查前置条件
        min_days = requirements.get("min_pass_days", 0)
        if state["shadow_pass_days"] < min_days:
            raise ValueError(
                f"达标天数不足: {state['shadow_pass_days']}/{min_days}"
            )

        if not state.get("health_gate_passed"):
            raise ValueError("健康门禁未通过")

        # 执行切换
        state["previous_phase"] = current
        state["phase"] = next_phase
        state["last_transition_at"] = datetime.utcnow().isoformat()

        logger.info(
            "cutover.advance",
            store_id=store_id,
            module=module,
            from_phase=current,
            to_phase=next_phase,
            operator=operator,
        )
        return self._to_status(state)

    def rollback(
        self,
        store_id: str,
        module: str,
        operator: str = "system",
        reason: str = "",
    ) -> CutoverStatus:
        """
        回退到上一阶段 — < 30秒生效

        安全机制：
        - sole 不能直接回退到 shadow（必须逐级）
        - 回退后重置达标天数
        """
        key = f"{store_id}:{module}"
        state = self._states.get(key)
        if not state:
            raise ValueError(f"切换状态不存在: {key}")

        current = state["phase"]
        idx = self.PHASE_ORDER.index(current)
        if idx <= 0:
            raise ValueError("已是最初阶段，无法回退")

        prev_phase = self.PHASE_ORDER[idx - 1]

        state["previous_phase"] = current
        state["phase"] = prev_phase
        state["shadow_pass_days"] = 0  # 回退后重置达标天数
        state["health_gate_passed"] = False
        state["last_transition_at"] = datetime.utcnow().isoformat()

        logger.info(
            "cutover.rollback",
            store_id=store_id,
            module=module,
            from_phase=current,
            to_phase=prev_phase,
            operator=operator,
            reason=reason,
        )
        return self._to_status(state)

    def update_health(
        self,
        store_id: str,
        module: str,
        consistency_rate: float,
        is_daily_pass: bool,
    ) -> CutoverStatus:
        """
        更新健康指标（由 ConsistencyChecker 每日回调）

        Args:
            consistency_rate: 当日一致性比率
            is_daily_pass: 当日是否达标
        """
        key = f"{store_id}:{module}"
        state = self._states.get(key)
        if not state:
            raise ValueError(f"切换状态不存在: {key}")

        if is_daily_pass:
            state["shadow_pass_days"] += 1
        else:
            state["shadow_pass_days"] = 0  # 不达标则重置

        # 判断健康门禁
        phase = state["phase"]
        transition_key = f"{phase}_to_{self.PHASE_ORDER[min(self.PHASE_ORDER.index(phase) + 1, len(self.PHASE_ORDER) - 1)]}"
        requirements = self.ADVANCE_REQUIREMENTS.get(transition_key, {})
        min_rate = requirements.get("min_consistency_rate", 0.999)
        min_days = requirements.get("min_pass_days", 7)

        state["health_gate_passed"] = (
            consistency_rate >= min_rate
            and state["shadow_pass_days"] >= min_days
        )

        return self._to_status(state)

    def set_canary_percentage(
        self,
        store_id: str,
        module: str,
        percentage: int,
    ) -> CutoverStatus:
        """设置灰度流量比例（仅canary阶段有效）"""
        key = f"{store_id}:{module}"
        state = self._states.get(key)
        if not state:
            raise ValueError(f"切换状态不存在: {key}")
        if state["phase"] != "canary":
            raise ValueError("仅canary阶段可设置灰度比例")
        state["canary_percentage"] = max(0, min(100, percentage))
        return self._to_status(state)

    def get_status(self, store_id: str, module: str) -> Optional[CutoverStatus]:
        """获取切换状态"""
        key = f"{store_id}:{module}"
        state = self._states.get(key)
        if not state:
            return None
        return self._to_status(state)

    def get_store_overview(self, store_id: str) -> List[CutoverStatus]:
        """获取门店所有模块的切换状态"""
        results = []
        for module in self.MODULE_ORDER:
            key = f"{store_id}:{module}"
            state = self._states.get(key)
            if state:
                results.append(self._to_status(state))
        return results

    def _to_status(self, state: Dict) -> CutoverStatus:
        phase = state["phase"]
        idx = self.PHASE_ORDER.index(phase)
        can_advance = idx < len(self.PHASE_ORDER) - 1 and state.get("health_gate_passed", False)
        can_rollback = idx > 0

        return CutoverStatus(
            store_id=state["store_id"],
            module=state["module"],
            phase=phase,
            previous_phase=state.get("previous_phase"),
            shadow_pass_days=state.get("shadow_pass_days", 0),
            health_gate_passed=state.get("health_gate_passed", False),
            canary_percentage=state.get("canary_percentage", 0),
            can_advance=can_advance,
            can_rollback=can_rollback,
        )
