"""
IM 打卡/考勤数据同步服务

从企微/钉钉拉取打卡记录 → 写入屯象OS考勤表。

企业微信：
  - POST /cgi-bin/checkin/getcheckindata
  - 支持按日期范围 + 员工列表查询

钉钉：
  - POST /attendance/list
  - 支持按用户 + 日期范围查询
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, date, timedelta
import os

import httpx
import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.brand_im_config import BrandIMConfig, IMPlatform
from ..models.employee import Employee
from ..services.im_sync_service import WeChatWorkAdapter, DingTalkAdapter

logger = structlog.get_logger()


class IMAttendanceSyncService:
    """IM 平台打卡数据同步"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_attendance(
        self,
        brand_id: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        同步指定日期范围的打卡数据。

        Returns:
            {"synced": int, "errors": int, "records": [...]}
        """
        result = await self.db.execute(
            select(BrandIMConfig).where(
                and_(BrandIMConfig.brand_id == brand_id, BrandIMConfig.is_active.is_(True))
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return {"error": f"品牌 {brand_id} 未配置IM平台"}

        if config.im_platform == IMPlatform.WECHAT_WORK:
            records = await self._fetch_wechat_attendance(config, start_date, end_date)
        elif config.im_platform == IMPlatform.DINGTALK:
            records = await self._fetch_dingtalk_attendance(config, start_date, end_date)
        else:
            return {"error": "不支持的平台"}

        synced = 0
        errors = 0

        for record in records:
            try:
                await self._save_attendance_record(record, config)
                synced += 1
            except Exception as e:
                errors += 1
                logger.warning("attendance_sync_save_failed", error=str(e), record=record)

        if synced > 0:
            await self.db.commit()

        logger.info(
            "attendance_sync_done",
            brand_id=brand_id,
            synced=synced,
            errors=errors,
        )
        return {"synced": synced, "errors": errors, "total_fetched": len(records)}

    async def _fetch_wechat_attendance(
        self, config: BrandIMConfig, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """从企微拉取打卡数据"""
        corp_id = config.wechat_corp_id or ""
        corp_secret = config.wechat_corp_secret or ""

        adapter = WeChatWorkAdapter(corp_id, corp_secret)
        token = await adapter.get_access_token()

        # 获取该品牌所有有企微ID的员工
        from ..models.store import Store
        store_result = await self.db.execute(
            select(Store.id).where(Store.brand_id == config.brand_id)
        )
        store_ids = [r[0] for r in store_result.all()]

        emp_result = await self.db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id.in_(store_ids),
                    Employee.wechat_userid.isnot(None),
                    Employee.is_active.is_(True),
                )
            )
        )
        employees = emp_result.scalars().all()
        if not employees:
            return []

        userid_list = [e.wechat_userid for e in employees]

        # 企微打卡接口一次最多100人
        records = []
        start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())

        async with httpx.AsyncClient() as client:
            for i in range(0, len(userid_list), 100):
                batch = userid_list[i:i + 100]
                try:
                    resp = await client.post(
                        f"https://qyapi.weixin.qq.com/cgi-bin/checkin/getcheckindata",
                        params={"access_token": token},
                        json={
                            "opencheckindatatype": 3,  # 1=上班 2=下班 3=全部
                            "starttime": start_ts,
                            "endtime": end_ts,
                            "useridlist": batch,
                        },
                        timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                    )
                    data = resp.json()
                    if data.get("errcode") == 0:
                        for item in data.get("checkindata", []):
                            records.append({
                                "platform": "wechat_work",
                                "userid": item.get("userid"),
                                "checkin_type": item.get("checkin_type"),
                                "checkin_time": datetime.fromtimestamp(
                                    item.get("checkin_time", 0)
                                ),
                                "exception_type": item.get("exception_type"),
                                "location_title": item.get("location_title"),
                                "notes": item.get("notes"),
                                "raw": item,
                            })
                except Exception as e:
                    logger.warning("wechat_attendance_fetch_failed", error=str(e))

        return records

    async def _fetch_dingtalk_attendance(
        self, config: BrandIMConfig, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """从钉钉拉取考勤数据"""
        app_key = config.dingtalk_app_key or ""
        app_secret = config.dingtalk_app_secret or ""

        adapter = DingTalkAdapter(app_key, app_secret)
        token = await adapter.get_access_token()

        from ..models.store import Store
        store_result = await self.db.execute(
            select(Store.id).where(Store.brand_id == config.brand_id)
        )
        store_ids = [r[0] for r in store_result.all()]

        emp_result = await self.db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id.in_(store_ids),
                    Employee.dingtalk_userid.isnot(None),
                    Employee.is_active.is_(True),
                )
            )
        )
        employees = emp_result.scalars().all()
        if not employees:
            return []

        userid_list = [e.dingtalk_userid for e in employees]
        records = []
        work_date_str = start_date.strftime("%Y-%m-%d 00:00:00")
        end_date_str = end_date.strftime("%Y-%m-%d 23:59:59")

        async with httpx.AsyncClient() as client:
            for i in range(0, len(userid_list), 50):
                batch = userid_list[i:i + 50]
                offset = 0
                while True:
                    try:
                        resp = await client.post(
                            f"https://oapi.dingtalk.com/attendance/list",
                            params={"access_token": token},
                            json={
                                "workDateFrom": work_date_str,
                                "workDateTo": end_date_str,
                                "userIdList": batch,
                                "offset": offset,
                                "limit": 50,
                            },
                            timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                        )
                        data = resp.json()
                        if data.get("errcode") != 0:
                            break

                        for item in data.get("recordresult", []):
                            records.append({
                                "platform": "dingtalk",
                                "userid": item.get("userId"),
                                "checkin_type": item.get("checkType"),
                                "checkin_time": datetime.strptime(
                                    item.get("userCheckTime", ""), "%Y-%m-%d %H:%M:%S"
                                ) if item.get("userCheckTime") else None,
                                "location_title": item.get("locationResult"),
                                "time_result": item.get("timeResult"),
                                "raw": item,
                            })

                        if not data.get("hasMore"):
                            break
                        offset += 50

                    except Exception as e:
                        logger.warning("dingtalk_attendance_fetch_failed", error=str(e))
                        break

        return records

    async def _save_attendance_record(
        self, record: Dict[str, Any], config: BrandIMConfig
    ):
        """保存考勤记录到本地表"""
        userid = record["userid"]
        platform = record["platform"]
        checkin_time = record.get("checkin_time")

        if not checkin_time:
            return

        # 查找员工
        if platform == "wechat_work":
            emp_result = await self.db.execute(
                select(Employee).where(Employee.wechat_userid == userid)
            )
        else:
            emp_result = await self.db.execute(
                select(Employee).where(Employee.dingtalk_userid == userid)
            )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            return

        # 写入考勤记录（如果模型存在）
        try:
            from ..models.hr_attendance import AttendanceRecord
            attendance_date = checkin_time.date()

            # 检查是否已存在
            existing = await self.db.execute(
                select(AttendanceRecord).where(
                    and_(
                        AttendanceRecord.employee_id == employee.id,
                        AttendanceRecord.attendance_date == attendance_date,
                    )
                )
            )
            if existing.scalar_one_or_none():
                return  # 已存在，跳过

            # 判断状态
            status = "present"
            exception_type = record.get("exception_type") or record.get("time_result")
            if exception_type:
                exc_str = str(exception_type).lower()
                if "late" in exc_str or "迟到" in exc_str:
                    status = "late"
                elif "absent" in exc_str or "缺卡" in exc_str:
                    status = "absent"
                elif "early" in exc_str or "早退" in exc_str:
                    status = "early_leave"

            att = AttendanceRecord(
                employee_id=employee.id,
                store_id=employee.store_id,
                attendance_date=attendance_date,
                check_in_time=checkin_time,
                status=status,
                source="im_sync",
                location=record.get("location_title"),
            )
            self.db.add(att)

        except ImportError:
            # AttendanceRecord 模型不存在时静默跳过
            logger.debug("attendance_model_not_found")
