"""
Payroll Service — 薪酬计算引擎
核心功能：月度算薪、个税累计预扣法、考勤扣款计算
支持两种计算模式：
  1. 标准模式：基于HRRuleEngine三级级联规则
  2. 公式引擎模式：当品牌配置了SalaryItemDefinition时自动切换
"""

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.attendance import AttendanceLog
from src.models.commission import CommissionRecord
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.payroll import PayrollRecord, PayrollStatus, SalaryStructure, TaxDeclaration, TaxStatus
from src.models.reward_penalty import RewardPenaltyRecord, RewardPenaltyStatus, RewardPenaltyType
from src.models.salary_item import SalaryItemDefinition
from src.models.social_insurance import EmployeeSocialInsurance, SocialInsuranceConfig
from src.models.store import Store
from src.services.base_service import BaseService
from src.services.hr_rule_engine import HRRuleEngine
from src.services.salary_formula_engine import SalaryFormulaEngine

logger = structlog.get_logger()

# ── 个税税率表（7级超额累进） ──────────────────────────────
# 年度累计应纳税所得额区间（元）→ 税率、速算扣除数（元）
TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float("inf"), 0.45, 181920),
]

# 每月基本减除费用（元）
MONTHLY_EXEMPTION_YUAN = 5000


def _compute_tax_yuan(cumulative_taxable_income_yuan: float) -> tuple:
    """
    根据累计应纳税所得额（元），计算累计应纳税额。
    返回 (累计税额元, 税率, 速算扣除数元)
    """
    if cumulative_taxable_income_yuan <= 0:
        return (0.0, 0.0, 0)
    for upper, rate, quick_deduction in TAX_BRACKETS:
        if cumulative_taxable_income_yuan <= upper:
            tax = cumulative_taxable_income_yuan * rate - quick_deduction
            return (max(0.0, tax), rate, quick_deduction)
    # 不应到达这里
    rate = 0.45
    quick_deduction = 181920
    tax = cumulative_taxable_income_yuan * rate - quick_deduction
    return (max(0.0, tax), rate, quick_deduction)


