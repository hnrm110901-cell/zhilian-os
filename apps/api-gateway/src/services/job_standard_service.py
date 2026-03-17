"""
JobStandardService — 岗位标准知识库服务
支持：岗位查询/搜索、员工岗位绑定、成长记录管理、KPI差距分析。
"""
import uuid
from datetime import datetime, date
from typing import List, Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from src.models.job_standard import JobStandard
from src.models.job_sop import JobSOP
from src.models.employee_job_binding import EmployeeJobBinding
from src.models.employee_growth_trace import EmployeeGrowthTrace

logger = structlog.get_logger()


class JobStandardService:
    """岗位标准知识库服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────────────────────────
    # 岗位标准查询
    # ─────────────────────────────────────────────────────────────

    async def list_standards(
        self,
        job_level: Optional[str] = None,
        job_category: Optional[str] = None,
    ) -> List[dict]:
        """列出岗位标准（支持按 level/category 过滤，不含SOP详情）"""
        stmt = select(JobStandard).where(JobStandard.is_active == True)
        if job_level:
            stmt = stmt.where(JobStandard.job_level == job_level)
        if job_category:
            stmt = stmt.where(JobStandard.job_category == job_category)
        stmt = stmt.order_by(JobStandard.sort_order, JobStandard.job_name)

        result = await self.db.execute(stmt)
        standards = result.scalars().all()
        return [self._to_standard_dict(s) for s in standards]

    async def get_standard_detail(self, job_code: str) -> Optional[dict]:
        """获取岗位标准完整详情，包含 sops 列表"""
        result = await self.db.execute(
            select(JobStandard).where(
                JobStandard.job_code == job_code,
                JobStandard.is_active == True,
            )
        )
        standard = result.scalar_one_or_none()
        if standard is None:
            return None

        # 获取关联 SOP
        sop_result = await self.db.execute(
            select(JobSOP)
            .where(JobSOP.job_standard_id == standard.id)
            .order_by(JobSOP.sort_order, JobSOP.sop_type)
        )
        sops = sop_result.scalars().all()

        detail = self._to_standard_dict(standard)
        detail["sops"] = [self._to_sop_dict(s) for s in sops]
        return detail

    async def search_standards(self, keyword: str) -> List[dict]:
        """搜索岗位名称或职责关键词"""
        stmt = (
            select(JobStandard)
            .where(
                JobStandard.is_active == True,
                or_(
                    JobStandard.job_name.ilike(f"%{keyword}%"),
                    JobStandard.job_code.ilike(f"%{keyword}%"),
                    JobStandard.job_objective.ilike(f"%{keyword}%"),
                ),
            )
            .order_by(JobStandard.sort_order)
        )
        result = await self.db.execute(stmt)
        standards = result.scalars().all()
        return [self._to_standard_dict(s) for s in standards]

    # ─────────────────────────────────────────────────────────────
    # 员工岗位绑定
    # ─────────────────────────────────────────────────────────────

    async def bind_employee_job(
        self,
        employee_id: str,
        employee_name: str,
        store_id: str,
        job_code: str,
        bound_by: str,
    ) -> dict:
        """
        绑定员工到岗位标准。
        先解绑该员工在同门店的所有旧绑定，再新建绑定。
        """
        # 查找岗位标准
        std_result = await self.db.execute(
            select(JobStandard).where(
                JobStandard.job_code == job_code,
                JobStandard.is_active == True,
            )
        )
        standard = std_result.scalar_one_or_none()
        if standard is None:
            raise ValueError(f"岗位标准不存在: {job_code}")

        now = datetime.utcnow()

        # 解绑旧的活跃绑定
        old_result = await self.db.execute(
            select(EmployeeJobBinding).where(
                EmployeeJobBinding.employee_id == employee_id,
                EmployeeJobBinding.store_id == store_id,
                EmployeeJobBinding.is_active == True,
            )
        )
        old_bindings = old_result.scalars().all()
        for old in old_bindings:
            old.is_active = False
            old.unbound_at = now

        # 新建绑定
        binding = EmployeeJobBinding(
            id=uuid.uuid4(),
            employee_id=employee_id,
            employee_name=employee_name,
            store_id=store_id,
            job_standard_id=standard.id,
            job_code=standard.job_code,
            job_name=standard.job_name,
            bound_at=now,
            is_active=True,
            bound_by=bound_by,
        )
        self.db.add(binding)
        await self.db.flush()

        logger.info(
            "员工岗位绑定完成",
            employee_id=employee_id,
            job_code=job_code,
            store_id=store_id,
        )
        return self._to_binding_dict(binding)

    async def get_employee_current_job(
        self, employee_id: str, store_id: str
    ) -> Optional[dict]:
        """获取员工当前绑定的岗位标准"""
        result = await self.db.execute(
            select(EmployeeJobBinding).where(
                EmployeeJobBinding.employee_id == employee_id,
                EmployeeJobBinding.store_id == store_id,
                EmployeeJobBinding.is_active == True,
            )
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            return None

        # 加载岗位详情
        std_result = await self.db.execute(
            select(JobStandard).where(JobStandard.id == binding.job_standard_id)
        )
        standard = std_result.scalar_one_or_none()

        result_dict = self._to_binding_dict(binding)
        if standard:
            result_dict["job_standard"] = self._to_standard_dict(standard)
        return result_dict

    async def get_store_job_coverage(self, store_id: str) -> dict:
        """
        获取门店岗位覆盖情况。
        返回：已覆盖岗位、未覆盖的建议岗位、覆盖率。
        """
        # 获取门店当前绑定
        binding_result = await self.db.execute(
            select(EmployeeJobBinding).where(
                EmployeeJobBinding.store_id == store_id,
                EmployeeJobBinding.is_active == True,
            )
        )
        bindings = binding_result.scalars().all()
        covered_codes = {b.job_code for b in bindings}

        # 门店级别的关键岗位
        store_level_result = await self.db.execute(
            select(JobStandard).where(
                JobStandard.job_level == "store",
                JobStandard.is_active == True,
            ).order_by(JobStandard.sort_order)
        )
        store_standards = store_level_result.scalars().all()

        covered = []
        missing = []
        for std in store_standards:
            entry = {
                "job_code": std.job_code,
                "job_name": std.job_name,
                "job_category": std.job_category,
            }
            if std.job_code in covered_codes:
                # 找出该岗位对应的员工数
                employees = [b for b in bindings if b.job_code == std.job_code]
                entry["employee_count"] = len(employees)
                entry["employees"] = [
                    {"employee_id": b.employee_id, "employee_name": b.employee_name}
                    for b in employees
                ]
                covered.append(entry)
            else:
                entry["employee_count"] = 0
                entry["employees"] = []
                missing.append(entry)

        total = len(store_standards)
        covered_count = len(covered)
        coverage_rate = round(covered_count / total * 100, 1) if total > 0 else 0.0

        return {
            "store_id": store_id,
            "total_key_positions": total,
            "covered_count": covered_count,
            "missing_count": len(missing),
            "coverage_rate": coverage_rate,
            "covered_positions": covered,
            "missing_positions": missing,
        }

    # ─────────────────────────────────────────────────────────────
    # 员工成长记录
    # ─────────────────────────────────────────────────────────────

    async def add_growth_trace(
        self,
        employee_id: str,
        employee_name: str,
        store_id: Optional[str],
        trace_type: str,
        event_title: str,
        event_detail: Optional[str] = None,
        from_job_code: Optional[str] = None,
        to_job_code: Optional[str] = None,
        kpi_snapshot: Optional[dict] = None,
        assessment_score: Optional[int] = None,
        is_milestone: bool = False,
        created_by: str = "system",
    ) -> dict:
        """添加员工成长记录"""
        # 解析岗位名称（冗余存储）
        from_job_name = None
        to_job_name = None

        if from_job_code:
            fr_result = await self.db.execute(
                select(JobStandard).where(JobStandard.job_code == from_job_code)
            )
            fr_std = fr_result.scalar_one_or_none()
            if fr_std:
                from_job_name = fr_std.job_name

        if to_job_code:
            to_result = await self.db.execute(
                select(JobStandard).where(JobStandard.job_code == to_job_code)
            )
            to_std = to_result.scalar_one_or_none()
            if to_std:
                to_job_name = to_std.job_name

        trace = EmployeeGrowthTrace(
            id=uuid.uuid4(),
            employee_id=employee_id,
            employee_name=employee_name,
            store_id=store_id,
            trace_type=trace_type,
            trace_date=date.today(),
            event_title=event_title,
            event_detail=event_detail,
            from_job_code=from_job_code,
            from_job_name=from_job_name,
            to_job_code=to_job_code,
            to_job_name=to_job_name,
            kpi_snapshot=kpi_snapshot,
            assessment_score=assessment_score,
            is_milestone=is_milestone,
            created_by=created_by,
        )
        self.db.add(trace)
        await self.db.flush()

        logger.info(
            "员工成长记录已添加",
            employee_id=employee_id,
            trace_type=trace_type,
            event_title=event_title,
        )
        return self._to_trace_dict(trace)

    async def get_growth_timeline(self, employee_id: str) -> List[dict]:
        """获取员工完整成长时间轴，按时间倒序"""
        result = await self.db.execute(
            select(EmployeeGrowthTrace)
            .where(EmployeeGrowthTrace.employee_id == employee_id)
            .order_by(EmployeeGrowthTrace.trace_date.desc(), EmployeeGrowthTrace.created_at.desc())
        )
        traces = result.scalars().all()
        return [self._to_trace_dict(t) for t in traces]

    async def get_employee_kpi_gap(self, employee_id: str, store_id: str) -> dict:
        """
        对比员工最新KPI快照 vs 岗位KPI基线，返回差距分析。
        返回: {job_name, kpi_targets, actual_kpis, gaps: [{name, target_desc, actual, gap_level}]}
        """
        # 获取当前岗位
        current_job = await self.get_employee_current_job(employee_id, store_id)
        if current_job is None:
            return {"error": "员工尚未绑定岗位标准", "employee_id": employee_id}

        standard_dict = current_job.get("job_standard", {})
        kpi_targets = standard_dict.get("kpi_targets", [])

        # 获取最近一次带KPI快照的成长记录
        result = await self.db.execute(
            select(EmployeeGrowthTrace)
            .where(
                EmployeeGrowthTrace.employee_id == employee_id,
                EmployeeGrowthTrace.kpi_snapshot.isnot(None),
            )
            .order_by(EmployeeGrowthTrace.trace_date.desc())
            .limit(1)
        )
        latest_trace = result.scalar_one_or_none()
        actual_kpis = latest_trace.kpi_snapshot if latest_trace else {}

        gaps = []
        for target in kpi_targets:
            name = target.get("name", "")
            actual = actual_kpis.get(name)
            gaps.append(
                {
                    "name": name,
                    "target_description": target.get("description", ""),
                    "unit": target.get("unit", ""),
                    "actual": actual,
                    "gap_level": "unknown" if actual is None else "measured",
                }
            )

        return {
            "employee_id": employee_id,
            "store_id": store_id,
            "job_code": current_job.get("job_code"),
            "job_name": current_job.get("job_name"),
            "kpi_targets": kpi_targets,
            "actual_kpis": actual_kpis,
            "gaps": gaps,
            "last_snapshot_date": latest_trace.trace_date.isoformat() if latest_trace else None,
        }

    # ─────────────────────────────────────────────────────────────
    # 私有：格式化方法
    # ─────────────────────────────────────────────────────────────

    def _to_standard_dict(self, s: JobStandard) -> dict:
        return {
            "id": str(s.id),
            "job_code": s.job_code,
            "job_name": s.job_name,
            "job_level": s.job_level,
            "job_category": s.job_category,
            "report_to_role": s.report_to_role,
            "manages_roles": s.manages_roles,
            "job_objective": s.job_objective,
            "responsibilities": s.responsibilities or [],
            "daily_tasks": s.daily_tasks or [],
            "weekly_tasks": s.weekly_tasks or [],
            "monthly_tasks": s.monthly_tasks or [],
            "kpi_targets": s.kpi_targets or [],
            "experience_years_min": s.experience_years_min,
            "education_requirement": s.education_requirement,
            "skill_requirements": s.skill_requirements or [],
            "common_issues": s.common_issues or [],
            "industry_category": s.industry_category,
            "is_active": s.is_active,
            "sort_order": s.sort_order,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }

    def _to_sop_dict(self, s: JobSOP) -> dict:
        return {
            "id": str(s.id),
            "job_standard_id": str(s.job_standard_id),
            "sop_type": s.sop_type,
            "sop_name": s.sop_name,
            "steps": s.steps or [],
            "duration_minutes": s.duration_minutes,
            "responsible_role": s.responsible_role,
            "sort_order": s.sort_order,
        }

    def _to_binding_dict(self, b: EmployeeJobBinding) -> dict:
        return {
            "id": str(b.id),
            "employee_id": b.employee_id,
            "employee_name": b.employee_name,
            "store_id": b.store_id,
            "job_standard_id": str(b.job_standard_id),
            "job_code": b.job_code,
            "job_name": b.job_name,
            "bound_at": b.bound_at.isoformat() if b.bound_at else None,
            "unbound_at": b.unbound_at.isoformat() if b.unbound_at else None,
            "is_active": b.is_active,
            "bound_by": b.bound_by,
            "notes": b.notes,
        }

    def _to_trace_dict(self, t: EmployeeGrowthTrace) -> dict:
        return {
            "id": str(t.id),
            "employee_id": t.employee_id,
            "employee_name": t.employee_name,
            "store_id": t.store_id,
            "trace_type": t.trace_type,
            "trace_date": t.trace_date.isoformat() if t.trace_date else None,
            "event_title": t.event_title,
            "event_detail": t.event_detail,
            "from_job_code": t.from_job_code,
            "from_job_name": t.from_job_name,
            "to_job_code": t.to_job_code,
            "to_job_name": t.to_job_name,
            "kpi_snapshot": t.kpi_snapshot,
            "assessment_score": t.assessment_score,
            "assessor_id": t.assessor_id,
            "attachments": t.attachments,
            "is_milestone": t.is_milestone,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
