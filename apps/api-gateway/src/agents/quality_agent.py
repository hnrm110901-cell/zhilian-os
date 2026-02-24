"""
QualityAgent - 菜品质量检测 Agent

职责：
- 接收菜品图片（base64）
- 调用视觉模型评分
- 不合格时推送企业微信告警
- 触发 quality.* 事件到神经系统
"""
import os
from typing import Dict, Any, List, Optional
import structlog

from .llm_agent import LLMEnhancedAgent, AgentResult
from ..services.quality_service import quality_service
from ..services.wechat_alert_service import wechat_alert_service

logger = structlog.get_logger()

ALERT_THRESHOLD = float(os.getenv("QUALITY_ALERT_THRESHOLD", "75.0"))


class QualityAgent(LLMEnhancedAgent):
    """
    菜品质量检测 Agent

    支持的 actions:
    - inspect_dish   分析单张菜品图片
    - get_report     获取门店检测报告
    - get_summary    获取门店质量汇总
    """

    def __init__(self):
        super().__init__(agent_type="quality")

    def get_supported_actions(self) -> List[str]:
        return ["inspect_dish", "get_report", "get_summary"]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResult:
        if action == "inspect_dish":
            return await self._inspect_dish(params)
        if action == "get_report":
            return await self._get_report(params)
        if action == "get_summary":
            return await self._get_summary(params)
        return AgentResult(
            success=False,
            data=None,
            message=f"不支持的操作: {action}",
        )

    # ── 核心方法 ──────────────────────────────────────────────

    async def inspect_dish(
        self,
        store_id: str,
        dish_name: str,
        image_b64: str,
        dish_id: Optional[str] = None,
        image_url: Optional[str] = None,
        media_type: str = "image/jpeg",
        recipient_ids: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        分析菜品图片质量，不合格时发送企业微信告警。

        Args:
            store_id:      门店ID
            dish_name:     菜品名称
            image_b64:     base64 编码图片
            dish_id:       菜品ID（可选）
            image_url:     图片存储路径（可选，用于记录）
            media_type:    图片 MIME 类型
            recipient_ids: 企业微信接收人ID列表
        """
        try:
            # 1. 视觉模型分析
            analysis = await quality_service.analyze_image(
                image_b64=image_b64,
                dish_name=dish_name,
                media_type=media_type,
            )

            # 2. 持久化
            record = await quality_service.save_inspection(
                store_id=store_id,
                dish_name=dish_name,
                analysis=analysis,
                dish_id=dish_id,
                image_url=image_url,
            )

            score = record["quality_score"]
            status = record["status"]

            # 3. 不合格 → 企业微信告警
            if score < ALERT_THRESHOLD and recipient_ids:
                issues_text = "\n".join(
                    f"  [{i['severity'].upper()}] {i['description']}"
                    for i in record.get("issues", [])
                ) or "  无具体问题描述"

                await wechat_alert_service.send_system_alert(
                    alert_type="quality_fail",
                    title=f"菜品质量预警：{dish_name}",
                    message=(
                        f"门店 {store_id} 菜品「{dish_name}」质量检测不合格\n"
                        f"质量评分：{score:.1f}（合格线 {ALERT_THRESHOLD}）\n"
                        f"问题详情：\n{issues_text}"
                    ),
                    severity="critical" if score < 60 else "warning",
                    recipient_ids=recipient_ids,
                )

            logger.info(
                "quality_agent.inspect_done",
                store_id=store_id,
                dish_name=dish_name,
                score=score,
                status=status,
            )

            return AgentResult(
                success=True,
                data=record,
                message=f"「{dish_name}」质量评分 {score:.1f}，状态：{status}",
                reasoning=analysis.get("reasoning", ""),
                confidence=min(score / 100, 1.0),
                source_data={"store_id": store_id, "dish_name": dish_name},
                recommendations=record.get("suggestions", []),
            )

        except Exception as e:
            logger.error("quality_agent.inspect_failed", store_id=store_id, dish_name=dish_name, error=str(e))
            return AgentResult(
                success=False,
                data=None,
                message=f"质量检测失败: {e}",
                source_data={"store_id": store_id, "dish_name": dish_name},
            )

    # ── execute 路由 ──────────────────────────────────────────

    async def _inspect_dish(self, params: Dict[str, Any]) -> AgentResult:
        for required in ("store_id", "dish_name", "image_b64"):
            if not params.get(required):
                return AgentResult(success=False, data=None, message=f"缺少参数: {required}")
        return await self.inspect_dish(
            store_id=params["store_id"],
            dish_name=params["dish_name"],
            image_b64=params["image_b64"],
            dish_id=params.get("dish_id"),
            image_url=params.get("image_url"),
            media_type=params.get("media_type", "image/jpeg"),
            recipient_ids=params.get("recipient_ids"),
        )

    async def _get_report(self, params: Dict[str, Any]) -> AgentResult:
        store_id = params.get("store_id")
        if not store_id:
            return AgentResult(success=False, data=None, message="缺少 store_id 参数")
        try:
            records = await quality_service.list_inspections(
                store_id=store_id,
                limit=params.get("limit", 20),
                status=params.get("status"),
            )
            return AgentResult(
                success=True,
                data={"inspections": records, "count": len(records)},
                message=f"获取到 {len(records)} 条检测记录",
                confidence=1.0,
                source_data={"store_id": store_id},
            )
        except Exception as e:
            return AgentResult(success=False, data=None, message=f"获取报告失败: {e}")

    async def _get_summary(self, params: Dict[str, Any]) -> AgentResult:
        store_id = params.get("store_id")
        if not store_id:
            return AgentResult(success=False, data=None, message="缺少 store_id 参数")
        try:
            summary = await quality_service.get_summary(store_id)
            return AgentResult(
                success=True,
                data=summary,
                message=(
                    f"门店 {store_id} 质量合格率 {summary['pass_rate_pct']}%，"
                    f"平均评分 {summary['avg_quality_score']}"
                ),
                confidence=1.0,
                source_data={"store_id": store_id},
            )
        except Exception as e:
            return AgentResult(success=False, data=None, message=f"获取汇总失败: {e}")


# 全局实例
quality_agent = QualityAgent()
