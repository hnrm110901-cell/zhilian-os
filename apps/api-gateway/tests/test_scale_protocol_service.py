"""
海鲜称重秤协议服务测试

覆盖：设备注册、多品牌协议解析、称重锁定/验证、校准、状态管理
"""

import os
import sys

# L002: 测试前设置环境变量，避免 pydantic_settings 校验失败
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SCALE_HMAC_SECRET", "test-hmac-secret-key")

import struct

import pytest
import pytest_asyncio

from src.services.scale_protocol_service import (
    CalibrationStatus,
    ConnectionType,
    DahuaProtocol,
    DingjianProtocol,
    MettlerToledoProtocol,
    ScaleBrand,
    ScaleProtocolService,
    ScaleStatus,
)


@pytest_asyncio.fixture
async def service():
    """每个测试用新的 service 实例"""
    svc = ScaleProtocolService()
    yield svc


@pytest_asyncio.fixture
async def registered_scale(service: ScaleProtocolService):
    """预注册一台大华秤"""
    result = await service.register_scale(
        store_id="S001",
        brand="dahua",
        connection_type="serial",
        precision_g=0.5,
        address="/dev/ttyUSB0",
        name="海鲜档口1号秤",
        scale_id="SCALE-001",
    )
    return result


# ── 设备注册测试 ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_scale_success(service: ScaleProtocolService):
    """正常注册秤设备"""
    result = await service.register_scale(
        store_id="S001",
        brand="dahua",
        connection_type="serial",
        precision_g=1.0,
        address="/dev/ttyUSB0",
        name="测试秤",
    )
    assert result["brand"] == "dahua"
    assert result["connection_type"] == "serial"
    assert result["store_id"] == "S001"
    assert result["precision_g"] == 1.0
    assert result["status"] == "online"
    assert result["name"] == "测试秤"
    assert "scale_id" in result


@pytest.mark.asyncio
async def test_register_scale_invalid_brand(service: ScaleProtocolService):
    """注册不支持的品牌应报错"""
    with pytest.raises(ValueError, match="不支持的秤品牌"):
        await service.register_scale(
            store_id="S001",
            brand="unknown_brand",
            connection_type="serial",
        )


@pytest.mark.asyncio
async def test_register_scale_invalid_connection(service: ScaleProtocolService):
    """注册不支持的连接方式应报错"""
    with pytest.raises(ValueError, match="不支持的连接方式"):
        await service.register_scale(
            store_id="S001",
            brand="dahua",
            connection_type="wifi",
        )


@pytest.mark.asyncio
async def test_register_scale_invalid_precision(service: ScaleProtocolService):
    """精度必须大于0"""
    with pytest.raises(ValueError, match="精度必须大于0"):
        await service.register_scale(
            store_id="S001",
            brand="dahua",
            connection_type="serial",
            precision_g=0,
        )


@pytest.mark.asyncio
async def test_register_all_brands(service: ScaleProtocolService):
    """三个品牌都能注册成功"""
    for brand in ["dahua", "mettler_toledo", "dingjian"]:
        result = await service.register_scale(
            store_id="S001",
            brand=brand,
            connection_type="network",
        )
        assert result["brand"] == brand


@pytest.mark.asyncio
async def test_register_all_connection_types(service: ScaleProtocolService):
    """四种连接方式都能注册成功"""
    for conn in ["serial", "bluetooth", "usb", "network"]:
        result = await service.register_scale(
            store_id="S001",
            brand="dahua",
            connection_type=conn,
        )
        assert result["connection_type"] == conn


# ── 品牌协议解析测试 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dahua_parse_stable_weight(service: ScaleProtocolService, registered_scale):
    """大华协议解析稳定称重"""
    # 构造大华帧：STX + 'S'(稳定) + "0350.0"(ASCII) + 空 + ETX
    frame = b"\x02S0350.0\x00\x03"
    result = await service.read_weight("SCALE-001", frame)
    assert result["weight_g"] == 350.0
    assert result["is_stable"] is True
    assert result["unit"] == "g"
    assert result["scale_id"] == "SCALE-001"


@pytest.mark.asyncio
async def test_dahua_parse_unstable_weight(service: ScaleProtocolService, registered_scale):
    """大华协议解析不稳定称重"""
    # 0x20 = 空格，表示不稳定
    frame = b"\x02 0125.5\x00\x03"
    result = await service.read_weight("SCALE-001", frame)
    assert result["weight_g"] == 125.5
    assert result["is_stable"] is False


@pytest.mark.asyncio
async def test_mettler_toledo_parse():
    """梅特勒-托利多协议解析"""
    protocol = MettlerToledoProtocol()
    # MT-SICS 格式：'S S     500.2 g'
    raw = b"S S     500.2 g"
    parsed = protocol.parse_weight_frame(raw)
    assert parsed["weight_g"] == 500.2
    assert parsed["is_stable"] is True


@pytest.mark.asyncio
async def test_mettler_toledo_dynamic():
    """梅特勒-托利多动态读数"""
    protocol = MettlerToledoProtocol()
    raw = b"S D     123.4 g"
    parsed = protocol.parse_weight_frame(raw)
    assert parsed["weight_g"] == 123.4
    assert parsed["is_stable"] is False


@pytest.mark.asyncio
async def test_dingjian_parse_stable():
    """顶尖协议解析稳定称重"""
    protocol = DingjianProtocol()
    # 帧：AA + 状态(bit0=1, 稳定) + 重量(15000 = 1500.0g, little-endian) + 校验 + 55
    weight_raw = 15000  # 0.1g 单位，即 1500.0g
    frame = (
        b"\xAA"
        + b"\x01"  # 稳定
        + weight_raw.to_bytes(4, "little")
        + b"\x00"  # 校验占位
        + b"\x55"
    )
    parsed = protocol.parse_weight_frame(frame)
    assert parsed["weight_g"] == 1500.0
    assert parsed["is_stable"] is True


