"""
条码管理服务
支持多种条码类型(EAN13/CODE128/QR/INTERNAL)的生成、扫描、批量入库、标签生成
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class BarcodeType(str, Enum):
    EAN13 = "ean13"
    CODE128 = "code128"
    QR = "qr"
    INTERNAL = "internal"  # 内部编码


@dataclass
class BarcodeRecord:
    """条码记录"""
    barcode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    barcode_type: BarcodeType = BarcodeType.INTERNAL
    barcode_value: str = ""
    # 关联信息
    item_id: str = ""       # 关联商品/食材ID
    item_name: str = ""
    item_type: str = ""     # "dish" / "ingredient" / "asset"
    store_id: str = ""
    price_fen: int = 0
    unit: str = ""          # 单位：份/kg/箱
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def price_yuan(self) -> float:
        return round(self.price_fen / 100, 2)


class BarcodeService:
    """条码管理服务"""

    def __init__(self):
        # barcode_value -> BarcodeRecord
        self._barcodes: Dict[str, BarcodeRecord] = {}
        # barcode_id -> BarcodeRecord（双索引）
        self._by_id: Dict[str, BarcodeRecord] = {}

    def generate(
        self,
        barcode_type: BarcodeType,
        item_id: str,
        item_name: str,
        item_type: str = "ingredient",
        store_id: str = "",
        price_fen: int = 0,
        unit: str = "",
        barcode_value: Optional[str] = None,
    ) -> BarcodeRecord:
        """
        生成条码
        如果未指定barcode_value，自动根据类型生成
        """
        if barcode_value is None:
            barcode_value = self._generate_value(barcode_type, item_id)

        if barcode_value in self._barcodes:
            raise ValueError(f"条码已存在: {barcode_value}")

        record = BarcodeRecord(
            barcode_type=barcode_type,
            barcode_value=barcode_value,
            item_id=item_id,
            item_name=item_name,
            item_type=item_type,
            store_id=store_id,
            price_fen=price_fen,
            unit=unit,
        )
        self._barcodes[barcode_value] = record
        self._by_id[record.barcode_id] = record
        logger.info("生成条码", barcode=barcode_value, item=item_name, type=barcode_type.value)
        return record

    def scan(self, barcode_value: str) -> Optional[BarcodeRecord]:
        """
        扫描条码，返回关联信息
        未找到返回 None
        """
        record = self._barcodes.get(barcode_value)
        if record:
            logger.info("扫码识别", barcode=barcode_value, item=record.item_name)
        else:
            logger.warning("未知条码", barcode=barcode_value)
        return record

    def batch_inbound(
        self,
        store_id: str,
        items: List[Dict],
    ) -> Dict:
        """
        批量入库（扫码入库）
        items: [{"barcode_value": "...", "qty": 5}, ...]
        返回入库结果
        """
        results = {"success": [], "not_found": [], "total_qty": 0}
        for item in items:
            bv = item["barcode_value"]
            qty = item.get("qty", 1)
            record = self._barcodes.get(bv)
            if record:
                results["success"].append({
                    "barcode": bv,
                    "item_name": record.item_name,
                    "qty": qty,
                    "price_fen": record.price_fen,
                    "price_yuan": record.price_yuan,
                    "subtotal_fen": record.price_fen * qty,
                    "subtotal_yuan": round(record.price_fen * qty / 100, 2),
                })
                results["total_qty"] += qty
            else:
                results["not_found"].append(bv)

        total_fen = sum(s["subtotal_fen"] for s in results["success"])
        results["total_amount_fen"] = total_fen
        results["total_amount_yuan"] = round(total_fen / 100, 2)
        logger.info("批量入库", store_id=store_id,
                     success=len(results["success"]), not_found=len(results["not_found"]))
        return results

    def generate_label(self, barcode_value: str) -> Dict:
        """
        生成打印标签数据
        包含条码、品名、价格、单位等信息
        """
        record = self._barcodes.get(barcode_value)
        if not record:
            raise ValueError(f"条码不存在: {barcode_value}")
        return {
            "barcode_value": record.barcode_value,
            "barcode_type": record.barcode_type.value,
            "item_name": record.item_name,
            "price_text": f"¥{record.price_yuan}" if record.price_fen > 0 else "",
            "unit": record.unit,
            "store_id": record.store_id,
            "print_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        }

    @staticmethod
    def _generate_value(barcode_type: BarcodeType, item_id: str) -> str:
        """根据类型自动生成条码值"""
        if barcode_type == BarcodeType.EAN13:
            # 简化的EAN13生成（12位+校验位）
            raw = hashlib.md5(item_id.encode()).hexdigest()[:12]
            digits = "".join(str(int(c, 16) % 10) for c in raw)
            return digits[:13]
        elif barcode_type == BarcodeType.CODE128:
            return f"TX{item_id[:10].upper().replace('-', '')}"
        elif barcode_type == BarcodeType.QR:
            return f"https://tunxiang.cn/item/{item_id}"
        else:
            # 内部编码
            return f"INT-{uuid.uuid4().hex[:8].upper()}"
