"""
抹零服务
支持按分/角/元级别抹零，统计抹零损失
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

import structlog

logger = structlog.get_logger()


class RoundingLevel(str, Enum):
    """抹零级别"""
    FEN = "fen"    # 抹分（实际不抹，保留原值）
    JIAO = "jiao"  # 抹角（去掉分位）
    YUAN = "yuan"  # 抹元（去掉角+分位）


@dataclass
class RoundingRecord:
    """抹零记录"""
    order_id: str = ""
    store_id: str = ""
    original_fen: int = 0
    rounded_fen: int = 0
    loss_fen: int = 0  # 抹掉的金额（分）
    level: RoundingLevel = RoundingLevel.JIAO
    created_at: datetime = None

    @property
    def original_yuan(self) -> float:
        return round(self.original_fen / 100, 2)

    @property
    def rounded_yuan(self) -> float:
        return round(self.rounded_fen / 100, 2)

    @property
    def loss_yuan(self) -> float:
        return round(self.loss_fen / 100, 2)


class RoundingService:
    """抹零服务"""

    def __init__(self):
        self._records: List[RoundingRecord] = []

    @staticmethod
    def round_amount(amount_fen: int, level: RoundingLevel) -> Dict:
        """
        抹零计算
        FEN: 不抹（保持原值）
        JIAO: 抹分位（如 1234 -> 1230）
        YUAN: 抹角分位（如 1234 -> 1200）
        始终向下取整（对顾客有利）

        返回: {"original_fen", "original_yuan", "rounded_fen", "rounded_yuan", "loss_fen", "loss_yuan"}
        """
        if amount_fen < 0:
            raise ValueError("金额不能为负")

        if level == RoundingLevel.FEN:
            rounded = amount_fen
        elif level == RoundingLevel.JIAO:
            # 抹掉分位：向下取到最近的10分（1角）
            rounded = (amount_fen // 10) * 10
        elif level == RoundingLevel.YUAN:
            # 抹掉角和分位：向下取到最近的100分（1元）
            rounded = (amount_fen // 100) * 100
        else:
            rounded = amount_fen

        loss = amount_fen - rounded
        return {
            "original_fen": amount_fen,
            "original_yuan": round(amount_fen / 100, 2),
            "rounded_fen": rounded,
            "rounded_yuan": round(rounded / 100, 2),
            "loss_fen": loss,
            "loss_yuan": round(loss / 100, 2),
            "level": level.value,
        }

    def apply_rounding(
        self,
        order_id: str,
        store_id: str,
        amount_fen: int,
        level: RoundingLevel,
    ) -> RoundingRecord:
        """应用抹零并记录"""
        result = self.round_amount(amount_fen, level)
        record = RoundingRecord(
            order_id=order_id,
            store_id=store_id,
            original_fen=amount_fen,
            rounded_fen=result["rounded_fen"],
            loss_fen=result["loss_fen"],
            level=level,
            created_at=datetime.now(timezone.utc),
        )
        self._records.append(record)
        if result["loss_fen"] > 0:
            logger.info("抹零", order_id=order_id, loss_yuan=result["loss_yuan"], level=level.value)
        return record

    def calculate_loss(self, amount_fen: int, level: RoundingLevel) -> Dict:
        """计算抹零损失（不记录）"""
        return self.round_amount(amount_fen, level)

    def batch_stats(self, store_id: str, date: datetime = None) -> Dict:
        """按门店统计抹零损失"""
        target_date = (date or datetime.now(timezone.utc)).date()
        records = [
            r for r in self._records
            if r.store_id == store_id and r.created_at and r.created_at.date() == target_date
        ]
        total_loss_fen = sum(r.loss_fen for r in records)
        by_level: Dict[str, Dict] = {}
        for r in records:
            lv = r.level.value
            if lv not in by_level:
                by_level[lv] = {"count": 0, "loss_fen": 0}
            by_level[lv]["count"] += 1
            by_level[lv]["loss_fen"] += r.loss_fen
        # 补上yuan字段
        for lv_data in by_level.values():
            lv_data["loss_yuan"] = round(lv_data["loss_fen"] / 100, 2)
        return {
            "store_id": store_id,
            "date": target_date.isoformat(),
            "total_count": len(records),
            "total_loss_fen": total_loss_fen,
            "total_loss_yuan": round(total_loss_fen / 100, 2),
            "by_level": by_level,
        }
