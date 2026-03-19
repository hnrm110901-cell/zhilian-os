"""
DailySettlementService — 门店日结单服务
负责日结状态流转、说明提交、审核闭环。
"""
import uuid
from datetime import date, datetime
from typing import Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.daily_settlement import StoreDailySettlement

logger = structlog.get_logger()


def _gen_settlement_no(store_id: str, biz_date) -> str:
    """生成日结单号：DS{yyyyMMdd}{storeId后6位}"""
    date_str = str(biz_date).replace("-", "")
    suffix = store_id[-6:] if len(store_id) >= 6 else store_id
    return f"DS{date_str}{suffix.upper()}"


class DailySettlementService:
    """门店日结单服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self, store_id: str, biz_date: date) -> StoreDailySettlement:
        """获取或初始化当日日结单"""
        result = await self.db.execute(
            select(StoreDailySettlement).where(
                and_(
                    StoreDailySettlement.store_id == store_id,
                    StoreDailySettlement.biz_date == str(biz_date),
                )
            )
        )
        s = result.scalar_one_or_none()
        if not s:
            s = StoreDailySettlement(
                id=uuid.uuid4(),
                store_id=store_id,
                biz_date=str(biz_date),
                settlement_no=_gen_settlement_no(store_id, biz_date),
                status="pending_confirm",
            )
            self.db.add(s)
            await self.db.commit()
            await self.db.refresh(s)
        return s

    async def get_by_settlement_no(self, settlement_no: str) -> Optional[StoreDailySettlement]:
        result = await self.db.execute(
            select(StoreDailySettlement).where(
                StoreDailySettlement.settlement_no == settlement_no
            )
        )
        return result.scalar_one_or_none()

    async def update_warning_info(
        self,
        store_id: str,
        biz_date: date,
        warning_level: str,
        warning_count: int,
        major_issue_types: list,
        auto_summary: str,
    ) -> None:
        """规则引擎完成后更新日结单预警摘要"""
        s = await self.get_or_create(store_id, biz_date)
        s.warning_level = warning_level
        s.warning_count = warning_count
        s.major_issue_types = major_issue_types
        s.auto_summary = auto_summary
        # 有红黄灯 → 必须说明
        if warning_level in ("red", "yellow") and warning_count > 0:
            s.status = "abnormal_wait_comment"
        else:
            s.status = "pending_confirm"
        await self.db.commit()

    async def submit(
        self,
        store_id: str,
        biz_date: date,
        submitted_by: str,
        manager_comment: str,
        chef_comment: Optional[str],
        next_day_action_plan: str,
        next_day_focus_targets: Optional[dict] = None,
    ) -> StoreDailySettlement:
        """店长提交日结"""
        s = await self.get_or_create(store_id, biz_date)

        # 状态机校验：只有 pending_confirm / abnormal_wait_comment / returned 状态可以提交
        allowed = {"pending_confirm", "abnormal_wait_comment", "returned"}
        if s.status not in allowed:
            raise ValueError(f"当前状态 [{s.status}] 不允许提交，允许状态：{allowed}")

        s.manager_comment = manager_comment
        s.chef_comment = chef_comment
        s.next_day_action_plan = next_day_action_plan
        s.next_day_focus_targets = next_day_focus_targets
        s.submitted_by = submitted_by
        s.submitted_at = datetime.utcnow()
        s.status = "pending_review"
        await self.db.commit()
        await self.db.refresh(s)
        return s

    async def review(
        self,
        settlement_no: str,
        reviewed_by: str,
        action: str,
        review_comment: str,
        returned_reason: Optional[str] = None,
    ) -> StoreDailySettlement:
        """区域经理审核日结（approve / return）"""
        s = await self.get_by_settlement_no(settlement_no)
        if not s:
            raise ValueError(f"日结单 [{settlement_no}] 不存在")
        if s.status != "pending_review":
            raise ValueError(f"当前状态 [{s.status}] 不允许审核")

        s.reviewed_by = reviewed_by
        s.reviewed_at = datetime.utcnow()
        s.review_comment = review_comment

        if action == "approve":
            s.status = "approved"
        elif action == "return":
            s.status = "returned"
            s.returned_reason = returned_reason or review_comment
        else:
            raise ValueError(f"无效审核动作：{action}")

        await self.db.commit()
        await self.db.refresh(s)
        return s

    def to_api_dict(self, s: StoreDailySettlement) -> dict:
        return {
            "settlementNo": s.settlement_no,
            "storeId": s.store_id,
            "bizDate": s.biz_date,
            "status": s.status,
            "warningLevel": s.warning_level,
            "warningCount": s.warning_count,
            "majorIssueTypes": s.major_issue_types or [],
            "autoSummary": s.auto_summary,
            "managerComment": s.manager_comment,
            "chefComment": s.chef_comment,
            "financeComment": s.finance_comment,
            "nextDayActionPlan": s.next_day_action_plan,
            "nextDayFocusTargets": s.next_day_focus_targets,
            "submittedBy": s.submitted_by,
            "submittedAt": s.submitted_at.isoformat() if s.submitted_at else None,
            "reviewedBy": s.reviewed_by,
            "reviewedAt": s.reviewed_at.isoformat() if s.reviewed_at else None,
            "reviewComment": s.review_comment,
        }
