"""
WeatherAdapter - 和风天气 QWeather free-tier 封装
"""
import os
import httpx
import structlog
from typing import Optional, Dict, Any

logger = structlog.get_logger()

# QWeather icon code → WeatherImpact key 映射
ICON_TO_WEATHER: Dict[str, str] = {
    "100": "晴天", "101": "多云", "102": "多云", "103": "多云", "104": "阴天",
    "300": "小雨", "301": "小雨", "302": "中雨", "303": "大雨",
    "304": "暴雨", "305": "小雨", "306": "中雨", "307": "大雨",
    "308": "暴雨", "309": "小雨", "310": "暴雨", "311": "暴雨",
    "312": "暴雨", "313": "暴雨", "314": "小雨", "315": "中雨",
    "316": "大雨", "317": "暴雨", "318": "暴雨", "399": "小雨",
    "400": "雪", "401": "雪", "402": "雪", "403": "雪",
    "404": "雪", "405": "雪", "406": "雪", "407": "雪",
    "408": "雪", "409": "雪", "410": "雪", "499": "雪",
    "500": "雾霾", "501": "雾霾", "502": "雾霾", "503": "雾霾",
    "504": "雾霾", "507": "雾霾", "508": "雾霾", "509": "雾霾",
    "510": "雾霾", "511": "雾霾", "512": "雾霾", "513": "雾霾",
    "514": "雾霾", "515": "雾霾",
}


class WeatherAdapter:
    """和风天气适配器，获取明日天气预报"""

    BASE_URL = "https://devapi.qweather.com/v7/weather/3d"

    def __init__(self):
        self.api_key = os.getenv("QWEATHER_API_KEY")
        self.location = os.getenv("QWEATHER_LOCATION", "101010100")

    async def get_tomorrow_weather(self) -> Optional[Dict[str, Any]]:
        """
        获取明日天气预报

        Returns:
            {"temperature": int, "weather": str} or None（降级时返回 None）
        """
        if not self.api_key:
            logger.info("QWEATHER_API_KEY 未配置，跳过天气预报")
            return None

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"location": self.location, "key": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") != "200" or not data.get("daily"):
                logger.warning("QWeather API 返回异常", code=data.get("code"))
                return None

            # daily[0] = 今天, daily[1] = 明天
            daily = data["daily"]
            if len(daily) < 2:
                return None

            tomorrow = daily[1]
            icon_day = tomorrow.get("iconDay", "")
            weather_text = ICON_TO_WEATHER.get(icon_day, "多云")

            # 取白天最高温和夜间最低温的均值作为代表温度
            try:
                temp_max = int(tomorrow.get("tempMax", 20))
                temp_min = int(tomorrow.get("tempMin", 15))
                temperature = (temp_max + temp_min) // 2
            except (ValueError, TypeError):
                temperature = 20

            return {"temperature": temperature, "weather": weather_text}

        except Exception as e:
            logger.warning("获取天气预报失败，降级为历史基线", error=str(e))
            return None


# 全局单例
weather_adapter = WeatherAdapter()