class PayrollService(BaseService):
    """薪酬计算服务"""

    async def get_salary_structure(self, db: AsyncSession, employee_id: str) -> Optional[SalaryStructure]:
        """获取员工当前生效的薪资方案"""
        result = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_id == employee_id,
                    SalaryStructure.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def upsert_salary_structure(self, db: AsyncSession, data: Dict[str, Any]) -> SalaryStructure:
        """创建或更新薪资方案（自动停用旧方案）"""
        employee_id = data["employee_id"]

        # 停用旧方案
        old = await self.get_salary_structure(db, employee_id)
        if old:
            old.is_active = False
            old.expire_date = date.today()

        structure = SalaryStructure(
            store_id=data.get("store_id") or self.store_id,
            employee_id=employee_id,
            salary_type=data.get("salary_type", "monthly"),
            base_salary_fen=data.get("base_salary_fen", 0),
            position_allowance_fen=data.get("position_allowance_fen", 0),
            meal_allowance_fen=data.get("meal_allowance_fen", 0),
            transport_allowance_fen=data.get("transport_allowance_fen", 0),
            hourly_rate_fen=data.get("hourly_rate_fen"),
            performance_coefficient=data.get("performance_coefficient", 1.0),
            social_insurance_fen=data.get("social_insurance_fen", 0),
            housing_fund_fen=data.get("housing_fund_fen", 0),
            special_deduction_fen=data.get("special_deduction_fen", 0),
            effective_date=data.get("effective_date", date.today()),
            approved_by=data.get("approved_by"),
            remark=data.get("remark"),
        )
        db.add(structure)
        await db.flush()
        logger.info("salary_structure_upserted", employee_id=employee_id)
        return structure

    async def _has_salary_item_definitions(self, db: AsyncSession, brand_id: str) -> bool:
        """检查品牌是否配置了薪酬项定义（决定使用公式引擎还是标准模式）"""
        result = await db.execute(
            select(SalaryItemDefinition.id)
            .where(
                and_(
                    SalaryItemDefinition.brand_id == brand_id,
                    SalaryItemDefinition.is_active.is_(True),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_brand_id(self, db: AsyncSession, store_id: str) -> str:
        """从门店ID获取品牌ID"""
        result = await db.execute(select(Store.brand_id).where(Store.id == store_id))
        brand_id = result.scalar_one_or_none()
        if not brand_id:
            raise ValueError(f"门店 {store_id} 不存在或未关联品牌")
        return brand_id

    async def _resolve_rules(
        self,
        db: AsyncSession,
        position: Optional[str],
        employment_type: str,
        seniority_months: int,
        store_id: str,
        brand_id: str,
        attendance_days: int,
    ) -> Dict[str, Any]:
        """
        通过HRRuleEngine三级级联查询所有适用的业务规则。
        返回解析后的规则值字典，同时作为 rule_snapshot 存入工资单。
        """
        engine = HRRuleEngine(brand_id=brand_id, store_id=store_id)

        # 考勤扣款规则
        late_deduction_per_time = await engine.get_late_deduction_fen(db, position, employment_type)
        absent_deduction_per_day = await engine.get_absent_deduction_fen(db, position, employment_type)
        early_leave_deduction_per_time = await engine.get_early_leave_deduction_fen(db, position, employment_type)

        # 加班倍数
        overtime_rates = await engine.get_overtime_rates(db, position)
        seniority_subsidy = await engine.get_seniority_subsidy_fen(db, seniority_months, position)

        # 全勤奖
        full_attendance_bonus = await engine.get_full_attendance_bonus_fen(db, position)

        # 餐补（按出勤天数计算）
        meal_subsidy = await engine.get_meal_subsidy_fen(db, attendance_days, position)

        # 岗位津贴
        position_allowance = 0
        if position:
            position_allowance = await engine.get_position_allowance_fen(db, position)

        return {
            "late_deduction_per_time_fen": late_deduction_per_time,
            "absent_deduction_per_day_fen": absent_deduction_per_day,
            "early_leave_deduction_per_time_fen": early_leave_deduction_per_time,
            "overtime_rates": overtime_rates,
            "seniority_months": seniority_months,
            "seniority_subsidy_fen": seniority_subsidy,
            "full_attendance_bonus_fen": full_attendance_bonus,
            "meal_subsidy_fen": meal_subsidy,
            "position_allowance_fen": position_allowance,
            "brand_id": brand_id,
            "store_id": store_id,
            "position": position,
            "employment_type": employment_type,
            "resolved_at": datetime.utcnow().isoformat(),
        }

    async def calculate_payroll(self, db: AsyncSession, employee_id: str, pay_month: str) -> PayrollRecord:
        """
        为员工计算指定月份工资。
        pay_month 格式: "YYYY-MM"

        计算流程:
        1. 读取薪资方案 + 员工信息
        2. 判断是否使用公式引擎模式
        3. 查询考勤数据 → 计算出勤天数、迟到、加班
        4. 通过HRRuleEngine解析业务规则
        5. 计算应发工资（使用规则值替代硬编码）
        6. 计算扣款（缺勤、迟到、早退、社保、个税）
        7. 生成工资单 + 规则快照
        """
        store_id = self.require_store_id()

        # 1. 获取薪资方案
        structure = await self.get_salary_structure(db, employee_id)
        if not structure:
            raise ValueError(f"员工 {employee_id} 无生效薪资方案")

        # 获取员工信息（Person + EmploymentAssignment）
        person_result = await db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            raise ValueError(f"员工 {employee_id} 不存在")

        assign_result = await db.execute(
            select(EmploymentAssignment)
            .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
            .order_by(EmploymentAssignment.start_date.asc())
            .limit(1)
        )
        assignment = assign_result.scalar_one_or_none()
        position = assignment.position if assignment else None
        employment_type = assignment.employment_type if assignment else "full_time"
        seniority_months = (
            (date.today() - assignment.start_date).days // 30
            if (assignment and assignment.start_date)
            else 0
        )

        # 获取品牌ID
        brand_id = await self._get_brand_id(db, store_id)

        # 2. 检查是否使用公式引擎模式
        if await self._has_salary_item_definitions(db, brand_id):
            return await self._calculate_with_formula_engine(db, employee_id, structure, pay_month, store_id, brand_id)

        # 3. 标准模式：查询考勤
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        work_days_in_month = _count_work_days(year, month)

        attendance = await self._get_attendance_summary(db, employee_id, month_start, month_end)

        # 4. 通过HRRuleEngine解析业务规则
        rules = await self._resolve_rules(
            db,
            position=position,
            employment_type=employment_type,
            seniority_months=seniority_months,
            store_id=store_id,
            brand_id=brand_id,
            attendance_days=attendance.get("attendance_days", 0),
        )

        # 5. 计算应发
        base = structure.base_salary_fen

        # 岗位津贴：优先使用规则引擎的值，兜底用薪资方案固定值
        rule_position_allowance = rules["position_allowance_fen"]
        position = rule_position_allowance if rule_position_allowance > 0 else structure.position_allowance_fen

        # 餐补：优先使用规则引擎按出勤天数计算的值，兜底用薪资方案固定值
        rule_meal = rules["meal_subsidy_fen"]
        meal = rule_meal if rule_meal > 0 else structure.meal_allowance_fen

        transport = structure.transport_allowance_fen

        # 工龄补贴（从规则引擎获取）
        seniority_subsidy = rules["seniority_subsidy_fen"]

        # 绩效奖金 = 基本工资 × (绩效系数 - 1)，系数>1才有奖金
        perf_coeff = float(structure.performance_coefficient or 1.0)
        performance_bonus = int(base * max(0, perf_coeff - 1))

        # 加班费 = 时薪 × 加班倍数 × 加班小时数（使用规则引擎的倍数）
        hourly_rate = structure.hourly_rate_fen or (int(base / work_days_in_month / 8) if work_days_in_month > 0 else 0)
        overtime_rate = rules["overtime_rates"].get("weekday", 1.5)
        overtime_pay = int(hourly_rate * overtime_rate * float(attendance.get("overtime_hours", 0)))

        # 提成合计
        commission_total = await self._get_commission_total(db, employee_id, pay_month)

        # 奖惩合计（已审批）
        reward_total, penalty_total = await self._get_reward_penalty_totals(db, employee_id, pay_month)

        # 全勤奖（从规则引擎获取）
        full_attendance_bonus = 0
        if (
            attendance.get("absence_days", 0) == 0
            and attendance.get("late_count", 0) == 0
            and attendance.get("early_leave_count", 0) == 0
        ):
            full_attendance_bonus = rules["full_attendance_bonus_fen"]

        gross = (
            base
            + position
            + meal
            + transport
            + seniority_subsidy
            + performance_bonus
            + overtime_pay
            + commission_total
            + reward_total
            + full_attendance_bonus
        )

        # 6. 计算扣款（使用规则引擎的扣款金额）
        # 缺勤扣款 = 日薪 × 缺勤天数
        daily_rate = int(base / work_days_in_month) if work_days_in_month > 0 else 0
        absence_days = float(attendance.get("absence_days", 0))
        absence_deduction = int(daily_rate * absence_days)

        # 迟到扣款（使用规则引擎的每次扣款金额）
        late_count = attendance.get("late_count", 0)
        late_deduction = late_count * rules["late_deduction_per_time_fen"]

        # 早退扣款（使用规则引擎的每次扣款金额）
        early_leave_count = attendance.get("early_leave_count", 0)
        early_leave_deduction = early_leave_count * rules["early_leave_deduction_per_time_fen"]

        # 社保公积金（优先使用个性化配置，兜底用薪资方案固定值）
        social, housing = await self._calculate_social_insurance(db, employee_id, year, structure)

        # 个税计算（应税收入 = 应发 - 缺勤扣 - 迟到扣 - 早退扣 - 罚款）
        taxable_gross = gross - absence_deduction - late_deduction - early_leave_deduction - penalty_total
        tax_fen = await self._calculate_monthly_tax(
            db,
            employee_id,
            pay_month,
            max(0, taxable_gross),
            social,
            housing,
            structure.special_deduction_fen,
        )

        total_deduction = (
            absence_deduction + late_deduction + early_leave_deduction + penalty_total + social + housing + tax_fen
        )
        net = gross - total_deduction

        # 7. 写入工资单
        # 检查是否已存在
        existing = await db.execute(
            select(PayrollRecord).where(
                and_(
                    PayrollRecord.employee_id == employee_id,
                    PayrollRecord.pay_month == pay_month,
                )
            )
        )
        record = existing.scalar_one_or_none()
        if record and record.status in (PayrollStatus.PAID, PayrollStatus.CONFIRMED):
            raise ValueError(f"员工 {employee_id} {pay_month} 工资单已确认/已发放，不可重算")

        if not record:
            record = PayrollRecord(store_id=store_id, employee_id=employee_id, pay_month=pay_month)
            db.add(record)

        record.base_salary_fen = base
        record.position_allowance_fen = position
        record.meal_allowance_fen = meal
        record.transport_allowance_fen = transport
        record.performance_bonus_fen = performance_bonus
        record.overtime_pay_fen = overtime_pay
        record.commission_fen = commission_total
        record.reward_fen = reward_total
        record.other_bonus_fen = seniority_subsidy + full_attendance_bonus
        record.gross_salary_fen = gross
        record.absence_deduction_fen = absence_deduction
        record.late_deduction_fen = late_deduction + early_leave_deduction
        record.penalty_fen = penalty_total
        record.social_insurance_fen = social
        record.housing_fund_fen = housing
        record.tax_fen = tax_fen
        record.total_deduction_fen = total_deduction
        record.net_salary_fen = net
        record.attendance_days = Decimal(str(attendance.get("attendance_days", 0)))
        record.absence_days = Decimal(str(absence_days))
        record.late_count = late_count
        record.overtime_hours = Decimal(str(attendance.get("overtime_hours", 0)))
        record.leave_days = Decimal(str(attendance.get("leave_days", 0)))
        record.status = PayrollStatus.DRAFT

        # 规则快照（审计溯源）
        record.rule_snapshot = rules

        record.calculation_detail = {
            "calc_mode": "standard_with_rule_engine",
            "work_days_in_month": work_days_in_month,
            "daily_rate_yuan": daily_rate / 100,
            "hourly_rate_yuan": hourly_rate / 100,
            "perf_coefficient": perf_coeff,
            "overtime_rate_applied": overtime_rate,
            "seniority_subsidy_yuan": seniority_subsidy / 100,
            "full_attendance_bonus_yuan": full_attendance_bonus / 100,
            "early_leave_count": early_leave_count,
            "early_leave_deduction_yuan": early_leave_deduction / 100,
            "commission_yuan": commission_total / 100,
            "reward_yuan": reward_total / 100,
            "penalty_yuan": penalty_total / 100,
            "social_insurance_yuan": social / 100,
            "housing_fund_yuan": housing / 100,
            "calculated_at": datetime.utcnow().isoformat(),
        }

        await db.flush()
        logger.info(
            "payroll_calculated",
            employee_id=employee_id,
            pay_month=pay_month,
            calc_mode="standard_with_rule_engine",
            net_yuan=net / 100,
        )
        return record

    async def _calculate_with_formula_engine(
        self,
        db: AsyncSession,
        employee_id: str,
        structure: SalaryStructure,
        pay_month: str,
        store_id: str,
        brand_id: str,
    ) -> PayrollRecord:
        """
        使用薪酬公式引擎计算（当品牌配置了SalaryItemDefinition时）。
        公式引擎自行处理所有薪酬项的计算和持久化，
        此方法负责将结果同步到PayrollRecord。
        """
        formula_engine = SalaryFormulaEngine(brand_id=brand_id)
        result = await formula_engine.calculate_employee_salary(db, employee_id, pay_month, store_id)

        # 获取考勤摘要（用于PayrollRecord统计字段）
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        attendance = await self._get_attendance_summary(db, employee_id, month_start, month_end)

        # 社保公积金
        social, housing = await self._calculate_social_insurance(db, employee_id, year, structure)

        # 个税
        tax_fen = await self._calculate_monthly_tax(
            db,
            employee_id,
            pay_month,
            max(0, result["total_income_fen"]),
            social,
            housing,
            structure.special_deduction_fen,
        )

        total_deduction = result["total_deduction_fen"] + social + housing + tax_fen
        net = result["total_income_fen"] - total_deduction

        # 写入/更新 PayrollRecord
        existing = await db.execute(
            select(PayrollRecord).where(
                and_(
                    PayrollRecord.employee_id == employee_id,
                    PayrollRecord.pay_month == pay_month,
                )
            )
        )
        record = existing.scalar_one_or_none()
        if record and record.status in (PayrollStatus.PAID, PayrollStatus.CONFIRMED):
            raise ValueError(f"员工 {employee_id} {pay_month} 工资单已确认/已发放，不可重算")

        if not record:
            record = PayrollRecord(store_id=store_id, employee_id=employee_id, pay_month=pay_month)
            db.add(record)

        # 从公式引擎结果中提取各类目汇总
        items_by_name = {item["item_name"]: item["amount_fen"] for item in result["items"]}

        record.base_salary_fen = items_by_name.get("基本工资", structure.base_salary_fen)
        record.position_allowance_fen = items_by_name.get("岗位补贴", structure.position_allowance_fen)
        record.meal_allowance_fen = items_by_name.get("餐补", structure.meal_allowance_fen)
        record.transport_allowance_fen = items_by_name.get("交通补贴", structure.transport_allowance_fen)
        record.performance_bonus_fen = items_by_name.get("绩效奖金", 0)
        record.overtime_pay_fen = items_by_name.get("加班费", 0)
        record.commission_fen = items_by_name.get("提成", 0)
        record.reward_fen = items_by_name.get("奖励", 0)
        record.other_bonus_fen = items_by_name.get("工龄补贴", 0) + items_by_name.get("全勤奖", 0)
        record.gross_salary_fen = result["total_income_fen"]
        record.absence_deduction_fen = items_by_name.get("缺勤扣款", 0)
        record.late_deduction_fen = items_by_name.get("迟到扣款", 0) + items_by_name.get("早退扣款", 0)
        record.penalty_fen = items_by_name.get("罚款", 0)
        record.social_insurance_fen = social
        record.housing_fund_fen = housing
        record.tax_fen = tax_fen
        record.total_deduction_fen = total_deduction
        record.net_salary_fen = net
        record.attendance_days = Decimal(str(attendance.get("attendance_days", 0)))
        record.absence_days = Decimal(str(attendance.get("absence_days", 0)))
        record.late_count = attendance.get("late_count", 0)
        record.overtime_hours = Decimal(str(attendance.get("overtime_hours", 0)))
        record.leave_days = Decimal(str(attendance.get("leave_days", 0)))
        record.status = PayrollStatus.DRAFT

        # 规则快照：记录公式引擎模式 + 各项明细
        record.rule_snapshot = {
            "calc_mode": "formula_engine",
            "brand_id": brand_id,
            "store_id": store_id,
            "items": result["items"],
            "resolved_at": datetime.utcnow().isoformat(),
        }

        record.calculation_detail = {
            "calc_mode": "formula_engine",
            "formula_items_count": len(result["items"]),
            "total_income_yuan": result["total_income_fen"] / 100,
            "total_deduction_yuan": total_deduction / 100,
            "social_insurance_yuan": social / 100,
            "housing_fund_yuan": housing / 100,
            "tax_yuan": tax_fen / 100,
            "calculated_at": datetime.utcnow().isoformat(),
        }

        await db.flush()
        logger.info(
            "payroll_calculated",
            employee_id=employee_id,
            pay_month=pay_month,
            calc_mode="formula_engine",
            net_yuan=net / 100,
        )
        return record

    async def batch_calculate(self, db: AsyncSession, store_id: str, pay_month: str) -> Dict[str, Any]:
        """批量算薪：为门店所有在职员工计算指定月份工资"""
        result = await db.execute(
            select(Person).where(
                and_(
                    Person.store_id == store_id,
                    Person.is_active.is_(True),
                )
            )
        )
        persons = result.scalars().all()

        success = 0
        failed = []
        total_net_fen = 0

        for person in persons:
            legacy_id = person.legacy_employee_id or str(person.id)
            try:
                record = await self.calculate_payroll(db, legacy_id, pay_month)
                success += 1
                total_net_fen += record.net_salary_fen
            except Exception as e:
                failed.append({"employee_id": legacy_id, "name": person.name, "error": str(e)})
                logger.warning("payroll_calc_failed", employee_id=legacy_id, error=str(e))

        return {
            "store_id": store_id,
            "pay_month": pay_month,
            "total_employees": len(persons),
            "success": success,
            "failed": failed,
            "total_net_salary_yuan": total_net_fen / 100,
        }

    async def confirm_payroll(self, db: AsyncSession, payroll_id: str, confirmed_by: str) -> PayrollRecord:
        """确认工资单（待发放）"""
        record = await db.get(PayrollRecord, payroll_id)
        if not record:
            raise ValueError(f"工资单 {payroll_id} 不存在")
        if record.status != PayrollStatus.DRAFT:
            raise ValueError(f"工资单状态为 {record.status}，不可确认")
        record.status = PayrollStatus.CONFIRMED
        record.confirmed_by = confirmed_by
        await db.flush()
        return record

    async def mark_paid(self, db: AsyncSession, store_id: str, pay_month: str) -> int:
        """标记门店整月工资已发放"""
        result = await db.execute(
            select(PayrollRecord).where(
                and_(
                    PayrollRecord.store_id == store_id,
                    PayrollRecord.pay_month == pay_month,
                    PayrollRecord.status == PayrollStatus.CONFIRMED,
                )
            )
        )
        records = result.scalars().all()
        for r in records:
            r.status = PayrollStatus.PAID
            r.paid_at = datetime.utcnow()
        await db.flush()
        return len(records)

    async def get_payroll_list(self, db: AsyncSession, store_id: str, pay_month: str) -> List[Dict[str, Any]]:
        """获取门店月度工资表"""
        result = await db.execute(
            select(PayrollRecord, Person.name, EmploymentAssignment.position)
            .join(Person, Person.legacy_employee_id == PayrollRecord.employee_id)
            .outerjoin(
                EmploymentAssignment,
                and_(
                    EmploymentAssignment.person_id == Person.id,
                    EmploymentAssignment.status == "active",
                ),
            )
            .where(
                and_(
                    PayrollRecord.store_id == store_id,
                    PayrollRecord.pay_month == pay_month,
                )
            )
            .order_by(Person.name)
        )
        rows = result.all()
        items = []
        for record, name, position in rows:
            items.append(
                {
                    "id": str(record.id),
                    "employee_id": record.employee_id,
                    "employee_name": name,
                    "position": position,
                    "pay_month": record.pay_month,
                    "status": record.status.value if record.status else "draft",
                    "gross_salary_yuan": record.gross_salary_fen / 100,
                    "total_deduction_yuan": record.total_deduction_fen / 100,
                    "net_salary_yuan": record.net_salary_fen / 100,
                    "tax_yuan": record.tax_fen / 100,
                    "attendance_days": float(record.attendance_days or 0),
                    "overtime_hours": float(record.overtime_hours or 0),
                    "paid_at": record.paid_at.isoformat() if record.paid_at else None,
                }
            )
        return items

    async def get_payroll_summary(self, db: AsyncSession, store_id: str, pay_month: str) -> Dict[str, Any]:
        """获取门店月度薪酬汇总"""
        result = await db.execute(
            select(
                func.count(PayrollRecord.id).label("count"),
                func.sum(PayrollRecord.gross_salary_fen).label("total_gross"),
                func.sum(PayrollRecord.net_salary_fen).label("total_net"),
                func.sum(PayrollRecord.tax_fen).label("total_tax"),
                func.sum(PayrollRecord.social_insurance_fen).label("total_social"),
                func.sum(PayrollRecord.housing_fund_fen).label("total_housing"),
                func.sum(PayrollRecord.overtime_pay_fen).label("total_overtime"),
                func.sum(PayrollRecord.commission_fen).label("total_commission"),
                func.sum(PayrollRecord.reward_fen).label("total_reward"),
                func.sum(PayrollRecord.penalty_fen).label("total_penalty"),
            ).where(
                and_(
                    PayrollRecord.store_id == store_id,
                    PayrollRecord.pay_month == pay_month,
                )
            )
        )
        row = result.one()
        return {
            "store_id": store_id,
            "pay_month": pay_month,
            "employee_count": row.count or 0,
            "total_gross_yuan": (row.total_gross or 0) / 100,
            "total_net_yuan": (row.total_net or 0) / 100,
            "total_tax_yuan": (row.total_tax or 0) / 100,
            "total_social_insurance_yuan": (row.total_social or 0) / 100,
            "total_housing_fund_yuan": (row.total_housing or 0) / 100,
            "total_overtime_pay_yuan": (row.total_overtime or 0) / 100,
            "total_commission_yuan": (row.total_commission or 0) / 100,
            "total_reward_yuan": (row.total_reward or 0) / 100,
            "total_penalty_yuan": (row.total_penalty or 0) / 100,
        }

    # ── 内部方法 ──────────────────────────────────────────

    async def _get_commission_total(self, db: AsyncSession, employee_id: str, pay_month: str) -> int:
        """汇总员工当月所有提成记录（分）"""
        result = await db.execute(
            select(func.coalesce(func.sum(CommissionRecord.commission_fen), 0)).where(
                and_(
                    CommissionRecord.employee_id == employee_id,
                    CommissionRecord.pay_month == pay_month,
                )
            )
        )
        return result.scalar() or 0

    async def _get_reward_penalty_totals(self, db: AsyncSession, employee_id: str, pay_month: str) -> tuple:
        """
        汇总员工当月已审批的奖励和罚款（分）。
        返回 (reward_total, penalty_total)
        """
        result = await db.execute(
            select(
                RewardPenaltyRecord.rp_type,
                func.coalesce(func.sum(RewardPenaltyRecord.amount_fen), 0).label("total"),
            )
            .where(
                and_(
                    RewardPenaltyRecord.employee_id == employee_id,
                    RewardPenaltyRecord.pay_month == pay_month,
                    RewardPenaltyRecord.status == RewardPenaltyStatus.APPROVED,
                )
            )
            .group_by(RewardPenaltyRecord.rp_type)
        )
        rows = result.all()
        reward = 0
        penalty = 0
        for row in rows:
            if row.rp_type == RewardPenaltyType.REWARD:
                reward = row.total
            elif row.rp_type == RewardPenaltyType.PENALTY:
                penalty = row.total
        return reward, penalty

    async def _calculate_social_insurance(
        self, db: AsyncSession, employee_id: str, year: int, structure: SalaryStructure
    ) -> tuple:
        """
        计算员工社保公积金个人扣款（分）。
        优先使用 EmployeeSocialInsurance 个性化配置；
        兜底使用 SalaryStructure 固定值。
        返回 (social_insurance_fen, housing_fund_fen)
        """
        # 查询员工参保方案
        result = await db.execute(
            select(EmployeeSocialInsurance).where(
                and_(
                    EmployeeSocialInsurance.employee_id == employee_id,
                    EmployeeSocialInsurance.effective_year == year,
                    EmployeeSocialInsurance.is_active.is_(True),
                )
            )
        )
        emp_si = result.scalar_one_or_none()

        if not emp_si:
            # 兜底：使用薪资方案固定值
            return structure.social_insurance_fen, structure.housing_fund_fen

        # 查询区域配置
        config_result = await db.execute(select(SocialInsuranceConfig).where(SocialInsuranceConfig.id == emp_si.config_id))
        config = config_result.scalar_one_or_none()
        if not config:
            return structure.social_insurance_fen, structure.housing_fund_fen

        base = emp_si.personal_base_fen  # 个人缴费基数（分）

        # 五险个人部分
        social = 0
        if emp_si.has_pension:
            social += int(base * float(config.pension_employee_pct) / 100)
        if emp_si.has_medical:
            social += int(base * float(config.medical_employee_pct) / 100)
        if emp_si.has_unemployment:
            social += int(base * float(config.unemployment_employee_pct) / 100)

        # 公积金个人部分
        housing = 0
        if emp_si.has_housing_fund:
            hf_pct = (
                float(emp_si.housing_fund_pct_override)
                if emp_si.housing_fund_pct_override is not None
                else float(config.housing_fund_employee_pct)
            )
            housing = int(base * hf_pct / 100)

        return social, housing

    async def _get_attendance_summary(self, db: AsyncSession, employee_id: str, start: date, end: date) -> Dict[str, Any]:
        """从 AttendanceLog 聚合考勤数据"""
        result = await db.execute(
            select(AttendanceLog).where(
                and_(
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.work_date >= start,
                    AttendanceLog.work_date <= end,
                )
            )
        )
        logs = result.scalars().all()

        attendance_days = 0
        absence_days = 0
        late_count = 0
        early_leave_count = 0
        overtime_hours = 0.0
        leave_days = 0

        for log in logs:
            if log.status == "normal":
                attendance_days += 1
            elif log.status == "absent":
                absence_days += 1
            elif log.status == "late":
                attendance_days += 1
                late_count += 1
            elif log.status == "leave":
                leave_days += 1
            elif log.status == "early_leave":
                attendance_days += 1
                early_leave_count += 1

            overtime_hours += float(log.overtime_hours or 0)

        return {
            "attendance_days": attendance_days,
            "absence_days": absence_days,
            "late_count": late_count,
            "early_leave_count": early_leave_count,
            "overtime_hours": overtime_hours,
            "leave_days": leave_days,
        }

    async def _calculate_monthly_tax(
        self,
        db: AsyncSession,
        employee_id: str,
        pay_month: str,
        taxable_gross_fen: int,
        social_fen: int,
        housing_fen: int,
        special_deduction_fen: int,
    ) -> int:
        """
        累计预扣法计算个税。

        公式:
        累计预扣预缴应纳税所得额 = 累计收入 - 累计免税收入 - 累计减除费用 - 累计专项扣除 - 累计专项附加扣除
        本期应预扣预缴税额 = (累计预扣预缴应纳税所得额 × 预扣率 - 速算扣除数) - 累计减免税额 - 累计已预扣预缴税额
        """
        year = int(pay_month[:4])
        month = int(pay_month[5:7])

        # 查询该年度之前月份的累计数据
        prev_months = []
        for m in range(1, month):
            prev_months.append(f"{year}-{m:02d}")

        cumulative_income_fen = 0
        cumulative_deduction_fen = 0
        cumulative_prepaid_fen = 0

        if prev_months:
            result = await db.execute(
                select(TaxDeclaration)
                .where(
                    and_(
                        TaxDeclaration.employee_id == employee_id,
                        TaxDeclaration.tax_month.in_(prev_months),
                    )
                )
                .order_by(TaxDeclaration.tax_month.desc())
                .limit(1)
            )
            last_record = result.scalar_one_or_none()
            if last_record:
                cumulative_income_fen = last_record.cumulative_income_fen
                cumulative_deduction_fen = last_record.cumulative_deduction_fen
                cumulative_prepaid_fen = last_record.cumulative_tax_fen

        # 本月累加
        monthly_income = max(0, taxable_gross_fen)
        monthly_deduction = (
            int(MONTHLY_EXEMPTION_YUAN * 100) + social_fen + housing_fen + special_deduction_fen  # 起征点（分）
        )

        new_cumulative_income = cumulative_income_fen + monthly_income
        new_cumulative_deduction = cumulative_deduction_fen + monthly_deduction
        cumulative_taxable = max(0, new_cumulative_income - new_cumulative_deduction)

        # 计算累计税额（转元计算）
        cumulative_taxable_yuan = cumulative_taxable / 100
        cumulative_tax_yuan, rate, quick_deduction_yuan = _compute_tax_yuan(cumulative_taxable_yuan)

        # 本月应扣 = 累计税额 - 已预扣
        cumulative_tax_fen = int(cumulative_tax_yuan * 100)
        current_month_tax = max(0, cumulative_tax_fen - cumulative_prepaid_fen)

        # 写入个税记录
        existing = await db.execute(
            select(TaxDeclaration).where(
                and_(
                    TaxDeclaration.employee_id == employee_id,
                    TaxDeclaration.tax_month == pay_month,
                )
            )
        )
        tax_record = existing.scalar_one_or_none()
        if not tax_record:
            tax_record = TaxDeclaration(
                store_id=self.store_id or "",
                employee_id=employee_id,
                tax_month=pay_month,
            )
            db.add(tax_record)

        tax_record.monthly_income_fen = monthly_income
        tax_record.monthly_social_deduction_fen = social_fen + housing_fen
        tax_record.monthly_special_deduction_fen = special_deduction_fen
        tax_record.cumulative_income_fen = new_cumulative_income
        tax_record.cumulative_deduction_fen = new_cumulative_deduction
        tax_record.cumulative_taxable_income_fen = cumulative_taxable
        tax_record.cumulative_tax_fen = cumulative_tax_fen
        tax_record.cumulative_prepaid_tax_fen = cumulative_prepaid_fen
        tax_record.current_month_tax_fen = current_month_tax
        tax_record.tax_rate_pct = Decimal(str(rate * 100))
        tax_record.quick_deduction_fen = int(quick_deduction_yuan * 100)

        await db.flush()
        return current_month_tax


def _count_work_days(year: int, month: int) -> int:
    """计算月内工作日（简单版：排除周末）"""
    days_in_month = calendar.monthrange(year, month)[1]
    count = 0
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d.weekday() < 5:  # 周一到周五
            count += 1
    return count
