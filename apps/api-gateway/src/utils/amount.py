"""
金额转换工具函数 — 统一 fen ↔ yuan 转换

全局规范：
  - 数据库/内部计算：fen (int, 分)
  - API返回/展示：同时提供 fen 和 yuan
  - yuan 精度：Decimal, 保留2位小数
  - 禁止浮点除法处理金额，必须用 Decimal
"""

from decimal import Decimal, ROUND_HALF_UP


def fen_to_yuan(fen: int) -> Decimal:
    """分转元（Decimal精确计算）"""
    return Decimal(str(fen)) / Decimal("100")


def fen_to_yuan_str(fen: int) -> str:
    """分转元字符串（保留2位小数）"""
    return str(fen_to_yuan(fen).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def yuan_to_fen(yuan) -> int:
    """元转分（四舍五入到整数分）"""
    d = Decimal(str(yuan)) * Decimal("100")
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_yuan(fen: int) -> str:
    """格式化为¥金额字符串，如 ¥123.45"""
    return f"¥{fen_to_yuan_str(fen)}"


def amount_dict(fen: int, prefix: str = "") -> dict:
    """
    生成标准金额字典，同时包含 fen 和 yuan。

    用法:
        amount_dict(5800)           → {"amount_fen": 5800, "amount_yuan": "58.00"}
        amount_dict(5800, "total")  → {"total_fen": 5800, "total_yuan": "58.00"}
    """
    key_prefix = f"{prefix}_" if prefix else "amount_"
    return {
        f"{key_prefix}fen": fen,
        f"{key_prefix}yuan": fen_to_yuan_str(fen),
    }