@pytest.mark.asyncio
async def test_dingjian_parse_negative():
    """顶尖协议解析负值（去皮后）"""
    protocol = DingjianProtocol()
    weight_raw = 500  # 0.1g 单位，即 50.0g
    frame = (
        b"\xAA"
        + b"\x03"  # bit0=稳定, bit1=负值
        + weight_raw.to_bytes(4, "little")
        + b"\x00"
        + b"\x55"
    )
    parsed = protocol.parse_weight_frame(frame)
    assert parsed["weight_g"] == -50.0
    assert parsed["is_stable"] is True


@pytest.mark.asyncio
async def test_read_weight_unregistered(service: ScaleProtocolService):
    """读取未注册设备应报错"""
    with pytest.raises(ValueError, match="秤设备未注册"):
        await service.read_weight("NOT-EXIST", b"\x00" * 10)


@pytest.mark.asyncio
async def test_read_weight_offline(service: ScaleProtocolService):
    """读取离线设备应报错"""
    await service.register_scale(
        store_id="S001", brand="dahua", connection_type="serial", scale_id="OFF-001"
    )
    await service.update_scale_status("OFF-001", "offline")
    with pytest.raises(RuntimeError, match="秤设备离线"):
        await service.read_weight("OFF-001", b"\x02S0100.0\x00\x03")


# ── 称重锁定与验证测试 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_and_verify_success(service: ScaleProtocolService, registered_scale):
    """锁定后验证通过"""
    lock = await service.lock_weight("SCALE-001", 800.5, operator_id="OP-01")
    assert lock["weight_g"] == 800.5
    assert lock["signature"]
    assert lock["lock_token"]

    verify = await service.verify_weight_lock(lock["lock_token"], 800.5)
    assert verify["valid"] is True
    assert verify["message"] == "验证通过"


@pytest.mark.asyncio
async def test_lock_verify_weight_mismatch(service: ScaleProtocolService, registered_scale):
    """重量不匹配时验证失败"""
    lock = await service.lock_weight("SCALE-001", 500.0)
    # 提交 510g，偏差超过精度 0.5g
    verify = await service.verify_weight_lock(lock["lock_token"], 510.0)
    assert verify["valid"] is False
    assert "重量不匹配" in verify["message"]


@pytest.mark.asyncio
async def test_lock_verify_within_tolerance(service: ScaleProtocolService, registered_scale):
    """精度范围内偏差验证通过"""
    lock = await service.lock_weight("SCALE-001", 500.0)
    # 精度 0.5g，偏差 0.3g 应通过
    verify = await service.verify_weight_lock(lock["lock_token"], 500.3)
    assert verify["valid"] is True


@pytest.mark.asyncio
async def test_lock_verify_invalid_token(service: ScaleProtocolService):
    """无效 token 验证失败"""
    verify = await service.verify_weight_lock("non-existent-token", 100.0)
    assert verify["valid"] is False
    assert "不存在" in verify["message"]


@pytest.mark.asyncio
async def test_lock_zero_weight(service: ScaleProtocolService, registered_scale):
    """锁定重量为0应报错"""
    with pytest.raises(ValueError, match="锁定重量必须大于0"):
        await service.lock_weight("SCALE-001", 0)


# ── 设备状态与校准测试 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_scale_status(service: ScaleProtocolService, registered_scale):
    """获取设备状态"""
    status = await service.get_scale_status("SCALE-001")
    assert status["status"] == "online"
    assert status["brand"] == "dahua"
    assert status["calibration_status"] == "pending"


@pytest.mark.asyncio
async def test_calibrate_scale(service: ScaleProtocolService, registered_scale):
    """发送校准指令"""
    result = await service.calibrate_scale("SCALE-001", target_weight_g=1000.0)
    assert result["target_weight_g"] == 1000.0
    assert result["command_hex"]  # 有校准指令帧
    assert result["calibration_status"] == "pending"

    # 设备应进入校准状态
    status = await service.get_scale_status("SCALE-001")
    assert status["status"] == "calibrating"


@pytest.mark.asyncio
async def test_calibrate_confirm(service: ScaleProtocolService, registered_scale):
    """校准确认"""
    await service.calibrate_scale("SCALE-001", target_weight_g=500.0)

    # 校准通过
    result = await service.confirm_calibration("SCALE-001", passed=True)
    assert result["calibration_status"] == "passed"
    assert result["status"] == "online"


@pytest.mark.asyncio
async def test_calibrate_failed(service: ScaleProtocolService, registered_scale):
    """校准失败"""
    await service.calibrate_scale("SCALE-001", target_weight_g=500.0)
    result = await service.confirm_calibration("SCALE-001", passed=False)
    assert result["calibration_status"] == "failed"
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_list_scales_by_store(service: ScaleProtocolService):
    """按门店列出设备"""
    await service.register_scale(store_id="S001", brand="dahua", connection_type="serial")
    await service.register_scale(store_id="S001", brand="dingjian", connection_type="usb")
    await service.register_scale(store_id="S002", brand="mettler_toledo", connection_type="network")

    s001_scales = await service.list_scales(store_id="S001")
    assert len(s001_scales) == 2

    all_scales = await service.list_scales()
    assert len(all_scales) == 3


@pytest.mark.asyncio
async def test_unregister_scale(service: ScaleProtocolService, registered_scale):
    """注销设备"""
    assert await service.unregister_scale("SCALE-001") is True
    assert await service.unregister_scale("SCALE-001") is False  # 再次注销返回 False

    with pytest.raises(ValueError, match="秤设备未注册"):
        await service.get_scale_status("SCALE-001")
