"""
合规告警服务 — 健康证/合同/身份证到期预警
功能：
1. 每日扫描健康证到期员工
2. 合同到期前60/30/7天分级提醒
3. 身份证到期告警
4. 推送到店长IM（复用 IMMessageService）
5. 生成合规看板数据
"""
from typing import Any, Dict, List
from datetime import date, timedelta
import structlog

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.employee import Employee
from src.models.employee_contract import EmployeeContract
from src.models.store import Store

logger = structlog.get_logger()

# 告警级别阈值（天）
HEALTH_CERT_THRESHOLDS = [30, 7, 0]  # 提前30天/7天/到期当天
CONTRACT_THRESHOLDS = [60, 30, 7]
ID_CARD_THRESHOLDS = [60, 30]


class ComplianceAlertService:
    """合规告警服务"""

    def __init__(self, store_id: str):
        self.store_id = store_id

    async def check_health_cert_expiry(
        self, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        扫描健康证到期员工
        返回三级告警列表：expired/critical(7天内)/warning(30天内)
        """
        today = date.today()
        threshold_30 = today + timedelta(days=30)
        threshold_7 = today + timedelta(days=7)

        result = await db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.is_active.is_(True),
                    Employee.health_cert_expiry.isnot(None),
                    Employee.health_cert_expiry <= threshold_30,
                )
            ).order_by(Employee.health_cert_expiry)
        )
        employees = result.scalars().all()

        expired = []
        critical = []
        warning = []

        for emp in employees:
            days_left = (emp.health_cert_expiry - today).days
            item = {
                "employee_id": emp.id,
                "employee_name": emp.name,
                "position": emp.position,
                "health_cert_expiry": str(emp.health_cert_expiry),
                "days_remaining": days_left,
            }
            if days_left <= 0:
                item["level"] = "expired"
                expired.append(item)
            elif days_left <= 7:
                item["level"] = "critical"
                critical.append(item)
            else:
                item["level"] = "warning"
                warning.append(item)

        return {
            "store_id": self.store_id,
            "check_date": str(today),
            "expired_count": len(expired),
            "critical_count": len(critical),
            "warning_count": len(warning),
            "expired": expired,
            "critical": critical,
            "warning": warning,
        }

    async def check_contract_expiry(
        self, db: AsyncSession
    ) -> Dict[str, Any]:
        """扫描合同到期员工"""
        today = date.today()
        threshold_60 = today + timedelta(days=60)

        result = await db.execute(
            select(EmployeeContract, Employee.name, Employee.position).join(
                Employee, EmployeeContract.employee_id == Employee.id
            ).where(
                and_(
                    EmployeeContract.store_id == self.store_id,
                    EmployeeContract.status == "active",
                    EmployeeContract.end_date.isnot(None),
                    EmployeeContract.end_date <= threshold_60,
                )
            ).order_by(EmployeeContract.end_date)
        )
        rows = result.all()

        items = []
        for contract, name, position in rows:
            days_left = (contract.end_date - today).days
            level = "expired" if days_left <= 0 else "critical" if days_left <= 7 else "warning" if days_left <= 30 else "notice"
            items.append({
                "employee_id": contract.employee_id,
                "employee_name": name,
                "position": position,
                "contract_no": contract.contract_no,
                "end_date": str(contract.end_date),
                "days_remaining": days_left,
                "renewal_count": contract.renewal_count,
                "level": level,
            })

        return {
            "store_id": self.store_id,
            "items": items,
            "total": len(items),
        }

    async def check_id_card_expiry(
        self, db: AsyncSession
    ) -> Dict[str, Any]:
        """扫描身份证到期员工"""
        today = date.today()
        threshold = today + timedelta(days=60)

        result = await db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.is_active.is_(True),
                    Employee.id_card_expiry.isnot(None),
                    Employee.id_card_expiry <= threshold,
                )
            ).order_by(Employee.id_card_expiry)
        )
        employees = result.scalars().all()

        items = []
        for emp in employees:
            days_left = (emp.id_card_expiry - today).days
            items.append({
                "employee_id": emp.id,
                "employee_name": emp.name,
                "id_card_expiry": str(emp.id_card_expiry),
                "days_remaining": days_left,
                "level": "expired" if days_left <= 0 else "critical" if days_left <= 7 else "warning",
            })

        return {
            "store_id": self.store_id,
            "items": items,
            "total": len(items),
        }

    async def get_compliance_dashboard(
        self, db: AsyncSession
    ) -> Dict[str, Any]:
        """合规看板聚合数据"""
        health = await self.check_health_cert_expiry(db)
        contract = await self.check_contract_expiry(db)
        id_card = await self.check_id_card_expiry(db)

        return {
            "store_id": self.store_id,
            "health_cert": {
                "expired": health["expired_count"],
                "critical": health["critical_count"],
                "warning": health["warning_count"],
                "items": health["expired"] + health["critical"] + health["warning"],
            },
            "contract": {
                "total": contract["total"],
                "items": contract["items"],
            },
            "id_card": {
                "total": id_card["total"],
                "items": id_card["items"],
            },
            "overall_risk_level": "high" if (health["expired_count"] > 0 or any(
                c["days_remaining"] <= 0 for c in contract["items"]
            )) else "medium" if (health["critical_count"] > 0) else "low",
        }

    async def send_compliance_alerts(
        self, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        发送合规告警到店长IM
        调用 IMMessageService 推送
        """
        dashboard = await self.get_compliance_dashboard(db)

        # 查找店长IM账号
        store_result = await db.execute(
            select(Store).where(Store.id == self.store_id)
        )
        store = store_result.scalar_one_or_none()
        if not store:
            return {"sent": False, "error": "门店不存在"}

        # 构建告警消息
        alerts = []
        if dashboard["health_cert"]["expired"] > 0:
            names = [i["employee_name"] for i in dashboard["health_cert"]["items"] if i.get("level") == "expired"]
            alerts.append(f"🔴 {len(names)}名员工健康证已过期：{', '.join(names[:5])}")
        if dashboard["health_cert"]["critical"] > 0:
            alerts.append(f"🟡 {dashboard['health_cert']['critical']}名员工健康证7天内到期")
        if any(c["days_remaining"] <= 7 for c in dashboard["contract"]["items"]):
            urgent = [c for c in dashboard["contract"]["items"] if c["days_remaining"] <= 7]
            alerts.append(f"🔴 {len(urgent)}份合同7天内到期")

        if not alerts:
            return {"sent": False, "reason": "无紧急合规告警"}

        # 推送到IM
        content = "### 合规告警\n\n" + "\n".join(f"- {a}" for a in alerts)
        content += "\n\n💡 请及时处理，避免合规风险"

        try:
            from src.services.im_message_service import IMMessageService
            msg_svc = IMMessageService(db)
            # 查找店长
            manager_result = await db.execute(
                select(Employee).where(
                    and_(
                        Employee.store_id == self.store_id,
                        Employee.position.in_(["store_manager", "manager", "店长"]),
                        Employee.is_active.is_(True),
                    )
                )
            )
            managers = manager_result.scalars().all()
            sent_count = 0
            for mgr in managers:
                im_userid = mgr.wechat_userid or mgr.dingtalk_userid
                if im_userid:
                    await msg_svc.send_markdown(
                        store.brand_id if hasattr(store, 'brand_id') else "",
                        im_userid, "合规告警", content,
                    )
                    sent_count += 1

            return {"sent": True, "sent_count": sent_count, "alerts": alerts}
        except Exception as e:
            logger.warning("compliance_alert_send_failed", error=str(e))
            return {"sent": False, "error": str(e)}
