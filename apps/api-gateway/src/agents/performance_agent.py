"""
PerformanceAgent - 连锁餐饮绩效与提成智能体 (智链OS 绩效方案)

对应《连锁餐饮绩效 Agent 规划》：
- 岗位绩效与提成配置
- 绩效得分计算
- 提成计算与规则追溯
- 绩效报表与自然语言查询
"""
import re
import time
from datetime import date, timedelta
from typing import Dict, Any, Optional, List, Tuple
import structlog

from .llm_agent import LLMEnhancedAgent
from ..core.base_agent import AgentResponse
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()

# 默认岗位配置（行业参考，可后续接入配置表/数据库）
DEFAULT_ROLE_CONFIG = {
    "store_manager": {
        "id": "store_manager",
        "name": "店长",
        "metrics": [
            {"id": "revenue", "name": "门店营收", "weight": 0.25},
            {"id": "profit", "name": "毛利/利润", "weight": 0.25},
            {"id": "labor_efficiency", "name": "人效", "weight": 0.15},
            {"id": "satisfaction", "name": "客户满意度", "weight": 0.15},
            {"id": "food_safety", "name": "食品安全", "weight": 0.10},
            {"id": "waste_rate", "name": "损耗率", "weight": 0.10},
        ],
        "commission_rules": ["月度目标达成奖", "超额提成 1-3%", "季度综合排名奖"],
    },
    "shift_manager": {
        "id": "shift_manager",
        "name": "值班经理",
        "metrics": [
            {"id": "period_revenue", "name": "时段营收", "weight": 0.35},
            {"id": "turnover", "name": "翻台率", "weight": 0.20},
            {"id": "complaint", "name": "客诉", "weight": 0.25},
            {"id": "schedule_exec", "name": "排班执行率", "weight": 0.20},
        ],
        "commission_rules": ["时段业绩达标奖", "客诉零事故奖", "月度绩效系数"],
    },
    "waiter": {
        "id": "waiter",
        "name": "服务员",
        "metrics": [
            {"id": "avg_per_table", "name": "桌均消费", "weight": 0.35},
            {"id": "add_order_rate", "name": "加单率", "weight": 0.25},
            {"id": "good_review_rate", "name": "好评率", "weight": 0.25},
            {"id": "attendance", "name": "出勤率", "weight": 0.15},
        ],
        "commission_rules": ["桌均提成", "加单提成", "好评奖"],
    },
    "cashier": {
        "id": "cashier",
        "name": "收银",
        "metrics": [
            {"id": "accuracy", "name": "收银准确率", "weight": 0.40},
            {"id": "member_card", "name": "会员开卡数", "weight": 0.30},
            {"id": "stored_value", "name": "储值/卡券销售", "weight": 0.30},
        ],
        "commission_rules": ["会员开卡提成(元/张)", "储值/卡券销售提成(%)"],
    },
    "kitchen": {
        "id": "kitchen",
        "name": "后厨/厨师",
        "metrics": [
            {"id": "serve_time", "name": "出餐时效", "weight": 0.30},
            {"id": "return_rate", "name": "退菜率", "weight": 0.25},
            {"id": "waste_rate", "name": "损耗率", "weight": 0.25},
            {"id": "food_safety", "name": "食品安全", "weight": 0.20},
        ],
        "commission_rules": ["出餐量奖", "退菜率低于阈值奖", "损耗节约奖"],
    },
    "delivery": {
        "id": "delivery",
        "name": "外卖专员",
        "metrics": [
            {"id": "order_count", "name": "外卖单量", "weight": 0.40},
            {"id": "on_time_rate", "name": "准时率", "weight": 0.30},
            {"id": "bad_review_rate", "name": "差评率", "weight": 0.30},
        ],
        "commission_rules": ["单量提成(元/单或阶梯)", "准时奖", "差评扣减"],
    },
}

