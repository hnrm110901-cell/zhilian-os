"""
OpsAgent - 连锁餐饮IT运维智能体 (屯象OS 运维方案)

对应《连锁餐饮AI Agent运维方案》：
- L1 感知层：数字哨兵（健康检查、资产概览）
- L2 推理层：诊断大脑（根因分析、故障预测、Runbook 建议）
- L3 执行层：行动建议（链路切换、安全加固、备件建议）
- 协调层：自然语言运维问答
- V2.0 新增：store_dashboard / alert_convergence / food_safety_status
"""

import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import structlog

from ..core.base_agent import AgentResponse
from ..core.monitoring import ErrorCategory, ErrorSeverity, error_monitor
from .llm_agent import LLMEnhancedAgent

logger = structlog.get_logger()


class OpsAgent(LLMEnhancedAgent):
    """
    运维智能体

    能力范围（与运维方案一致）：
    - 软件域：POS/收银、ERP/进销存、会员营销 健康与异常
    - 硬件域：POS终端、打印机、KDS、门禁、监控 健康预测与备件建议
    - 网络域：拓扑感知、链路切换建议、安全（弱密码/非授权设备/漏洞/VPN）
    - 通用：根因分析、Runbook 建议、自然语言运维问答
    """

    def __init__(self):
        super().__init__(agent_type="ops")

    def get_supported_actions(self) -> List[str]:
        return [
            "health_check",  # 单店/全域健康检查建议
            "diagnose_fault",  # 故障根因分析
            "runbook_suggestion",  # 修复步骤/Runbook 建议
            "predict_maintenance",  # 预测性维护建议（硬件/网络）
            "security_advice",  # 安全加固建议（弱密码/漏洞/VPN/白名单）
            "link_switch_advice",  # 主备链路切换建议
            "asset_overview",  # 资产概览与台账建议
            "nl_query",  # 自然语言运维问答
            # V2.0 新增 ──────────────────────────────────────────────────────
            "store_dashboard",  # 门店健康总览（L1+L2+L3实时数据汇总）
            "alert_convergence",  # 告警收敛（多信号→根因事件）
            "food_safety_status",  # 食安合规状态查询
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """统一入口：将 action 分发到具体能力，并返回 AgentResponse。"""
        start = time.time()
        if action not in self.get_supported_actions():
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(self.get_supported_actions())}",
                execution_time=time.time() - start,
            )
        try:
            if action == "health_check":
                out = await self._health_check(params)
            elif action == "diagnose_fault":
                out = await self._diagnose_fault(params)
            elif action == "runbook_suggestion":
                out = await self._runbook_suggestion(params)
            elif action == "predict_maintenance":
                out = await self._predict_maintenance(params)
            elif action == "security_advice":
                out = await self._security_advice(params)
            elif action == "link_switch_advice":
                out = await self._link_switch_advice(params)
            elif action == "asset_overview":
                out = await self._asset_overview(params)
            elif action == "store_dashboard":
                out = await self._store_dashboard(params)
            elif action == "alert_convergence":
                out = await self._alert_convergence(params)
            elif action == "food_safety_status":
                out = await self._food_safety_status(params)
            else:  # nl_query
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
            logger.error("OpsAgent 执行异常", action=action, error=str(e), exc_info=e)
            error_monitor.log_error(
                message=f"OpsAgent failed: {action}",
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

    async def _with_rag(self, query: str, store_id: Optional[str], top_k: int = 5) -> Dict[str, Any]:
        """RAG 查询包装：无 RAG 时返回空上下文，供单测与降级路径复用。"""
        if not getattr(self, "_rag", None):
            return {"response": "", "metadata": {"context_count": 0, "timestamp": ""}}
        try:
            return await self._rag.analyze_with_rag(
                query=query,
                store_id=store_id or "",
                collection="events",
                top_k=top_k,
            )
        except Exception as exc:
            logger.warning("ops_rag_failed", error=str(exc))
            return {"response": "", "metadata": {"context_count": 0, "timestamp": "", "error": str(exc)}}

    async def _safe_execute_with_tools(
        self,
        user_message: str,
        store_id: str,
        context: Dict[str, Any],
    ):
        """LLM 可用时走工具执行；不可用时走本地降级，保持接口稳定。"""
        if getattr(self, "llm_enabled", False):
            return await self.execute_with_tools(user_message=user_message, store_id=store_id, context=context)

        rag_result = await self._with_rag(user_message, store_id)
        fallback_text = rag_result.get("response") or f"已生成运维建议（降级模式）：{user_message}"
        return SimpleNamespace(
            success=True,
            data=fallback_text,
            message=None,
            tool_calls=[],
            iterations=0,
        )

    async def _health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """健康检查：结合方案中的软件/硬件/网络域，给出检查项与结论建议。"""
        store_id = params.get("store_id")
        scope = params.get("scope", "store")
        user_message = (
            f"门店 {store_id or '全域'} IT健康检查（scope={scope}）："
            f"请检查软件域(POS/ERP/会员)、硬件域(POS/打印机/KDS/门禁/监控)、"
            f"网络域(带宽/链路/VPN)，列出各域检查项状态与结论建议。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"scope": scope}
        )
        return {
            "success": result.success,
            "data": {
                "check_advice": result.data,
                "scope": scope,
                "store_id": store_id,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _diagnose_fault(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """故障根因分析：目标 80% 故障 5 分钟内定位（网络/数据库/应用）。"""
        store_id = params.get("store_id")
        symptom = params.get("symptom", "")
        user_message = (
            f"门店 {store_id} 故障根因分析：症状「{symptom}」。"
            f"请做根因分析（网络/数据库/应用），给出可能原因（按概率排序）与排查顺序。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"symptom": symptom}
        )
        return {
            "success": result.success,
            "data": {
                "diagnosis": result.data,
                "symptom": symptom,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _runbook_suggestion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Runbook/修复步骤建议（对应方案中的自动修复 Runbook 库）。"""
        fault_type = params.get("fault_type", "")
        store_id = params.get("store_id")
        user_message = f"故障类型「{fault_type}」的标准修复步骤（Runbook）：" f"请给出分步操作指南、注意事项与回滚建议。"
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"fault_type": fault_type}
        )
        return {
            "success": result.success,
            "data": {
                "runbook": result.data,
                "fault_type": fault_type,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _predict_maintenance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """预测性维护：打印机/网络设备/KDS/门禁电池等（方案中 72h/48h/7d/3d 预测）。"""
        store_id = params.get("store_id")
        device_type = params.get("device_type", "")
        user_message = (
            f"门店 {store_id} 设备类型「{device_type}」预测性维护："
            f"请根据使用频率与历史故障数据，给出维护时间窗口、备件建议和巡检计划。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"device_type": device_type}
        )
        return {
            "success": result.success,
            "data": {
                "maintenance_advice": result.data,
                "device_type": device_type,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _security_advice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """安全建议：弱密码、非授权设备、固件漏洞、VPN 健康（方案中的网络安全 Agent）。"""
        store_id = params.get("store_id")
        focus = params.get("focus")
        user_message = (
            f"门店 {store_id} 网络安全加固建议（focus={focus or '全面'}）："
            f"请分析弱密码风险、非授权设备、固件漏洞、VPN 隧道健康，给出优先级排序的加固措施。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"focus": focus}
        )
        return {
            "success": result.success,
            "data": {
                "security_advice": result.data,
                "focus": focus,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _link_switch_advice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """主备链路切换建议：主链路质量分 <70 时 30 秒内切换、回切时机（方案 2.4.2）。"""
        store_id = params.get("store_id")
        quality_score = params.get("quality_score")
        user_message = (
            f"门店 {store_id} 主备链路切换决策：当前主链路质量分 {quality_score}。"
            f"请判断是否建议切换、切换时机、回切条件与注意事项。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"quality_score": quality_score}
        )
        return {
            "success": result.success,
            "data": {
                "link_advice": result.data,
                "quality_score": quality_score,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _asset_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """资产概览与台账建议（软件/硬件/网络域，方案 1.2 运维资产全景图）。"""
        store_id = params.get("store_id")
        user_message = (
            f"门店 {store_id or '全域'} IT资产台账概览："
            f"请列出软件域(POS/ERP/进销存/收银/外卖/会员/BI)、"
            f"硬件域(POS/打印机/显示屏/KDS/门禁/监控/服务器)、"
            f"网络域(局域网/广域网/WiFi/4G5G/VPN)的建议采集项与分类。"
        )
        result = await self._safe_execute_with_tools(user_message=user_message, store_id=store_id or "", context={})
        return {
            "success": result.success,
            "data": {
                "asset_advice": result.data,
                "store_id": store_id,
                "tool_calls": len(result.tool_calls),
                "iterations": result.iterations,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _nl_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """自然语言运维问答，如「3号店今天网络为什么慢」（方案 3.2.3 LLM 运维助手）。"""
        question = params.get("question", "")
        store_id = params.get("store_id")
        user_message = f"运维问答 门店 {store_id or '不限'}：{question}。" f"请结合运维知识给出人类可读的分析与操作建议。"
        result = await self._safe_execute_with_tools(
            user_message=user_message, store_id=store_id or "", context={"question": question}
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

    # ── V2.0 新增方法 ─────────────────────────────────────────────────────────

    async def _store_dashboard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        门店健康总览（L1设备 + L2网络 + L3系统实时数据）。
        直接调用 OpsMonitorService.get_store_dashboard，
        再用 Claude 对结果生成自然语言摘要和处置建议。
        """
        from ..services.ops_monitor_service import OpsMonitorService

        store_id = params.get("store_id", "")
        session = params.get("session")
        window_minutes = params.get("window_minutes", 30)

        # 如果有真实 DB session，先拉实时数据
        dashboard_data: Dict = {}
        if session:
            svc = OpsMonitorService()
            try:
                dashboard_data = await svc.get_store_dashboard(session, store_id, window_minutes=window_minutes)
            except Exception as exc:
                logger.warning("get_store_dashboard DB error", error=str(exc))

        summary_text = f"门店 {store_id} 运维健康总览（最近 {window_minutes} 分钟）：\n" + (
            f"整体状态: {dashboard_data.get('overall_status', '未知')}，"
            f"健康分: {dashboard_data.get('overall_score', 'N/A')}，"
            f"活跃告警: {dashboard_data.get('active_alerts', 'N/A')} 条"
            if dashboard_data
            else "暂无实时数据，请基于运维知识给出巡检建议"
        )
        result = await self._safe_execute_with_tools(
            user_message=summary_text + "。请给出摘要解读和优先处置建议。",
            store_id=store_id,
            context={"dashboard": dashboard_data},
        )
        return {
            "success": result.success,
            "data": {
                "dashboard": dashboard_data,
                "llm_summary": result.data,
                "store_id": store_id,
                "window_minutes": window_minutes,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use+db"},
        }

    async def _alert_convergence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        告警收敛：将同一时间窗口内多条告警归并为根因事件。
        对应方案 5.2 故障关联分析。
        """
        from ..services.ops_monitor_service import OpsMonitorService

        store_id = params.get("store_id", "")
        session = params.get("session")
        window_minutes = params.get("window_minutes", 5)

        convergence_data: Dict = {}
        if session:
            svc = OpsMonitorService()
            try:
                convergence_data = await svc.converge_alerts(session, store_id, window_minutes=window_minutes)
            except Exception as exc:
                logger.warning("converge_alerts DB error", error=str(exc))

        root_cause = convergence_data.get("root_cause", "")
        user_message = (
            f"门店 {store_id} 告警收敛分析（窗口 {window_minutes} 分钟）：\n"
            f"规则引擎判断根因：{root_cause or '待分析'}。\n"
            f"告警分布：{convergence_data.get('alert_counts', {})}。\n"
            f"请验证根因判断，补充可能遗漏的原因，并给出优先级排序的处置步骤。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message,
            store_id=store_id,
            context={"convergence": convergence_data},
        )
        return {
            "success": result.success,
            "data": {
                "convergence": convergence_data,
                "llm_analysis": result.data,
                "store_id": store_id,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "rule_engine+llm"},
        }

    async def _food_safety_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """食安合规状态查询（对应方案 3.2 食安设备监控SOP）。"""
        from ..services.ops_monitor_service import OpsMonitorService

        store_id = params.get("store_id", "")
        session = params.get("session")
        days = params.get("days", 7)

        fs_data: Dict = {}
        if session:
            svc = OpsMonitorService()
            try:
                fs_data = await svc.get_food_safety_status(session, store_id, days=days)
            except Exception as exc:
                logger.warning("get_food_safety_status DB error", error=str(exc))

        violations = fs_data.get("total_violations", 0)
        user_message = (
            f"门店 {store_id} 最近 {days} 天食安合规状态：\n"
            f"违规次数: {violations}，"
            f"分类明细: {fs_data.get('by_type', [])}，"
            f"未解决问题: {fs_data.get('open_issues', [])}。\n"
            f"请给出食安风险等级评估和整改建议，并关注2026年6月食安新规合规要求。"
        )
        result = await self._safe_execute_with_tools(
            user_message=user_message,
            store_id=store_id,
            context={"food_safety": fs_data},
        )
        return {
            "success": result.success,
            "data": {
                "food_safety": fs_data,
                "llm_assessment": result.data,
                "store_id": store_id,
                "days": days,
            },
            "error": result.message if not result.success else None,
            "metadata": {"source": "db+llm"},
        }
