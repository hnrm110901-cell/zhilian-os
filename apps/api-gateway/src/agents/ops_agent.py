"""
OpsAgent - 连锁餐饮IT运维智能体 (智链OS 运维方案)

对应《连锁餐饮AI Agent运维方案》：
- L1 感知层：数字哨兵（健康检查、资产概览）
- L2 推理层：诊断大脑（根因分析、故障预测、Runbook 建议）
- L3 执行层：行动建议（链路切换、安全加固、备件建议）
- 协调层：自然语言运维问答
"""
import time
from typing import Dict, Any, Optional, List
import structlog

from .llm_agent import LLMEnhancedAgent
from ..core.base_agent import AgentResponse
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

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
            "health_check",        # 单店/全域健康检查建议
            "diagnose_fault",      # 故障根因分析
            "runbook_suggestion",  # 修复步骤/Runbook 建议
            "predict_maintenance", # 预测性维护建议（硬件/网络）
            "security_advice",     # 安全加固建议（弱密码/漏洞/VPN/白名单）
            "link_switch_advice",  # 主备链路切换建议
            "asset_overview",      # 资产概览与台账建议
            "nl_query",            # 自然语言运维问答
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

    async def _health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """健康检查：结合方案中的软件/硬件/网络域，给出检查项与结论建议。"""
        store_id = params.get("store_id")
        scope = params.get("scope", "store")
        user_message = (
            f"门店 {store_id or '全域'} IT健康检查（scope={scope}）："
            f"请检查软件域(POS/ERP/会员)、硬件域(POS/打印机/KDS/门禁/监控)、"
            f"网络域(带宽/链路/VPN)，列出各域检查项状态与结论建议。"
        )
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"scope": scope}
        )
        return {
            "success": result.success,
            "data": {"check_advice": result.data, "scope": scope, "store_id": store_id,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
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
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"symptom": symptom}
        )
        return {
            "success": result.success,
            "data": {"diagnosis": result.data, "symptom": symptom,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _runbook_suggestion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Runbook/修复步骤建议（对应方案中的自动修复 Runbook 库）。"""
        fault_type = params.get("fault_type", "")
        store_id = params.get("store_id")
        user_message = (
            f"故障类型「{fault_type}」的标准修复步骤（Runbook）："
            f"请给出分步操作指南、注意事项与回滚建议。"
        )
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"fault_type": fault_type}
        )
        return {
            "success": result.success,
            "data": {"runbook": result.data, "fault_type": fault_type,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
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
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"device_type": device_type}
        )
        return {
            "success": result.success,
            "data": {"maintenance_advice": result.data, "device_type": device_type,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
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
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"focus": focus}
        )
        return {
            "success": result.success,
            "data": {"security_advice": result.data, "focus": focus,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
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
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"quality_score": quality_score}
        )
        return {
            "success": result.success,
            "data": {"link_advice": result.data, "quality_score": quality_score,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
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
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={}
        )
        return {
            "success": result.success,
            "data": {"asset_advice": result.data, "store_id": store_id,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }

    async def _nl_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """自然语言运维问答，如「3号店今天网络为什么慢」（方案 3.2.3 LLM 运维助手）。"""
        question = params.get("question", "")
        store_id = params.get("store_id")
        user_message = (
            f"运维问答 门店 {store_id or '不限'}：{question}。"
            f"请结合运维知识给出人类可读的分析与操作建议。"
        )
        result = await self.execute_with_tools(
            user_message=user_message,
            store_id=store_id or "",
            context={"question": question}
        )
        return {
            "success": result.success,
            "data": {"answer": result.data, "question": question,
                     "tool_calls": len(result.tool_calls), "iterations": result.iterations},
            "error": result.message if not result.success else None,
            "metadata": {"source": "tool_use"},
        }
