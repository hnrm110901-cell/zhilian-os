"""
急推菜服务
管理临期/滞销菜品的急推促销，同步到各渠道(KDS/外卖/大屏)，追踪效果
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class RushReason(str, Enum):
    """急推原因"""
    EXPIRING = "expiring"          # 食材临期
    OVERSTOCK = "overstock"        # 库存过多
    SLOW_SELLING = "slow_selling"  # 当日滞销
    CHEF_RECOMMEND = "chef_recommend"  # 厨师长推荐（加工好的半成品）
    SEASONAL = "seasonal"          # 时令推荐


class RushChannel(str, Enum):
    """推送渠道"""
    KDS = "kds"              # 厨显/出品屏
    FLOOR_SCREEN = "floor_screen"  # 楼面大屏
    WECHAT_MINI = "wechat_mini"    # 小程序
    MEITUAN = "meituan"      # 美团外卖
    ELEME = "eleme"          # 饿了么
    POS = "pos"              # 收银台弹窗


class RushStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    COMPLETED = "completed"


@dataclass
class RushPromotion:
    """急推菜记录"""
    rush_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    dish_id: str = ""
    dish_name: str = ""
    reason: RushReason = RushReason.EXPIRING
    # 促销信息
    original_price_fen: int = 0
    rush_price_fen: int = 0
    target_qty: int = 0  # 目标售出数量
    sold_qty: int = 0
    # 渠道与状态
    channels: List[RushChannel] = field(default_factory=list)
    synced_channels: List[str] = field(default_factory=list)
    status: RushStatus = RushStatus.ACTIVE
    # 时间
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expire_at: Optional[datetime] = None
    operator_id: str = ""
    note: str = ""

    @property
    def original_price_yuan(self) -> float:
        return round(self.original_price_fen / 100, 2)

    @property
    def rush_price_yuan(self) -> float:
        return round(self.rush_price_fen / 100, 2)

    @property
    def discount_rate(self) -> float:
        """折扣率（0~1）"""
        if self.original_price_fen == 0:
            return 0.0
        return round(self.rush_price_fen / self.original_price_fen, 2)

    @property
    def is_expired(self) -> bool:
        if self.expire_at is None:
            return False
        return datetime.now(timezone.utc) > self.expire_at


class RushPromotionService:
    """急推菜服务"""

    def __init__(self):
        self._rushes: Dict[str, RushPromotion] = {}

    def create_rush(
        self,
        store_id: str,
        dish_id: str,
        dish_name: str,
        reason: RushReason,
        original_price_fen: int,
        rush_price_fen: int,
        target_qty: int,
        channels: Optional[List[RushChannel]] = None,
        expire_hours: float = 4.0,
        operator_id: str = "",
        note: str = "",
    ) -> RushPromotion:
        """创建急推菜"""
        if rush_price_fen <= 0:
            raise ValueError("急推价必须大于0")
        if rush_price_fen >= original_price_fen:
            raise ValueError("急推价必须低于原价")
        if target_qty <= 0:
            raise ValueError("目标数量必须大于0")

        rush = RushPromotion(
            store_id=store_id,
            dish_id=dish_id,
            dish_name=dish_name,
            reason=reason,
            original_price_fen=original_price_fen,
            rush_price_fen=rush_price_fen,
            target_qty=target_qty,
            channels=channels or [RushChannel.KDS, RushChannel.POS],
            expire_at=datetime.now(timezone.utc) + timedelta(hours=expire_hours),
            operator_id=operator_id,
            note=note,
        )
        self._rushes[rush.rush_id] = rush
        logger.info(
            "创建急推菜",
            rush_id=rush.rush_id,
            dish=dish_name,
            reason=reason.value,
            rush_yuan=rush.rush_price_yuan,
        )
        return rush

    def sync_to_channels(self, rush_id: str) -> Dict:
        """同步急推信息到各渠道（模拟）"""
        rush = self._get_rush(rush_id)
        if rush.status != RushStatus.ACTIVE:
            raise ValueError(f"急推已结束: {rush.status.value}")
        results = {}
        for ch in rush.channels:
            # 模拟同步，实际会调用各渠道API
            success = True
            results[ch.value] = {"synced": success}
            if success:
                rush.synced_channels.append(ch.value)
        logger.info("急推同步到渠道", rush_id=rush_id, channels=[c.value for c in rush.channels])
        return {"rush_id": rush_id, "sync_results": results}

    def cancel_rush(self, rush_id: str, reason: str = "") -> RushPromotion:
        """取消急推"""
        rush = self._get_rush(rush_id)
        if rush.status != RushStatus.ACTIVE:
            raise ValueError("急推已结束，无法取消")
        rush.status = RushStatus.CANCELLED
        logger.info("取消急推", rush_id=rush_id, reason=reason)
        return rush

    def record_sale(self, rush_id: str, qty: int = 1) -> RushPromotion:
        """记录急推菜售出"""
        rush = self._get_rush(rush_id)
        if rush.status != RushStatus.ACTIVE:
            raise ValueError("急推已结束")
        rush.sold_qty += qty
        if rush.sold_qty >= rush.target_qty:
            rush.status = RushStatus.COMPLETED
            logger.info("急推菜已售罄", rush_id=rush_id, sold=rush.sold_qty)
        return rush

    def auto_detect_expiring(
        self,
        store_id: str,
        inventory_items: List[Dict],
        expiry_hours: int = 24,
    ) -> List[Dict]:
        """
        自动检测临期食材，生成急推建议
        inventory_items: [{"dish_id": "...", "dish_name": "...", "expiry_time": datetime, "qty": int, "price_fen": int}]
        """
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(hours=expiry_hours)
        suggestions = []
        for item in inventory_items:
            expiry = item.get("expiry_time")
            if expiry and expiry <= threshold:
                hours_left = max(0, (expiry - now).total_seconds() / 3600)
                # 根据剩余时间计算建议折扣
                if hours_left < 4:
                    discount = 0.5  # 5折
                elif hours_left < 12:
                    discount = 0.7  # 7折
                else:
                    discount = 0.85  # 8.5折
                suggested_price = int(item["price_fen"] * discount)
                suggestions.append({
                    "dish_id": item["dish_id"],
                    "dish_name": item["dish_name"],
                    "original_price_fen": item["price_fen"],
                    "suggested_price_fen": suggested_price,
                    "suggested_price_yuan": round(suggested_price / 100, 2),
                    "discount": discount,
                    "qty_available": item.get("qty", 0),
                    "hours_until_expiry": round(hours_left, 1),
                    "urgency": "高" if hours_left < 4 else ("中" if hours_left < 12 else "低"),
                })
        suggestions.sort(key=lambda x: x["hours_until_expiry"])
        logger.info("临期食材检测", store_id=store_id, count=len(suggestions))
        return suggestions

    def get_active_rushes(self, store_id: str) -> List[RushPromotion]:
        """获取门店当前活跃的急推菜"""
        now = datetime.now(timezone.utc)
        result = []
        for rush in self._rushes.values():
            if rush.store_id != store_id:
                continue
            # 自动过期
            if rush.status == RushStatus.ACTIVE and rush.is_expired:
                rush.status = RushStatus.EXPIRED
            if rush.status == RushStatus.ACTIVE:
                result.append(rush)
        return result

    def get_effectiveness(self, rush_id: str) -> Dict:
        """获取急推效果评估"""
        rush = self._get_rush(rush_id)
        completion_rate = round(rush.sold_qty / rush.target_qty, 2) if rush.target_qty > 0 else 0
        # 折扣损失 = (原价 - 急推价) × 售出数量
        discount_loss_fen = (rush.original_price_fen - rush.rush_price_fen) * rush.sold_qty
        # 挽回收入 = 急推价 × 售出数量（否则可能全部损耗）
        recovered_fen = rush.rush_price_fen * rush.sold_qty
        return {
            "rush_id": rush_id,
            "dish_name": rush.dish_name,
            "target_qty": rush.target_qty,
            "sold_qty": rush.sold_qty,
            "completion_rate": completion_rate,
            "discount_rate": rush.discount_rate,
            "discount_loss_fen": discount_loss_fen,
            "discount_loss_yuan": round(discount_loss_fen / 100, 2),
            "recovered_revenue_fen": recovered_fen,
            "recovered_revenue_yuan": round(recovered_fen / 100, 2),
            "status": rush.status.value,
        }

    def generate_kds_alert(self, rush_id: str) -> Dict:
        """生成KDS（厨显）提醒数据"""
        rush = self._get_rush(rush_id)
        return {
            "alert_type": "rush_promotion",
            "rush_id": rush_id,
            "dish_name": rush.dish_name,
            "rush_price_yuan": rush.rush_price_yuan,
            "original_price_yuan": rush.original_price_yuan,
            "reason": rush.reason.value,
            "remaining_qty": max(0, rush.target_qty - rush.sold_qty),
            "urgency": "高" if rush.reason == RushReason.EXPIRING else "中",
            "display_text": f"【急推】{rush.dish_name} ¥{rush.rush_price_yuan}（原¥{rush.original_price_yuan}）剩{max(0, rush.target_qty - rush.sold_qty)}份",
        }

    def _get_rush(self, rush_id: str) -> RushPromotion:
        if rush_id not in self._rushes:
            raise ValueError(f"急推记录不存在: {rush_id}")
        return self._rushes[rush_id]