# ── 提成规则参数（可后续迁移至数据库配置表）──────────────────────────────────
# 金额单位均为 分（fen），对外接口统一转换为 元（yuan）。
COMMISSION_RULE_CONFIG: Dict[str, List[Dict[str, Any]]] = {
    "store_manager": [
        {
            "name":      "月度目标达成奖",
            "type":      "achievement_bonus",
            "metric":    "revenue",
            "threshold": 0.80,
            "fixed_fen": 200_000,        # ¥2,000
            "desc":      "revenue 达成率 ≥ 80% → 固定奖金 ¥2,000",
        },
        {
            "name":          "超额提成 1-3%",
            "type":          "excess_commission",
            "metric":        "revenue",
            "base_rate":     0.01,        # 超额比例 0% 时取 1%
            "max_rate":      0.03,        # 超额比例 ≥ 30% 时取 3%
            "max_excess_rate": 0.30,
            "desc":          "超额营收 × 1–3%（超额幅度 0%→1%，30%→3%，线性插值）",
        },
        {
            "name":  "季度综合排名奖",
            "type":  "cross_store",
            "metric": None,
            "desc":  "跨门店季度综合排名奖，需汇总后计算，当前返回 None",
        },
    ],
    "shift_manager": [
        {
            "name":      "时段业绩达标奖",
            "type":      "achievement_bonus",
            "metric":    "period_revenue",
            "threshold": 0.90,
            "fixed_fen": 50_000,         # ¥500
            "desc":      "period_revenue 达成率 ≥ 90% → 固定奖金 ¥500",
        },
        {
            "name":      "客诉零事故奖",
            "type":      "achievement_bonus",
            "metric":    "complaint",
            "threshold": 1.00,           # 达成率 ≥ 1.0 意味着客诉数 ≤ 目标（越低越好）
            "fixed_fen": 30_000,         # ¥300
            "desc":      "complaint 达成率 ≥ 1.0（无客诉）→ 固定奖金 ¥300",
        },
        {
            "name":            "月度绩效系数",
            "type":            "score_coefficient",
            "metric":          "ALL",
            "base_salary_fen": 500_000,  # 假设基础工资 ¥5,000（分）
            "coeff_scale":     0.20,     # 奖励 = 基础工资 × total_score × 20%
            "desc":            "绩效系数奖 = ¥5,000 × total_score × 20%",
        },
    ],
    "waiter": [
        {
            "name":   "桌均提成",
            "type":   "excess_linear",
            "metric": "avg_per_table",
            "rate":   0.005,             # 超额均消部分的 0.5%（分计算）
            "desc":   "桌均消费超出目标部分 × 0.5%",
        },
        {
            "name":         "加单提成",
            "type":         "rate_on_count",
            "metric":       "add_order_rate",
            "count_metric": "order_count",
            "per_unit_fen": 1_00,        # ¥1/次加单
            "desc":         "加单率 × 订单数 × ¥1/次",
        },
        {
            "name":      "好评奖",
            "type":      "achievement_bonus",
            "metric":    "good_review_rate",
            "threshold": 0.80,
            "fixed_fen": 10_000,         # ¥100
            "desc":      "好评率达成率 ≥ 80% → 固定奖金 ¥100",
        },
    ],
    "cashier": [
        {
            "name":         "会员开卡提成(元/张)",
            "type":         "count_commission",
            "metric":       "member_card",
            "per_unit_fen": 5_00,        # ¥5/张
            "desc":         "开卡数 × ¥5/张",
        },
        {
            "name":   "储值/卡券销售提成(%)",
            "type":   "rate_on_value",
            "metric": "stored_value",
            "rate":   0.01,              # 1%
            "desc":   "储值销售额 × 1%",
        },
    ],
    "kitchen": [
        {
            "name":         "出餐量奖",
            "type":         "count_commission",
            "metric":       "order_count",   # 复用 waiter 计算的 order_count
            "per_unit_fen": 50,              # ¥0.5/单
            "desc":         "出餐量（订单数）× ¥0.5/单",
        },
        {
            "name":      "退菜率低于阈值奖",
            "type":      "below_threshold",
            "metric":    "return_rate",
            "threshold": 0.02,
            "fixed_fen": 20_000,         # ¥200
            "desc":      "退菜率 < 2% → 固定奖金 ¥200",
        },
        {
            "name":        "损耗节约奖",
            "type":        "saving_bonus",
            "metric":      "waste_rate",
            "base_target": 0.05,         # 与 DEFAULT_TARGETS['waste_rate'] 一致
            "coeff_fen":   50_000,       # 每节省 1% 奖励 ¥500（分）
            "desc":        "（目标损耗率 5% - 实际损耗率）× ¥500/1%",
        },
    ],
    "delivery": [
        {
            "name":   "单量提成(元/单或阶梯)",
            "type":   "tiered_count",
            "metric": "order_count",
            "tiers":  [(100, 1_00), (300, 1_50), (9999, 2_00)],  # (上限单量, 分/单)
            "desc":   "≤100 单 ¥1/单，101–300 单 ¥1.5/单，>300 单 ¥2/单",
        },
        {
            "name":      "准时奖",
            "type":      "achievement_bonus",
            "metric":    "on_time_rate",
            "threshold": 0.95,
            "fixed_fen": 20_000,         # ¥200
            "desc":      "准时率达成率 ≥ 95% → 固定奖金 ¥200",
        },
        {
            "name":         "差评扣减",
            "type":         "penalty_on_rate",
            "metric":       "bad_review_rate",
            "count_metric": "order_count",
            "per_unit_fen": -1_000,      # -¥10/条差评
            "desc":         "差评数（差评率 × 订单数）× -¥10/条",
        },
    ],
}


