"""
数据模型映射器
用于在不同系统间转换数据格式
"""
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal


class DataMapper:
    """数据模型映射器"""

    @staticmethod
    def yuan_to_fen(yuan: float) -> int:
        """
        元转分

        Args:
            yuan: 金额（元）

        Returns:
            金额（分）
        """
        return int(yuan * 100)

    @staticmethod
    def fen_to_yuan(fen: int) -> Decimal:
        """
        分转元

        Args:
            fen: 金额（分）

        Returns:
            金额（元）
        """
        return Decimal(fen) / 100

    @staticmethod
    def format_datetime(dt: datetime, format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """
        格式化日期时间

        Args:
            dt: 日期时间对象
            format: 格式字符串

        Returns:
            格式化后的字符串
        """
        return dt.strftime(format)

    @staticmethod
    def parse_datetime(dt_str: str, format: str = "%Y-%m-%d %H:%M:%S") -> datetime:
        """
        解析日期时间字符串

        Args:
            dt_str: 日期时间字符串
            format: 格式字符串

        Returns:
            日期时间对象
        """
        return datetime.strptime(dt_str, format)

    @staticmethod
    def map_member(source_data: Dict[str, Any], source_system: str) -> Dict[str, Any]:
        """
        会员数据映射

        Args:
            source_data: 源数据
            source_system: 源系统名称 (aoqiwei, pinzhi)

        Returns:
            标准化的会员数据
        """
        if source_system == "aoqiwei":
            return {
                "member_id": source_data.get("cardNo"),
                "mobile": source_data.get("mobile"),
                "name": source_data.get("name"),
                "sex": source_data.get("sex"),
                "birthday": source_data.get("birthday"),
                "level": source_data.get("level"),
                "points": source_data.get("points"),
                "balance": DataMapper.fen_to_yuan(source_data.get("balance", 0)),
                "reg_time": source_data.get("regTime"),
                "reg_store": source_data.get("regStore"),
                "source_system": "aoqiwei",
            }
        elif source_system == "pinzhi":
            return {
                "member_id": source_data.get("vipCard"),
                "mobile": source_data.get("mobile"),
                "name": source_data.get("vipName"),
                "source_system": "pinzhi",
            }
        else:
            raise ValueError(f"不支持的源系统: {source_system}")

    @staticmethod
    def map_order(source_data: Dict[str, Any], source_system: str) -> Dict[str, Any]:
        """
        订单数据映射

        Args:
            source_data: 源数据
            source_system: 源系统名称

        Returns:
            标准化的订单数据
        """
        if source_system == "aoqiwei":
            return {
                "order_id": source_data.get("orderId"),
                "order_no": source_data.get("orderNo"),
                "store_id": source_data.get("storeId"),
                "member_id": source_data.get("cardNo"),
                "total_amount": DataMapper.fen_to_yuan(
                    source_data.get("totalAmount", 0)
                ),
                "discount_amount": DataMapper.fen_to_yuan(
                    source_data.get("discountAmount", 0)
                ),
                "real_amount": DataMapper.fen_to_yuan(source_data.get("realAmount", 0)),
                "status": source_data.get("status"),
                "create_time": source_data.get("orderTime"),
                "pay_time": source_data.get("payTime"),
                "source_system": "aoqiwei",
            }
        elif source_system == "pinzhi":
            return {
                "order_id": source_data.get("billId"),
                "order_no": source_data.get("billNo"),
                "store_id": source_data.get("ognid"),
                "member_id": source_data.get("vipCard"),
                "total_amount": DataMapper.fen_to_yuan(
                    source_data.get("billPriceTotal", 0)
                ),
                "discount_amount": DataMapper.fen_to_yuan(
                    source_data.get("specialOfferPrice", 0)
                    + source_data.get("singleDiscountPrice", 0)
                ),
                "real_amount": DataMapper.fen_to_yuan(source_data.get("realPrice", 0)),
                "status": source_data.get("billStatus"),
                "create_time": source_data.get("openTime"),
                "pay_time": source_data.get("payTime"),
                "source_system": "pinzhi",
            }
        else:
            raise ValueError(f"不支持的源系统: {source_system}")
