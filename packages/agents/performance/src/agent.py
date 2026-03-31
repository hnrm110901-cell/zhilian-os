"""
PerformanceAgent - 连锁餐饮绩效与提成智能体（独立包版本）

独立包特点：
- 无数据库依赖，指标数据通过 params["metric_values"] 注入
- 无 LLM 依赖，nl_query 使用关键词意图分发
- 与 apps/api-gateway/src/agents/performance_agent.py 共享规则配置逻辑

支持的 action：
  get_role_config       — 查询岗位绩效配置
  calculate_performance — 计算绩效得分（需注入 metric_values）
  calculate_commission  — 计算提成金额（需注入 metric_values）
  get_performance_report— 生成绩效报表
  explain_rule          — 解释提成规则
  nl_query              — 自然语言查询（关键词派发）
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import structlog

# 加载 base_agent（api-gateway/src/core）
core_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"
sys.path.insert(0, str(core_path))
from base_agent import BaseAgent, AgentResponse  # noqa: E402

# 加载 OrgHierarchyService（api-gateway/src/services）
_svc_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "apps" / "api-gateway" / "src"
if str(_svc_path) not in sys.path:
    sys.path.insert(0, str(_svc_path))
try:
    from services.org_hierarchy_service import OrgHierarchyService  # noqa: E402
except ImportError:
    OrgHierarchyService = None  # type: ignore[assignment,misc]

logger = structlog.get_logger()

# ── 岗位配置 ──────────────────────────────────────────────────────────────────

ROLE_CONFIG: Dict[str, Dict[str, Any]] = {
    "store_manager": {
        "id": "store_manager",
        "name": "店长",
        "metrics": [
            {"id": "revenue",          "name": "门店营收",    "weight": 0.25},
            {"id": "profit",           "name": "毛利/利润",   "weight": 0.25},
            {"id": "labor_efficiency", "name": "人效",        "weight": 0.15},
            {"id": "satisfaction",     "name": "客户满意度",  "weight": 0.15},
            {"id": "food_safety",      "name": "食品安全",    "weight": 0.10},
            {"id": "waste_rate",       "name": "损耗率",      "weight": 0.10},
        ],
        "commission_rules": ["月度目标达成奖", "超额提成 1-3%", "季度综合排名奖"],
    },
    "shift_manager": {
        "id": "shift_manager",
        "name": "值班经理",
        "metrics": [
            {"id": "period_revenue", "name": "时段营收",    "weight": 0.35},
            {"id": "turnover",       "name": "翻台率",      "weight": 0.20},
            {"id": "complaint",      "name": "客诉",        "weight": 0.25},
            {"id": "schedule_exec",  "name": "排班执行率",  "weight": 0.20},
        ],
        "commission_rules": ["时段业绩达标奖", "客诉零事故奖", "月度绩效系数"],
    },
    "waiter": {
        "id": "waiter",
        "name": "服务员",
        "metrics": [
            {"id": "avg_per_table",   "name": "桌均消费",  "weight": 0.35},
            {"id": "add_order_rate",  "name": "加单率",    "weight": 0.25},
            {"id": "good_review_rate","name": "好评率",    "weight": 0.25},
            {"id": "attendance",      "name": "出勤率",    "weight": 0.15},
        ],
        "commission_rules": ["桌均提成", "加单提成", "好评奖"],
    },
    "cashier": {
        "id": "cashier",
        "name": "收银",
        "metrics": [
            {"id": "accuracy",     "name": "收银准确率",       "weight": 0.40},
            {"id": "member_card",  "name": "会员开卡数",       "weight": 0.30},
            {"id": "stored_value", "name": "储值/卡券销售",    "weight": 0.30},
        ],
        "commission_rules": ["会员开卡提成(元/张)", "储值/卡券销售提成(%)"],
    },
    "kitchen": {
        "id": "kitchen",
        "name": "后厨/厨师",
        "metrics": [
            {"id": "serve_time",  "name": "出餐时效",  "weight": 0.30},
            {"id": "return_rate", "name": "退菜率",    "weight": 0.25},
            {"id": "waste_rate",  "name": "损耗率",    "weight": 0.25},
            {"id": "food_safety", "name": "食品安全",  "weight": 0.20},
        ],
        "commission_rules": ["出餐量奖", "退菜率低于阈值奖", "损耗节约奖"],
    },
    "delivery": {
        "id": "delivery",
        "name": "外卖专员",
        "metrics": [
            {"id": "order_count",    "name": "外卖单量",  "weight": 0.40},
            {"id": "on_time_rate",   "name": "准时率",    "weight": 0.30},
            {"id": "bad_review_rate","name": "差评率",    "weight": 0.30},
        ],
        "commission_rules": ["单量提成(元/单或阶梯)", "准时奖", "差评扣减"],
    },
}

# 越低越好的指标（达成率 = target / value）
LOWER_IS_BETTER = {"waste_rate", "return_rate", "bad_review_rate", "complaint", "serve_time"}

# 默认目标值（用于无 target 时的 achievement 计算）
DEFAULT_TARGETS: Dict[str, float] = {
    "revenue":          30_000_000,  # 分：300,000 元
    "profit":           0.55,
    "labor_efficiency": 500_000,     # 分：5,000 元/人
    "waste_rate":       0.05,
    "avg_per_table":    15_000,      # 分：150 元/桌
    "order_count":      300,
    "serve_time":       15.0,        # 分钟
    "return_rate":      0.02,
    "add_order_rate":   0.30,
    "good_review_rate": 0.90,
    "bad_review_rate":  0.03,
    "on_time_rate":     0.95,
    "attendance":       0.95,
    "satisfaction":     4.5,         # 1–5分
    "food_safety":      1.0,         # 达成即满分
    "accuracy":         0.999,
    "member_card":      50,
    "stored_value":     50_000_00,   # 分：50,000 元
    "period_revenue":   8_000_000,   # 分：80,000 元/时段
    "turnover":         3.0,         # 翻台次数
    "schedule_exec":    0.95,
    "complaint":        0,           # 零客诉为目标
}

# ── 提成规则配置 ──────────────────────────────────────────────────────────────

COMMISSION_RULES: Dict[str, List[Dict[str, Any]]] = {
    "store_manager": [
        {
            "name":      "月度目标达成奖",
            "type":      "achievement_bonus",
            "metric":    "revenue",
            "threshold": 0.80,
            "fixed_fen": 200_000,
            "desc":      "revenue 达成率 ≥ 80% → 固定奖金 ¥2,000",
        },
        {
            "name":          "超额提成 1-3%",
            "type":          "excess_commission",
            "metric":        "revenue",
            "base_rate":     0.01,
            "max_rate":      0.03,
            "max_excess_rate": 0.30,
            "desc":          "超额营收 × 1–3%（超额幅度越大，提成率越高）",
        },
        {
            "name":  "季度综合排名奖",
            "type":  "cross_store",
            "metric": None,
            "desc":  "跨门店季度综合排名奖，需总部汇总后计算",
        },
    ],
    "shift_manager": [
        {
            "name":      "时段业绩达标奖",
            "type":      "achievement_bonus",
            "metric":    "period_revenue",
            "threshold": 0.90,
            "fixed_fen": 50_000,
            "desc":      "period_revenue 达成率 ≥ 90% → 固定奖金 ¥500",
        },
        {
            "name":      "客诉零事故奖",
            "type":      "achievement_bonus",
            "metric":    "complaint",
            "threshold": 1.00,
            "fixed_fen": 30_000,
            "desc":      "complaint 达成率 ≥ 1.0（无客诉）→ 固定奖金 ¥300",
        },
        {
            "name":            "月度绩效系数",
            "type":            "score_coefficient",
            "metric":          "ALL",
            "base_salary_fen": 500_000,
            "coeff_scale":     0.20,
            "desc":            "绩效系数奖 = ¥5,000 × total_score × 20%",
        },
    ],
    "waiter": [
        {
            "name":   "桌均提成",
            "type":   "excess_linear",
            "metric": "avg_per_table",
            "rate":   0.005,
            "desc":   "桌均消费超出目标部分 × 0.5%",
        },
        {
            "name":         "加单提成",
            "type":         "rate_on_count",
            "metric":       "add_order_rate",
            "count_metric": "order_count",
            "per_unit_fen": 100,
            "desc":         "加单率 × 订单数 × ¥1/次",
        },
        {
            "name":      "好评奖",
            "type":      "achievement_bonus",
            "metric":    "good_review_rate",
            "threshold": 0.80,
            "fixed_fen": 10_000,
            "desc":      "好评率达成率 ≥ 80% → 固定奖金 ¥100",
        },
    ],
    "cashier": [
        {
            "name":         "会员开卡提成(元/张)",
            "type":         "count_commission",
            "metric":       "member_card",
            "per_unit_fen": 500,
            "desc":         "开卡数 × ¥5/张",
        },
        {
            "name":   "储值/卡券销售提成(%)",
            "type":   "rate_on_value",
            "metric": "stored_value",
            "rate":   0.01,
            "desc":   "储值销售额 × 1%",
        },
    ],
    "kitchen": [
        {
            "name":         "出餐量奖",
            "type":         "count_commission",
            "metric":       "order_count",
            "per_unit_fen": 50,
            "desc":         "出餐量（订单数）× ¥0.5/单",
        },
        {
            "name":      "退菜率低于阈值奖",
            "type":      "below_threshold",
            "metric":    "return_rate",
            "threshold": 0.02,
            "fixed_fen": 20_000,
            "desc":      "退菜率 < 2% → 固定奖金 ¥200",
        },
        {
            "name":        "损耗节约奖",
            "type":        "saving_bonus",
            "metric":      "waste_rate",
            "base_target": 0.05,
            "coeff_fen":   50_000,
            "desc":        "（目标损耗率 5% - 实际损耗率）× ¥500/1%",
        },
    ],
    "delivery": [
        {
            "name":   "单量提成(元/单或阶梯)",
            "type":   "tiered_count",
            "metric": "order_count",
            "tiers":  [(100, 100), (300, 150), (9999, 200)],
            "desc":   "≤100单 ¥1/单，101–300单 ¥1.5/单，>300单 ¥2/单",
        },
        {
            "name":      "准时奖",
            "type":      "achievement_bonus",
            "metric":    "on_time_rate",
            "threshold": 0.95,
            "fixed_fen": 20_000,
            "desc":      "准时率达成率 ≥ 95% → 固定奖金 ¥200",
        },
        {
            "name":         "差评扣减",
            "type":         "penalty_on_rate",
            "metric":       "bad_review_rate",
            "count_metric": "order_count",
            "per_unit_fen": -1_000,
            "desc":         "差评数（差评率 × 订单数）× -¥10/条",
        },
    ],
}

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _achievement(value: float, target: float, metric_id: str, cap: float = 2.0) -> float:
    """计算达成率，最高 cap（默认2.0），避免除零。越低越好的指标取反向。"""
    if target == 0:
        return 0.0
    rate = (target / value) if metric_id in LOWER_IS_BETTER else (value / target)
    return min(round(rate, 4), cap)


def _compute_rule_amount(
    rule: Dict[str, Any],
    metric_values: Dict[str, float],
    metric_achievements: Dict[str, float],
    total_score: Optional[float],
) -> Optional[int]:
    """
    根据规则类型计算提成金额（分）。返回 None 表示条件未触发或需人工处理。
    """
    rtype = rule["type"]
    metric = rule.get("metric")

    if rtype == "achievement_bonus":
        ach = metric_achievements.get(metric)
        if ach is None:
            return None
        return rule["fixed_fen"] if ach >= rule["threshold"] else 0

    if rtype == "excess_commission":
        value = metric_values.get(metric)
        target = DEFAULT_TARGETS.get(metric)
        if value is None or target is None or target == 0:
            return None
        excess_rate = max(0.0, (value - target) / target)
        if excess_rate <= 0:
            return 0
        # 线性插值：0% → base_rate，max_excess_rate → max_rate
        max_exc = rule.get("max_excess_rate", 0.30)
        base_r  = rule.get("base_rate", 0.01)
        max_r   = rule.get("max_rate", 0.03)
        rate = base_r + (max_r - base_r) * min(excess_rate / max_exc, 1.0)
        excess_fen = max(0.0, value - target)
        return int(excess_fen * rate)

    if rtype == "excess_linear":
        value = metric_values.get(metric)
        target = DEFAULT_TARGETS.get(metric)
        if value is None or target is None:
            return None
        excess = max(0.0, value - target)
        return int(excess * rule["rate"])

    if rtype == "count_commission":
        value = metric_values.get(metric)
        if value is None:
            return None
        return int(value * rule["per_unit_fen"])

    if rtype == "rate_on_count":
        rate_val = metric_values.get(metric)
        cnt_val  = metric_values.get(rule.get("count_metric", ""), 0)
        if rate_val is None:
            return None
        count = int(rate_val * (cnt_val or 0))
        return count * rule["per_unit_fen"]

    if rtype == "rate_on_value":
        value = metric_values.get(metric)
        if value is None:
            return None
        return int(value * rule["rate"])

    if rtype == "below_threshold":
        value = metric_values.get(metric)
        if value is None:
            return None
        return rule["fixed_fen"] if value < rule["threshold"] else 0

    if rtype == "saving_bonus":
        value = metric_values.get(metric)
        base  = rule.get("base_target", 0.05)
        if value is None:
            return None
        saving_pct = max(0.0, base - value) * 100  # 每节省 1%
        return int(saving_pct * rule["coeff_fen"])

    if rtype == "tiered_count":
        value = metric_values.get(metric)
        if value is None:
            return None
        count = int(value)
        tiers = rule.get("tiers", [])
        for upper, rate in tiers:
            if count <= upper:
                return count * rate
        return count * (tiers[-1][1] if tiers else 0)

    if rtype == "penalty_on_rate":
        rate_val = metric_values.get(metric)
        cnt_val  = metric_values.get(rule.get("count_metric", ""), 0)
        if rate_val is None:
            return None
        penalty_cnt = int(rate_val * (cnt_val or 0))
        return penalty_cnt * rule["per_unit_fen"]  # 负数

    if rtype == "score_coefficient":
        if total_score is None:
            return None
        base = rule.get("base_salary_fen", 500_000)
        scale = rule.get("coeff_scale", 0.20)
        return int(base * total_score * scale)

    if rtype == "cross_store":
        return None  # 需跨门店汇总，当前不计算

    return None


# ── NL 查询关键词映射 ─────────────────────────────────────────────────────────

_NL_ROLE_KEYWORDS: List[Tuple[str, str]] = [
    ("店长", "store_manager"),
    ("值班经理", "shift_manager"),
    ("服务员", "waiter"),
    ("收银", "cashier"),
    ("后厨", "kitchen"),
    ("厨师", "kitchen"),
    ("外卖", "delivery"),
]

_NL_ACTION_KEYWORDS = {
    "config":      ["配置", "岗位", "规则", "指标", "有哪些", "什么岗"],
    "performance": ["得分", "评分", "绩效", "达成率", "综合"],
    "commission":  ["提成", "奖金", "奖励", "多少钱", "工资"],
    "report":      ["报表", "报告", "汇总", "总结", "本月"],
    "explain":     ["解释", "如何计算", "怎么算", "计算方式"],
}


def _detect_role(question: str) -> Optional[str]:
    for kw, role_id in _NL_ROLE_KEYWORDS:
        if kw in question:
            return role_id
    return None


def _detect_action(question: str) -> str:
    for action, keywords in _NL_ACTION_KEYWORDS.items():
        if any(kw in question for kw in keywords):
            return action
    return "config"


# ── PerformanceAgent ──────────────────────────────────────────────────────────

class PerformanceAgent(BaseAgent):
    """
    连锁餐饮绩效与提成智能体（独立包版本）。

    所有计算均为纯函数，无数据库依赖。
    指标实际值通过 params["metric_values"]: Dict[str, float] 注入。
    """

    SUPPORTED_ACTIONS = [
        "get_role_config",
        "calculate_performance",
        "calculate_commission",
        "get_performance_report",
        "explain_rule",
        "nl_query",
    ]

    def __init__(self, store_id: str = "STORE001", config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config=config)
        self.store_id = store_id

    def get_supported_actions(self) -> List[str]:
        return self.SUPPORTED_ACTIONS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        try:
            # ── 动态配置解析 ──────────────────────────────────────────────
            store_id = params.get("store_id", self.store_id)
            db = params.get("db")
            dyn_cfg: Dict[str, Any] = {}
            if db is not None and OrgHierarchyService is not None:
                try:
                    svc = OrgHierarchyService(db)
                    dyn_cfg["store_kpi_weights"] = await svc.resolve(
                        store_id, "store_kpi_weights",
                        default={"revenue": 0.25, "profit": 0.25, "labor": 0.15,
                                 "satisfaction": 0.15, "waste": 0.20}
                    )
                    dyn_cfg["table_turnover_baseline"] = await svc.resolve(
                        store_id, "baseline_table_turnover", default=3.0
                    )
                    dyn_cfg["piece_rate_tiers"] = await svc.resolve(
                        store_id, "piece_rate_tiers",
                        default=[
                            {"max_orders": 100, "rate": 1.0},
                            {"max_orders": 300, "rate": 1.5},
                            {"max_orders": None, "rate": 2.0},
                        ]
                    )
                    dyn_cfg["kpi_achievement_cap"] = await svc.resolve(
                        store_id, "kpi_achievement_max_cap", default=2.0
                    )
                except Exception as _cfg_err:
                    logger.warning("performance_dyn_cfg_failed", error=str(_cfg_err))
            # 将动态配置注入 params，供子方法读取
            params = {**params, "_dyn_cfg": dyn_cfg}
            # ────────────────────────────────────────────────────────────

            if action == "get_role_config":
                return AgentResponse(success=True, data=self._get_role_config(params))
            if action == "calculate_performance":
                return AgentResponse(success=True, data=self._calculate_performance(params))
            if action == "calculate_commission":
                return AgentResponse(success=True, data=self._calculate_commission(params))
            if action == "get_performance_report":
                return AgentResponse(success=True, data=self._get_performance_report(params))
            if action == "explain_rule":
                return AgentResponse(success=True, data=self._explain_rule(params))
            if action == "nl_query":
                return AgentResponse(success=True, data=self._nl_query(params))
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(self.SUPPORTED_ACTIONS)}",
            )
        except Exception as exc:
            logger.error("PerformanceAgent.execute 异常", action=action, error=str(exc))
            return AgentResponse(success=False, error=str(exc))

    # ── get_role_config ───────────────────────────────────────────────────────

    def _get_role_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        role_id = params.get("role_id")
        if role_id:
            if role_id not in ROLE_CONFIG:
                return {"error": f"未知岗位: {role_id}", "available": list(ROLE_CONFIG.keys())}
            cfg = ROLE_CONFIG[role_id]
            return {
                "role_id":         cfg["id"],
                "role_name":       cfg["name"],
                "metrics":         cfg["metrics"],
                "commission_rules": COMMISSION_RULES.get(role_id, []),
            }
        # 返回所有岗位摘要
        return {
            "roles": [
                {
                    "role_id":   r["id"],
                    "role_name": r["name"],
                    "metric_count":     len(r["metrics"]),
                    "commission_count": len(COMMISSION_RULES.get(r["id"], [])),
                }
                for r in ROLE_CONFIG.values()
            ]
        }

    # ── calculate_performance ─────────────────────────────────────────────────

    def _calculate_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算绩效得分。

        params:
            role_id       (str, required)
            metric_values (Dict[str, float], optional) — 指标实际值（分或小数）
            period        (str, optional) — 'YYYY-MM' 或 'month'
        """
        role_id = params.get("role_id", "")
        if not role_id or role_id not in ROLE_CONFIG:
            return {"success": False, "error": f"无效 role_id: {role_id}"}

        role    = ROLE_CONFIG[role_id]
        mv      = params.get("metric_values", {}) or {}
        period  = params.get("period", datetime.now().strftime("%Y-%m"))
        dyn_cfg = params.get("_dyn_cfg", {})

        # 动态翻台基准（仅在 store_manager/shift_manager 的 turnover 指标中生效）
        table_turnover_baseline = dyn_cfg.get("table_turnover_baseline", DEFAULT_TARGETS.get("turnover", 3.0))
        dynamic_targets = {**DEFAULT_TARGETS, "turnover": table_turnover_baseline}

        # KPI达成率上限
        kpi_cap = dyn_cfg.get("kpi_achievement_cap", 2.0)

        items: List[Dict[str, Any]] = []
        for m in role["metrics"]:
            mid    = m["id"]
            value  = mv.get(mid)
            target = dynamic_targets.get(mid)
            ach    = _achievement(value, target, mid, cap=kpi_cap) if (value is not None and target is not None) else None
            items.append({
                "metric_id":        mid,
                "metric_name":      m["name"],
                "weight":           m["weight"],
                "value":            value,
                "target":           target,
                "achievement_rate": ach,
            })

        scored = [i for i in items if i["achievement_rate"] is not None]
        if scored:
            w_sum       = sum(i["weight"] for i in scored)
            total_score = round(sum(i["weight"] * i["achievement_rate"] for i in scored) / w_sum, 4)
        else:
            total_score = None

        return {
            "role_id":    role_id,
            "role_name":  role["name"],
            "period":     period,
            "metrics":    items,
            "total_score": total_score,
        }

    # ── calculate_commission ─────────────────────────────────────────────────

    def _calculate_commission(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算提成金额。

        params:
            role_id       (str, required)
            metric_values (Dict[str, float], optional)
            period        (str, optional)
        """
        role_id = params.get("role_id", "")
        if not role_id or role_id not in ROLE_CONFIG:
            return {"success": False, "error": f"无效 role_id: {role_id}"}

        mv      = params.get("metric_values", {}) or {}
        period  = params.get("period", datetime.now().strftime("%Y-%m"))
        dyn_cfg = params.get("_dyn_cfg", {})

        # 动态翻台基准 & KPI上限
        table_turnover_baseline = dyn_cfg.get("table_turnover_baseline", DEFAULT_TARGETS.get("turnover", 3.0))
        dynamic_targets = {**DEFAULT_TARGETS, "turnover": table_turnover_baseline}
        kpi_cap = dyn_cfg.get("kpi_achievement_cap", 2.0)

        # 先算达成率
        role = ROLE_CONFIG[role_id]
        achievements: Dict[str, float] = {}
        for m in role["metrics"]:
            mid = m["id"]
            v   = mv.get(mid)
            t   = dynamic_targets.get(mid)
            if v is not None and t is not None:
                achievements[mid] = _achievement(v, t, mid, cap=kpi_cap)

        scored = [
            achievements[m["id"]] * m["weight"]
            for m in role["metrics"]
            if m["id"] in achievements
        ]
        w_scored = [m["weight"] for m in role["metrics"] if m["id"] in achievements]
        total_score = (
            round(sum(scored) / sum(w_scored), 4) if w_scored else None
        )

        # 动态计件提成分段（外卖专员 delivery）
        piece_rate_tiers = dyn_cfg.get("piece_rate_tiers")
        rules = COMMISSION_RULES.get(role_id, [])
        if piece_rate_tiers and role_id == "delivery":
            rules = []
            for rule in COMMISSION_RULES.get(role_id, []):
                if rule.get("type") == "tiered_count" and rule.get("metric") == "order_count":
                    # 将动态分段转换为原始 tiers 格式 [(max_orders, rate_fen), ...]
                    converted_tiers = []
                    for tier in piece_rate_tiers:
                        max_o = tier.get("max_orders") or 9999
                        rate_fen = int(tier.get("rate", 1.0) * 100)
                        converted_tiers.append((max_o, rate_fen))
                    rule = {**rule, "tiers": converted_tiers}
                rules.append(rule)

        rule_results  = []
        total_fen     = 0

        for rule in rules:
            amount = _compute_rule_amount(rule, mv, achievements, total_score)
            rule_results.append({
                "name":    rule["name"],
                "type":    rule["type"],
                "amount_fen": amount,
                "amount_yuan": round(amount / 100, 2) if amount is not None else None,
                "triggered":  amount is not None and amount != 0,
                "desc":   rule["desc"],
            })
            if amount is not None:
                total_fen += amount

        return {
            "role_id":        role_id,
            "role_name":      ROLE_CONFIG[role_id]["name"],
            "period":         period,
            "total_score":    total_score,
            "rule_results":   rule_results,
            "total_commission_fen":  total_fen,
            "total_commission_yuan": round(total_fen / 100, 2),
        }

    # ── get_performance_report ────────────────────────────────────────────────

    def _get_performance_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成门店绩效报表（汇总多岗位）。

        params:
            store_id    (str, optional)
            period      (str, optional)
            role_results (List[Dict], optional) — 已算好的各岗位结果注入
        """
        store_id     = params.get("store_id", self.store_id)
        period       = params.get("period", datetime.now().strftime("%Y-%m"))
        role_results = params.get("role_results", [])

        # 汇总统计
        total_commission = sum(r.get("total_commission_fen", 0) for r in role_results)
        scores = [r["total_score"] for r in role_results if r.get("total_score") is not None]
        avg_score = round(sum(scores) / len(scores), 4) if scores else None

        report = {
            "store_id": store_id,
            "period":   period,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "roles_counted":        len(role_results),
                "avg_total_score":      avg_score,
                "total_commission_fen":  total_commission,
                "total_commission_yuan": round(total_commission / 100, 2),
            },
            "role_details": role_results,
        }
        return report

    # ── explain_rule ──────────────────────────────────────────────────────────

    def _explain_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """解释指定岗位的指定提成规则。"""
        role_id   = params.get("role_id", "")
        rule_name = params.get("rule_name", "")

        if role_id not in ROLE_CONFIG:
            return {"error": f"未知岗位: {role_id}", "available": list(ROLE_CONFIG.keys())}

        rules = COMMISSION_RULES.get(role_id, [])

        if rule_name:
            matched = [r for r in rules if rule_name in r["name"]]
            if not matched:
                return {"error": f"未找到规则: {rule_name}", "available": [r["name"] for r in rules]}
            rule = matched[0]
            return {
                "role_id":   role_id,
                "rule_name": rule["name"],
                "type":      rule["type"],
                "desc":      rule["desc"],
                "params":    {k: v for k, v in rule.items() if k not in ("name", "type", "desc")},
                "steps": _build_rule_steps(rule),
            }

        # 返回该岗位所有规则摘要
        return {
            "role_id":   role_id,
            "role_name": ROLE_CONFIG[role_id]["name"],
            "rules": [
                {"name": r["name"], "type": r["type"], "desc": r["desc"]}
                for r in rules
            ],
        }

    # ── nl_query ──────────────────────────────────────────────────────────────

    def _nl_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """自然语言查询：关键词意图分发，无 LLM 依赖。"""
        question = params.get("question", "")
        if not question:
            return {"error": "question 参数不能为空"}

        role_id = _detect_role(question) or params.get("role_id")
        action  = _detect_action(question)

        if action == "config":
            return self._get_role_config({"role_id": role_id})
        if action == "performance":
            return self._calculate_performance({
                "role_id":       role_id or "store_manager",
                "metric_values": params.get("metric_values", {}),
                "period":        params.get("period", ""),
            })
        if action == "commission":
            return self._calculate_commission({
                "role_id":       role_id or "store_manager",
                "metric_values": params.get("metric_values", {}),
                "period":        params.get("period", ""),
            })
        if action == "report":
            return self._get_performance_report({
                "store_id":    params.get("store_id", self.store_id),
                "period":      params.get("period", ""),
                "role_results": [],
            })
        if action == "explain":
            return self._explain_rule({
                "role_id":   role_id or "store_manager",
                "rule_name": params.get("rule_name", ""),
            })
        return {"question": question, "answer": "暂未识别意图，请直接调用对应 action。"}


