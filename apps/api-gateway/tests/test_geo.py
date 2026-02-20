"""
Tests for geographic utility functions
地理位置工具函数测试
"""
import pytest
import math
from src.utils.geo import haversine_distance, is_within_radius, format_distance


class TestHaversineDistance:
    """测试Haversine距离计算"""

    def test_same_location(self):
        """测试相同位置的距离应该为0"""
        distance = haversine_distance(39.9042, 116.4074, 39.9042, 116.4074)
        assert distance == 0

    def test_beijing_to_shanghai(self):
        """测试北京到上海的距离(约1067公里)"""
        # 北京天安门: 39.9042°N, 116.4074°E
        # 上海外滩: 31.2304°N, 121.4737°E
        distance = haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
        # 实际距离约1067公里,允许1%的误差
        expected = 1067000  # 米
        assert abs(distance - expected) / expected < 0.01

    def test_short_distance(self):
        """测试短距离计算(1公里内)"""
        # 两个相距约1公里的点
        distance = haversine_distance(39.9042, 116.4074, 39.9142, 116.4074)
        # 纬度差0.01度约等于1.11公里
        assert 1000 < distance < 1200

    def test_negative_coordinates(self):
        """测试负坐标(南半球和西半球)"""
        # 悉尼到墨尔本
        distance = haversine_distance(-33.8688, 151.2093, -37.8136, 144.9631)
        # 实际距离约714公里
        expected = 714000
        assert abs(distance - expected) / expected < 0.05

    def test_cross_meridian(self):
        """测试跨越本初子午线的距离"""
        # 伦敦到巴黎
        distance = haversine_distance(51.5074, -0.1278, 48.8566, 2.3522)
        # 实际距离约344公里
        expected = 344000
        assert abs(distance - expected) / expected < 0.05


class TestIsWithinRadius:
    """测试半径内判断"""

    def test_within_radius(self):
        """测试点在半径内"""
        # 相距约1公里的两点,半径2公里
        result = is_within_radius(39.9042, 116.4074, 39.9142, 116.4074, 2000)
        assert result is True

    def test_outside_radius(self):
        """测试点在半径外"""
        # 相距约1公里的两点,半径500米
        result = is_within_radius(39.9042, 116.4074, 39.9142, 116.4074, 500)
        assert result is False

    def test_exactly_on_radius(self):
        """测试点恰好在半径边界上"""
        # 计算实际距离
        distance = haversine_distance(39.9042, 116.4074, 39.9142, 116.4074)
        # 使用实际距离作为半径
        result = is_within_radius(39.9042, 116.4074, 39.9142, 116.4074, distance)
        assert result is True

    def test_same_location_zero_radius(self):
        """测试相同位置,半径为0"""
        result = is_within_radius(39.9042, 116.4074, 39.9042, 116.4074, 0)
        assert result is True


class TestFormatDistance:
    """测试距离格式化"""

    def test_format_meters(self):
        """测试格式化米"""
        assert format_distance(500) == "500m"
        assert format_distance(999) == "999m"

    def test_format_kilometers(self):
        """测试格式化公里"""
        assert format_distance(1000) == "1.0km"
        assert format_distance(1500) == "1.5km"
        assert format_distance(12345) == "12.3km"

    def test_format_zero(self):
        """测试格式化0距离"""
        assert format_distance(0) == "0m"

    def test_format_large_distance(self):
        """测试格式化大距离"""
        assert format_distance(1000000) == "1000.0km"
