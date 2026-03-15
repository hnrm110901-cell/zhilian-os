"""
工资条服务 — PDF生成 + IM推送 + 员工确认

核心功能：
- generate_payslip_data() — 从PayrollRecord + SalaryItemRecord组装工资条结构化数据
- generate_payslip_pdf() — 生成A4工资条PDF（reportlab，含降级方案）
- push_payslip_to_employee() — 通过IM推送工资条摘要到员工
- batch_push_payslips() — 批量推送全店工资条
"""
import io
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

import structlog
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class PayslipService:
    """工资条生成与推送服务"""

    def __init__(self, store_id: str, brand_id: str):
        self.store_id = store_id
        self.brand_id = brand_id

    async def generate_payslip_data(
        self, db: AsyncSession, employee_id: str, pay_month: str
    ) -> Optional[dict]:
        """
        从PayrollRecord + SalaryItemRecord组装工资条数据

        Returns: {
            "employee_name": "张三",
            "employee_id": "EMP001",
            "position": "服务员",
            "pay_month": "2026-03",
            "department": "前厅",
            "income_items": [{"name": "基本工资", "amount_yuan": 4000.00}, ...],
            "deduction_items": [{"name": "个人社保", "amount_yuan": 800.00}, ...],
            "summary": {
                "gross_yuan": 5500.00, "total_deduction_yuan": 1200.00,
                "tax_yuan": 45.00, "net_yuan": 4255.00
            },
            "attendance": {"work_days": 22, "overtime_hours": 8, "late_count": 1},
        }
        """
        from src.models.employee import Employee
        from src.models.payroll import PayrollRecord
        from src.models.salary_item import SalaryItemRecord

        # 查询员工信息
        emp_result = await db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            logger.warning("payslip.employee_not_found", employee_id=employee_id)
            return None

        # 查询月度工资单
        payroll_result = await db.execute(
            select(PayrollRecord).where(
                and_(
                    PayrollRecord.store_id == self.store_id,
                    PayrollRecord.employee_id == employee_id,
                    PayrollRecord.pay_month == pay_month,
                )
            )
        )
        payroll = payroll_result.scalar_one_or_none()
        if not payroll:
            logger.warning(
                "payslip.payroll_not_found",
                employee_id=employee_id,
                pay_month=pay_month,
            )
            return None

        # 查询薪酬项明细
        items_result = await db.execute(
            select(SalaryItemRecord).where(
                and_(
                    SalaryItemRecord.store_id == self.store_id,
                    SalaryItemRecord.employee_id == employee_id,
                    SalaryItemRecord.pay_month == pay_month,
                )
            )
        )
        salary_items = items_result.scalars().all()

        # 按分类归组
        income_items: List[Dict[str, Any]] = []
        deduction_items: List[Dict[str, Any]] = []

        for item in salary_items:
            entry = {
                "name": item.item_name,
                "amount_yuan": round(item.amount_fen / 100, 2),
            }
            if item.item_category in ("income", "subsidy"):
                income_items.append(entry)
            elif item.item_category in ("deduction", "tax"):
                deduction_items.append(entry)

        # 若没有明细记录，从PayrollRecord字段构建
        if not income_items:
            income_items = self._build_income_from_payroll(payroll)
        if not deduction_items:
            deduction_items = self._build_deduction_from_payroll(payroll)

        # 组装返回数据
        data = {
            "employee_name": employee.name,
            "employee_id": employee.id,
            "position": employee.position or "",
            "pay_month": pay_month,
            "department": "",  # 可扩展从组织架构获取
            "income_items": income_items,
            "deduction_items": deduction_items,
            "summary": {
                "gross_yuan": round(payroll.gross_salary_fen / 100, 2),
                "total_deduction_yuan": round(payroll.total_deduction_fen / 100, 2),
                "tax_yuan": round(payroll.tax_fen / 100, 2),
                "net_yuan": round(payroll.net_salary_fen / 100, 2),
            },
            "attendance": {
                "work_days": float(payroll.attendance_days or 0),
                "overtime_hours": float(payroll.overtime_hours or 0),
                "late_count": payroll.late_count or 0,
            },
        }

        logger.info(
            "payslip.data_generated",
            employee_id=employee_id,
            pay_month=pay_month,
            net_yuan=data["summary"]["net_yuan"],
        )
        return data

    def _build_income_from_payroll(self, payroll) -> List[Dict[str, Any]]:
        """从PayrollRecord字段构建收入项（无SalaryItemRecord明细时的降级方案）"""
        items = []
        field_map = [
            ("base_salary_fen", "基本工资"),
            ("position_allowance_fen", "岗位补贴"),
            ("meal_allowance_fen", "餐补"),
            ("transport_allowance_fen", "交通补贴"),
            ("performance_bonus_fen", "绩效奖金"),
            ("overtime_pay_fen", "加班费"),
            ("commission_fen", "提成"),
            ("reward_fen", "奖励"),
            ("other_bonus_fen", "其他奖金"),
        ]
        for field, name in field_map:
            val = getattr(payroll, field, 0) or 0
            if val > 0:
                items.append({"name": name, "amount_yuan": round(val / 100, 2)})
        return items

    def _build_deduction_from_payroll(self, payroll) -> List[Dict[str, Any]]:
        """从PayrollRecord字段构建扣除项"""
        items = []
        field_map = [
            ("absence_deduction_fen", "缺勤扣款"),
            ("late_deduction_fen", "迟到扣款"),
            ("penalty_fen", "罚款"),
            ("social_insurance_fen", "社保（个人）"),
            ("housing_fund_fen", "公积金（个人）"),
            ("other_deduction_fen", "其他扣款"),
        ]
        for field, name in field_map:
            val = getattr(payroll, field, 0) or 0
            if val > 0:
                items.append({"name": name, "amount_yuan": round(val / 100, 2)})
        return items

    async def generate_payslip_pdf(
        self, db: AsyncSession, employee_id: str, pay_month: str
    ) -> bytes:
        """
        生成工资条PDF
        使用 reportlab 生成简洁的A4 PDF；reportlab不可用时降级为文本格式。
        """
        data = await self.generate_payslip_data(db, employee_id, pay_month)
        if not data:
            return b""
        return self._render_pdf(data)

    def _render_pdf(self, data: dict) -> bytes:
        """使用reportlab生成PDF，不可用时降级为纯文本"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            # 尝试注册中文字体
            font_registered = False
            for font_path in [
                "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
                "/System/Library/Fonts/PingFang.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            ]:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont("ChineseFont", font_path))
                        font_registered = True
                        break
                    except Exception:
                        continue

            font_name = "ChineseFont" if font_registered else "Helvetica"

            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                topMargin=20 * mm,
                bottomMargin=15 * mm,
                leftMargin=15 * mm,
                rightMargin=15 * mm,
            )

            elements = []
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "PayslipTitle",
                parent=styles["Title"],
                fontName=font_name,
                fontSize=16,
                alignment=1,
            )
            normal_style = ParagraphStyle(
                "PayslipNormal",
                parent=styles["Normal"],
                fontName=font_name,
                fontSize=10,
            )

            # 标题
            elements.append(
                Paragraph(f"工资条 — {data['pay_month']}", title_style)
            )
            elements.append(Spacer(1, 5 * mm))

            # 员工信息
            info_data = [
                ["姓名", data.get("employee_name", ""), "工号", data.get("employee_id", "")],
                ["岗位", data.get("position", ""), "部门", data.get("department", "")],
            ]
            info_table = Table(info_data, colWidths=[60, 120, 60, 120])
            info_table.setStyle(
                TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.95)),
                    ("BACKGROUND", (2, 0), (2, -1), colors.Color(0.95, 0.95, 0.95)),
                ])
            )
            elements.append(info_table)
            elements.append(Spacer(1, 5 * mm))

            # 收入项
            income_items = data.get("income_items", [])
            if income_items:
                elements.append(Paragraph("收入项", normal_style))
                income_data = [["项目", "金额(元)"]]
                for item in income_items:
                    income_data.append([item["name"], f"¥{item['amount_yuan']:,.2f}"])
                income_table = Table(income_data, colWidths=[250, 100])
                income_table.setStyle(
                    TableStyle([
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.95, 0.9)),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ])
                )
                elements.append(income_table)
                elements.append(Spacer(1, 3 * mm))

            # 扣除项
            deduction_items = data.get("deduction_items", [])
            if deduction_items:
                elements.append(Paragraph("扣除项", normal_style))
                ded_data = [["项目", "金额(元)"]]
                for item in deduction_items:
                    ded_data.append([item["name"], f"-¥{item['amount_yuan']:,.2f}"])
                ded_table = Table(ded_data, colWidths=[250, 100])
                ded_table.setStyle(
                    TableStyle([
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.95, 0.9, 0.9)),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ])
                )
                elements.append(ded_table)
                elements.append(Spacer(1, 3 * mm))

            # 汇总
            summary = data.get("summary", {})
            summary_data = [
                ["应发工资", f"¥{summary.get('gross_yuan', 0):,.2f}"],
                ["扣除合计", f"-¥{summary.get('total_deduction_yuan', 0):,.2f}"],
                ["个人所得税", f"-¥{summary.get('tax_yuan', 0):,.2f}"],
                ["实发工资", f"¥{summary.get('net_yuan', 0):,.2f}"],
            ]
            sum_table = Table(summary_data, colWidths=[250, 100])
            sum_table.setStyle(
                TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (-2, -1), (-1, -1), colors.Color(0.85, 0.95, 0.85)),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, -1), (-1, -1), 12),
                ])
            )
            elements.append(sum_table)
            elements.append(Spacer(1, 5 * mm))

            # 考勤信息
            att = data.get("attendance", {})
            if att:
                att_data = [
                    [
                        "出勤天数", str(att.get("work_days", 0)),
                        "加班小时", str(att.get("overtime_hours", 0)),
                        "迟到次数", str(att.get("late_count", 0)),
                    ],
                ]
                att_table = Table(att_data, colWidths=[60, 50, 60, 50, 60, 50])
                att_table.setStyle(
                    TableStyle([
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ])
                )
                elements.append(att_table)

            elements.append(Spacer(1, 10 * mm))

            # 页脚
            footer_style = ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontName=font_name,
                fontSize=8,
                textColor=colors.grey,
                alignment=1,
            )
            elements.append(
                Paragraph(
                    f"本工资条由屯象OS系统自动生成 | 生成时间: "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    footer_style,
                )
            )

            doc.build(elements)
            return buf.getvalue()

        except ImportError:
            logger.warning("reportlab_not_installed, generating text payslip")
            return self._render_text_payslip(data)

    def _render_text_payslip(self, data: dict) -> bytes:
        """纯文本工资条（reportlab不可用时的降级方案）"""
        lines = []
        lines.append(f"{'=' * 50}")
        lines.append(f"工资条 — {data['pay_month']}")
        lines.append(f"{'=' * 50}")
        lines.append(
            f"姓名: {data.get('employee_name', '')}  "
            f"工号: {data.get('employee_id', '')}"
        )
        lines.append(
            f"岗位: {data.get('position', '')}  "
            f"部门: {data.get('department', '')}"
        )
        lines.append(f"{'-' * 50}")

        lines.append("【收入项】")
        for item in data.get("income_items", []):
            lines.append(f"  {item['name']:<20} ¥{item['amount_yuan']:>10,.2f}")

        lines.append("【扣除项】")
        for item in data.get("deduction_items", []):
            lines.append(f"  {item['name']:<20} -¥{item['amount_yuan']:>9,.2f}")

        lines.append(f"{'-' * 50}")
        summary = data.get("summary", {})
        lines.append(f"应发工资:  ¥{summary.get('gross_yuan', 0):>10,.2f}")
        lines.append(f"扣除合计: -¥{summary.get('total_deduction_yuan', 0):>9,.2f}")
        lines.append(f"个人所得税:-¥{summary.get('tax_yuan', 0):>9,.2f}")
        lines.append(f"{'=' * 50}")
        lines.append(f"实发工资:  ¥{summary.get('net_yuan', 0):>10,.2f}")
        lines.append(f"{'=' * 50}")
        lines.append("")
        lines.append(
            f"本工资条由屯象OS系统自动生成 | "
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        return "\n".join(lines).encode("utf-8")

    async def push_payslip_to_employee(
        self, db: AsyncSession, employee_id: str, pay_month: str
    ) -> dict:
        """
        推送工资条到员工IM
        1. 生成Markdown摘要
        2. 通过IMMessageService推送
        3. 记录推送状态到payslip_records
        """
        from src.models.employee import Employee
        from src.models.store import Store
        from src.models.payslip import PayslipRecord
        from src.services.im_message_service import IMMessageService

        # 获取员工信息
        emp_result = await db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            return {"pushed": False, "error": f"Employee {employee_id} not found"}

        im_userid = employee.wechat_userid or employee.dingtalk_userid
        push_channel = "wechat" if employee.wechat_userid else "dingtalk"
        if not im_userid:
            await self._upsert_payslip_record(
                db, employee_id, pay_month, "failed", push_channel=None,
                error="Employee has no IM binding",
            )
            return {"pushed": False, "error": "Employee has no IM binding"}

        # 获取工资条数据
        data = await self.generate_payslip_data(db, employee_id, pay_month)
        if not data:
            await self._upsert_payslip_record(
                db, employee_id, pay_month, "failed", push_channel=push_channel,
                error="No payroll data found",
            )
            return {"pushed": False, "error": "No payroll data found"}

        # 构建Markdown消息
        summary = data.get("summary", {})
        content = (
            f"### {pay_month} 工资条\n\n"
            f"**{data.get('employee_name', '')}** 您好！\n\n"
            f"- 应发工资: ¥{summary.get('gross_yuan', 0):,.2f}\n"
            f"- 扣除合计: ¥{summary.get('total_deduction_yuan', 0):,.2f}\n"
            f"- 个人所得税: ¥{summary.get('tax_yuan', 0):,.2f}\n"
            f"- **实发工资: ¥{summary.get('net_yuan', 0):,.2f}**\n\n"
            f"出勤 {data.get('attendance', {}).get('work_days', 0)} 天\n\n"
            f"如需查看详细明细，请登录屯象OS系统"
        )

        # 获取品牌ID
        store_result = await db.execute(
            select(Store.brand_id).where(Store.id == self.store_id)
        )
        brand_id = store_result.scalar_one_or_none() or self.brand_id

        # 通过IM推送
        msg_service = IMMessageService(db)
        try:
            await msg_service.send_markdown(
                brand_id, im_userid, f"{pay_month}工资条", content
            )
            await self._upsert_payslip_record(
                db, employee_id, pay_month, "sent", push_channel=push_channel,
            )
            logger.info(
                "payslip.pushed",
                employee_id=employee_id,
                pay_month=pay_month,
                channel=push_channel,
            )
            return {"pushed": True, "employee_name": data.get("employee_name")}
        except Exception as e:
            logger.warning(
                "payslip_push.failed",
                employee_id=employee_id,
                error=str(e),
            )
            await self._upsert_payslip_record(
                db, employee_id, pay_month, "failed",
                push_channel=push_channel, error=str(e)[:500],
            )
            return {"pushed": False, "error": str(e)}

    async def batch_push_payslips(
        self, db: AsyncSession, pay_month: str
    ) -> dict:
        """批量推送工资条到全店在职员工"""
        from src.models.employee import Employee

        result = await db.execute(
            select(Employee.id).where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.is_active.is_(True),
                )
            )
        )
        employee_ids = [r[0] for r in result.all()]

        pushed = 0
        errors = 0
        details: List[dict] = []
        for emp_id in employee_ids:
            res = await self.push_payslip_to_employee(db, emp_id, pay_month)
            if res.get("pushed"):
                pushed += 1
            else:
                errors += 1
            details.append({"employee_id": emp_id, **res})

        logger.info(
            "payslip.batch_push_done",
            store_id=self.store_id,
            pay_month=pay_month,
            total=len(employee_ids),
            pushed=pushed,
            errors=errors,
        )
        return {
            "total": len(employee_ids),
            "pushed": pushed,
            "errors": errors,
            "details": details,
        }

    async def confirm_payslip(
        self, db: AsyncSession, employee_id: str, pay_month: str
    ) -> dict:
        """员工确认工资条"""
        from src.models.payslip import PayslipRecord

        result = await db.execute(
            select(PayslipRecord).where(
                and_(
                    PayslipRecord.store_id == self.store_id,
                    PayslipRecord.employee_id == employee_id,
                    PayslipRecord.pay_month == pay_month,
                )
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return {"confirmed": False, "error": "Payslip record not found"}

        if record.confirmed:
            return {"confirmed": True, "already": True, "confirmed_at": str(record.confirmed_at)}

        record.confirmed = True
        record.confirmed_at = datetime.utcnow()
        await db.commit()

        logger.info(
            "payslip.confirmed",
            employee_id=employee_id,
            pay_month=pay_month,
        )
        return {"confirmed": True, "confirmed_at": str(record.confirmed_at)}

    async def get_push_status(
        self, db: AsyncSession, pay_month: str
    ) -> List[dict]:
        """查询指定月份全店推送状态"""
        from src.models.payslip import PayslipRecord
        from src.models.employee import Employee

        result = await db.execute(
            select(PayslipRecord, Employee.name).outerjoin(
                Employee, PayslipRecord.employee_id == Employee.id
            ).where(
                and_(
                    PayslipRecord.store_id == self.store_id,
                    PayslipRecord.pay_month == pay_month,
                )
            )
        )
        rows = result.all()
        return [
            {
                "employee_id": rec.employee_id,
                "employee_name": emp_name or "",
                "push_status": rec.push_status,
                "push_channel": rec.push_channel,
                "pushed_at": str(rec.pushed_at) if rec.pushed_at else None,
                "confirmed": rec.confirmed,
                "confirmed_at": str(rec.confirmed_at) if rec.confirmed_at else None,
            }
            for rec, emp_name in rows
        ]

    async def _upsert_payslip_record(
        self,
        db: AsyncSession,
        employee_id: str,
        pay_month: str,
        status: str,
        push_channel: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """创建或更新推送记录"""
        from src.models.payslip import PayslipRecord

        result = await db.execute(
            select(PayslipRecord).where(
                and_(
                    PayslipRecord.store_id == self.store_id,
                    PayslipRecord.employee_id == employee_id,
                    PayslipRecord.pay_month == pay_month,
                )
            )
        )
        record = result.scalar_one_or_none()

        if record:
            record.push_status = status
            record.push_channel = push_channel or record.push_channel
            record.push_error = error
            if status == "sent":
                record.pushed_at = datetime.utcnow()
        else:
            import uuid
            record = PayslipRecord(
                id=uuid.uuid4(),
                store_id=self.store_id,
                employee_id=employee_id,
                pay_month=pay_month,
                push_status=status,
                push_channel=push_channel,
                push_error=error,
                pushed_at=datetime.utcnow() if status == "sent" else None,
            )
            db.add(record)

        await db.commit()
