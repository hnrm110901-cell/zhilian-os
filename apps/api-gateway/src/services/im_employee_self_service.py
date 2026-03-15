"""
IM 员工自助服务 — 通过企微/钉钉消息触发业务操作

支持的命令：
- "我的排班" / "排班查询"  → 返回本周排班卡片
- "请假"                   → 引导提交请假申请
- "调班"                   → 引导提交调班申请
- "工资条" / "薪资"        → 推送加密工资条链接
- "考勤" / "打卡记录"      → 返回本月考勤统计

设计：
- 根据 IM userid 查 Employee + User
- 调用已有 Service 获取数据
- 返回格式化消息（Markdown）
"""
from typing import Any, Dict, Optional, Tuple

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

from ..models.employee import Employee
from ..models.user import User

logger = structlog.get_logger()


class IMEmployeeSelfService:
    """IM 员工自助服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle_command(
        self,
        im_userid: str,
        command: str,
        platform: str = "wechat_work",
    ) -> Dict[str, Any]:
        """
        处理员工自助命令，返回格式化的回复消息。

        Returns:
            {"type": "markdown", "title": str, "content": str}
        """
        employee, user = await self._resolve_employee(im_userid, platform)
        if not employee:
            return {
                "type": "text",
                "content": "未找到您的员工信息，请联系管理员确认通讯录同步状态。",
            }

        cmd = command.strip().lower()

        # 排班查询
        if any(k in cmd for k in ["排班", "班次", "上班"]):
            return await self._query_schedule(employee)

        # 请假
        if any(k in cmd for k in ["请假", "休假", "病假", "事假", "年假"]):
            return await self._leave_guide(employee, cmd)

        # 调班
        if any(k in cmd for k in ["调班", "换班", "代班"]):
            return await self._shift_swap_guide(employee)

        # 工资条
        if any(k in cmd for k in ["工资", "薪资", "薪酬", "工资条"]):
            return await self._payslip_info(employee)

        # 考勤
        if any(k in cmd for k in ["考勤", "打卡", "出勤", "迟到"]):
            return await self._attendance_summary(employee)

        # 个人信息
        if any(k in cmd for k in ["个人信息", "我的信息", "我是谁"]):
            return self._personal_info(employee)

        return {
            "type": "text",
            "content": (
                f"{employee.name}您好！我可以帮您：\n"
                "1. 回复「排班」查看本周排班\n"
                "2. 回复「请假」提交请假申请\n"
                "3. 回复「调班」申请调班\n"
                "4. 回复「工资条」查看薪资\n"
                "5. 回复「考勤」查看出勤记录\n"
                "6. 回复「个人信息」查看档案"
            ),
        }

    async def _resolve_employee(
        self, im_userid: str, platform: str
    ) -> Tuple[Optional[Employee], Optional[User]]:
        """根据 IM userid 查找 Employee + User"""
        if platform == "wechat_work":
            emp_result = await self.db.execute(
                select(Employee).where(Employee.wechat_userid == im_userid)
            )
        else:
            emp_result = await self.db.execute(
                select(Employee).where(Employee.dingtalk_userid == im_userid)
            )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            return None, None

        # 查对应 User
        if platform == "wechat_work":
            user_result = await self.db.execute(
                select(User).where(User.wechat_user_id == im_userid)
            )
        else:
            user_result = await self.db.execute(
                select(User).where(User.dingtalk_user_id == im_userid)
            )
        user = user_result.scalar_one_or_none()
        return employee, user

    async def _query_schedule(self, employee: Employee) -> Dict[str, Any]:
        """查询本周排班"""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        try:
            from ..models.schedule import Schedule
            result = await self.db.execute(
                select(Schedule).where(
                    and_(
                        Schedule.employee_id == employee.id,
                        Schedule.date >= week_start,
                        Schedule.date <= week_end,
                    )
                ).order_by(Schedule.date)
            )
            schedules = result.scalars().all()

            if not schedules:
                return {
                    "type": "markdown",
                    "title": "本周排班",
                    "content": (
                        f"### 本周排班 ({week_start} ~ {week_end})\n\n"
                        f"**{employee.name}** 本周暂无排班记录。\n\n"
                        f"如有疑问请联系您的店长。"
                    ),
                }

            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            lines = []
            for s in schedules:
                day_name = weekday_names[s.date.weekday()]
                shift_info = getattr(s, 'shift_type', '') or getattr(s, 'shift_name', '') or '排班'
                start_time = getattr(s, 'start_time', '') or ''
                end_time = getattr(s, 'end_time', '') or ''
                time_str = f"{start_time}-{end_time}" if start_time else ""
                is_today = "**今日**" if s.date == today else ""
                lines.append(f"- {s.date} {day_name} {is_today} | {shift_info} {time_str}")

            content = (
                f"### 本周排班 ({week_start} ~ {week_end})\n\n"
                + "\n".join(lines) + "\n\n"
                f"如需调班，请回复「调班」。"
            )
            return {"type": "markdown", "title": "本周排班", "content": content}

        except Exception as e:
            logger.warning("im_self_service.schedule_query_failed", error=str(e))
            return {
                "type": "text",
                "content": f"{employee.name}，排班查询暂时不可用，请稍后再试。",
            }

    async def _leave_guide(self, employee: Employee, cmd: str) -> Dict[str, Any]:
        """请假引导"""
        leave_types = {
            "病假": "sick_leave",
            "事假": "personal_leave",
            "年假": "annual_leave",
            "婚假": "marriage_leave",
            "产假": "maternity_leave",
        }

        detected_type = None
        for name, code in leave_types.items():
            if name in cmd:
                detected_type = name
                break

        content = f"### 请假申请\n\n**{employee.name}**，请通过以下方式提交请假：\n\n"

        if detected_type:
            content += f"检测到您要请 **{detected_type}**\n\n"

        content += (
            "1. 登录屯象OS系统 → 假勤管理 → 新建请假\n"
            "2. 或直接联系您的店长代为提交\n\n"
            "**假期类型**：事假 / 病假 / 年假 / 婚假 / 产假\n\n"
            "提交后将自动通知您的店长审批。"
        )

        return {"type": "markdown", "title": "请假申请", "content": content}

    async def _shift_swap_guide(self, employee: Employee) -> Dict[str, Any]:
        """调班引导"""
        content = (
            f"### 调班申请\n\n"
            f"**{employee.name}**，调班流程：\n\n"
            f"1. 先与同事协商确认可互换班次\n"
            f"2. 登录屯象OS → 排班管理 → 申请调班\n"
            f"3. 填写调换日期、班次、互换同事\n"
            f"4. 等待店长审批\n\n"
            f"审批通过后排班将自动更新。"
        )
        return {"type": "markdown", "title": "调班申请", "content": content}

    async def _payslip_info(self, employee: Employee) -> Dict[str, Any]:
        """工资条信息"""
        today = date.today()
        if today.day < 10:
            month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y年%m月")
        else:
            month = today.strftime("%Y年%m月")

        content = (
            f"### {month} 工资条\n\n"
            f"**{employee.name}**，为保护您的隐私，"
            f"工资条详情需登录系统查看：\n\n"
            f"1. 登录屯象OS → 薪酬管理 → 我的工资条\n"
            f"2. 身份验证后可查看完整明细\n\n"
            f"如有薪资疑问，请联系HR。"
        )
        return {"type": "markdown", "title": "工资条查询", "content": content}

    async def _attendance_summary(self, employee: Employee) -> Dict[str, Any]:
        """考勤统计"""
        today = date.today()
        month_start = today.replace(day=1)

        try:
            from ..models.hr_attendance import AttendanceRecord
            result = await self.db.execute(
                select(AttendanceRecord).where(
                    and_(
                        AttendanceRecord.employee_id == employee.id,
                        AttendanceRecord.attendance_date >= month_start,
                        AttendanceRecord.attendance_date <= today,
                    )
                )
            )
            records = result.scalars().all()

            total = len(records)
            present = sum(1 for r in records if getattr(r, 'status', '') in ('present', 'normal'))
            late = sum(1 for r in records if getattr(r, 'status', '') == 'late')
            absent = sum(1 for r in records if getattr(r, 'status', '') == 'absent')
            leave = sum(1 for r in records if getattr(r, 'status', '') == 'leave')

            content = (
                f"### {today.strftime('%Y年%m月')} 考勤统计\n\n"
                f"**{employee.name}**\n\n"
                f"- 应出勤：{total} 天\n"
                f"- 正常：{present} 天\n"
                f"- 迟到：{late} 次\n"
                f"- 缺勤：{absent} 天\n"
                f"- 请假：{leave} 天\n\n"
                f"详细记录请登录系统查看。"
            )
            return {"type": "markdown", "title": "考勤统计", "content": content}

        except Exception as e:
            logger.warning("im_self_service.attendance_failed", error=str(e))
            return {
                "type": "text",
                "content": f"{employee.name}，考勤数据查询暂时不可用，请稍后再试。",
            }

    def _personal_info(self, employee: Employee) -> Dict[str, Any]:
        """个人信息"""
        content = (
            f"### 个人信息\n\n"
            f"**姓名**：{employee.name}\n\n"
            f"**工号**：{employee.id}\n\n"
            f"**岗位**：{employee.position or '-'}\n\n"
            f"**门店**：{employee.store_id}\n\n"
            f"**入职日期**：{employee.hire_date or '-'}\n\n"
            f"**状态**：{'在职' if employee.is_active else '离职'}\n\n"
            f"**手机**：{employee.phone or '-'}\n\n"
            f"如需修改个人信息，请联系HR。"
        )
        return {"type": "markdown", "title": "个人信息", "content": content}
