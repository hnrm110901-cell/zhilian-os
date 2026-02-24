"""
ComplianceAgent - 合规证照管理 Agent

职责：
- 扫描即将到期/已过期证照
- 生成带优先级的提醒消息
- 通过企业微信推送告警
- 触发 compliance.* 事件到神经系统
"""
from datetime import date
from typing import Dict, Any, List, Optional
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.compliance_service import ComplianceService
from ..services.wechat_alert_service import wechat_alert_service
from ..models.compliance import LicenseStatus

logger = structlog.get_logger()

# 告警阈值（天）
CRITICAL_DAYS = 7
WARNING_DAYS = 15
NOTICE_DAYS = 30


def _urgency(days_left: int) -> str:
    if days_left < 0:
        return "已过期"
    if days_left <= CRITICAL_DAYS:
        return "紧急"
    if days_left <= WARNING_DAYS:
        return "警告"
    return "提醒"


class ComplianceAgent(LLMEnhancedAgent):
    """
    合规证照管理 Agent

    支持的 actions:
    - scan_store      扫描单门店证照状态
    - scan_all        扫描全部门店
    - check_license   检查单张证照
    """

    def __init__(self):
        super().__init__(agent_type="compliance")
        self.compliance_svc = ComplianceService()

    def get_supported_actions(self) -> List[str]:
        return ["scan_store", "scan_all", "check_license"]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResult:
        if action == "scan_store":
            return await self._scan_store(params)
        if action == "scan_all":
            return await self._scan_all(params)
        if action == "check_license":
            return await self._check_license(params)
        return AgentResult(
            success=False,
            data=None,
            message=f"不支持的操作: {action}",
        )

    # ── 核心方法 ──────────────────────────────────────────────

    async def scan_store(
        self,
        store_id: str,
        recipient_ids: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        扫描门店证照，发送企业微信告警。

        Args:
            store_id: 门店ID
            recipient_ids: 企业微信接收人ID列表
        """
        try:
            scan = await self.compliance_svc.scan_expiring(store_id=store_id)

            alerts = scan["expired"] + scan["expiring_soon"]
            if not alerts:
                return AgentResult(
                    success=True,
                    data=scan,
                    message="所有证照均在有效期内",
                    confidence=1.0,
                    source_data={"store_id": store_id},
                )

            # 构建告警消息
            lines = [f"**门店 {store_id} 证照预警**\n"]
            for lic in sorted(alerts, key=lambda x: x["days_left"]):
                days = lic["days_left"]
                urgency = _urgency(days)
                holder = f"（{lic['holder_name']}）" if lic.get("holder_name") else ""
                lines.append(
                    f"[{urgency}] {lic['license_name']}{holder} — "
                    f"{'已过期' if days < 0 else f'还剩 {days} 天'} "
                    f"（{lic['expiry_date']}）"
                )

            message = "\n".join(lines)

            # 推送企业微信
            if recipient_ids:
                await wechat_alert_service.send_system_alert(
                    title="证照合规预警",
                    content=message,
                    level="critical" if scan["expired"] else "warning",
                    recipient_ids=recipient_ids,
                )

            logger.info(
                "compliance_scan_alerted",
                store_id=store_id,
                expired=len(scan["expired"]),
                expiring=len(scan["expiring_soon"]),
            )

            return AgentResult(
                success=True,
                data=scan,
                message=message,
                reasoning=f"发现 {len(scan['expired'])} 张已过期，{len(scan['expiring_soon'])} 张即将到期",
                confidence=1.0,
                source_data={"store_id": store_id, "scanned_at": scan["scanned_at"]},
                recommendations=[
                    f"立即续期：{lic['license_name']}"
                    for lic in scan["expired"]
                ] + [
                    f"尽快续期（{lic['days_left']}天内）：{lic['license_name']}"
                    for lic in scan["expiring_soon"]
                    if lic["days_left"] <= WARNING_DAYS
                ],
            )

        except Exception as e:
            logger.error("compliance_scan_failed", store_id=store_id, error=str(e))
            return AgentResult(
                success=False,
                data=None,
                message=f"证照扫描失败: {e}",
                source_data={"store_id": store_id},
            )

    # ── execute 路由 ──────────────────────────────────────────

    async def _scan_store(self, params: Dict[str, Any]) -> AgentResult:
        store_id = params.get("store_id")
        if not store_id:
            return AgentResult(success=False, data=None, message="缺少 store_id 参数")
        return await self.scan_store(
            store_id=store_id,
            recipient_ids=params.get("recipient_ids"),
        )

    async def _scan_all(self, params: Dict[str, Any]) -> AgentResult:
        """扫描全部门店（从数据库读取活跃门店列表）"""
        try:
            from src.core.database import get_db_session
            from src.models.store import Store
            from sqlalchemy import select

            async with get_db_session() as session:
                result = await session.execute(
                    select(Store.id).where(Store.is_active == True)
                )
                store_ids = [str(r[0]) for r in result.all()]

            all_results = []
            total_alerts = 0
            for sid in store_ids:
                r = await self.scan_store(
                    store_id=sid,
                    recipient_ids=params.get("recipient_ids"),
                )
                all_results.append({"store_id": sid, "result": r.data})
                if r.data:
                    total_alerts += r.data.get("total_alerts", 0)

            return AgentResult(
                success=True,
                data={"stores": all_results, "total_alerts": total_alerts},
                message=f"扫描 {len(store_ids)} 家门店，共 {total_alerts} 条证照预警",
                confidence=1.0,
                source_data={"store_count": len(store_ids)},
            )
        except Exception as e:
            logger.error("compliance_scan_all_failed", error=str(e))
            return AgentResult(success=False, data=None, message=f"全店扫描失败: {e}")

    async def _check_license(self, params: Dict[str, Any]) -> AgentResult:
        """检查单张证照状态"""
        license_id = params.get("license_id")
        if not license_id:
            return AgentResult(success=False, data=None, message="缺少 license_id 参数")

        licenses = await self.compliance_svc.list_licenses()
        match = next((l for l in licenses if l["id"] == license_id), None)
        if not match:
            return AgentResult(success=False, data=None, message="证照不存在")

        expiry = date.fromisoformat(match["expiry_date"])
        days_left = (expiry - date.today()).days

        return AgentResult(
            success=True,
            data={**match, "days_left": days_left},
            message=f"{match['license_name']} — {_urgency(days_left)}，{'已过期' if days_left < 0 else f'还剩 {days_left} 天'}",
            confidence=1.0,
            source_data={"license_id": license_id},
        )


# 全局实例
compliance_agent = ComplianceAgent()
