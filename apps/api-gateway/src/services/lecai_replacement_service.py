"""
LeCaiReplacementService — 乐才平替聚合服务

核心理念：乐才告诉你昨天用了多少人工成本；
屯象OS告诉你明天少排1个人能多赚多少钱。

本服务将考勤+排班+薪酬+审批+成长整合为统一的员工自助查询入口，
是对乐才（合规管理工具）的全面平替 + 经营决策增强。

乐才功能覆盖清单（按优先级）：
✅ P0 员工花名册/档案（Person + EmploymentAssignment）
✅ P0 考勤管理（AttendanceService）
✅ P0 排班管理（ScheduleService + WorkforceService）
✅ P0 假勤管理（LeaveService）
✅ P0 薪酬核算（PayrollService + TaxService + SocialInsuranceService）
✅ P1 审批流（ApprovalWorkflowService）
✅ P1 培训管理（TrainingService）
✅ P1 绩效考核（PerformanceAgent）
✅ P2 员工自助（本服务新增）
✅ P2 成长旅程（MissionJourneyService — 屯象独有）
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class LeCaiReplacementService:
    """乐才平替聚合服务 — 员工自助门户数据层"""

    # ── 员工自助：我的概览 ────────────────────────────

    @staticmethod
    async def get_my_overview(
        db: AsyncSession,
        person_id: uuid.UUID,
        month: Optional[str] = None,
    ) -> dict:
        """员工自助门户首页概览

        一次调用返回员工当月核心数据：
        - 基本信息
        - 本月考勤摘要
        - 本月薪资（如已发放）
        - 假期余额
        - 当前排班
        - 成长旅程进度

        Args:
            person_id: Person UUID
            month: YYYY-MM 格式，默认当月
        """
        from src.models.hr.person import Person

        if not month:
            month = date.today().strftime("%Y-%m")

        # 1. 基本信息
        person = await db.get(Person, person_id)
        if not person:
            return {"error": "员工不存在"}

        profile = {
            "person_id": str(person_id),
            "name": person.name,
            "phone": person.phone,
            "career_stage": person.career_stage,
            "store_id": person.store_id,
            "photo_url": person.photo_url,
            "is_active": person.is_active,
        }

        # 2. 考勤摘要（查 daily_attendance_records）
        attendance = await _get_attendance_summary(db, person_id, month)

        # 3. 薪资信息（查 payroll_items）
        payroll = await _get_payroll_summary(db, person_id, month)

        # 4. 假期余额（查 leave_balances）
        leave = await _get_leave_balance(db, person_id)

        # 5. 成长旅程（查 mj_employee_journeys）
        journey = await _get_journey_summary(db, person_id)

        return {
            "profile": profile,
            "attendance": attendance,
            "payroll": payroll,
            "leave": leave,
            "journey": journey,
            "month": month,
        }

    # ── 员工自助：我的考勤明细 ────────────────────────

    @staticmethod
    async def get_my_attendance(
        db: AsyncSession,
        person_id: uuid.UUID,
        month: str,
    ) -> dict:
        """获取员工月度考勤明细"""
        return await _get_attendance_summary(db, person_id, month)

    # ── 员工自助：我的薪资条 ──────────────────────────

    @staticmethod
    async def get_my_payslip(
        db: AsyncSession,
        person_id: uuid.UUID,
        month: str,
    ) -> dict:
        """获取员工薪资条详情"""
        return await _get_payroll_summary(db, person_id, month)

    # ── 员工自助：我的排班 ────────────────────────────

    @staticmethod
    async def get_my_schedule(
        db: AsyncSession,
        person_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """获取员工排班信息"""
        try:
            from src.models.schedule import Schedule
            result = await db.execute(
                select(Schedule).where(
                    and_(
                        Schedule.employee_id == str(person_id),
                        Schedule.date >= start_date,
                        Schedule.date <= end_date,
                    )
                ).order_by(Schedule.date)
            )
            schedules = result.scalars().all()
            return [
                {
                    "date": str(s.date),
                    "shift_name": getattr(s, "shift_name", None),
                    "start_time": str(getattr(s, "start_time", "")),
                    "end_time": str(getattr(s, "end_time", "")),
                    "status": getattr(s, "status", "scheduled"),
                }
                for s in schedules
            ]
        except Exception as e:
            logger.warning("排班查询降级", error=str(e))
            return []

    # ── 乐才对标功能矩阵 ──────────────────────────────

    @staticmethod
    def get_feature_matrix() -> dict:
        """返回乐才 vs 屯象OS功能对标矩阵

        用于商务演示和客户沟通。
        """
        return {
            "comparison_date": date.today().isoformat(),
            "categories": [
                {
                    "name": "人员档案管理",
                    "lecai": "基础花名册",
                    "tunxiang": "Person三层架构(档案→在岗→合同) + 跨门店唯一身份",
                    "advantage": "tunxiang",
                    "detail": "支持正式/小时工/外包/派遣/合伙人多种用工类型",
                },
                {
                    "name": "考勤管理",
                    "lecai": "打卡记录 + 月报",
                    "tunxiang": "多班次 + GPS围栏 + 异常自动检测 + 企微打卡同步",
                    "advantage": "tunxiang",
                    "detail": "凌晨2-3点餐饮特殊时段处理",
                },
                {
                    "name": "排班管理",
                    "lecai": "手动排班 + 模板",
                    "tunxiang": "AI客流预测→人力需求→排班建议→成本分析→采纳追踪",
                    "advantage": "tunxiang",
                    "detail": "每天少排1人可节省¥180-300",
                },
                {
                    "name": "薪酬核算",
                    "lecai": "基础工资计算",
                    "tunxiang": "4种薪酬类型 + 累计预扣个税 + 长沙社保费率 + 公式引擎",
                    "advantage": "equal",
                    "detail": "支持月薪/日薪/时薪/计件",
                },
                {
                    "name": "假勤管理",
                    "lecai": "请假/加班审批",
                    "tunxiang": "假期余额 + 多级审批 + 代班/换班",
                    "advantage": "equal",
                    "detail": "完整的请假→审批→扣薪链路",
                },
                {
                    "name": "审批流",
                    "lecai": "基础审批",
                    "tunxiang": "多级路由 + 金额阈梯 + 委托 + 超期自动升级",
                    "advantage": "tunxiang",
                    "detail": "审批模板可配置化",
                },
                {
                    "name": "培训管理",
                    "lecai": "培训记录",
                    "tunxiang": "完整链路:课程→报名→考试→学分→证书 + AI推荐",
                    "advantage": "tunxiang",
                    "detail": "TrainingAgent智能推荐学习路径",
                },
                {
                    "name": "绩效考核",
                    "lecai": "KPI打分",
                    "tunxiang": "PerformanceAgent + 360度评估 + OKR对齐",
                    "advantage": "tunxiang",
                    "detail": "自动对标行业P50/P90",
                },
                {
                    "name": "员工成长",
                    "lecai": "无",
                    "tunxiang": "使命旅程引擎 + 技能矩阵 + 职业路径 + 里程碑 + 幸福指数",
                    "advantage": "tunxiang_unique",
                    "detail": "屯象独有：五级工匠体系 + 成长叙事 + 文化墙",
                },
                {
                    "name": "离职风险预测",
                    "lecai": "无",
                    "tunxiang": "ML模型 + 留任策略推荐",
                    "advantage": "tunxiang_unique",
                    "detail": "提前30天预警，留住核心员工",
                },
                {
                    "name": "人力成本决策",
                    "lecai": "事后报表",
                    "tunxiang": "事前预测 + 主动推送 + 一键确认 + ¥节省计算",
                    "advantage": "tunxiang_unique",
                    "detail": "每日07:00推送明日人力建议",
                },
            ],
            "summary": {
                "lecai_features": 7,
                "tunxiang_features": 11,
                "tunxiang_unique": 3,
                "tunxiang_advantage": 6,
                "equal": 2,
                "conclusion": "屯象OS完全覆盖乐才所有功能，并在排班AI、成长旅程、风险预测方面具有独有优势",
            },
        }


# ── 内部查询函数 ──────────────────────────────────────


async def _get_attendance_summary(
    db: AsyncSession, person_id: uuid.UUID, month: str,
) -> dict:
    """考勤月度摘要"""
    try:
        from src.models.hr.daily_attendance import DailyAttendanceRecord
        year, mon = month.split("-")
        start = date(int(year), int(mon), 1)
        if int(mon) == 12:
            end = date(int(year) + 1, 1, 1)
        else:
            end = date(int(year), int(mon) + 1, 1)

        result = await db.execute(
            select(DailyAttendanceRecord).where(
                and_(
                    DailyAttendanceRecord.person_id == person_id,
                    DailyAttendanceRecord.work_date >= start,
                    DailyAttendanceRecord.work_date < end,
                )
            )
        )
        records = result.scalars().all()

        normal = sum(1 for r in records if getattr(r, "status", "") == "normal")
        late = sum(1 for r in records if getattr(r, "status", "") == "late")
        absent = sum(1 for r in records if getattr(r, "status", "") == "absent")
        ot_hours = sum(getattr(r, "overtime_hours", 0) or 0 for r in records)

        return {
            "month": month,
            "total_days": len(records),
            "normal_days": normal,
            "late_days": late,
            "absent_days": absent,
            "overtime_hours": round(ot_hours, 1),
        }
    except Exception as e:
        logger.warning("考勤查询降级", error=str(e))
        return {"month": month, "total_days": 0, "note": "考勤数据暂未同步"}


async def _get_payroll_summary(
    db: AsyncSession, person_id: uuid.UUID, month: str,
) -> dict:
    """薪资摘要"""
    try:
        from src.models.hr.payroll_item import PayrollItem
        result = await db.execute(
            select(PayrollItem).where(
                and_(
                    PayrollItem.person_id == person_id,
                    PayrollItem.period == month,
                )
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return {"month": month, "status": "未生成"}

        return {
            "month": month,
            "status": getattr(item, "status", "draft"),
            "base_salary_yuan": round(getattr(item, "base_salary_fen", 0) / 100, 2),
            "overtime_yuan": round(getattr(item, "overtime_fen", 0) / 100, 2),
            "bonus_yuan": round(getattr(item, "bonus_fen", 0) / 100, 2),
            "deductions_yuan": round(getattr(item, "deductions_fen", 0) / 100, 2),
            "social_insurance_yuan": round(getattr(item, "social_insurance_fen", 0) / 100, 2),
            "tax_yuan": round(getattr(item, "tax_fen", 0) / 100, 2),
            "net_pay_yuan": round(getattr(item, "net_pay_fen", 0) / 100, 2),
        }
    except Exception as e:
        logger.warning("薪资查询降级", error=str(e))
        return {"month": month, "status": "查询降级", "note": str(e)}


async def _get_leave_balance(
    db: AsyncSession, person_id: uuid.UUID,
) -> dict:
    """假期余额"""
    try:
        from src.models.leave import LeaveBalance
        result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == str(person_id),
            )
        )
        balances = result.scalars().all()
        return {
            "balances": [
                {
                    "leave_type": getattr(b, "leave_type", ""),
                    "total_days": getattr(b, "total_days", 0),
                    "used_days": getattr(b, "used_days", 0),
                    "remaining_days": getattr(b, "remaining_days", 0),
                }
                for b in balances
            ]
        }
    except Exception as e:
        logger.warning("假期余额查询降级", error=str(e))
        return {"balances": [], "note": "假期数据暂未同步"}


async def _get_journey_summary(
    db: AsyncSession, person_id: uuid.UUID,
) -> dict:
    """成长旅程摘要"""
    try:
        from src.models.mission_journey import EmployeeJourney, JourneyStatus
        result = await db.execute(
            select(EmployeeJourney).where(
                and_(
                    EmployeeJourney.person_id == person_id,
                    EmployeeJourney.status == JourneyStatus.IN_PROGRESS,
                )
            )
        )
        journeys = result.scalars().all()
        return {
            "active_journeys": len(journeys),
            "journeys": [
                {
                    "name": j.current_stage_name,
                    "progress_pct": float(j.progress_pct or 0),
                    "achieved_milestones": j.achieved_milestones,
                    "total_milestones": j.total_milestones,
                }
                for j in journeys
            ],
        }
    except Exception as e:
        logger.warning("旅程查询降级", error=str(e))
        return {"active_journeys": 0, "journeys": []}
