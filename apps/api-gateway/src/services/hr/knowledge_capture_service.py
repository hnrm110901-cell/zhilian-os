"""KnowledgeCaptureService — WF-4 知识采集触发流.

功能：
1. trigger_capture  — 生成AI提问模板，通过企微推送给员工
2. submit_capture   — 接收对话，LLM结构化解析 + 质量评分 + 写 knowledge_captures
3. get_captures     — 列表查询（供 API 层复用）

纯函数：
- _score_quality(context, action, result) → float
- _build_question_template(trigger_type) → str
- _parse_dialogue(raw_dialogue) → dict
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 七种触发类型对应的采集问题模板
_QUESTION_TEMPLATES = {
    "exit": (
        "您好，感谢在公司的付出。为了帮助我们改进，想请您分享一下：\n"
        "1. 在公司工作期间，您觉得最有价值的一次经历是什么？\n"
        "2. 遇到过什么问题，您是怎么处理的？结果如何？\n"
        "3. 有什么经验或建议希望留给团队？"
    ),
    "monthly_review": (
        "本月复盘时间到了！请分享：\n"
        "1. 本月遇到的最大挑战是什么？您是如何解决的？\n"
        "2. 有什么值得推广给其他同事的做法或经验？"
    ),
    "incident": (
        "针对刚才发生的情况，请记录：\n"
        "1. 当时的具体情况是什么？（Context）\n"
        "2. 您采取了什么处理动作？（Action）\n"
        "3. 最终结果如何？（Result）"
    ),
    "onboarding": (
        "入职引导中遇到了什么？\n"
        "1. 哪个环节让您印象最深？\n"
        "2. 有什么流程是您认为可以优化的？"
    ),
    "growth_review": (
        "技能成长评议：\n"
        "1. 最近掌握了什么新技能或解决了什么新问题？\n"
        "2. 这个技能对您的工作有什么具体帮助？"
    ),
    "talent_assessment": (
        "人才评估问卷：\n"
        "1. 您认为自己在团队中最擅长的3件事是什么？\n"
        "2. 您在哪个岗位或方向上有意愿发展？"
    ),
    "legacy_import": (
        "历史经验记录：\n"
        "1. 请简要描述这段经历的背景、做法和成果。"
    ),
}


def _build_question_template(trigger_type: str) -> str:
    """根据触发类型返回标准化采集问题模板."""
    return _QUESTION_TEMPLATES.get(trigger_type, _QUESTION_TEMPLATES["incident"])


def _score_quality(context: Optional[str], action: Optional[str], result: Optional[str]) -> float:
    """纯函数：基于CAR三段完整性评分知识质量.

    评分规则：
    - context 非空且长度≥10：+0.3
    - action 非空且长度≥10：+0.4
    - result 非空且长度≥10：+0.3
    最终 clamp 到 [0.0, 1.0]
    """
    score = 0.0
    if context and len(context.strip()) >= 10:
        score += 0.3
    if action and len(action.strip()) >= 10:
        score += 0.4
    if result and len(result.strip()) >= 10:
        score += 0.3
    return round(min(1.0, max(0.0, score)), 2)


def _parse_dialogue(raw_dialogue: str) -> dict:
    """将原始对话文本解析为 context/action/result 三段结构.

    降级策略：无法解析时将整段对话放入 context，action/result 为空。
    不调用外部 LLM（避免依赖），使用关键词启发式分割。
    生产环境可替换为 Claude API 调用。
    """
    lines = [ln.strip() for ln in raw_dialogue.strip().splitlines() if ln.strip()]

    # 关键词启发式：识别"动作"相关段落
    context_lines, action_lines, result_lines = [], [], []
    current_section = "context"

    action_keywords = {"处理", "采取", "操作", "动作", "做法", "方法", "解决", "action", "Action"}
    result_keywords = {"结果", "效果", "影响", "成果", "result", "Result", "反馈", "最终"}

    for line in lines:
        # 判断是否进入新段落
        if any(kw in line for kw in action_keywords) and current_section == "context":
            current_section = "action"
        elif any(kw in line for kw in result_keywords) and current_section in ("context", "action"):
            current_section = "result"

        if current_section == "context":
            context_lines.append(line)
        elif current_section == "action":
            action_lines.append(line)
        else:
            result_lines.append(line)

    # 若完全无法分段，退化：全部视为 context
    if not action_lines and not result_lines:
        return {
            "context": raw_dialogue.strip(),
            "action": None,
            "result": None,
            "structured_output": {"parse_method": "fallback_full_context"},
        }

    return {
        "context": "\n".join(context_lines) or None,
        "action": "\n".join(action_lines) or None,
        "result": "\n".join(result_lines) or None,
        "structured_output": {"parse_method": "keyword_heuristic"},
    }


class KnowledgeCaptureService:
    """WF-4 知识采集触发与提交服务."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def trigger_capture(self, person_id: str, trigger_type: str) -> dict:
        """WF-4 触发：生成提问模板，通过企微推送给员工.

        推送失败时静默降级：返回 wechat_sent=False，不抛异常。
        """
        template = _build_question_template(trigger_type)

        # 查询员工的企业微信 openid（通过 persons.phone 关联）
        wechat_sent = False
        wechat_error = None
        try:
            result = await self._session.execute(
                sa.text("SELECT phone FROM persons WHERE id = :person_id"),
                {"person_id": person_id},
            )
            row = result.fetchone()
            phone = row.phone if row else None

            if phone:
                from src.services.wechat_service import WeChatService
                wechat = WeChatService()
                message = f"【屯象知识采集】\n{template}"
                await wechat.send_text_message(touser=phone, content=message)
                wechat_sent = True
        except Exception as exc:  # noqa: BLE001
            wechat_error = str(exc)
            logger.warning(
                "knowledge_capture.wechat_push_failed",
                person_id=person_id,
                trigger_type=trigger_type,
                error=wechat_error,
            )

        logger.info(
            "knowledge_capture.triggered",
            person_id=person_id,
            trigger_type=trigger_type,
            wechat_sent=wechat_sent,
        )
        return {
            "trigger_type": trigger_type,
            "question_template": template,
            "wechat_sent": wechat_sent,
        }

    async def submit_capture(
        self,
        person_id: str,
        trigger_type: str,
        raw_dialogue: str,
    ) -> dict:
        """WF-4 提交：解析对话 + 质量评分 + 写 knowledge_captures.

        LLM 不可用时降级：使用关键词启发式解析，quality_score 按字段完整性打分。
        """
        parsed = _parse_dialogue(raw_dialogue)
        context = parsed["context"]
        action = parsed["action"]
        result_text = parsed["result"]
        structured_output = parsed["structured_output"]

        quality_score = _score_quality(context, action, result_text)

        capture_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        await self._session.execute(
            sa.text(
                "INSERT INTO knowledge_captures "
                "(id, person_id, trigger_type, raw_dialogue, context, action, result, "
                " structured_output, quality_score, created_at) "
                "VALUES (:id, :person_id, :trigger_type, :raw_dialogue, :context, "
                "        :action, :result, CAST(:structured_output AS jsonb), "
                "        :quality_score, :created_at)"
            ),
            {
                "id": str(capture_id),
                "person_id": person_id,
                "trigger_type": trigger_type,
                "raw_dialogue": raw_dialogue,
                "context": context,
                "action": action,
                "result": result_text,
                "structured_output": str(structured_output).replace("'", '"'),
                "quality_score": quality_score,
                "created_at": now.isoformat(),
            },
        )
        await self._session.commit()

        logger.info(
            "knowledge_capture.submitted",
            capture_id=str(capture_id),
            person_id=person_id,
            trigger_type=trigger_type,
            quality_score=quality_score,
        )
        return {
            "id": str(capture_id),
            "person_id": person_id,
            "trigger_type": trigger_type,
            "quality_score": quality_score,
            "context": context,
            "action": action,
            "result": result_text,
            "created_at": now.isoformat(),
        }

    async def get_captures(
        self,
        store_id: Optional[str] = None,
        trigger_type: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """列出知识采集记录（复用于 API 层和 Celery 报告任务）."""
        _BASE = (
            "SELECT kc.id, kc.person_id, p.name AS person_name, "
            "       kc.trigger_type, kc.quality_score, kc.created_at "
            "FROM knowledge_captures kc "
            "LEFT JOIN persons p ON p.id = kc.person_id "
        )
        _ORDER = "ORDER BY kc.created_at DESC LIMIT :limit"
        _STORE_FILTER = (
            "WHERE EXISTS ("
            "  SELECT 1 FROM employment_assignments ea "
            "  JOIN stores s ON s.org_node_id = ea.org_node_id "
            "  WHERE ea.person_id = kc.person_id AND s.id = :store_id"
            ") "
        )
        _TYPE_FILTER = "WHERE kc.trigger_type = :trigger_type "
        _BOTH_FILTER = (
            "WHERE kc.trigger_type = :trigger_type "
            "  AND EXISTS ("
            "    SELECT 1 FROM employment_assignments ea "
            "    JOIN stores s ON s.org_node_id = ea.org_node_id "
            "    WHERE ea.person_id = kc.person_id AND s.id = :store_id"
            "  ) "
        )

        if store_id and trigger_type:
            sql = _BASE + _BOTH_FILTER + _ORDER
            params: dict = {"limit": limit, "store_id": store_id, "trigger_type": trigger_type}
        elif store_id:
            sql = _BASE + _STORE_FILTER + _ORDER
            params = {"limit": limit, "store_id": store_id}
        elif trigger_type:
            sql = _BASE + _TYPE_FILTER + _ORDER
            params = {"limit": limit, "trigger_type": trigger_type}
        else:
            sql = _BASE + _ORDER
            params = {"limit": limit}

        result = await self._session.execute(sa.text(sql), params)
        rows = result.fetchall()
        return [
            {
                "id": str(row.id),
                "person_id": str(row.person_id),
                "person_name": row.person_name,
                "trigger_type": row.trigger_type,
                "quality_score": float(row.quality_score) if row.quality_score is not None else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
