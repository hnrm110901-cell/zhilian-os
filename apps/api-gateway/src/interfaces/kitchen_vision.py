"""
FEAT-003: 厨房视觉接口预留

KitchenVisionInterface Protocol — 为 2027Q3 厨房视觉系统预留标准接口。

实现要求（待 2027Q3 接入实际摄像头/CV模型）：
1. 实现 KitchenVisionInterface Protocol
2. 提供菜品出品记录查询
3. 提供烹饪时间统计
4. 接入摄像头流分析（YOLOv8 或类似模型）

接口设计原则：
- 数据类定义完整，满足业务需求
- Protocol 约束实现方必须满足的方法签名
- TODO 注释标明 2027Q3 实现计划
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable


# ==================== 数据类 ====================

@dataclass
class DishOutputRecord:
    """
    菜品出品记录

    由厨房摄像头系统识别并记录，每次出品操作触发一条记录。
    """
    record_id: str
    dish_id: str
    dish_name: str
    station_id: str                 # 操作台/档口ID
    chef_id: Optional[str]          # 厨师ID（可选，取决于识别精度）
    output_count: int               # 出品份数
    recorded_at: datetime           # 记录时间（摄像头时间戳）
    confidence: float               # 识别置信度（0.0-1.0）
    image_path: Optional[str] = None  # 图像存储路径（可选）


@dataclass
class CookTimeStats:
    """
    烹饪时间统计

    按菜品/档口/时段统计烹饪时间，用于效率分析和预警。
    """
    sku_id: str
    dish_name: str
    station_id: str
    avg_cook_time_seconds: float    # 平均烹饪时间（秒）
    min_cook_time_seconds: float    # 最短烹饪时间
    max_cook_time_seconds: float    # 最长烹饪时间
    p95_cook_time_seconds: float    # 95分位数烹饪时间（用于 SLA 设定）
    sample_count: int               # 样本数量
    period_start: datetime          # 统计周期开始
    period_end: datetime            # 统计周期结束
    slow_count: int = 0             # 超时出品次数（>平均值 * 1.5）


# ==================== Protocol ====================

@runtime_checkable
class KitchenVisionInterface(Protocol):
    """
    厨房视觉系统接口

    TODO(2027Q3): 实现此接口，接入厨房摄像头和计算机视觉模型。

    实现建议：
    - 使用 YOLOv8 或 RT-DETR 进行菜品识别
    - 使用姿态估计（OpenPose）识别厨师操作
    - 摄像头流处理使用 RTSP + OpenCV
    - 延迟目标：出品识别 < 500ms
    """

    async def get_dish_output_records(
        self,
        store_id: str,
        start_time: datetime,
        end_time: datetime,
        station_id: Optional[str] = None,
        dish_id: Optional[str] = None,
    ) -> List[DishOutputRecord]:
        """
        查询菜品出品记录

        Args:
            store_id: 门店ID
            start_time: 查询开始时间
            end_time: 查询结束时间
            station_id: 档口ID（可选，不传则查所有档口）
            dish_id: 菜品ID（可选）

        Returns:
            List[DishOutputRecord]: 出品记录列表
        """
        ...  # TODO: 2027Q3 实现

    async def get_cook_time_stats(
        self,
        store_id: str,
        sku_ids: Optional[List[str]] = None,
        period_days: int = 7,
    ) -> List[CookTimeStats]:
        """
        获取烹饪时间统计

        Args:
            store_id: 门店ID
            sku_ids: 要统计的菜品ID列表（None 表示所有菜品）
            period_days: 统计周期（天）

        Returns:
            List[CookTimeStats]: 各菜品/档口的烹饪时间统计
        """
        ...  # TODO: 2027Q3 实现

    async def get_realtime_station_status(
        self,
        store_id: str,
    ) -> dict:
        """
        获取各档口实时状态

        Returns:
            Dict[station_id, status]，status 包含：
            - current_dish: 正在烹饪的菜品
            - cook_start_time: 开始时间
            - estimated_done_time: 预计完成时间
            - chef_id: 当前厨师
        """
        ...  # TODO: 2027Q3 实现


# ==================== 占位实现（返回空数据）====================

class KitchenVisionStub:
    """
    KitchenVisionInterface 占位实现

    在 2027Q3 接入真实摄像头系统之前，所有方法返回空数据。
    确保调用方代码在接口接入前可正常运行。
    """

    async def get_dish_output_records(
        self,
        store_id: str,
        start_time: datetime,
        end_time: datetime,
        station_id: Optional[str] = None,
        dish_id: Optional[str] = None,
    ) -> List[DishOutputRecord]:
        # TODO(2027Q3): 接入摄像头系统
        return []

    async def get_cook_time_stats(
        self,
        store_id: str,
        sku_ids: Optional[List[str]] = None,
        period_days: int = 7,
    ) -> List[CookTimeStats]:
        # TODO(2027Q3): 接入摄像头系统
        return []

    async def get_realtime_station_status(
        self,
        store_id: str,
    ) -> dict:
        # TODO(2027Q3): 接入摄像头系统
        return {}


# 全局占位实例（供其他模块导入使用）
kitchen_vision: KitchenVisionInterface = KitchenVisionStub()

assert isinstance(kitchen_vision, KitchenVisionInterface), (
    "KitchenVisionStub 必须满足 KitchenVisionInterface Protocol"
)
