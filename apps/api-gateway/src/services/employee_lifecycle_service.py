"""
Employee Lifecycle Service -- 员工生命周期服务
试岗→入职→转正 全流程 + 企业微信通知
"""
from typing import Optional, Dict, Any
from datetime import date, timedelta
from decimal import Decimal
import uuid
import structlog

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.employee import Employee
from src.models.employee_lifecycle import EmployeeChange, ChangeType
from src.models.employee_contract import EmployeeContract, ContractType, ContractStatus
from src.models.payroll import SalaryStructure

logger = structlog.get_logger()


class EmployeeLifecycleService:
    """员工生命周期服务：试岗→入职→转正"""

    async def start_trial(
        self, db: AsyncSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        试岗登记：创建员工（employment_status=trial）+ 试岗变动记录。
        试岗期默认7天，到期需决定是否正式入职。
        """
        employee_id = data["employee_id"]
        store_id = data["store_id"]
        trial_days = data.get("trial_days", 7)
        hire_date = date.fromisoformat(data["hire_date"])

        # 检查ID是否已存在
        exists = await db.execute(
            select(Employee.id).where(Employee.id == employee_id)
        )
        if exists.scalars().first():
            raise ValueError(f"员工ID {employee_id} 已存在")

        # 创建员工（试岗状态）
        employee = Employee(
            id=employee_id,
            store_id=store_id,
            name=data["name"],
            phone=data.get("phone"),
            email=data.get("email"),
            position=data["position"],
            hire_date=hire_date,
            is_active=True,
            employment_status="trial",
            wechat_userid=data.get("wechat_userid"),
        )
        db.add(employee)

        # 创建试岗变动记录
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=store_id,
            employee_id=employee_id,
            change_type=ChangeType.TRIAL,
            effective_date=hire_date,
            to_position=data["position"],
            to_store_id=store_id,
            remark=data.get("remark", f"试岗{trial_days}天 - {data['position']}"),
        )
        db.add(change)
        await db.flush()

        # 企业微信通知
        trial_end = hire_date + timedelta(days=trial_days)
        await self._notify_wechat(
            store_id=store_id,
            title="新员工试岗通知",
            description=(
                f"**{data['name']}** 开始试岗\n"
                f"岗位: {data['position']}\n"
                f"试岗期: {hire_date} ~ {trial_end}\n"
                f"请关注其工作表现"
            ),
        )

        logger.info("employee_trial_started", employee_id=employee_id)
        return {
            "employee_id": employee_id,
            "employment_status": "trial",
            "trial_end_date": str(trial_end),
        }

    async def confirm_onboard(
        self, db: AsyncSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        正式入职：试岗通过 → 签合同 → 建薪资方案。
        employment_status: trial → probation
        """
        employee_id = data["employee_id"]

        emp_result = await db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"员工 {employee_id} 不存在")
        if employee.employment_status not in ("trial", None, ""):
            raise ValueError(
                f"员工当前状态为 {employee.employment_status}，"
                f"不可执行入职操作（需要trial状态）"
            )

        probation_months = data.get("probation_months", 3)
        effective_date = date.fromisoformat(
            data.get("effective_date", str(date.today()))
        )
        probation_end = effective_date + timedelta(days=probation_months * 30)

        # 更新员工状态
        employee.employment_status = "probation"
        employee.probation_end_date = probation_end

        # 创建入职变动记录
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=employee.store_id,
            employee_id=employee_id,
            change_type=ChangeType.ONBOARD,
            effective_date=effective_date,
            to_position=data.get("position", employee.position),
            to_store_id=employee.store_id,
            to_salary_fen=data.get("base_salary_fen"),
            remark=data.get("remark", f"正式入职 - 试用期{probation_months}个月"),
        )
        db.add(change)

        # 创建劳动合同
        probation_salary_pct = data.get("probation_salary_pct", 80)
        contract = EmployeeContract(
            id=uuid.uuid4(),
            store_id=employee.store_id,
            employee_id=employee_id,
            contract_type=ContractType.FIXED_TERM,
            status=ContractStatus.ACTIVE,
            start_date=effective_date,
            end_date=data.get("contract_end_date"),
            probation_end_date=probation_end,
            probation_salary_pct=probation_salary_pct,
            agreed_salary_fen=data.get("base_salary_fen", 0),
            position=data.get("position", employee.position),
            contract_no=data.get("contract_no"),
        )
        db.add(contract)

        # 创建薪资方案（试用期打折）
        base_salary = data.get("base_salary_fen", 0)
        trial_salary = int(base_salary * probation_salary_pct / 100)

        salary = SalaryStructure(
            store_id=employee.store_id,
            employee_id=employee_id,
            base_salary_fen=trial_salary,
            position_allowance_fen=data.get("position_allowance_fen", 0),
            meal_allowance_fen=data.get("meal_allowance_fen", 0),
            transport_allowance_fen=data.get("transport_allowance_fen", 0),
            social_insurance_fen=data.get("social_insurance_fen", 0),
            housing_fund_fen=data.get("housing_fund_fen", 0),
            special_deduction_fen=data.get("special_deduction_fen", 0),
            effective_date=effective_date,
            remark=f"试用期薪资（{probation_salary_pct}%）",
        )
        db.add(salary)
        await db.flush()

        # 企业微信通知
        await self._notify_wechat(
            store_id=employee.store_id,
            title="员工正式入职通知",
            description=(
                f"**{employee.name}** 已正式入职\n"
                f"岗位: {employee.position}\n"
                f"试用期至: {probation_end}\n"
                f"试用期薪资: {probation_salary_pct}%"
            ),
        )

        logger.info("employee_onboarded", employee_id=employee_id)
        return {
            "employee_id": employee_id,
            "employment_status": "probation",
            "probation_end_date": str(probation_end),
            "trial_salary_yuan": trial_salary / 100,
        }

    async def confirm_probation_pass(
        self, db: AsyncSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        转正：试用期结束 → 正式员工 → 调整薪资到100%。
        employment_status: probation → regular
        """
        employee_id = data["employee_id"]

        emp_result = await db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"员工 {employee_id} 不存在")
        if employee.employment_status != "probation":
            raise ValueError(
                f"员工当前状态为 {employee.employment_status}，不可转正（需要probation状态）"
            )

        effective_date = date.fromisoformat(
            data.get("effective_date", str(date.today()))
        )

        # 更新员工状态
        employee.employment_status = "regular"
        employee.probation_end_date = None

        # 查询合同获取约定薪资
        contract_result = await db.execute(
            select(EmployeeContract).where(
                and_(
                    EmployeeContract.employee_id == employee_id,
                    EmployeeContract.status == ContractStatus.ACTIVE,
                )
            ).order_by(EmployeeContract.start_date.desc()).limit(1)
        )
        contract = contract_result.scalar_one_or_none()
        agreed_salary = contract.agreed_salary_fen if contract else 0

        # 获取当前薪资方案（试用期）
        salary_result = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_id == employee_id,
                    SalaryStructure.is_active.is_(True),
                )
            )
        )
        current_salary = salary_result.scalar_one_or_none()

        # 停用旧薪资方案
        from_salary = 0
        if current_salary:
            from_salary = current_salary.base_salary_fen
            current_salary.is_active = False
            current_salary.expire_date = effective_date

        # 创建正式薪资方案（100%）
        to_salary = data.get("base_salary_fen", agreed_salary)
        new_salary = SalaryStructure(
            store_id=employee.store_id,
            employee_id=employee_id,
            base_salary_fen=to_salary,
            position_allowance_fen=(
                data.get("position_allowance_fen")
                or (current_salary.position_allowance_fen if current_salary else 0)
            ),
            meal_allowance_fen=(
                data.get("meal_allowance_fen")
                or (current_salary.meal_allowance_fen if current_salary else 0)
            ),
            transport_allowance_fen=(
                data.get("transport_allowance_fen")
                or (current_salary.transport_allowance_fen if current_salary else 0)
            ),
            performance_coefficient=data.get("performance_coefficient", Decimal("1.0")),
            social_insurance_fen=(
                data.get("social_insurance_fen")
                or (current_salary.social_insurance_fen if current_salary else 0)
            ),
            housing_fund_fen=(
                data.get("housing_fund_fen")
                or (current_salary.housing_fund_fen if current_salary else 0)
            ),
            special_deduction_fen=(
                data.get("special_deduction_fen")
                or (current_salary.special_deduction_fen if current_salary else 0)
            ),
            effective_date=effective_date,
            remark="转正薪资（100%）",
        )
        db.add(new_salary)

        # 创建转正变动记录
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=employee.store_id,
            employee_id=employee_id,
            change_type=ChangeType.PROBATION_PASS,
            effective_date=effective_date,
            from_salary_fen=from_salary,
            to_salary_fen=to_salary,
            remark=data.get("remark", "试用期通过，转正"),
        )
        db.add(change)
        await db.flush()

        # 企业微信通知
        await self._notify_wechat(
            store_id=employee.store_id,
            title="员工转正通知",
            description=(
                f"**{employee.name}** 已通过试用期，正式转正\n"
                f"转正日期: {effective_date}\n"
                f"转正薪资: {to_salary / 100:.0f}元/月"
            ),
        )

        logger.info("employee_probation_passed", employee_id=employee_id)
        return {
            "employee_id": employee_id,
            "employment_status": "regular",
            "base_salary_yuan": to_salary / 100,
        }

    async def _notify_wechat(
        self, store_id: str, title: str, description: str
    ):
        """发送企业微信通知（失败静默）"""
        try:
            from src.services.wechat_service import WeChatService
            wechat = WeChatService()
            if wechat.is_configured():
                await wechat.send_markdown_message(
                    content=f"### {title}\n{description}",
                    touser="@all",
                )
        except Exception as e:
            logger.warning("wechat_notify_failed", error=str(e))
