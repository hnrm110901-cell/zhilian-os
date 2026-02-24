"""
Quality Service - 菜品质量检测服务

核心能力：
- 调用视觉模型分析菜品图片
- 生成质量评分和问题列表
- 持久化检测记录
"""
import json
import os
import re
from typing import Dict, Any, List, Optional
import structlog

from ..core.llm import get_llm_client
from ..models.quality import InspectionStatus

logger = structlog.get_logger()

PASS_THRESHOLD = float(os.getenv("QUALITY_PASS_THRESHOLD", "75.0"))

_SYSTEM_PROMPT = """你是一位专业的餐饮菜品质量检测专家。
请根据提供的菜品图片，从以下维度评估质量：
1. 色泽（颜色是否正常、有无变色）
2. 形态（摆盘是否整齐、份量是否达标）
3. 卫生（有无异物、容器是否洁净）
4. 新鲜度（食材是否新鲜）

请以 JSON 格式返回评估结果，格式如下：
{
  "quality_score": <0-100的整数>,
  "issues": [
    {"type": "color|shape|hygiene|freshness", "description": "问题描述", "severity": "low|medium|high"}
  ],
  "suggestions": ["改进建议1", "改进建议2"],
  "reasoning": "综合评估说明"
}

评分标准：90-100优秀，75-89合格，60-74需改进，60以下不合格。"""


class QualityService:
    """菜品质量检测服务"""

    async def analyze_image(
        self,
        image_b64: str,
        dish_name: str,
        media_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """
        调用视觉模型分析菜品图片。

        Args:
            image_b64: base64 编码的图片
            dish_name: 菜品名称
            media_type: 图片 MIME 类型

        Returns:
            包含 quality_score / issues / suggestions / reasoning 的字典
        """
        llm = get_llm_client()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"请检测这道菜品「{dish_name}」的质量，按要求返回 JSON。",
                    },
                ],
            }
        ]

        raw = await llm.generate_with_context(
            messages=messages,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=800,
        )

        return self._parse_llm_response(raw)

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON，容错处理"""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        # 降级：返回中等分数，标记需人工复核
        logger.warning("quality_service.parse_failed", raw_snippet=raw[:200])
        return {
            "quality_score": 70,
            "issues": [{"type": "parse_error", "description": "视觉模型响应解析失败，需人工复核", "severity": "medium"}],
            "suggestions": ["请人工检查此菜品"],
            "reasoning": raw[:500],
        }

    async def save_inspection(
        self,
        store_id: str,
        dish_name: str,
        analysis: Dict[str, Any],
        dish_id: Optional[str] = None,
        image_url: Optional[str] = None,
        inspector: str = "quality_agent",
    ) -> Dict[str, Any]:
        """持久化检测记录"""
        from ..core.database import get_db_session
        from ..models.quality import QualityInspection

        score = float(analysis.get("quality_score", 0))
        if score >= PASS_THRESHOLD:
            status = InspectionStatus.PASS
        elif score >= 60:
            status = InspectionStatus.REVIEW
        else:
            status = InspectionStatus.FAIL

        async with get_db_session() as session:
            record = QualityInspection(
                store_id=store_id,
                dish_id=dish_id,
                dish_name=dish_name,
                image_url=image_url,
                quality_score=score,
                status=status,
                issues=analysis.get("issues", []),
                suggestions=analysis.get("suggestions", []),
                llm_reasoning=analysis.get("reasoning", ""),
                inspector=inspector,
                pass_threshold=PASS_THRESHOLD,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        logger.info(
            "quality_inspection_saved",
            store_id=store_id,
            dish_name=dish_name,
            score=score,
            status=status.value,
        )

        return {
            "id": str(record.id),
            "store_id": store_id,
            "dish_name": dish_name,
            "quality_score": score,
            "status": status.value,
            "issues": record.issues,
            "suggestions": record.suggestions,
            "created_at": record.created_at.isoformat(),
        }

    async def list_inspections(
        self,
        store_id: str,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询门店检测记录"""
        from sqlalchemy import select
        from ..core.database import get_db_session
        from ..models.quality import QualityInspection

        async with get_db_session() as session:
            q = select(QualityInspection).where(
                QualityInspection.store_id == store_id
            ).order_by(QualityInspection.created_at.desc()).limit(limit)

            if status:
                q = q.where(QualityInspection.status == InspectionStatus(status))

            result = await session.execute(q)
            rows = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "dish_name": r.dish_name,
                "quality_score": r.quality_score,
                "status": r.status.value,
                "issues": r.issues,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def get_summary(self, store_id: str) -> Dict[str, Any]:
        """门店质量检测汇总统计"""
        from sqlalchemy import select, func
        from ..core.database import get_db_session
        from ..models.quality import QualityInspection

        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.count(QualityInspection.id).label("total"),
                    func.avg(QualityInspection.quality_score).label("avg_score"),
                    func.count(QualityInspection.id).filter(
                        QualityInspection.status == InspectionStatus.PASS
                    ).label("pass_count"),
                    func.count(QualityInspection.id).filter(
                        QualityInspection.status == InspectionStatus.FAIL
                    ).label("fail_count"),
                ).where(QualityInspection.store_id == store_id)
            )
            row = result.one()

        total = row.total or 0
        pass_rate = round(row.pass_count / total * 100, 1) if total > 0 else 0.0

        return {
            "store_id": store_id,
            "total_inspections": total,
            "avg_quality_score": round(row.avg_score or 0, 1),
            "pass_count": row.pass_count or 0,
            "fail_count": row.fail_count or 0,
            "pass_rate_pct": pass_rate,
        }


quality_service = QualityService()
