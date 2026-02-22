"""
中国法定节假日数据
用于销售预测的特征工程
"""
from datetime import date, datetime
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


class ChineseHolidays:
    """
    中国法定节假日和特殊日期
    """

    # 2026年法定节假日（示例数据）
    HOLIDAYS_2026 = {
        # 元旦
        date(2026, 1, 1): {"name": "元旦", "type": "法定节假日", "impact": "high"},
        date(2026, 1, 2): {"name": "元旦调休", "type": "调休", "impact": "medium"},
        date(2026, 1, 3): {"name": "元旦调休", "type": "调休", "impact": "medium"},

        # 春节
        date(2026, 2, 17): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 18): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 19): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 20): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 21): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 22): {"name": "春节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 2, 23): {"name": "春节", "type": "法定节假日", "impact": "very_high"},

        # 清明节
        date(2026, 4, 4): {"name": "清明节", "type": "法定节假日", "impact": "high"},
        date(2026, 4, 5): {"name": "清明节", "type": "法定节假日", "impact": "high"},
        date(2026, 4, 6): {"name": "清明节", "type": "法定节假日", "impact": "high"},

        # 劳动节
        date(2026, 5, 1): {"name": "劳动节", "type": "法定节假日", "impact": "high"},
        date(2026, 5, 2): {"name": "劳动节", "type": "法定节假日", "impact": "high"},
        date(2026, 5, 3): {"name": "劳动节", "type": "法定节假日", "impact": "high"},

        # 端午节
        date(2026, 6, 19): {"name": "端午节", "type": "法定节假日", "impact": "high"},
        date(2026, 6, 20): {"name": "端午节", "type": "法定节假日", "impact": "high"},
        date(2026, 6, 21): {"name": "端午节", "type": "法定节假日", "impact": "high"},

        # 中秋节
        date(2026, 9, 25): {"name": "中秋节", "type": "法定节假日", "impact": "high"},
        date(2026, 9, 26): {"name": "中秋节", "type": "法定节假日", "impact": "high"},
        date(2026, 9, 27): {"name": "中秋节", "type": "法定节假日", "impact": "high"},

        # 国庆节
        date(2026, 10, 1): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 2): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 3): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 4): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 5): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 6): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
        date(2026, 10, 7): {"name": "国庆节", "type": "法定节假日", "impact": "very_high"},
    }

    # 特殊营销日期
    SPECIAL_DAYS_2026 = {
        date(2026, 2, 14): {"name": "情人节", "type": "营销节日", "impact": "high"},
        date(2026, 3, 8): {"name": "妇女节", "type": "营销节日", "impact": "medium"},
        date(2026, 5, 10): {"name": "母亲节", "type": "营销节日", "impact": "medium"},
        date(2026, 6, 21): {"name": "父亲节", "type": "营销节日", "impact": "medium"},
        date(2026, 11, 11): {"name": "双十一", "type": "营销节日", "impact": "high"},
        date(2026, 12, 12): {"name": "双十二", "type": "营销节日", "impact": "medium"},
        date(2026, 12, 24): {"name": "平安夜", "type": "营销节日", "impact": "high"},
        date(2026, 12, 25): {"name": "圣诞节", "type": "营销节日", "impact": "high"},
    }

    @classmethod
    def is_holiday(cls, target_date: date) -> bool:
        """判断是否为节假日"""
        return target_date in cls.HOLIDAYS_2026

    @classmethod
    def is_special_day(cls, target_date: date) -> bool:
        """判断是否为特殊营销日"""
        return target_date in cls.SPECIAL_DAYS_2026

    @classmethod
    def get_holiday_info(cls, target_date: date) -> Optional[Dict]:
        """获取节假日信息"""
        return cls.HOLIDAYS_2026.get(target_date) or cls.SPECIAL_DAYS_2026.get(target_date)

    @classmethod
    def get_holiday_impact_score(cls, target_date: date) -> float:
        """
        获取节假日影响系数

        Returns:
            影响系数：1.0-2.5
        """
        info = cls.get_holiday_info(target_date)
        if not info:
            return 1.0

        impact_map = {
            "very_high": 2.5,  # 春节、国庆
            "high": 2.0,  # 其他法定节假日、情人节
            "medium": 1.5,  # 调休、一般营销节日
            "low": 1.2,  # 小型节日
        }

        return impact_map.get(info.get("impact", "low"), 1.0)

    @classmethod
    def is_holiday_eve(cls, target_date: date) -> bool:
        """判断是否为节假日前一天"""
        from datetime import timedelta
        next_day = target_date + timedelta(days=1)
        return cls.is_holiday(next_day)

    @classmethod
    def get_days_to_next_holiday(cls, target_date: date) -> int:
        """获取距离下一个节假日的天数"""
        from datetime import timedelta

        for i in range(1, 365):
            check_date = target_date + timedelta(days=i)
            if cls.is_holiday(check_date):
                return i

        return 365  # 一年内没有节假日

    @classmethod
    def get_holiday_period(cls, target_date: date) -> Optional[str]:
        """
        获取节假日所属时期

        Returns:
            节假日时期：节前、节中、节后
        """
        from datetime import timedelta

        if cls.is_holiday(target_date):
            return "节中"

        # 检查是否为节前3天
        for i in range(1, 4):
            check_date = target_date + timedelta(days=i)
            if cls.is_holiday(check_date):
                return "节前"

        # 检查是否为节后3天
        for i in range(1, 4):
            check_date = target_date - timedelta(days=i)
            if cls.is_holiday(check_date):
                return "节后"

        return None


class WeatherImpact:
    """
    天气影响因子
    """

    # 天气类型对餐饮的影响系数
    WEATHER_IMPACT = {
        "晴天": 1.0,
        "多云": 1.0,
        "阴天": 0.95,
        "小雨": 0.85,
        "中雨": 0.7,
        "大雨": 0.5,
        "暴雨": 0.3,
        "雪": 0.6,
        "雾霾": 0.9,
    }

    # 温度对餐饮的影响（火锅店特别受益于寒冷天气）
    @staticmethod
    def get_temperature_impact(temperature: float, restaurant_type: str = "正餐") -> float:
        """
        根据温度获取影响系数

        Args:
            temperature: 温度（摄氏度）
            restaurant_type: 餐厅类型

        Returns:
            影响系数
        """
        if restaurant_type == "火锅":
            # 火锅店：温度越低，生意越好
            if temperature < 0:
                return 1.5
            elif temperature < 10:
                return 1.3
            elif temperature < 20:
                return 1.1
            elif temperature < 30:
                return 1.0
            else:
                return 0.8
        else:
            # 一般餐厅：极端温度影响客流
            if temperature < 0 or temperature > 35:
                return 0.8
            elif temperature < 10 or temperature > 30:
                return 0.9
            else:
                return 1.0

    @staticmethod
    def get_weather_impact(weather_type: str) -> float:
        """获取天气类型的影响系数"""
        return WeatherImpact.WEATHER_IMPACT.get(weather_type, 1.0)


class BusinessDistrictEvents:
    """
    商圈活动影响
    """

    # 活动类型影响系数
    EVENT_IMPACT = {
        "大型展会": 1.8,
        "音乐会": 1.5,
        "体育赛事": 1.6,
        "商场促销": 1.3,
        "周边施工": 0.6,
        "交通管制": 0.7,
    }

    @staticmethod
    def get_event_impact(event_type: str) -> float:
        """获取活动类型的影响系数"""
        return BusinessDistrictEvents.EVENT_IMPACT.get(event_type, 1.0)