def _compute_rule_amount(
    rule: Dict[str, Any],
    metric_map: Dict[str, Dict[str, Any]],
    total_score: Optional[float],
) -> Tuple[Optional[int], str, Optional[int]]:
    """
    计算单条提成规则的金额。

    Args:
        rule:        COMMISSION_RULE_CONFIG 中的单条规则字典
        metric_map:  metric_id -> {value, target, achievement_rate}
        total_score: 综合绩效得分（0.0–2.0），score_coefficient 类型使用

    Returns:
        (amount_fen, formula_trace, red_line_deduction_fen)
        amount_fen: None 表示无数据无法计算；负数表示扣减
        red_line_deduction_fen: 仅 penalty 类型时有值
    """
    rtype     = rule["type"]
    metric_id = rule.get("metric")
    m         = metric_map.get(metric_id) if metric_id and metric_id != "ALL" else None

    # ── 跨店计算，当前无法本地计算 ──────────────────────────────────────
    if rtype == "cross_store":
        return None, rule["desc"], None

    # ── 固定奖：达成率超过阈值即发放 ────────────────────────────────────
    if rtype == "achievement_bonus":
        if m is None or m.get("achievement_rate") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        ar = m["achievement_rate"]
        if ar >= rule["threshold"]:
            amt = rule["fixed_fen"]
            return amt, f"达成率 {ar:.2%} ≥ {rule['threshold']:.0%} → 奖金 ¥{amt/100:.0f}", None
        return 0, f"达成率 {ar:.2%} < {rule['threshold']:.0%} → 未达标 ¥0", None

    # ── 超额分成：超出目标收入按线性比率提成 ────────────────────────────
    if rtype == "excess_commission":
        if m is None or m.get("value") is None or m.get("target") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        actual, target = m["value"], m["target"]
        if actual <= target or target <= 0:
            return 0, f"实际 ¥{actual/100:.0f} ≤ 目标 ¥{target/100:.0f} → 无超额 ¥0", None
        excess       = actual - target
        excess_rate  = excess / target
        max_ex       = rule["max_excess_rate"]
        comm_rate    = min(
            rule["base_rate"] + (rule["max_rate"] - rule["base_rate"]) * excess_rate / max_ex,
            rule["max_rate"],
        )
        amt = int(excess * comm_rate)
        return amt, (
            f"超额 ¥{excess/100:.0f}（{excess_rate:.1%}）× {comm_rate:.2%} = ¥{amt/100:.0f}"
        ), None

    # ── 绩效系数奖：综合得分 × 系数 × 基础工资 ──────────────────────────
    if rtype == "score_coefficient":
        if total_score is None:
            return None, f"【数据缺失】{rule['desc']}", None
        amt = int(rule["base_salary_fen"] * total_score * rule["coeff_scale"])
        return amt, (
            f"¥{rule['base_salary_fen']/100:.0f} × {total_score:.2%} × {rule['coeff_scale']:.0%}"
            f" = ¥{amt/100:.0f}"
        ), None

    # ── 超额线性提成（如桌均超出部分）─────────────────────────────────
    if rtype == "excess_linear":
        if m is None or m.get("value") is None or m.get("target") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        excess = max(0.0, m["value"] - m["target"])
        amt    = int(excess * rule["rate"])
        if excess <= 0:
            return 0, f"桌均 ¥{m['value']/100:.0f} ≤ 目标 ¥{m['target']/100:.0f} → 无超额 ¥0", None
        return amt, (
            f"超额桌均 ¥{excess/100:.0f} × {rule['rate']} = ¥{amt/100:.0f}"
        ), None

    # ── 按数量提成（整数指标 × 单价）───────────────────────────────────
    if rtype == "count_commission":
        if m is None or m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        count = max(0, int(m["value"]))
        amt   = count * rule["per_unit_fen"]
        return amt, f"{count} 个 × ¥{rule['per_unit_fen']/100:.1f} = ¥{amt/100:.0f}", None

    # ── 比率 × 数量 × 单价（如加单率 × 订单数 × ¥1）───────────────────
    if rtype == "rate_on_count":
        cnt_m = metric_map.get(rule.get("count_metric", "order_count"))
        if m is None or m.get("value") is None or cnt_m is None or cnt_m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        n_units = int(m["value"] * cnt_m["value"])
        amt     = n_units * rule["per_unit_fen"]
        return amt, (
            f"比率 {m['value']:.1%} × {int(cnt_m['value'])} 单"
            f" = {n_units} 次 × ¥{rule['per_unit_fen']/100:.1f} = ¥{amt/100:.0f}"
        ), None

    # ── 按金额比率（如储值销售 × 1%）───────────────────────────────────
    if rtype == "rate_on_value":
        if m is None or m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        amt = int(m["value"] * rule["rate"])
        return amt, f"¥{m['value']/100:.0f} × {rule['rate']:.0%} = ¥{amt/100:.0f}", None

    # ── 低于阈值奖（退菜率等绝对值指标）────────────────────────────────
    if rtype == "below_threshold":
        if m is None or m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        if m["value"] < rule["threshold"]:
            amt = rule["fixed_fen"]
            return amt, f"指标值 {m['value']:.2%} < 阈值 {rule['threshold']:.0%} → ¥{amt/100:.0f}", None
        return 0, f"指标值 {m['value']:.2%} ≥ 阈值 {rule['threshold']:.0%} → 未达标 ¥0", None

    # ── 节约奖（实际 < 目标才有奖励，如损耗率）──────────────────────────
    if rtype == "saving_bonus":
        if m is None or m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        saving = rule["base_target"] - m["value"]
        if saving <= 0:
            return 0, f"损耗率 {m['value']:.2%} ≥ 目标 {rule['base_target']:.2%} → 无节约奖励 ¥0", None
        amt = int(saving * 100 * rule["coeff_fen"])   # saving_pct×100 = 百分点数
        return amt, (
            f"节约 {saving:.2%} × ¥{rule['coeff_fen']/100:.0f}/1% = ¥{amt/100:.0f}"
        ), None

    # ── 阶梯单量提成 ───────────────────────────────────────────────────
    if rtype == "tiered_count":
        if m is None or m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        count  = max(0, int(m["value"]))
        total  = 0
        prev   = 0
        detail = []
        for tier_max, rate_fen in rule["tiers"]:
            n = max(0, min(count, tier_max) - prev)
            if n > 0:
                total  += n * rate_fen
                detail.append(f"{n} 单×¥{rate_fen/100:.1f}")
            prev = tier_max
            if count <= tier_max:
                break
        return total, f"{count} 单阶梯提成（{', '.join(detail)}）= ¥{total/100:.0f}", None

    # ── 差评扣减（计算为负值）──────────────────────────────────────────
    if rtype == "penalty_on_rate":
        cnt_m = metric_map.get(rule.get("count_metric", "order_count"))
        if m is None or m.get("value") is None or cnt_m is None or cnt_m.get("value") is None:
            return None, f"【数据缺失】{rule['desc']}", None
        bad_count = int(m["value"] * cnt_m["value"])
        amt       = bad_count * rule["per_unit_fen"]   # per_unit_fen 为负数
        return amt, (
            f"差评 {bad_count} 条（{m['value']:.2%} × {int(cnt_m['value'])} 单）"
            f"× ¥{rule['per_unit_fen']/100:.0f} = ¥{amt/100:.0f}"
        ), amt

    return None, f"未知规则类型: {rtype}", None