# ── 辅助：规则说明步骤 ────────────────────────────────────────────────────────

def _build_rule_steps(rule: Dict[str, Any]) -> List[str]:
    rtype = rule["type"]
    if rtype == "achievement_bonus":
        return [
            f"1. 取指标 {rule['metric']} 的达成率",
            f"2. 达成率 ≥ {rule['threshold']} → 奖金 ¥{rule['fixed_fen'] // 100}",
            f"3. 达成率 < {rule['threshold']} → ¥0",
        ]
    if rtype == "excess_commission":
        return [
            f"1. 计算指标 {rule['metric']} 超额比例 = (实际值 - 目标值) / 目标值",
            f"2. 提成率 = {rule['base_rate']*100:.0f}%–{rule['max_rate']*100:.0f}%（线性插值）",
            "3. 提成 = 超额金额 × 提成率",
        ]
    if rtype == "tiered_count":
        tiers = rule.get("tiers", [])
        steps = ["1. 根据数量所在阶梯取单价："]
        prev = 0
        for upper, rate in tiers:
            steps.append(f"   {prev+1}–{upper} 单 → ¥{rate/100:.1f}/单")
            prev = upper
        steps.append("2. 总提成 = 数量 × 单价")
        return steps
    if rtype == "score_coefficient":
        return [
            f"1. 取综合绩效得分 total_score（0–2.0）",
            f"2. 奖金 = 基础工资 ¥{rule.get('base_salary_fen', 0)//100} × total_score × {rule.get('coeff_scale', 0)*100:.0f}%",
        ]
    return [rule.get("desc", "")]
