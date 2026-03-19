"""
Employee Lifecycle Service -- 员工生命周期服务
试岗→入职→转正 全流程 + 企业微信通知
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.employee_contract import ContractStatus, ContractType, EmployeeContract
from src.models.employee_lifecycle import ChangeType, EmployeeChange
from src.models.payroll import SalaryStructure

logger = structlog.get_logger()


class EmployeeLifecycleService:
    """员工生命周期服务：试岗→入职→转正"""

    async def start_trial(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        试岗登记：创建 Person 档案（career_stage=probation）+ 试岗变动记录。
        试岗期默认7天，到期需决定是否正式入职。
        """
        employee_id = data["employee_id"]
        store_id = data["store_id"]
        trial_days = data.get("trial_days", 7)
        hire_date = date.fromisoformat(data["hire_date"])

        # 检查 legacy_employee_id 是否已存在
        exists = await db.execute(
            select(Person.id).where(Person.legacy_employee_id == str(employee_id))
        )
        if exists.scalars().first():
            raise ValueError(f"员工ID {employee_id} 已存在")

        # 创建人员档案（三层模型：Person 存身份，EmploymentAssignment 存在岗关系）
        person = Person(
            legacy_employee_id=str(employee_id),
            store_id=store_id,
            name=data["name"],
            phone=data.get("phone"),
            email=data.get("email"),
            is_active=True,
            career_stage="probation",
            wechat_userid=data.get("wechat_userid"),
        )
        db.add(person)

        # 创建试岗变动记录（employee_id 使用 legacy string 保持现有流程兼容）
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=store_id,
            employee_id=str(employee_id),
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

    async def confirm_onboard(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        正式入职：试岗通过 → 签合同 → 建薪资方案。
        career_stage: probation（试岗期即 probation，入职后继续 probation 直至转正）
        """
        employee_id = data["employee_id"]

        # 通过 legacy_employee_id 查找 Person
        person_result = await db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            raise ValueError(f"员工 {employee_id} 不存在")
        if person.career_stage not in ("probation", None, ""):
            raise ValueError(
                f"员工当前状态为 {person.career_stage}，不可执行入职操作（需要probation状态）"
            )

        probation_months = data.get("probation_months", 3)
        effective_date = date.fromisoformat(data.get("effective_date", str(date.today())))
        probation_end = effective_date + timedelta(days=probation_months * 30)

        # 更新 Person 状态（career_stage 保持 probation；is_active 确认为 True）
        person.career_stage = "probation"
        person.is_active = True

        # 查询当前在岗关系（获取 position，可能不存在）
        assign_result = await db.execute(
            select(EmploymentAssignment)
            .where(
                and_(
                    EmploymentAssignment.person_id == person.id,
                    EmploymentAssignment.status == "active",
                )
            )
            .order_by(EmploymentAssignment.start_date.desc())
            .limit(1)
        )
        assignment = assign_result.scalar_one_or_none()
        current_position = (
            (assignment.position if assignment else None)
            or data.get("position", "")
        )

        # 如果有 assignment，同步 position 更新
        if assignment and data.get("position"):
            assignment.position = data["position"]
            current_position = data["position"]

        # 创建入职变动记录
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=person.store_id,
            employee_id=str(employee_id),
            change_type=ChangeType.ONBOARD,
            effective_date=effective_date,
            to_position=current_position,
            to_store_id=person.store_id,
            to_salary_fen=data.get("base_salary_fen"),
            remark=data.get("remark", f"正式入职 - 试用期{probation_months}个月"),
        )
        db.add(change)

        # 创建劳动合同
        probation_salary_pct = data.get("probation_salary_pct", 80)
        contract = EmployeeContract(
            id=uuid.uuid4(),
            store_id=person.store_id,
            employee_id=str(employee_id),
            contract_type=ContractType.FIXED_TERM,
            status=ContractStatus.ACTIVE,
            start_date=effective_date,
            end_date=data.get("contract_end_date"),
            probation_end_date=probation_end,
            probation_salary_pct=probation_salary_pct,
            agreed_salary_fen=data.get("base_salary_fen", 0),
            position=current_position,
            contract_no=data.get("contract_no"),
        )
        db.add(contract)

        # 创建薪资方案（试用期打折）
        base_salary = data.get("base_salary_fen", 0)
        trial_salary = int(base_salary * probation_salary_pct / 100)

        salary = SalaryStructure(
            store_id=person.store_id,
            employee_id=str(employee_id),
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
            store_id=person.store_id,
            title="员工正式入职通知",
            description=(
                f"**{person.name}** 已正式入职\n"
                f"岗位: {current_position}\n"
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

    async def confirm_probation_pass(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转正：试用期结束 → 正式员工 → 调整薪资到100%。
        career_stage: probation → regular
        """
        employee_id = data["employee_id"]

        # 通过 legacy_employee_id 查找 Person
        person_result = await db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            raise ValueError(f"员工 {employee_id} 不存在")
        if person.career_stage != "probation":
            raise ValueError(
                f"员工当前状态为 {person.career_stage}，不可转正（需要probation状态）"
            )

        effective_date = date.fromisoformat(data.get("effective_date", str(date.today())))

        # 更新 Person career_stage 为正式员工
        person.career_stage = "regular"

        # 查询合同获取约定薪资（employee_id 仍使用 legacy string）
        contract_result = await db.execute(
            select(EmployeeContract)
            .where(
                and_(
                    EmployeeContract.employee_id == str(employee_id),
                    EmployeeContract.status == ContractStatus.ACTIVE,
                )
            )
            .order_by(EmployeeContract.start_date.desc())
            .limit(1)
        )
        contract = contract_result.scalar_one_or_none()
        agreed_salary = contract.agreed_salary_fen if contract else 0

        # 获取当前薪资方案（试用期）
        salary_result = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_id == str(employee_id),
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
            store_id=person.store_id,
            employee_id=str(employee_id),
            base_salary_fen=to_salary,
            position_allowance_fen=(
                data.get("position_allowance_fen") or (current_salary.position_allowance_fen if current_salary else 0)
            ),
            meal_allowance_fen=(
                data.get("meal_allowance_fen") or (current_salary.meal_allowance_fen if current_salary else 0)
            ),
            transport_allowance_fen=(
                data.get("transport_allowance_fen") or (current_salary.transport_allowance_fen if current_salary else 0)
            ),
            performance_coefficient=data.get("performance_coefficient", Decimal("1.0")),
            social_insurance_fen=(
                data.get("social_insurance_fen") or (current_salary.social_insurance_fen if current_salary else 0)
            ),
            housing_fund_fen=(data.get("housing_fund_fen") or (current_salary.housing_fund_fen if current_salary else 0)),
            special_deduction_fen=(
                data.get("special_deduction_fen") or (current_salary.special_deduction_fen if current_salary else 0)
            ),
            effective_date=effective_date,
            remark="转正薪资（100%）",
        )
        db.add(new_salary)

        # 创建转正变动记录
        change = EmployeeChange(
            id=uuid.uuid4(),
            store_id=person.store_id,
            employee_id=str(employee_id),
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
            store_id=person.store_id,
            title="员工转正通知",
            description=(
                f"**{person.name}** 已通过试用期，正式转正\n"
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

    async def _notify_wechat(self, store_id: str, title: str, description: str):
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