def _parse_period_to_ym(period: str) -> Tuple[Optional[int], Optional[int]]:
    """将 period 字符串解析为 (year, month)。无法解析时返回当前年月。"""
    if not period:
        today = date.today()
        return today.year, today.month
    # "YYYY-MM"
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if m:
        return int(m.group(1)), int(m.group(2))
    # "last_month"
    if period == "last_month":
        first = date.today().replace(day=1)
        last_m = first - timedelta(days=1)
        return last_m.year, last_m.month
    # "month" / "current_month" / anything else → current month
    today = date.today()
    return today.year, today.month


class PerformanceAgent(LLMEnhancedAgent):
    """
    绩效智能体（智链OS 连锁餐饮绩效方案）

    能力：get_role_config, calculate_performance, calculate_commission,
    get_performance_report, explain_rule, nl_query
    """

    def __init__(self):
        super().__init__(agent_type="performance")

    def get_supported_actions(self) -> List[str]:
        return [
            "get_role_config",
            "calculate_performance",
            "calculate_commission",
            "get_performance_report",
            "explain_rule",
            "nl_query",
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        start = time.time()
        if action not in self.get_supported_actions():
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(self.get_supported_actions())}",
                execution_time=time.time() - start,
            )
        try:
            if action == "get_role_config":
                out = await self._get_role_config(params)
            elif action == "calculate_performance":
                out = await self._calculate_performance(params)
            elif action == "calculate_commission":
                out = await self._calculate_commission(params)
            elif action == "get_performance_report":
                out = await self._get_performance_report(params)
            elif action == "explain_rule":
                out = await self._explain_rule(params)
            else:
                out = await self._nl_query(params)

            exec_time = time.time() - start
            if isinstance(out, dict):
                return AgentResponse(
                    success=out.get("success", True),
                    data=out.get("data"),
                    error=out.get("error"),
                    execution_time=exec_time,
                    metadata=out.get("metadata"),
                )
            return AgentResponse(success=True, data=out, execution_time=exec_time)
        except Exception as e:
            logger.error("PerformanceAgent 执行异常", action=action, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"PerformanceAgent failed: {action}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"action": action, "params": params},
            )
            return AgentResponse(
                success=False,
                error=str(e),
                execution_time=time.time() - start,
            )

    async def _get_role_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取岗位绩效与提成配置。"""
        store_id = params.get("store_id")
        role_id = params.get("role_id")
        if role_id:
            config = DEFAULT_ROLE_CONFIG.get(role_id)
            if not config:
                return {
                    "success": False,
                    "error": f"未知岗位: {role_id}",
                    "data": None,
                }
            roles = [config]
        else:
            roles = list(DEFAULT_ROLE_CONFIG.values())
        return {
            "success": True,
            "data": {"roles": roles, "store_id": store_id},
            "metadata": {"source": "default_config"},
        }

    async def _calculate_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算指定岗位、周期、人员绩效得分。DB-first：优先从 employee_metric_records 读取真实指标，无 DB 时降级占位。"""
        store_id = params.get("store_id", "")
        role_id = params.get("role_id", "")
        period = params.get("period", "month")
        staff_ids = params.get("staff_ids")  # 可选，不传则按门店汇总

        if not role_id or role_id not in DEFAULT_ROLE_CONFIG:
            return {
                "success": False,
                "error": "缺少或无效的 role_id",
                "data": None,
            }

        role = DEFAULT_ROLE_CONFIG[role_id]
        year, month = _parse_period_to_ym(period)

        # ── DB-first：有 store_id 时尝试计算真实指标 ─────────────────────────
        if store_id and year and month:
            try:
                from ..core.database import get_db_session
                from ..services.performance_compute_service import PerformanceComputeService
                from ..models.employee_metric import EmployeeMetricRecord
                from sqlalchemy import func as sa_func, select as sa_select, and_ as sa_and

                async with get_db_session(enable_tenant_isolation=False) as session:
                    # 计算并写入最新指标
                    await PerformanceComputeService.compute_and_write(
                        session, store_id, year, month
                    )

                    period_start = date(year, month, 1)
                    metric_ids = [m["id"] for m in role["metrics"]]

                    # 按 metric_id 聚合（AVG），支持多员工
                    stmt = (
                        sa_select(
                            EmployeeMetricRecord.metric_id,
                            sa_func.avg(EmployeeMetricRecord.value).label("value"),
                            sa_func.avg(EmployeeMetricRecord.target).label("target"),
                            sa_func.avg(EmployeeMetricRecord.achievement_rate).label("achievement_rate"),
                        )
                        .where(
                            sa_and(
                                EmployeeMetricRecord.store_id == store_id,
                                EmployeeMetricRecord.period_start == period_start,
                                EmployeeMetricRecord.metric_id.in_(metric_ids),
                            )
                        )
                        .group_by(EmployeeMetricRecord.metric_id)
                    )
                    if staff_ids:
                        stmt = stmt.where(EmployeeMetricRecord.employee_id.in_(staff_ids))

                    rows = (await session.execute(stmt)).all()
                    db_map = {r.metric_id: r for r in rows}

                    items = []
                    for m in role["metrics"]:
                        row = db_map.get(m["id"])
                        items.append({
                            "metric_id": m["id"],
                            "metric_name": m["name"],
                            "weight": m["weight"],
                            "value": float(row.value) if row and row.value is not None else None,
                            "target": float(row.target) if row and row.target is not None else None,
                            "achievement_rate": (
                                float(row.achievement_rate)
                                if row and row.achievement_rate is not None else None
                            ),
                        })

                    # 加权总得分（仅含有数据的指标）
                    scored = [i for i in items if i["achievement_rate"] is not None]
                    if scored:
                        w_sum = sum(i["weight"] for i in scored)
                        total_score = round(
                            sum(i["weight"] * i["achievement_rate"] for i in scored) / w_sum, 4
                        )
                    else:
                        total_score = None

                    return {
                        "success": True,
                        "data": {
                            "store_id": store_id,
                            "role_id": role_id,
                            "role_name": role["name"],
                            "period": period,
                            "staff_ids": staff_ids,
                            "metrics": items,
                            "total_score": total_score,
                            "data_source_note": "来自 employee_metric_records 实时计算",
                        },
                        "metadata": {
                            "source": "performance_engine",
                            "year": year,
                            "month": month,
                        },
                    }
            except Exception as e:
                logger.warning("绩效 DB 查询失败，降级占位", error=str(e))

        # ── 降级：占位结构（维持向后兼容） ───────────────────────────────────
        items = []
        for m in role["metrics"]:
            items.append({
                "metric_id": m["id"],
                "metric_name": m["name"],
                "weight": m["weight"],
                "value": None,
                "target": None,
                "achievement_rate": None,
            })

        return {
            "success": True,
            "data": {
                "store_id": store_id,
                "role_id": role_id,
                "role_name": role["name"],
                "period": period,
                "staff_ids": staff_ids,
                "metrics": items,
                "total_score": None,
                "data_source_note": "当前为占位结构，接入指标表后可计算真实得分",
            },
            "metadata": {"source": "performance_engine"},
        }

    async def _calculate_commission(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算提成金额。DB-first：从 employee_metric_records 读取真实指标，再应用规则引擎。"""
        store_id  = params.get("store_id", "")
        role_id   = params.get("role_id", "")
        period    = params.get("period", "month")
        staff_ids = params.get("staff_ids")

        if not role_id or role_id not in DEFAULT_ROLE_CONFIG:
            return {"success": False, "error": "缺少或无效的 role_id", "data": None}

        role  = DEFAULT_ROLE_CONFIG[role_id]
        rules = COMMISSION_RULE_CONFIG.get(role_id, [])
        year, month = _parse_period_to_ym(period)

        # ── DB-first：读取 employee_metric_records ────────────────────────
        # metric_map: metric_id -> {value, target, achievement_rate}（浮点，分或小数）
        metric_map:  Dict[str, Dict[str, Any]] = {}
        total_score: Optional[float]            = None
        data_source = "commission_rule_engine（无指标数据，规则逐条为 None）"

        if store_id and year and month:
            try:
                from ..core.database import get_db_session
                from ..services.performance_compute_service import PerformanceComputeService
                from ..models.employee_metric import EmployeeMetricRecord
                from sqlalchemy import func as sa_func, select as sa_select, and_ as sa_and

                async with get_db_session(enable_tenant_isolation=False) as session:
                    # 触发最新指标计算（幂等）
                    await PerformanceComputeService.compute_and_write(
                        session, store_id, year, month
                    )

                    period_start = date(year, month, 1)

                    # 抓取该门店当期所有指标（不限于当前岗位，order_count 等共享指标也一并取入）
                    stmt = (
                        sa_select(
                            EmployeeMetricRecord.metric_id,
                            sa_func.avg(EmployeeMetricRecord.value).label("value"),
                            sa_func.avg(EmployeeMetricRecord.target).label("target"),
                            sa_func.avg(EmployeeMetricRecord.achievement_rate).label("achievement_rate"),
                        )
                        .where(
                            sa_and(
                                EmployeeMetricRecord.store_id == store_id,
                                EmployeeMetricRecord.period_start == period_start,
                            )
                        )
                        .group_by(EmployeeMetricRecord.metric_id)
                    )
                    if staff_ids:
                        stmt = stmt.where(EmployeeMetricRecord.employee_id.in_(staff_ids))

                    rows = (await session.execute(stmt)).all()
                    for r in rows:
                        metric_map[r.metric_id] = {
                            "value":            float(r.value)            if r.value            is not None else None,
                            "target":           float(r.target)           if r.target           is not None else None,
                            "achievement_rate": float(r.achievement_rate) if r.achievement_rate is not None else None,
                        }

                    # 综合绩效得分（加权平均达成率，仅基于当前岗位指标）
                    weights  = {m["id"]: m["weight"] for m in role["metrics"]}
                    scored   = [(mid, v) for mid, v in metric_map.items()
                                if mid in weights and v["achievement_rate"] is not None]
                    if scored:
                        w_sum       = sum(weights[mid] for mid, _ in scored)
                        total_score = round(
                            sum(weights[mid] * v["achievement_rate"] for mid, v in scored) / w_sum, 4
                        ) if w_sum > 0 else None

                    data_source = "employee_metric_records + commission_rule_engine"
            except Exception as e:
                logger.warning("提成 DB 查询失败，降级占位", error=str(e))

        # ── 应用提成规则引擎 ──────────────────────────────────────────────
        details: List[Dict[str, Any]] = []
        total_fen     = 0
        has_any_data  = False

        for rule in rules:
            amount_fen, trace, deduction_fen = _compute_rule_amount(rule, metric_map, total_score)
            details.append({
                "rule_name":          rule["name"],
                "amount":             round(amount_fen / 100, 2) if amount_fen is not None else None,
                "formula_trace":      trace,
                "red_line_deduction": round(deduction_fen / 100, 2) if deduction_fen is not None else None,
            })
            if amount_fen is not None:
                total_fen    += amount_fen
                has_any_data  = True

        total_commission = round(total_fen / 100, 2) if has_any_data else None

        return {
            "success": True,
            "data": {
                "store_id":         store_id,
                "role_id":          role_id,
                "role_name":        role["name"],
                "period":           period,
                "staff_ids":        staff_ids,
                "total_commission": total_commission,
                "details":          details,
                "data_source_note": data_source,
            },
            "metadata": {
                "source":      "commission_engine",
                "year":        year,
                "month":       month,
                "total_score": total_score,
            },
        }

    async def _get_performance_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """绩效报表（门店/岗位/个人）。"""
        store_id = params.get("store_id", "")
        period = params.get("period", "month")
        role_id = params.get("role_id")
        report_format = params.get("format", "summary")  # summary | detail | trend

        roles = list(DEFAULT_ROLE_CONFIG.values()) if not role_id else [
            DEFAULT_ROLE_CONFIG[r] for r in [role_id] if r in DEFAULT_ROLE_CONFIG
        ]
        if role_id and not roles:
            return {"success": False, "error": f"未知岗位: {role_id}", "data": None}

        summary = []
        for r in roles:
            summary.append({
                "role_id": r["id"],
                "role_name": r["name"],
                "period": period,
                "avg_score": None,
                "total_commission": None,
            })

        return {
            "success": True,
            "data": {
                "store_id": store_id,
                "period": period,
                "format": report_format,
                "summary": summary,
                "data_source_note": "当前为占位结构，接入数据后可产出真实报表",
            },
            "metadata": {"source": "report"},
        }

    async def _explain_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """解释某条规则或某笔提成。"""
        rule_id = params.get("rule_id")
        commission_id = params.get("commission_id")
        if not rule_id and not commission_id:
            return {
                "success": False,
                "error": "请提供 rule_id 或 commission_id",
                "data": None,
            }

        # 占位：从配置或审计表取规则原文与计算过程
        role_id = params.get("role_id")
        if rule_id and role_id and role_id in DEFAULT_ROLE_CONFIG:
            rules = DEFAULT_ROLE_CONFIG[role_id]["commission_rules"]
            rule_text = next((r for r in rules if rule_id in r or r == rule_id), rule_id)
        else:
            rule_text = str(rule_id or commission_id)

        return {
            "success": True,
            "data": {
                "rule_id": rule_id,
                "commission_id": commission_id,
                "rule_text": rule_text,
                "applicable_data": None,
                "calculation_steps": None,
                "note": "当前为占位，接入规则版本与审计后可返回完整追溯",
            },
            "metadata": {"source": "explain"},
        }

    async def _nl_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """自然语言查询绩效/提成。"""
        question = params.get("query", params.get("question", ""))
        store_id = params.get("store_id")
        period = params.get("period")

        if not question.strip():
            return {
                "success": False,
                "error": "请提供 query 或 question",
                "data": None,
            }

        role_summary = {k: v["name"] for k, v in DEFAULT_ROLE_CONFIG.items()}
        user_message = (
            f"绩效查询 门店={store_id} 周期={period}：{question}。"
            f"可用岗位配置：{role_summary}。"
            f"请结合绩效规则给出具体数值与规则解释。"
        )

        if self.llm_enabled:
            try:
                result = await self.execute_with_tools(
                    user_message=user_message,
                    store_id=store_id or "",
                    context={"period": period, "role_config_summary": role_summary}
                )
                return {
                    "success": result.success,
                    "data": {
                        "answer": result.data,
                        "question": question,
                        "tool_calls": len(result.tool_calls),
                        "iterations": result.iterations,
                    },
                    "error": result.message if not result.success else None,
                    "metadata": {"source": "tool_use"},
                }
            except Exception as e:
                logger.warning("绩效 nl_query Tool Use 失败，返回占位", error=str(e))

        # 无 LLM 或失败时返回占位
        return {
            "success": True,
            "data": {
                "answer": f"已收到查询：「{question}」。当前为占位回复，接入 LLM 与绩效数据后可返回具体数值与规则解释。门店={store_id}，周期={period}。",
                "question": question,
            },
            "metadata": {"source": "placeholder"},
        }
