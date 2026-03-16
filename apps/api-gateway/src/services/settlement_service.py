"""
离职结算服务 — 按中国劳动法计算离职结算金额
Settlement Service: computes final pay, unused annual leave compensation,
and economic compensation (N / N+1 / 2N) per Chinese Labor Law.
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.attendance import AttendanceLog
from src.models.employee import Employee
from src.models.leave import LeaveBalance, LeaveCategory
from src.models.payroll import PayrollRecord, PayrollStatus
from src.models.settlement import SettlementRecord, SettlementStatus

logger = structlog.get_logger()

# 中国劳动法常量
STANDARD_WORK_DAYS_PER_MONTH = 21.75
# 经济补偿金上限年限
MAX_COMPENSATION_YEARS = 12


class SettlementService:
    """离职结算服务"""

    def __init__(self, store_id: str, brand_id: str):
        self.store_id = store_id
        self.brand_id = brand_id

    # ── 公开方法 ─────────────────────────────────────────

    async def calculate_settlement(
        self,
        db: AsyncSession,
        employee_id: str,
        last_work_date: date,
        separation_type: str = "resign",
        compensation_type: str = "none",
        annual_leave_method: str = "legal",
        overtime_pay_fen: int = 0,
        bonus_fen: int = 0,
        deduction_fen: int = 0,
        deduction_detail: str = "",
    ) -> dict:
        """
        自动计算离职结算（不入库，预览用）。

        Returns:
            dict with all settlement line items and total.
        """
        # 获取员工信息
        emp = await self._get_employee(db, employee_id)
        if not emp:
            raise ValueError(f"员工 {employee_id} 不存在")

        hire_date = emp.hire_date
        if not hire_date:
            raise ValueError(f"员工 {employee_id} 缺少入职日期")

        # 1. 最后月工资
        last_salary = await self._calc_last_month_salary(db, employee_id, last_work_date)

        # 2. 日薪（前12个月平均）
        avg_monthly = await self._get_avg_monthly_salary(db, employee_id, months=12)
        daily_wage_fen = round(avg_monthly / STANDARD_WORK_DAYS_PER_MONTH) if avg_monthly > 0 else 0

        # 如果无历史工资记录，用员工表的日薪标准
        if daily_wage_fen == 0 and emp.daily_wage_standard_fen:
            daily_wage_fen = emp.daily_wage_standard_fen

        # 3. 未休年假补偿
        annual_leave = await self._calc_annual_leave_compensation(
            db,
            employee_id,
            daily_wage_fen,
            method=annual_leave_method,
        )

        # 4. 经济补偿金
        econ_comp = await self._calc_economic_compensation(
            db,
            employee_id,
            separation_type,
            compensation_type,
            last_work_date,
            hire_date,
            avg_monthly,
        )

        # 5. 汇总
        total = (
            last_salary["last_month_salary_fen"]
            + annual_leave["annual_leave_compensation_fen"]
            + econ_comp["economic_compensation_fen"]
            + overtime_pay_fen
            + bonus_fen
            - deduction_fen
        )

        result = {
            "employee_id": employee_id,
            "employee_name": emp.name,
            "store_id": self.store_id,
            "brand_id": self.brand_id,
            "separation_type": separation_type,
            "last_work_date": last_work_date.isoformat(),
            "separation_date": last_work_date.isoformat(),
            "hire_date": hire_date.isoformat(),
            # 最后月工资
            **last_salary,
            # 年假补偿
            **annual_leave,
            "annual_leave_calc_method": annual_leave_method,
            # 经济补偿金
            **econ_comp,
            "compensation_type": compensation_type,
            # 其他
            "overtime_pay_fen": overtime_pay_fen,
            "bonus_fen": bonus_fen,
            "deduction_fen": deduction_fen,
            "deduction_detail": deduction_detail,
            # 日薪（辅助信息）
            "daily_wage_fen": daily_wage_fen,
            "avg_monthly_salary_fen": avg_monthly,
            # 总计
            "total_payable_fen": max(total, 0),
            "total_payable_yuan": round(max(total, 0) / 100, 2),
        }

        logger.info(
            "settlement.calculated",
            employee_id=employee_id,
            total_fen=result["total_payable_fen"],
            separation_type=separation_type,
        )
        return result

    async def create_settlement(
        self,
        db: AsyncSession,
        employee_id: str,
        last_work_date: date,
        separation_type: str = "resign",
        compensation_type: str = "none",
        annual_leave_method: str = "legal",
        overtime_pay_fen: int = 0,
        bonus_fen: int = 0,
        deduction_fen: int = 0,
        deduction_detail: str = "",
        remark: str = "",
    ) -> SettlementRecord:
        """创建结算单（计算并入库）"""
        calc = await self.calculate_settlement(
            db,
            employee_id,
            last_work_date,
            separation_type,
            compensation_type,
            annual_leave_method,
            overtime_pay_fen,
            bonus_fen,
            deduction_fen,
            deduction_detail,
        )

        record = SettlementRecord(
            store_id=self.store_id,
            brand_id=self.brand_id,
            employee_id=employee_id,
            employee_name=calc["employee_name"],
            separation_type=separation_type,
            last_work_date=last_work_date,
            separation_date=last_work_date,
            # 最后月工资
            work_days_last_month=calc["work_days_last_month"],
            last_month_salary_fen=calc["last_month_salary_fen"],
            # 年假补偿
            unused_annual_days=calc["unused_annual_days"],
            annual_leave_compensation_fen=calc["annual_leave_compensation_fen"],
            annual_leave_calc_method=annual_leave_method,
            # 经济补偿金
            service_years=calc["service_years_x10"],
            compensation_months=calc["compensation_n_x10"],
            compensation_base_fen=calc["compensation_base_fen"],
            economic_compensation_fen=calc["economic_compensation_fen"],
            compensation_type=compensation_type,
            # 其他
            overtime_pay_fen=overtime_pay_fen,
            bonus_fen=bonus_fen,
            deduction_fen=deduction_fen,
            deduction_detail=deduction_detail,
            # 汇总
            total_payable_fen=calc["total_payable_fen"],
            # 计算快照
            calculation_snapshot=calc,
            status=SettlementStatus.DRAFT.value,
            remark=remark,
        )

        db.add(record)
        await db.flush()

        logger.info(
            "settlement.created",
            settlement_id=str(record.id),
            employee_id=employee_id,
            total_fen=calc["total_payable_fen"],
        )
        return record

    async def get_settlement(self, db: AsyncSession, settlement_id: UUID) -> Optional[SettlementRecord]:
        """获取结算单详情"""
        result = await db.execute(select(SettlementRecord).where(SettlementRecord.id == settlement_id))
        return result.scalar_one_or_none()

    async def list_settlements(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        employee_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """结算单列表"""
        query = select(SettlementRecord).where(SettlementRecord.store_id == self.store_id)
        count_query = select(func.count()).select_from(SettlementRecord).where(SettlementRecord.store_id == self.store_id)

        if status:
            query = query.where(SettlementRecord.status == status)
            count_query = count_query.where(SettlementRecord.status == status)
        if employee_id:
            query = query.where(SettlementRecord.employee_id == employee_id)
            count_query = count_query.where(SettlementRecord.employee_id == employee_id)

        query = query.order_by(SettlementRecord.created_at.desc()).offset(offset).limit(limit)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        result = await db.execute(query)
        records = result.scalars().all()

        return {
            "total": total,
            "items": records,
            "offset": offset,
            "limit": limit,
        }

    async def update_handover(
        self,
        db: AsyncSession,
        settlement_id: UUID,
        handover_items: list,
    ) -> SettlementRecord:
        """更新交接清单"""
        record = await self.get_settlement(db, settlement_id)
        if not record:
            raise ValueError(f"结算单 {settlement_id} 不存在")

        record.handover_items = handover_items
        # 检查是否全部交接完毕
        record.handover_completed = all(item.get("returned", False) for item in handover_items) if handover_items else False

        await db.flush()
        logger.info("settlement.handover_updated", settlement_id=str(settlement_id))
        return record

    async def approve_settlement(
        self,
        db: AsyncSession,
        settlement_id: UUID,
        approver: str,
    ) -> SettlementRecord:
        """审批结算单"""
        record = await self.get_settlement(db, settlement_id)
        if not record:
            raise ValueError(f"结算单 {settlement_id} 不存在")

        if record.status not in (SettlementStatus.DRAFT.value, SettlementStatus.PENDING_APPROVAL.value):
            raise ValueError(f"结算单状态 {record.status} 不允许审批")

        record.status = SettlementStatus.APPROVED.value
        await db.flush()

        logger.info(
            "settlement.approved",
            settlement_id=str(settlement_id),
            approver=approver,
        )
        return record

    async def mark_paid(
        self,
        db: AsyncSession,
        settlement_id: UUID,
        paid_by: str,
    ) -> SettlementRecord:
        """标记已打款"""
        record = await self.get_settlement(db, settlement_id)
        if not record:
            raise ValueError(f"结算单 {settlement_id} 不存在")

        if record.status != SettlementStatus.APPROVED.value:
            raise ValueError("只有已审批的结算单才能标记打款")

        record.status = SettlementStatus.PAID.value
        record.paid_at = datetime.utcnow()
        record.paid_by = paid_by
        await db.flush()

        logger.info(
            "settlement.paid",
            settlement_id=str(settlement_id),
            paid_by=paid_by,
            amount_fen=record.total_payable_fen,
        )
        return record

    # ── 内部计算方法 ──────────────────────────────────────

    async def _get_employee(self, db: AsyncSession, employee_id: str) -> Optional[Employee]:
        """获取员工信息"""
        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        return result.scalar_one_or_none()

    async def _calc_last_month_salary(
        self,
        db: AsyncSession,
        employee_id: str,
        last_work_date: date,
    ) -> dict:
        """
        计算最后月工资（按日折算）。
        公式：月基本工资 ÷ 21.75（法定月均工作日） × 实际出勤天数

        优先从 AttendanceLog 查询实际出勤天数（status 为 normal/late/early_leave 均算出勤）；
        若无考勤记录（新入职员工等），降级为日历日比例估算。
        """
        # 查找最近一条工资记录获取月薪基数
        result = await db.execute(
            select(PayrollRecord)
            .where(
                PayrollRecord.employee_id == employee_id,
                PayrollRecord.store_id == self.store_id,
            )
            .order_by(PayrollRecord.pay_month.desc())
            .limit(1)
        )
        latest_payroll = result.scalar_one_or_none()

        if not latest_payroll:
            return {"work_days_last_month": 0, "last_month_salary_fen": 0}

        monthly_base = (
            latest_payroll.base_salary_fen
            + latest_payroll.position_allowance_fen
            + latest_payroll.meal_allowance_fen
            + latest_payroll.transport_allowance_fen
        )

        # ── 从考勤记录查询实际出勤天数 ──
        # 当月范围：月初 ~ 最后工作日（含）的次日（用于 < 比较）
        month_start = date(last_work_date.year, last_work_date.month, 1)
        month_end_exclusive = last_work_date + timedelta(days=1)

        actual_work_days_result = await db.execute(
            select(func.count(AttendanceLog.id)).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.work_date >= month_start,
                AttendanceLog.work_date < month_end_exclusive,
                # normal/late/early_leave 均计为有效出勤
                AttendanceLog.status.in_(["normal", "late", "early_leave"]),
            )
        )
        actual_days = actual_work_days_result.scalar() or 0

        if actual_days > 0:
            # 有考勤记录，使用实际出勤天数
            work_days = min(actual_days, STANDARD_WORK_DAYS_PER_MONTH)
        else:
            # 降级方案：无考勤记录（新入职员工等），用日历日比例估算
            total_days_in_month = calendar.monthrange(last_work_date.year, last_work_date.month)[1]
            work_days = round(last_work_date.day / total_days_in_month * STANDARD_WORK_DAYS_PER_MONTH, 1)
            work_days = min(work_days, STANDARD_WORK_DAYS_PER_MONTH)
            logger.info(
                "settlement.last_salary_fallback_estimation",
                employee_id=employee_id,
                estimated_days=work_days,
                reason="无考勤记录，降级为日历日比例估算",
            )

        daily_rate = monthly_base / STANDARD_WORK_DAYS_PER_MONTH
        last_month_salary = round(daily_rate * work_days)

        return {
            "work_days_last_month": int(work_days),
            "last_month_salary_fen": last_month_salary,
        }

    async def _calc_annual_leave_compensation(
        self,
        db: AsyncSession,
        employee_id: str,
        daily_wage_fen: int,
        method: str = "legal",
    ) -> dict:
        """
        计算未休年假补偿。
        法定方式：日薪 × 3 × 未休天数（含已支付的1倍，实际额外补偿2倍）
        协商方式：日薪 × 1 × 未休天数
        注：法律规定的"3倍"中已包含正常工作日的1倍工资，
            但实务中若该员工最后月已按正常出勤计薪，则只需额外补2倍。
            本系统按3倍全额计算，由HR在deduction中调整。
        """
        current_year = date.today().year
        result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == current_year,
                LeaveBalance.leave_category == LeaveCategory.ANNUAL,
            )
        )
        balance = result.scalar_one_or_none()

        if not balance:
            return {"unused_annual_days": 0, "annual_leave_compensation_fen": 0}

        unused_days = max(float(balance.total_days) - float(balance.used_days), 0)
        unused_days_int = int(unused_days)

        multiplier = 3 if method == "legal" else 1
        compensation = round(daily_wage_fen * multiplier * unused_days)

        return {
            "unused_annual_days": unused_days_int,
            "annual_leave_compensation_fen": compensation,
        }

    async def _calc_economic_compensation(
        self,
        db: AsyncSession,
        employee_id: str,
        separation_type: str,
        compensation_type: str,
        last_work_date: date,
        hire_date: date,
        avg_monthly_salary_fen: int,
    ) -> dict:
        """
        计算经济补偿金。

        中国劳动法规则：
        - N = 工龄年数（不满6月算0.5年，满6月不满1年算1年）
        - 月平均工资 = 前12个月总工资 ÷ 12
        - N型: N × 月平均工资（合同到期不续、协商解除）
        - N+1型: (N+1) × 月平均工资（未提前30天通知的辞退）
        - 2N型: 2N × 月平均工资（违法解除）
        - 上限: 月工资超过当地社平工资3倍时，按3倍计算且年限不超过12年
        - 主动辞职（resign）一般不享受经济补偿金
        """
        # 主动辞职且无补偿
        if compensation_type == "none":
            return {
                "service_years_x10": 0,
                "compensation_n_x10": 0,
                "compensation_base_fen": 0,
                "economic_compensation_fen": 0,
            }

        # 计算工龄
        service_years_x10 = self._calc_service_years_x10(hire_date, last_work_date)

        # N值 = service_years_x10（已经是×10存储的）
        n_x10 = service_years_x10

        # 补偿基数
        comp_base = avg_monthly_salary_fen
        if comp_base <= 0:
            # 无工资记录，尝试从员工日薪推算
            emp = await self._get_employee(db, employee_id)
            if emp and emp.daily_wage_standard_fen:
                comp_base = round(emp.daily_wage_standard_fen * STANDARD_WORK_DAYS_PER_MONTH)

        # 计算补偿金额
        if compensation_type == "n":
            # N × 月平均工资
            compensation_fen = round(n_x10 * comp_base / 10)
        elif compensation_type == "n_plus_1":
            # (N+1) × 月平均工资
            compensation_fen = round((n_x10 + 10) * comp_base / 10)
        elif compensation_type == "2n":
            # 2N × 月平均工资（违法解除赔偿金）
            compensation_fen = round(2 * n_x10 * comp_base / 10)
        else:
            compensation_fen = 0

        return {
            "service_years_x10": service_years_x10,
            "compensation_n_x10": n_x10,
            "compensation_base_fen": comp_base,
            "economic_compensation_fen": max(compensation_fen, 0),
        }

    async def _get_avg_monthly_salary(
        self,
        db: AsyncSession,
        employee_id: str,
        months: int = 12,
    ) -> int:
        """
        获取前N个月平均工资（应发合计 gross_salary_fen）。
        如果不足N个月，按实际月数取平均。
        """
        result = await db.execute(
            select(PayrollRecord.gross_salary_fen)
            .where(
                PayrollRecord.employee_id == employee_id,
                PayrollRecord.store_id == self.store_id,
                PayrollRecord.status.in_(
                    [
                        PayrollStatus.CONFIRMED.value,
                        PayrollStatus.PAID.value,
                        "confirmed",
                        "paid",
                    ]
                ),
            )
            .order_by(PayrollRecord.pay_month.desc())
            .limit(months)
        )
        rows = result.scalars().all()

        if not rows:
            return 0

        total = sum(r for r in rows if r)
        return round(total / len(rows))

    @staticmethod
    def _calc_service_years_x10(hire_date: date, last_work_date: date) -> int:
        """
        计算工龄（×10存储以支持0.5精度）。

        规则：
        - 不满6个月，按0.5年（返回5）
        - 满6个月不满1年，按1年（返回10）
        - 以此类推，每多一段判断是否满半年
        - 上限12年（返回120）
        """
        if last_work_date <= hire_date:
            return 0

        # 计算总月数
        total_months = (last_work_date.year - hire_date.year) * 12 + (last_work_date.month - hire_date.month)
        # 日期补偿
        if last_work_date.day >= hire_date.day:
            pass  # 已满整月
        else:
            total_months -= 1

        total_months = max(total_months, 0)

        # 整年数
        full_years = total_months // 12
        remaining_months = total_months % 12

        if remaining_months == 0:
            service_x10 = full_years * 10
        elif remaining_months < 6:
            service_x10 = full_years * 10 + 5  # 不满6个月算0.5年
        else:
            service_x10 = (full_years + 1) * 10  # 满6个月不满1年算1年

        # 上限12年
        service_x10 = min(service_x10, MAX_COMPENSATION_YEARS * 10)

        return service_x10
