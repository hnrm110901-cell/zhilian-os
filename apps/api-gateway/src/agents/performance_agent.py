"""
PerformanceAgent - 连锁餐饮绩效与提成智能体 (智链OS 绩效方案)

对应《连锁餐饮绩效 Agent 规划》：
- 岗位绩效与提成配置
- 绩效得分计算
- 提成计算与规则追溯
- 绩效报表与自然语言查询
"""
import time
from typing import Dict, Any, Optional, List
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


class PerformanceAgent(LLMEnhancedAgent):
    """
    绩效智能体（智链OS 连锁餐饮绩效方案）

    能力：get_role_config, calculate_performance, calculate_commission,
    get_performance_report, explain_rule, nl_query
    """

    def __init__(self):
        super().__init__(agent_type="performance")
        self._rag = None
        try:
            from ..services.rag_service import RAGService
            self._rag = RAGService()
        except Exception as e:
            logger.warning("RAGService 未注入，绩效 Agent nl_query 将仅使用 LLM", reason=str(e))

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
        """计算指定岗位、周期、人员绩效得分（当前为规则引擎占位，无真实数据源时返回示例结构）。"""
        store_id = params.get("store_id", "")
        role_id = params.get("role_id", "")
        period = params.get("period", "month")
        staff_ids = params.get("staff_ids")  # 可选，不传则按岗位汇总

        if not role_id or role_id not in DEFAULT_ROLE_CONFIG:
            return {
                "success": False,
                "error": "缺少或无效的 role_id",
                "data": None,
            }

        role = DEFAULT_ROLE_CONFIG[role_id]
        # 占位：实际应从 POS/ERP/考勤等聚合表读取指标值
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
        total_score = None  # 加权得分，有数据时计算

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
                "data_source_note": "当前为占位结构，接入指标表后可计算真实得分",
            },
            "metadata": {"source": "performance_engine"},
        }

    async def _calculate_commission(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算提成金额（当前为规则引擎占位）。"""
        store_id = params.get("store_id", "")
        role_id = params.get("role_id", "")
        period = params.get("period", "month")
        staff_ids = params.get("staff_ids")

        if not role_id or role_id not in DEFAULT_ROLE_CONFIG:
            return {
                "success": False,
                "error": "缺少或无效的 role_id",
                "data": None,
            }

        role = DEFAULT_ROLE_CONFIG[role_id]
        # 占位：按规则公式与指标值计算；每条可关联 rule_id 与数据追溯
        details = []
        for rule in role["commission_rules"]:
            details.append({
                "rule_name": rule,
                "amount": None,
                "formula_trace": None,
                "red_line_deduction": None,
            })

        return {
            "success": True,
            "data": {
                "store_id": store_id,
                "role_id": role_id,
                "role_name": role["name"],
                "period": period,
                "staff_ids": staff_ids,
                "total_commission": None,
                "details": details,
                "data_source_note": "当前为占位结构，接入规则引擎与指标后可计算真实提成",
            },
            "metadata": {"source": "commission_engine"},
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

        context = {
            "store_id": store_id,
            "period": period,
            "role_config_summary": {k: v["name"] for k, v in DEFAULT_ROLE_CONFIG.items()},
        }
        if self.llm_enabled:
            try:
                llm_out = await self.execute_with_llm("nl_query", params, context=context)
                if isinstance(llm_out, dict) and "data" in llm_out:
                    return llm_out
                return {
                    "success": True,
                    "data": {"answer": str(llm_out.get("data", llm_out)), "question": question},
                    "metadata": {"source": "llm"},
                }
            except Exception as e:
                logger.warning("绩效 nl_query LLM 失败，返回占位", error=str(e))
        # 无 LLM 或失败时返回占位
        return {
            "success": True,
            "data": {
                "answer": f"已收到查询：「{question}」。当前为占位回复，接入 RAG/LLM 与绩效数据后可返回具体数值与规则解释。门店={store_id}，周期={period}。",
                "question": question,
            },
            "metadata": {"source": "placeholder"},
        }
