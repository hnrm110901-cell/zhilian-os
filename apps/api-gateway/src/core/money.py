"""
金融计算工具
使用 Decimal 避免 float 精度问题

规则：
- 数据库存储金额单位为「分」（整数）
- 业务层展示/计算单位为「元」（Decimal）
- 禁止直接用 float 做金额乘除法

用法：
    from src.core.money import D, yuan_to_fen, fen_to_yuan, mul_rate

    fen = yuan_to_fen(order.total_amount)   # float/str → int(分)
    yuan = fen_to_yuan(record.total_amount) # int(分) → Decimal(元)
    fee = mul_rate(total_saved, "0.20")     # Decimal × 费率 → Decimal
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

Number = Union[int, float, str, Decimal]


def D(value: Number) -> Decimal:
    """安全地将任意数值转为 Decimal（避免 Decimal(float) 的精度陷阱）"""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def yuan_to_fen(yuan: Number) -> int:
    """元 → 分（四舍五入到整数分）"""
    return int((D(yuan) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fen_to_yuan(fen: Number) -> Decimal:
    """分 → 元（保留 2 位小数）"""
    return (D(fen) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def mul_rate(amount: Number, rate: Number) -> Decimal:
    """金额 × 费率，结果保留 2 位小数（四舍五入）"""
    return (D(amount) * D(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
