"""
外卖订单会员归因服务 — Phase 2

功能：
1. 美团外卖订单归因到会员（手机号匹配）
2. 饿了么订单归因（同逻辑，字段名不同）
3. 多渠道统一消费历史视图（堂食 + 美团 + 饿了么 + 小程序）
4. 批量回填历史美团订单会员归因

注意：
- 外卖平台手机号可能加密，解密必须走现有密钥管理机制（当前为占位符）
- 归因失败时返回 None（不抛异常），记录日志后降级为匿名订单
- 所有数据库查询必须显式传入 brand_id / store_id
- 金额单位：数据库存分（fen）
"""

import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.brand_consumer_profile import BrandConsumerProfile
from src.models.consumer_identity import ConsumerIdentity
from src.repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo

logger = structlog.get_logger()

# ---------- 渠道常量 ----------
CHANNEL_MEITUAN = "meituan"
CHANNEL_ELEME = "eleme"
CHANNEL_POS = "pos"
CHANNEL_WECHAT_MP = "wechat_mp"
CHANNEL_MANUAL = "manual"


class DeliveryOrderAttributionService:
    """外卖订单会员归因服务

    核心逻辑：
    - 用手机号（phone_match）在 consumer_identities 中查找 One ID
    - 归因成功后写入 omnichannel_order_records 并更新品牌消费档案
    - 归因失败（无手机号/解密失败/无匹配）→ 写入匿名记录，返回 None
    """

    async def attribute_meituan_order(
        self,
        db: AsyncSession,
        order_data: dict,
        store_id: str,
        brand_id: str,
        group_id: str,
    ) -> Optional[str]:
        """
        美团外卖订单归因到会员。

        关键字段（美团外卖开放平台）：
        - buyer_phone / phone：买家手机号（可能加密）
        - order_id：美团订单号
        - total_price：订单金额（分）
        - created_time：下单时间（Unix 毫秒）

        Args:
            db         : 异步数据库 Session
            order_data : 美团订单原始数据
            store_id   : 门店 ID
            brand_id   : 品牌 ID
            group_id   : 集团 ID

        Returns:
            consumer_id（str）或 None（归因失败/匿名订单）
        """
        external_order_no = str(order_data.get("order_id", ""))

        # 幂等检查：同一美团订单不重复归因
        if await self._order_already_attributed(db, CHANNEL_MEITUAN, external_order_no):
            logger.info(
                "DeliveryAttribution: 美团订单已归因，跳过",
                order_id=external_order_no,
            )
            existing = await self._get_existing_attribution(
                db, CHANNEL_MEITUAN, external_order_no
            )
            return existing

        # 1. 提取并解密手机号
        phone = self._extract_meituan_phone(order_data)
        if not phone:
            await self._write_omnichannel_record(
                db,
                consumer_id=None,
                brand_id=brand_id,
                store_id=store_id,
                group_id=group_id,
                channel=CHANNEL_MEITUAN,
                external_order_no=external_order_no,
                amount_fen=self._extract_meituan_amount(order_data),
                item_count=order_data.get("item_count"),
                order_at=self._extract_meituan_order_at(order_data),
                attribution_status="anonymous",
                attribution_method=None,
                raw_platform_data=order_data,
            )
            logger.info(
                "DeliveryAttribution: 美团订单手机号为空，记为匿名",
                order_id=external_order_no,
                store_id=store_id,
            )
            return None

        # 2. 用手机号查 ConsumerIdentity
        consumer_id = await self._find_or_skip_consumer(db, phone)

        amount_fen = self._extract_meituan_amount(order_data)
        order_at = self._extract_meituan_order_at(order_data)

        if consumer_id:
            # 3. 更新 BrandConsumerProfile
            await self._update_brand_profile(
                db,
                consumer_id=consumer_id,
                brand_id=brand_id,
                group_id=group_id,
                amount_fen=amount_fen,
                order_at=order_at,
                channel=CHANNEL_MEITUAN,
            )
            attribution_status = "attributed"
            attribution_method = "phone_match"
        else:
            attribution_status = "anonymous"
            attribution_method = None

        # 4. 写入多渠道消费记录
        await self._write_omnichannel_record(
            db,
            consumer_id=uuid.UUID(consumer_id) if consumer_id else None,
            brand_id=brand_id,
            store_id=store_id,
            group_id=group_id,
            channel=CHANNEL_MEITUAN,
            external_order_no=external_order_no,
            amount_fen=amount_fen,
            item_count=order_data.get("item_count"),
            order_at=order_at,
            attribution_status=attribution_status,
            attribution_method=attribution_method,
            raw_platform_data=order_data,
        )

        # 5. 触发 RFM 重计算（异步，不阻塞归因结果）
        if consumer_id:
            await self._trigger_rfm_recalc(consumer_id, brand_id, store_id)

        logger.info(
            "DeliveryAttribution: 美团订单归因完成",
            order_id=external_order_no,
            consumer_id=consumer_id,
            status=attribution_status,
        )
        return consumer_id

    async def attribute_eleme_order(
        self,
        db: AsyncSession,
        order_data: dict,
        store_id: str,
        brand_id: str,
        group_id: str,
    ) -> Optional[str]:
        """
        饿了么订单归因（同美团逻辑，字段名不同）。

        关键字段差异（饿了么开放平台）：
        - user_phone / mobile：买家手机号
        - order_code / id：订单号
        - total_price：订单金额（分）
        - created_at：下单时间（ISO 格式字符串）
        """
        external_order_no = str(
            order_data.get("order_code") or order_data.get("id", "")
        )

        if await self._order_already_attributed(db, CHANNEL_ELEME, external_order_no):
            logger.info(
                "DeliveryAttribution: 饿了么订单已归因，跳过",
                order_id=external_order_no,
            )
            return await self._get_existing_attribution(
                db, CHANNEL_ELEME, external_order_no
            )

        phone = self._extract_eleme_phone(order_data)
        amount_fen = int(order_data.get("total_price", 0))
        order_at = self._parse_eleme_order_at(order_data)

        consumer_id = None
        if phone:
            consumer_id = await self._find_or_skip_consumer(db, phone)

        if consumer_id:
            await self._update_brand_profile(
                db,
                consumer_id=consumer_id,
                brand_id=brand_id,
                group_id=group_id,
                amount_fen=amount_fen,
                order_at=order_at,
                channel=CHANNEL_ELEME,
            )
            attribution_status = "attributed"
            attribution_method = "phone_match"
        else:
            attribution_status = "anonymous"
            attribution_method = None

        await self._write_omnichannel_record(
            db,
            consumer_id=uuid.UUID(consumer_id) if consumer_id else None,
            brand_id=brand_id,
            store_id=store_id,
            group_id=group_id,
            channel=CHANNEL_ELEME,
            external_order_no=external_order_no,
            amount_fen=amount_fen,
            item_count=order_data.get("item_count"),
            order_at=order_at,
            attribution_status=attribution_status,
            attribution_method=attribution_method,
            raw_platform_data=order_data,
        )

        if consumer_id:
            await self._trigger_rfm_recalc(consumer_id, brand_id, store_id)

        logger.info(
            "DeliveryAttribution: 饿了么订单归因完成",
            order_id=external_order_no,
            consumer_id=consumer_id,
            status=attribution_status,
        )
        return consumer_id

    async def get_omnichannel_order_history(
        self,
        db: AsyncSession,
        consumer_id: str,
        brand_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """
        多渠道统一消费历史视图。

        合并：堂食(omnichannel_order_records, channel=pos) + 美团 + 饿了么 + 小程序
        统一字段：order_no, channel, amount_fen, amount_yuan, store_id, created_at, attribution_status

        Args:
            db          : 异步数据库 Session
            consumer_id : 统一消费者 ID
            brand_id    : 品牌 ID（只返回该品牌下的消费记录）
            limit       : 最多返回条数

        Returns:
            统一消费历史列表，按时间倒序
        """
        try:
            cid = uuid.UUID(consumer_id)
        except ValueError:
            logger.error("DeliveryAttribution: 无效 consumer_id", consumer_id=consumer_id)
            return []

        stmt = text(
            """
            SELECT
                id,
                channel,
                external_order_no      AS order_no,
                amount_fen,
                item_count,
                store_id,
                order_at               AS created_at,
                attribution_status,
                attribution_method
            FROM omnichannel_order_records
            WHERE consumer_id = :consumer_id
              AND brand_id    = :brand_id
            ORDER BY order_at DESC
            LIMIT :limit
            """
        )

        result = await db.execute(
            stmt,
            {"consumer_id": cid, "brand_id": brand_id, "limit": limit},
        )
        rows = result.mappings().all()

        history = []
        for row in rows:
            history.append(
                {
                    "id": str(row["id"]),
                    "channel": row["channel"],
                    "order_no": row["order_no"],
                    "amount_fen": row["amount_fen"],
                    "amount_yuan": round(row["amount_fen"] / 100, 2),
                    "item_count": row["item_count"],
                    "store_id": row["store_id"],
                    "created_at": str(row["created_at"]) if row["created_at"] else None,
                    "attribution_status": row["attribution_status"],
                    "attribution_method": row["attribution_method"],
                }
            )

        return history

    async def batch_backfill_meituan_attribution(
        self,
        db: AsyncSession,
        store_id: str,
        brand_id: str,
        group_id: str,
        start_date: date,
        end_date: date,
        app_auth_token: str,
    ) -> Dict[str, int]:
        """
        批量回填历史美团订单的会员归因。

        流程：
        1. 调用 meituan_queue_service.sync_offline_order 获取历史订单列表
           （注：当前 meituan_queue_service 是等位 API，外卖历史订单拉取
            需使用美团外卖开放平台独立接口，此处以结构兼容方式实现）
        2. 批量执行 attribute_meituan_order
        3. 返回统计结果

        Args:
            db             : 异步数据库 Session
            store_id       : 门店 ID
            brand_id       : 品牌 ID
            group_id       : 集团 ID
            start_date     : 回填开始日期
            end_date       : 回填结束日期
            app_auth_token : 美团 API 授权 token

        Returns:
            {"total": N, "attributed": M, "anonymous": K, "error": E}
        """
        # 拉取历史订单（使用现有 meituan_queue_service 的 API 基础设施）
        orders = await self._fetch_meituan_historical_orders(
            start_date=start_date,
            end_date=end_date,
            app_auth_token=app_auth_token,
        )

        total = len(orders)
        attributed = 0
        anonymous = 0
        error_count = 0

        for order_data in orders:
            try:
                consumer_id = await self.attribute_meituan_order(
                    db=db,
                    order_data=order_data,
                    store_id=store_id,
                    brand_id=brand_id,
                    group_id=group_id,
                )
                if consumer_id:
                    attributed += 1
                else:
                    anonymous += 1
            except Exception as exc:
                error_count += 1
                logger.warning(
                    "DeliveryAttribution: 批量回填单笔订单失败",
                    order_id=order_data.get("order_id"),
                    error=str(exc),
                )

        logger.info(
            "DeliveryAttribution: 批量回填完成",
            store_id=store_id,
            brand_id=brand_id,
            total=total,
            attributed=attributed,
            anonymous=anonymous,
            error=error_count,
        )

        return {
            "total": total,
            "attributed": attributed,
            "anonymous": anonymous,
            "error": error_count,
        }

    # ---------- 私有辅助方法 ----------

    def _extract_meituan_phone(self, order_data: dict) -> Optional[str]:
        """
        提取美团订单手机号。

        注：美团外卖开放平台的手机号字段可能是加密字符串。
        解密逻辑必须通过现有密钥管理机制实现（KeyManagementService）。
        当前为占位符实现：直接取明文字段，加密场景需集成解密。
        """
        # 尝试多个可能的字段名
        raw_phone = (
            order_data.get("buyer_phone")
            or order_data.get("phone")
            or order_data.get("mobile")
        )

        if not raw_phone:
            return None

        # TODO: 若 raw_phone 是加密串（美团虚拟号），需调用 KeyManagementService.decrypt()
        # 当前仅处理明文手机号（本地测试 / 部分 API 版本返回明文）
        cleaned = str(raw_phone).strip().replace("-", "").replace(" ", "")
        if len(cleaned) == 11 and cleaned.isdigit():
            return cleaned

        # 加密手机号占位符处理
        logger.info(
            "DeliveryAttribution: 美团手机号疑似加密，归因失败降级匿名",
            raw_phone_prefix=str(raw_phone)[:4] if raw_phone else "",
        )
        return None

    def _extract_eleme_phone(self, order_data: dict) -> Optional[str]:
        """
        提取饿了么订单手机号。
        同美团，加密场景需接入 KeyManagementService.decrypt()。
        """
        raw_phone = (
            order_data.get("user_phone")
            or order_data.get("mobile")
            or order_data.get("phone")
        )
        if not raw_phone:
            return None

        cleaned = str(raw_phone).strip().replace("-", "").replace(" ", "")
        if len(cleaned) == 11 and cleaned.isdigit():
            return cleaned

        logger.info(
            "DeliveryAttribution: 饿了么手机号疑似加密，归因失败降级匿名",
            raw_phone_prefix=str(raw_phone)[:4] if raw_phone else "",
        )
        return None

    def _extract_meituan_amount(self, order_data: dict) -> int:
        """提取美团订单金额（分）"""
        # 美团 total_price 通常为分
        return int(order_data.get("total_price") or order_data.get("amount", 0))

    def _extract_meituan_order_at(self, order_data: dict) -> datetime:
        """提取美团订单时间"""
        ts = order_data.get("created_time") or order_data.get("takeNumTime")
        if ts:
            try:
                # 美团返回毫秒时间戳
                ts_int = int(ts)
                if ts_int > 1e12:
                    ts_int = ts_int // 1000
                return datetime.fromtimestamp(ts_int)
            except (ValueError, OSError):
                pass
        return datetime.utcnow()

    def _parse_eleme_order_at(self, order_data: dict) -> datetime:
        """解析饿了么订单时间（ISO 格式字符串或毫秒时间戳）"""
        ts = order_data.get("created_at") or order_data.get("order_time")
        if ts:
            try:
                if isinstance(ts, str):
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_int = int(ts)
                if ts_int > 1e12:
                    ts_int = ts_int // 1000
                return datetime.fromtimestamp(ts_int)
            except (ValueError, OSError):
                pass
        return datetime.utcnow()

    async def _find_or_skip_consumer(
        self, db: AsyncSession, phone: str
    ) -> Optional[str]:
        """用手机号查 ConsumerIdentity，未找到返回 None（不抛异常）"""
        try:
            result = await db.execute(
                select(ConsumerIdentity).where(
                    ConsumerIdentity.primary_phone == phone,
                    ConsumerIdentity.is_merged.is_(False),
                )
            )
            identity = result.scalar_one_or_none()
            return str(identity.id) if identity else None
        except Exception as exc:
            logger.warning(
                "DeliveryAttribution: 查询 ConsumerIdentity 异常",
                phone_prefix=phone[:3] if phone else "",
                error=str(exc),
            )
            return None

    async def _update_brand_profile(
        self,
        db: AsyncSession,
        consumer_id: str,
        brand_id: str,
        group_id: str,
        amount_fen: int,
        order_at: datetime,
        channel: str,
    ) -> None:
        """更新 BrandConsumerProfile（订单数 + 金额 + 最近下单时间）"""
        try:
            cid = uuid.UUID(consumer_id)
            existing = await BrandConsumerProfileRepo.get_by_consumer_and_brand(
                db, cid, brand_id
            )
            if existing:
                new_count = (existing.brand_order_count or 0) + 1
                new_amount = (existing.brand_order_amount_fen or 0) + amount_fen
                first_at = existing.brand_first_order_at or order_at
                last_at = (
                    order_at
                    if not existing.brand_last_order_at or order_at > existing.brand_last_order_at
                    else existing.brand_last_order_at
                )
                # 推进 lifecycle_state
                new_state = self._advance_lifecycle(
                    existing.lifecycle_state, new_count
                )
                await BrandConsumerProfileRepo.upsert_profile(
                    db,
                    consumer_id=cid,
                    brand_id=brand_id,
                    group_id=group_id,
                    brand_order_count=new_count,
                    brand_order_amount_fen=new_amount,
                    brand_first_order_at=first_at,
                    brand_last_order_at=last_at,
                    lifecycle_state=new_state,
                    registration_channel=channel,
                )
            else:
                await BrandConsumerProfileRepo.upsert_profile(
                    db,
                    consumer_id=cid,
                    brand_id=brand_id,
                    group_id=group_id,
                    brand_order_count=1,
                    brand_order_amount_fen=amount_fen,
                    brand_first_order_at=order_at,
                    brand_last_order_at=order_at,
                    lifecycle_state="registered",
                    registration_channel=channel,
                )
        except Exception as exc:
            logger.warning(
                "DeliveryAttribution: 更新 BrandConsumerProfile 失败",
                consumer_id=consumer_id,
                brand_id=brand_id,
                error=str(exc),
            )

    def _advance_lifecycle(self, current_state: str, order_count: int) -> str:
        """根据订单数推进 lifecycle_state（简化规则，Phase 3 可接入 ML 模型）"""
        if order_count >= 10:
            return "vip"
        elif order_count >= 3:
            return "repeat"
        elif order_count >= 1:
            return "registered"
        return current_state

    async def _write_omnichannel_record(
        self,
        db: AsyncSession,
        consumer_id: Optional[uuid.UUID],
        brand_id: str,
        store_id: str,
        group_id: str,
        channel: str,
        external_order_no: str,
        amount_fen: int,
        item_count: Optional[int],
        order_at: datetime,
        attribution_status: str,
        attribution_method: Optional[str],
        raw_platform_data: dict,
    ) -> None:
        """写入 omnichannel_order_records（幂等：channel + external_order_no 唯一约束）"""
        import json

        stmt = text(
            """
            INSERT INTO omnichannel_order_records (
                id, consumer_id, brand_id, store_id, group_id,
                channel, external_order_no, amount_fen, item_count,
                order_at, attribution_status, attribution_method,
                raw_platform_data, created_at
            ) VALUES (
                gen_random_uuid(), :consumer_id, :brand_id, :store_id, :group_id,
                :channel, :external_order_no, :amount_fen, :item_count,
                :order_at, :attribution_status, :attribution_method,
                :raw_platform_data, NOW()
            )
            ON CONFLICT ON CONSTRAINT uq_omni_channel_order DO NOTHING
            """
        )

        await db.execute(
            stmt,
            {
                "consumer_id": consumer_id,
                "brand_id": brand_id,
                "store_id": store_id,
                "group_id": group_id,
                "channel": channel,
                "external_order_no": external_order_no if external_order_no else None,
                "amount_fen": amount_fen,
                "item_count": item_count,
                "order_at": order_at,
                "attribution_status": attribution_status,
                "attribution_method": attribution_method,
                "raw_platform_data": json.dumps(raw_platform_data, ensure_ascii=False, default=str),
            },
        )

    async def _order_already_attributed(
        self, db: AsyncSession, channel: str, external_order_no: str
    ) -> bool:
        """幂等检查：订单是否已归因"""
        if not external_order_no:
            return False
        result = await db.execute(
            text(
                """
                SELECT 1 FROM omnichannel_order_records
                WHERE channel = :channel AND external_order_no = :order_no
                LIMIT 1
                """
            ),
            {"channel": channel, "order_no": external_order_no},
        )
        return result.scalar_one_or_none() is not None

    async def _get_existing_attribution(
        self, db: AsyncSession, channel: str, external_order_no: str
    ) -> Optional[str]:
        """获取已存在的归因 consumer_id"""
        result = await db.execute(
            text(
                """
                SELECT consumer_id::text FROM omnichannel_order_records
                WHERE channel = :channel AND external_order_no = :order_no
                LIMIT 1
                """
            ),
            {"channel": channel, "order_no": external_order_no},
        )
        row = result.scalar_one_or_none()
        return row

    async def _trigger_rfm_recalc(
        self, consumer_id: str, brand_id: str, store_id: str
    ) -> None:
        """
        触发 RFM 重计算（异步，不阻塞）。
        Phase 3 接入 Celery 任务队列；当前仅记录日志触发信号。
        """
        logger.info(
            "DeliveryAttribution: 触发 RFM 重计算信号",
            event_type="rfm_recalc_trigger",
            consumer_id=consumer_id,
            brand_id=brand_id,
            store_id=store_id,
        )

    async def _fetch_meituan_historical_orders(
        self,
        start_date: date,
        end_date: date,
        app_auth_token: str,
    ) -> List[dict]:
        """
        拉取美团历史外卖订单列表。

        注：美团外卖开放平台历史订单查询接口（非等位接口）需单独申请权限。
        当前通过 meituan_queue_service 的 API 基础设施发起请求（路径不同）。
        实际生产中替换为正确的外卖历史订单查询 endpoint。
        """
        try:
            from src.services.meituan_queue_service import MeituanQueueService

            svc = MeituanQueueService()
            # 构造历史订单查询参数（按实际 API 文档调整）
            biz_data = {
                "startTime": int(
                    datetime.combine(start_date, datetime.min.time()).timestamp() * 1000
                ),
                "endTime": int(
                    datetime.combine(end_date, datetime.max.time()).timestamp() * 1000
                ),
                "pageSize": 100,
                "pageIndex": 1,
            }
            # 注：此 endpoint 为示例，需替换为美团外卖历史订单 API
            result = await svc._make_request(
                "/dcpd/order/history/list", biz_data, app_auth_token
            )
            orders = result.get("data", {}).get("list", [])
            logger.info(
                "DeliveryAttribution: 拉取历史美团订单",
                count=len(orders),
                start=str(start_date),
                end=str(end_date),
            )
            return orders
        except Exception as exc:
            logger.warning(
                "DeliveryAttribution: 拉取历史美团订单失败",
                error=str(exc),
            )
            return []


# 全局单例
delivery_order_attribution_service = DeliveryOrderAttributionService()
