"""
海鲜称重秤硬件对接协议服务

核心能力：
  1. 多品牌协议支持（大华/梅特勒-托利多/顶尖）
  2. 多连接方式（串口/蓝牙/USB/网络）
  3. 称重读取 + 稳定判定
  4. 防篡改：HMAC 签名锁定称重结果
  5. 远程校准指令
  6. 设备状态与心跳

金额规则：本服务不涉及金额，重量单位统一为克(g)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# HMAC 密钥，从环境变量读取；未配置时生成随机密钥（仅限开发环境，生产必须配置）
_HMAC_SECRET = os.getenv("SCALE_HMAC_SECRET", "")
if not _HMAC_SECRET:
    import secrets as _secrets
    _HMAC_SECRET = _secrets.token_hex(32)
    logger.warning("SCALE_HMAC_SECRET 未配置，已生成随机密钥（仅限开发环境）")


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class ScaleBrand(str, Enum):
    """支持的秤品牌"""
    DAHUA = "dahua"                    # 大华
    METTLER_TOLEDO = "mettler_toledo"  # 梅特勒-托利多
    DINGJIAN = "dingjian"              # 顶尖


class ConnectionType(str, Enum):
    """连接方式"""
    SERIAL = "serial"        # 串口 RS232/RS485
    BLUETOOTH = "bluetooth"  # 蓝牙 BLE
    USB = "usb"              # USB HID
    NETWORK = "network"      # TCP/IP 网络


class ScaleStatus(str, Enum):
    """秤设备状态"""
    ONLINE = "online"            # 在线正常
    OFFLINE = "offline"          # 离线
    CALIBRATING = "calibrating"  # 校准中
    ERROR = "error"              # 异常


class CalibrationStatus(str, Enum):
    """校准状态"""
    PASSED = "passed"      # 校准通过
    PENDING = "pending"    # 待校准
    FAILED = "failed"      # 校准失败
    EXPIRED = "expired"    # 校准过期（超30天）


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class ScaleDevice:
    """秤设备注册信息"""

    def __init__(
        self,
        scale_id: str,
        brand: ScaleBrand,
        connection_type: ConnectionType,
        store_id: str,
        precision_g: float = 0.5,
        address: str = "",
        name: str = "",
    ):
        self.scale_id = scale_id
        self.brand = brand
        self.connection_type = connection_type
        self.store_id = store_id
        # 精度，单位克，如 0.5 表示 ±0.5g
        self.precision_g = precision_g
        self.address = address  # 串口路径/蓝牙MAC/IP:端口
        self.name = name or f"{brand.value}-{scale_id[:8]}"
        self.status = ScaleStatus.OFFLINE
        self.calibration_status = CalibrationStatus.PENDING
        self.last_heartbeat: Optional[str] = None
        self.last_calibration: Optional[str] = None
        self.registered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scale_id": self.scale_id,
            "brand": self.brand.value,
            "connection_type": self.connection_type.value,
            "store_id": self.store_id,
            "precision_g": self.precision_g,
            "address": self.address,
            "name": self.name,
            "status": self.status.value,
            "calibration_status": self.calibration_status.value,
            "last_heartbeat": self.last_heartbeat,
            "last_calibration": self.last_calibration,
            "registered_at": self.registered_at,
        }


class WeightReading:
    """单次称重读数"""

    def __init__(
        self,
        weight_g: float,
        is_stable: bool,
        scale_id: str,
        unit: str = "g",
        lock_token: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.weight_g = weight_g
        self.unit = unit
        self.is_stable = is_stable
        self.scale_id = scale_id
        self.lock_token = lock_token or ""
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weight_g": self.weight_g,
            "unit": self.unit,
            "is_stable": self.is_stable,
            "lock_token": self.lock_token,
            "timestamp": self.timestamp,
            "scale_id": self.scale_id,
        }


# ── 品牌协议解析器 ───────────────────────────────────────────────────────────

class _BaseBrandProtocol:
    """品牌协议基类"""

    brand: ScaleBrand

    def parse_weight_frame(self, raw_data: bytes) -> Dict[str, Any]:
        """解析称重帧数据，返回 {weight_g, is_stable}"""
        raise NotImplementedError

    def build_calibrate_command(self, target_weight_g: float) -> bytes:
        """构建校准指令帧"""
        raise NotImplementedError

    def build_zero_command(self) -> bytes:
        """构建置零指令"""
        raise NotImplementedError


class DahuaProtocol(_BaseBrandProtocol):
    """
    大华电子秤协议

    帧格式（简化）：STX(0x02) + 稳定标志(1B) + 重量BCD(6B) + 单位(1B) + ETX(0x03)
    稳定标志：0x20=不稳 0x53=稳定('S')
    """

    brand = ScaleBrand.DAHUA

    def parse_weight_frame(self, raw_data: bytes) -> Dict[str, Any]:
        if len(raw_data) < 10:
            raise ValueError("大华协议帧长度不足，需至少10字节")
        # 稳定标志在第2字节
        stable_byte = raw_data[1] if len(raw_data) > 1 else 0
        is_stable = stable_byte == 0x53  # 'S'
        # 重量字段在 [2:8]，BCD 编码
        weight_bcd = raw_data[2:8]
        weight_str = weight_bcd.decode("ascii", errors="replace").strip()
        try:
            weight_g = float(weight_str)
        except (ValueError, TypeError):
            weight_g = 0.0
        return {"weight_g": weight_g, "is_stable": is_stable}

    def build_calibrate_command(self, target_weight_g: float) -> bytes:
        # 大华校准指令：0x02 + 'C' + 重量ASCII(8B) + 0x03
        weight_ascii = f"{target_weight_g:08.1f}".encode("ascii")
        return b"\x02C" + weight_ascii + b"\x03"

    def build_zero_command(self) -> bytes:
        return b"\x02Z\x03"


class MettlerToledoProtocol(_BaseBrandProtocol):
    """
    梅特勒-托利多协议 (MT-SICS)

    返回格式：'S S     123.4 g\\r\\n'
    第一个S=命令回应, 第二个S=稳定(D=动态), 数值部分右对齐, 单位
    """

    brand = ScaleBrand.METTLER_TOLEDO

    def parse_weight_frame(self, raw_data: bytes) -> Dict[str, Any]:
        line = raw_data.decode("ascii", errors="replace").strip()
        if len(line) < 4:
            raise ValueError("梅特勒-托利多响应格式无效")
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"梅特勒-托利多解析失败: {line}")
        # parts[0] = 'S'(命令), parts[1] = 'S'/'D'(稳定/动态), parts[2] = 数值
        is_stable = parts[1] == "S"
        try:
            weight_g = float(parts[2])
        except (ValueError, TypeError):
            weight_g = 0.0
        return {"weight_g": weight_g, "is_stable": is_stable}

    def build_calibrate_command(self, target_weight_g: float) -> bytes:
        # MT-SICS 外部校准指令
        return f"CA {target_weight_g:.1f}\r\n".encode("ascii")

    def build_zero_command(self) -> bytes:
        return b"Z\r\n"


class DingjianProtocol(_BaseBrandProtocol):
    """
    顶尖电子秤协议

    帧格式：AA + 状态(1B) + 重量(4B little-endian, 单位0.1g) + 校验(1B) + 55
    状态位：bit0=稳定, bit1=负值, bit2=超载
    """

    brand = ScaleBrand.DINGJIAN

    def parse_weight_frame(self, raw_data: bytes) -> Dict[str, Any]:
        if len(raw_data) < 8:
            raise ValueError("顶尖协议帧长度不足，需至少8字节")
        if raw_data[0] != 0xAA or raw_data[-1] != 0x55:
            raise ValueError("顶尖协议帧头/帧尾不匹配")
        status = raw_data[1]
        is_stable = bool(status & 0x01)
        is_negative = bool(status & 0x02)
        # 重量4字节 little-endian，单位 0.1g
        weight_raw = int.from_bytes(raw_data[2:6], byteorder="little", signed=False)
        weight_g = weight_raw / 10.0
        if is_negative:
            weight_g = -weight_g
        return {"weight_g": weight_g, "is_stable": is_stable}

    def build_calibrate_command(self, target_weight_g: float) -> bytes:
        weight_raw = int(target_weight_g * 10)
        return (
            b"\xAA\x43"
            + weight_raw.to_bytes(4, byteorder="little")
            + b"\x00\x55"
        )

    def build_zero_command(self) -> bytes:
        return b"\xAA\x5A\x00\x00\x00\x00\x00\x55"


# 品牌协议注册表
_BRAND_PROTOCOLS: Dict[ScaleBrand, _BaseBrandProtocol] = {
    ScaleBrand.DAHUA: DahuaProtocol(),
    ScaleBrand.METTLER_TOLEDO: MettlerToledoProtocol(),
    ScaleBrand.DINGJIAN: DingjianProtocol(),
}


# ── 主服务 ────────────────────────────────────────────────────────────────────

class ScaleProtocolService:
    """
    海鲜称重秤协议服务

    管理设备注册、称重读取、防篡改签名、校准指令等核心功能。
    当前阶段使用内存存储，后续迁移到 Redis + PostgreSQL。
    """

    def __init__(self):
        # scale_id -> ScaleDevice
        self._devices: Dict[str, ScaleDevice] = {}
        # lock_token -> 签名信息（用于验证）
        self._lock_store: Dict[str, Dict[str, Any]] = {}

    # ── 设备注册 ──────────────────────────────────────────────────────────

    async def register_scale(
        self,
        store_id: str,
        brand: str,
        connection_type: str,
        precision_g: float = 0.5,
        address: str = "",
        name: str = "",
        scale_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        注册秤设备

        Args:
            store_id: 门店ID
            brand: 品牌 (dahua/mettler_toledo/dingjian)
            connection_type: 连接方式 (serial/bluetooth/usb/network)
            precision_g: 精度(克)
            address: 设备地址（串口路径/MAC/IP等）
            name: 设备名称
            scale_id: 自定义设备ID，不传则自动生成

        Returns:
            设备注册信息
        """
        # 参数校验
        try:
            brand_enum = ScaleBrand(brand)
        except ValueError:
            raise ValueError(
                f"不支持的秤品牌: {brand}，"
                f"支持: {[b.value for b in ScaleBrand]}"
            )

        try:
            conn_enum = ConnectionType(connection_type)
        except ValueError:
            raise ValueError(
                f"不支持的连接方式: {connection_type}，"
                f"支持: {[c.value for c in ConnectionType]}"
            )

        if precision_g <= 0:
            raise ValueError(f"精度必须大于0，当前: {precision_g}")

        sid = scale_id or str(uuid.uuid4())
        device = ScaleDevice(
            scale_id=sid,
            brand=brand_enum,
            connection_type=conn_enum,
            store_id=store_id,
            precision_g=precision_g,
            address=address,
            name=name,
        )
        # 注册后默认在线
        device.status = ScaleStatus.ONLINE
        device.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._devices[sid] = device

        logger.info(
            "秤设备已注册",
            scale_id=sid,
            brand=brand,
            connection_type=connection_type,
            store_id=store_id,
        )
        return device.to_dict()

    # ── 称重读取 ──────────────────────────────────────────────────────────

    async def read_weight(
        self,
        scale_id: str,
        raw_data: bytes,
    ) -> Dict[str, Any]:
        """
        读取称重结果

        根据设备品牌选择对应协议解析原始帧数据。

        Args:
            scale_id: 设备ID
            raw_data: 硬件返回的原始字节数据

        Returns:
            称重结果 {weight_g, unit, is_stable, lock_token, timestamp, scale_id}
        """
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        if device.status == ScaleStatus.OFFLINE:
            raise RuntimeError(f"秤设备离线: {scale_id}")

        protocol = _BRAND_PROTOCOLS.get(device.brand)
        if protocol is None:
            raise ValueError(f"未找到品牌协议: {device.brand.value}")

        # 解析原始帧
        parsed = protocol.parse_weight_frame(raw_data)

        reading = WeightReading(
            weight_g=parsed["weight_g"],
            is_stable=parsed["is_stable"],
            scale_id=scale_id,
        )

        # 更新心跳
        device.last_heartbeat = reading.timestamp

        logger.debug(
            "称重读数",
            scale_id=scale_id,
            weight_g=parsed["weight_g"],
            is_stable=parsed["is_stable"],
        )
        return reading.to_dict()

    # ── 锁定称重（防篡改） ───────────────────────────────────────────────

    async def lock_weight(
        self,
        scale_id: str,
        weight_g: float,
        operator_id: str = "",
        order_id: str = "",
    ) -> Dict[str, Any]:
        """
        锁定称重结果，生成 HMAC 签名防篡改

        称重锁定后，POS 结算时必须验证签名才能接受该重量。

        Args:
            scale_id: 设备ID
            weight_g: 锁定的重量(克)
            operator_id: 操作员ID
            order_id: 关联订单ID

        Returns:
            锁定凭证 {lock_token, weight_g, signature, timestamp, ...}
        """
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        if weight_g <= 0:
            raise ValueError(f"锁定重量必须大于0: {weight_g}")

        lock_token = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # 构造签名载荷：scale_id|weight_g|timestamp|lock_token
        payload = f"{scale_id}|{weight_g:.2f}|{timestamp}|{lock_token}"
        signature = hmac.new(
            _HMAC_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        lock_info = {
            "lock_token": lock_token,
            "scale_id": scale_id,
            "weight_g": weight_g,
            "unit": "g",
            "signature": signature,
            "timestamp": timestamp,
            "operator_id": operator_id,
            "order_id": order_id,
        }
        self._lock_store[lock_token] = lock_info

        logger.info(
            "称重已锁定",
            scale_id=scale_id,
            weight_g=weight_g,
            lock_token=lock_token,
        )
        return lock_info

    # ── 验证称重签名 ─────────────────────────────────────────────────────

    async def verify_weight_lock(
        self,
        lock_token: str,
        weight_g: float,
    ) -> Dict[str, Any]:
        """
        验证称重锁定签名

        POS 结算时调用，确认称重结果未被篡改。

        Args:
            lock_token: 锁定凭证
            weight_g: 待验证重量(克)

        Returns:
            验证结果 {valid, message, lock_info}
        """
        lock_info = self._lock_store.get(lock_token)
        if lock_info is None:
            return {
                "valid": False,
                "message": "锁定凭证不存在或已过期",
                "lock_info": None,
            }

        # 重新计算签名
        payload = (
            f"{lock_info['scale_id']}|{lock_info['weight_g']:.2f}"
            f"|{lock_info['timestamp']}|{lock_token}"
        )
        expected_sig = hmac.new(
            _HMAC_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, lock_info["signature"]):
            logger.warning("称重签名验证失败：签名不匹配", lock_token=lock_token)
            return {
                "valid": False,
                "message": "签名校验失败，数据可能被篡改",
                "lock_info": None,
            }

        # 比对重量（允许精度内偏差）
        device = self._devices.get(lock_info["scale_id"])
        tolerance = device.precision_g if device else 0.5
        if abs(weight_g - lock_info["weight_g"]) > tolerance:
            logger.warning(
                "称重验证失败：重量不一致",
                lock_token=lock_token,
                expected=lock_info["weight_g"],
                actual=weight_g,
                tolerance=tolerance,
            )
            return {
                "valid": False,
                "message": (
                    f"重量不匹配，锁定值={lock_info['weight_g']:.1f}g，"
                    f"提交值={weight_g:.1f}g，容差={tolerance:.1f}g"
                ),
                "lock_info": lock_info,
            }

        logger.info("称重验证通过", lock_token=lock_token, weight_g=weight_g)
        return {
            "valid": True,
            "message": "验证通过",
            "lock_info": lock_info,
        }

    # ── 设备状态 ──────────────────────────────────────────────────────────

    async def get_scale_status(self, scale_id: str) -> Dict[str, Any]:
        """
        获取秤设备状态

        Args:
            scale_id: 设备ID

        Returns:
            设备状态信息
        """
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        return {
            "scale_id": device.scale_id,
            "name": device.name,
            "brand": device.brand.value,
            "status": device.status.value,
            "calibration_status": device.calibration_status.value,
            "last_heartbeat": device.last_heartbeat,
            "last_calibration": device.last_calibration,
            "connection_type": device.connection_type.value,
            "precision_g": device.precision_g,
        }

    async def update_scale_status(
        self,
        scale_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """更新秤设备状态（心跳/上下线）"""
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        try:
            device.status = ScaleStatus(status)
        except ValueError:
            raise ValueError(
                f"无效状态: {status}，支持: {[s.value for s in ScaleStatus]}"
            )

        device.last_heartbeat = datetime.now(timezone.utc).isoformat()
        logger.info("秤状态更新", scale_id=scale_id, status=status)
        return device.to_dict()

    # ── 远程校准 ──────────────────────────────────────────────────────────

    async def calibrate_scale(
        self,
        scale_id: str,
        target_weight_g: float,
    ) -> Dict[str, Any]:
        """
        远程校准指令

        向秤设备发送校准指令，实际发送由边缘节点执行。
        本方法生成指令帧并更新校准状态。

        Args:
            scale_id: 设备ID
            target_weight_g: 校准砝码重量(克)

        Returns:
            校准指令信息 {command_hex, status, ...}
        """
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        if target_weight_g <= 0:
            raise ValueError(f"校准砝码重量必须大于0: {target_weight_g}")

        protocol = _BRAND_PROTOCOLS.get(device.brand)
        if protocol is None:
            raise ValueError(f"未找到品牌协议: {device.brand.value}")

        # 构建校准指令帧
        command = protocol.build_calibrate_command(target_weight_g)

        # 更新校准状态
        device.calibration_status = CalibrationStatus.PENDING
        device.status = ScaleStatus.CALIBRATING

        now = datetime.now(timezone.utc).isoformat()
        device.last_calibration = now

        logger.info(
            "校准指令已生成",
            scale_id=scale_id,
            brand=device.brand.value,
            target_weight_g=target_weight_g,
        )

        return {
            "scale_id": scale_id,
            "command_hex": command.hex(),
            "command_bytes": list(command),
            "target_weight_g": target_weight_g,
            "calibration_status": device.calibration_status.value,
            "timestamp": now,
        }

    async def confirm_calibration(
        self,
        scale_id: str,
        passed: bool,
    ) -> Dict[str, Any]:
        """校准结果确认（边缘节点回调）"""
        device = self._devices.get(scale_id)
        if device is None:
            raise ValueError(f"秤设备未注册: {scale_id}")

        if passed:
            device.calibration_status = CalibrationStatus.PASSED
            device.status = ScaleStatus.ONLINE
        else:
            device.calibration_status = CalibrationStatus.FAILED
            device.status = ScaleStatus.ERROR

        logger.info(
            "校准结果确认",
            scale_id=scale_id,
            passed=passed,
        )
        return device.to_dict()

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    async def list_scales(
        self,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出设备（可按门店过滤）"""
        devices = self._devices.values()
        if store_id:
            devices = [d for d in devices if d.store_id == store_id]
        return [d.to_dict() for d in devices]

    async def unregister_scale(self, scale_id: str) -> bool:
        """注销设备"""
        if scale_id in self._devices:
            del self._devices[scale_id]
            logger.info("秤设备已注销", scale_id=scale_id)
            return True
        return False

    def get_protocol(self, brand: str) -> _BaseBrandProtocol:
        """获取品牌协议实例（供外部调试用）"""
        try:
            brand_enum = ScaleBrand(brand)
        except ValueError:
            raise ValueError(f"不支持的品牌: {brand}")
        return _BRAND_PROTOCOLS[brand_enum]


# 模块级单例
scale_protocol_service = ScaleProtocolService()
