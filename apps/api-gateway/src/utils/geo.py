"""
Geographic utility functions
地理位置相关工具函数
"""
import math
from typing import Tuple


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    Calculate the great circle distance between two points on Earth
    使用Haversine公式计算两个地理坐标之间的距离

    Args:
        lat1: 第一个点的纬度
        lon1: 第一个点的经度
        lat2: 第二个点的纬度
        lon2: 第二个点的经度

    Returns:
        float: 距离(单位:米)

    Example:
        >>> # 北京天安门到上海外滩的距离
        >>> distance = haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
        >>> print(f"{distance:.2f} meters")
    """
    # 地球平均半径(米)
    EARTH_RADIUS = 6371000

    # 将角度转换为弧度
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine公式
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    # 计算距离
    distance = EARTH_RADIUS * c

    return distance


def is_within_radius(
    lat1: float, lon1: float, lat2: float, lon2: float, radius: float
) -> bool:
    """
    Check if two points are within a specified radius
    检查两个点是否在指定半径内

    Args:
        lat1: 第一个点的纬度
        lon1: 第一个点的经度
        lat2: 第二个点的纬度
        lon2: 第二个点的经度
        radius: 半径(单位:米)

    Returns:
        bool: 如果在半径内返回True,否则返回False
    """
    distance = haversine_distance(lat1, lon1, lat2, lon2)
    return distance <= radius


def format_distance(distance: float) -> str:
    """
    Format distance for display
    格式化距离用于显示

    Args:
        distance: 距离(单位:米)

    Returns:
        str: 格式化后的距离字符串

    Example:
        >>> format_distance(500)
        '500m'
        >>> format_distance(1500)
        '1.5km'
        >>> format_distance(12345)
        '12.3km'
    """
    if distance < 1000:
        return f"{int(distance)}m"
    else:
        return f"{distance / 1000:.1f}km"
