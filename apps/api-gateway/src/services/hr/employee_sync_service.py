"""EmployeeSyncService — POS员工数据同步

支持从POS系统（奥琦玮/品智）拉取员工主数据，与HR系统双向同步。
如POS无员工API，则依赖Excel手动导入（P1-D保底）。

映射表使用 employee_id_map.legacy_employee_id 存储 POS external_id。
"""
from datetime import date
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.person import Person
from ...models.hr.employment_assignment import EmploymentAssignment
from ...models.hr.employee_id_map import EmployeeIdMap

logger = structlog.get_logger()


class EmployeeSyncService:
    """POS员工同步服务"""

    async def sync_from_pos(
        self,
        store_org_node_id: str,
        pos_employees: list[dict],
        session: AsyncSession,
    ) -> dict:
        """从POS员工列表同步到HR系统

        Args:
            store_org_node_id: 门店org_node_id
            pos_employees: POS返回的员工列表，每项包含:
                - external_id: POS系统员工ID
                - name: 姓名
                - phone: 手机号（可选）
                - position: 岗位名称（可选）
                - status: active/inactive
        """
        created = 0
        updated = 0
        terminated = 0
        unchanged = 0

        for pe in pos_employees:
            ext_id = str(pe.get("external_id", ""))
            if not ext_id:
                continue

            name = pe.get("name", "")
            phone = pe.get("phone")
            status = pe.get("status", "active")

            # 查找现有映射（legacy_employee_id 即 POS external_id）
            map_result = await session.execute(
                select(EmployeeIdMap).where(
                    EmployeeIdMap.legacy_employee_id == ext_id,
                )
            )
            id_map = map_result.scalar_one_or_none()

            if id_map is None:
                # 新员工：创建Person + Assignment + IdMap
                if status != "active":
                    unchanged += 1
                    continue

                person = Person(name=name, phone=phone)
                session.add(person)
                await session.flush()

                assignment = EmploymentAssignment(
                    person_id=person.id,
                    org_node_id=store_org_node_id,
                    employment_type="full_time",
                    start_date=date.today(),
                    status="active",
                )
                session.add(assignment)
                await session.flush()

                new_map = EmployeeIdMap(
                    legacy_employee_id=ext_id,
                    person_id=person.id,
                    assignment_id=assignment.id,
                )
                session.add(new_map)
                await session.flush()
                created += 1

            elif status != "active":
                # POS标记离职：关闭在岗关系
                await session.execute(
                    update(EmploymentAssignment)
                    .where(
                        EmploymentAssignment.person_id == id_map.person_id,
                        EmploymentAssignment.org_node_id == store_org_node_id,
                        EmploymentAssignment.status == "active",
                    )
                    .values(status="ended", end_date=date.today())
                )
                terminated += 1

            else:
                # 已有且活跃：检查是否有变更
                person_result = await session.execute(
                    select(Person).where(Person.id == id_map.person_id)
                )
                person = person_result.scalar_one_or_none()
                if person and (person.name != name or (phone and person.phone != phone)):
                    person.name = name
                    if phone:
                        person.phone = phone
                    updated += 1
                else:
                    unchanged += 1

        await session.flush()
        result = {
            "store": store_org_node_id,
            "created": created,
            "updated": updated,
            "terminated": terminated,
            "unchanged": unchanged,
            "total_processed": len(pos_employees),
        }
        logger.info("employee_sync.completed", **result)
        return result

    async def sync_single_store(
        self,
        store_org_node_id: str,
        adapter_type: str,
        session: AsyncSession,
    ) -> dict:
        """从POS适配器同步单个门店（占位：需要真实POS API）"""
        # 占位实现：返回空同步结果
        # 实际实装时根据adapter_type调用对应POS适配器的get_employees()
        logger.info(
            "employee_sync.adapter_stub",
            store=store_org_node_id,
            adapter=adapter_type,
        )
        return {
            "store": store_org_node_id,
            "created": 0,
            "updated": 0,
            "terminated": 0,
            "unchanged": 0,
            "total_processed": 0,
            "note": f"POS adapter '{adapter_type}' employee API not yet implemented",
        }
