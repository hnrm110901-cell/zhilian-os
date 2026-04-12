"""
固定资产管理服务
资产登记、直线法折旧计算、维护计划、报废处理
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class AssetCategory(str, Enum):
    """资产类别"""
    KITCHEN_EQUIPMENT = "kitchen_equipment"  # 厨房设备
    DINING_FURNITURE = "dining_furniture"    # 餐厅家具
    POS_DEVICE = "pos_device"               # 收银设备
    REFRIGERATION = "refrigeration"         # 冷链设备
    VEHICLE = "vehicle"                     # 车辆
    DECORATION = "decoration"               # 装修
    OTHER = "other"


class AssetStatus(str, Enum):
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    IDLE = "idle"
    SCRAPPED = "scrapped"


# 默认折旧年限（年）
DEFAULT_USEFUL_LIFE = {
    AssetCategory.KITCHEN_EQUIPMENT.value: 5,
    AssetCategory.DINING_FURNITURE.value: 5,
    AssetCategory.POS_DEVICE.value: 3,
    AssetCategory.REFRIGERATION.value: 8,
    AssetCategory.VEHICLE.value: 4,
    AssetCategory.DECORATION.value: 5,
    AssetCategory.OTHER.value: 5,
}


@dataclass
class Asset:
    """固定资产"""
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    name: str = ""
    category: AssetCategory = AssetCategory.OTHER
    status: AssetStatus = AssetStatus.IN_USE
    # 金额（分）
    purchase_price_fen: int = 0     # 购入价
    salvage_value_fen: int = 0      # 残值
    # 时间
    purchase_date: Optional[date] = None
    useful_life_years: int = 5      # 使用年限
    # 维护
    last_maintenance: Optional[date] = None
    next_maintenance: Optional[date] = None
    maintenance_interval_days: int = 90  # 维护周期（天）
    location: str = ""
    serial_no: str = ""
    note: str = ""

    @property
    def purchase_price_yuan(self) -> float:
        return round(self.purchase_price_fen / 100, 2)

    @property
    def salvage_value_yuan(self) -> float:
        return round(self.salvage_value_fen / 100, 2)


@dataclass
class MaintenanceRecord:
    """维护记录"""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = ""
    maintenance_date: date = field(default_factory=date.today)
    description: str = ""
    cost_fen: int = 0
    operator: str = ""

    @property
    def cost_yuan(self) -> float:
        return round(self.cost_fen / 100, 2)


class AssetManagementService:
    """固定资产管理服务"""

    def __init__(self):
        self._assets: Dict[str, Asset] = {}
        self._maintenance_records: Dict[str, List[MaintenanceRecord]] = {}

    def register(
        self,
        store_id: str,
        name: str,
        category: AssetCategory,
        purchase_price_fen: int,
        purchase_date: Optional[date] = None,
        salvage_value_fen: int = 0,
        useful_life_years: Optional[int] = None,
        serial_no: str = "",
        location: str = "",
    ) -> Asset:
        """登记固定资产"""
        if purchase_price_fen <= 0:
            raise ValueError("购入价必须大于0")
        life = useful_life_years or DEFAULT_USEFUL_LIFE.get(category.value, 5)
        asset = Asset(
            store_id=store_id,
            name=name,
            category=category,
            purchase_price_fen=purchase_price_fen,
            salvage_value_fen=salvage_value_fen,
            purchase_date=purchase_date or date.today(),
            useful_life_years=life,
            serial_no=serial_no,
            location=location,
        )
        self._assets[asset.asset_id] = asset
        self._maintenance_records[asset.asset_id] = []
        logger.info("登记固定资产", asset_id=asset.asset_id, name=name,
                     price_yuan=asset.purchase_price_yuan)
        return asset

    def calculate_depreciation(self, asset_id: str, as_of_date: Optional[date] = None) -> Dict:
        """
        计算折旧（直线法）
        年折旧额 = (原值 - 残值) / 使用年限
        已提折旧 = 年折旧额 × 已使用年数
        净值 = 原值 - 已提折旧
        """
        asset = self._get_asset(asset_id)
        ref_date = as_of_date or date.today()

        if asset.purchase_date is None:
            raise ValueError("资产缺少购入日期")

        # 计算已使用天数和年数
        days_used = (ref_date - asset.purchase_date).days
        years_used = days_used / 365.25
        total_life_days = asset.useful_life_years * 365.25

        # 年折旧额（分）
        depreciable = asset.purchase_price_fen - asset.salvage_value_fen
        annual_depreciation_fen = depreciable // asset.useful_life_years if asset.useful_life_years > 0 else 0

        # 累计折旧（分），不超过可折旧总额
        accumulated_fen = int(min(depreciable, annual_depreciation_fen * years_used))
        # 净值
        net_value_fen = asset.purchase_price_fen - accumulated_fen

        return {
            "asset_id": asset_id,
            "name": asset.name,
            "purchase_price_fen": asset.purchase_price_fen,
            "purchase_price_yuan": asset.purchase_price_yuan,
            "salvage_value_fen": asset.salvage_value_fen,
            "salvage_value_yuan": asset.salvage_value_yuan,
            "useful_life_years": asset.useful_life_years,
            "years_used": round(years_used, 2),
            "annual_depreciation_fen": annual_depreciation_fen,
            "annual_depreciation_yuan": round(annual_depreciation_fen / 100, 2),
            "accumulated_depreciation_fen": accumulated_fen,
            "accumulated_depreciation_yuan": round(accumulated_fen / 100, 2),
            "net_value_fen": net_value_fen,
            "net_value_yuan": round(net_value_fen / 100, 2),
            "depreciation_complete": years_used >= asset.useful_life_years,
        }

    def schedule_maintenance(
        self,
        asset_id: str,
        interval_days: Optional[int] = None,
    ) -> Asset:
        """安排维护计划"""
        asset = self._get_asset(asset_id)
        if interval_days:
            asset.maintenance_interval_days = interval_days
        today = date.today()
        asset.next_maintenance = today + timedelta(days=asset.maintenance_interval_days)
        logger.info("安排维护计划", asset_id=asset_id, next=str(asset.next_maintenance))
        return asset

    def record_maintenance(
        self,
        asset_id: str,
        description: str,
        cost_fen: int = 0,
        operator: str = "",
    ) -> MaintenanceRecord:
        """记录维护"""
        asset = self._get_asset(asset_id)
        record = MaintenanceRecord(
            asset_id=asset_id,
            description=description,
            cost_fen=cost_fen,
            operator=operator,
        )
        self._maintenance_records[asset_id].append(record)
        asset.last_maintenance = record.maintenance_date
        asset.next_maintenance = record.maintenance_date + timedelta(days=asset.maintenance_interval_days)
        asset.status = AssetStatus.IN_USE
        return record

    def get_report(self, store_id: str) -> Dict:
        """获取门店资产报告"""
        assets = [a for a in self._assets.values() if a.store_id == store_id]
        total_purchase_fen = sum(a.purchase_price_fen for a in assets)
        # 计算总净值
        total_net_fen = 0
        for a in assets:
            try:
                dep = self.calculate_depreciation(a.asset_id)
                total_net_fen += dep["net_value_fen"]
            except ValueError:
                total_net_fen += a.purchase_price_fen

        by_category: Dict[str, int] = {}
        for a in assets:
            cat = a.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        by_status: Dict[str, int] = {}
        for a in assets:
            st = a.status.value
            by_status[st] = by_status.get(st, 0) + 1

        # 需要维护的资产
        today = date.today()
        due_maintenance = [
            a for a in assets
            if a.next_maintenance and a.next_maintenance <= today and a.status != AssetStatus.SCRAPPED
        ]

        return {
            "store_id": store_id,
            "total_assets": len(assets),
            "total_purchase_fen": total_purchase_fen,
            "total_purchase_yuan": round(total_purchase_fen / 100, 2),
            "total_net_value_fen": total_net_fen,
            "total_net_value_yuan": round(total_net_fen / 100, 2),
            "by_category": by_category,
            "by_status": by_status,
            "due_maintenance_count": len(due_maintenance),
            "due_maintenance_assets": [a.name for a in due_maintenance],
        }

    def scrap(self, asset_id: str, reason: str = "") -> Asset:
        """报废资产"""
        asset = self._get_asset(asset_id)
        if asset.status == AssetStatus.SCRAPPED:
            raise ValueError("资产已报废")
        asset.status = AssetStatus.SCRAPPED
        logger.info("资产报废", asset_id=asset_id, name=asset.name, reason=reason)
        return asset

    def _get_asset(self, asset_id: str) -> Asset:
        if asset_id not in self._assets:
            raise ValueError(f"资产不存在: {asset_id}")
        return self._assets[asset_id]
