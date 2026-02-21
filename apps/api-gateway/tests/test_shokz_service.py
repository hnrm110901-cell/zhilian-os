"""
Shokz骨传导耳机集成服务测试
Tests for Shokz Bone Conduction Headset Integration Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.shokz_service import (
    ShokzService,
    ShokzDevice,
    DeviceType,
    DeviceRole,
    shokz_service,
)


class TestShokzDevice:
    """ShokzDevice测试类"""

    def test_init(self):
        """测试设备初始化"""
        device = ShokzDevice(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )

        assert device.device_id == "device123"
        assert device.device_type == DeviceType.OPENCOMM_2
        assert device.role == DeviceRole.FRONT_OF_HOUSE
        assert device.user_id == "user123"
        assert device.bluetooth_address == "00:11:22:33:44:55"
        assert device.is_connected is False
        assert device.battery_level == 100
        assert device.last_activity is None


class TestShokzService:
    """ShokzService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = ShokzService()
        assert service.devices == {}
        assert service.active_sessions == {}

    @pytest.mark.asyncio
    async def test_register_device_success(self):
        """测试设备注册成功"""
        service = ShokzService()

        result = await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )

        assert result["success"] is True
        assert result["device_id"] == "device123"
        assert result["message"] == "设备注册成功"
        assert "device123" in service.devices
        assert service.devices["device123"].device_type == DeviceType.OPENCOMM_2

    @pytest.mark.asyncio
    async def test_register_device_kitchen(self):
        """测试注册后厨设备"""
        service = ShokzService()

        result = await service.register_device(
            device_id="kitchen001",
            device_type=DeviceType.OPENRUN_PRO_2,
            role=DeviceRole.KITCHEN,
            user_id="chef123",
            bluetooth_address="AA:BB:CC:DD:EE:FF"
        )

        assert result["success"] is True
        assert service.devices["kitchen001"].role == DeviceRole.KITCHEN
        assert service.devices["kitchen001"].device_type == DeviceType.OPENRUN_PRO_2

    @pytest.mark.asyncio
    async def test_register_device_cashier(self):
        """测试注册收银设备"""
        service = ShokzService()

        result = await service.register_device(
            device_id="cashier001",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.CASHIER,
            user_id="cashier123",
            bluetooth_address="11:22:33:44:55:66"
        )

        assert result["success"] is True
        assert service.devices["cashier001"].role == DeviceRole.CASHIER

    @pytest.mark.asyncio
    async def test_connect_device_success(self):
        """测试设备连接成功"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )

        result = await service.connect_device("device123")

        assert result["success"] is True
        assert result["device_id"] == "device123"
        assert result["message"] == "设备连接成功"
        assert service.devices["device123"].is_connected is True

    @pytest.mark.asyncio
    async def test_connect_device_not_found(self):
        """测试连接不存在的设备"""
        service = ShokzService()

        result = await service.connect_device("nonexistent")

        assert result["success"] is False
        assert result["error"] == "设备不存在"

    @pytest.mark.asyncio
    async def test_disconnect_device_success(self):
        """测试设备断开成功"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        await service.connect_device("device123")

        result = await service.disconnect_device("device123")

        assert result["success"] is True
        assert result["device_id"] == "device123"
        assert result["message"] == "设备断开成功"
        assert service.devices["device123"].is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_device_not_found(self):
        """测试断开不存在的设备"""
        service = ShokzService()

        result = await service.disconnect_device("nonexistent")

        assert result["success"] is False
        assert result["error"] == "设备不存在"

    @pytest.mark.asyncio
    async def test_send_audio_success(self):
        """测试发送音频成功"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        await service.connect_device("device123")

        audio_data = b"fake_audio_data"
        result = await service.send_audio("device123", audio_data)

        assert result["success"] is True
        assert result["device_id"] == "device123"
        assert result["bytes_sent"] == len(audio_data)

    @pytest.mark.asyncio
    async def test_send_audio_device_not_found(self):
        """测试发送音频到不存在的设备"""
        service = ShokzService()

        result = await service.send_audio("nonexistent", b"audio")

        assert result["success"] is False
        assert result["error"] == "设备不存在"

    @pytest.mark.asyncio
    async def test_send_audio_device_not_connected(self):
        """测试发送音频到未连接的设备"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )

        result = await service.send_audio("device123", b"audio")

        assert result["success"] is False
        assert result["error"] == "设备未连接"

    @pytest.mark.asyncio
    async def test_send_audio_custom_format(self):
        """测试发送自定义格式音频"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        await service.connect_device("device123")

        result = await service.send_audio("device123", b"audio", format="mp3")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_receive_audio_success(self):
        """测试接收音频成功"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        await service.connect_device("device123")

        result = await service.receive_audio("device123", duration_seconds=3)

        assert result["success"] is True
        assert result["device_id"] == "device123"
        assert result["audio_data"] == b""
        assert result["duration"] == 3
        assert result["format"] == "pcm"
        assert result["sample_rate"] == 16000

    @pytest.mark.asyncio
    async def test_receive_audio_device_not_found(self):
        """测试从不存在的设备接收音频"""
        service = ShokzService()

        result = await service.receive_audio("nonexistent")

        assert result["success"] is False
        assert result["error"] == "设备不存在"

    @pytest.mark.asyncio
    async def test_receive_audio_device_not_connected(self):
        """测试从未连接的设备接收音频"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )

        result = await service.receive_audio("device123")

        assert result["success"] is False
        assert result["error"] == "设备未连接"

    @pytest.mark.asyncio
    async def test_receive_audio_custom_duration(self):
        """测试接收自定义时长音频"""
        service = ShokzService()
        await service.register_device(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        await service.connect_device("device123")

        result = await service.receive_audio("device123", duration_seconds=10)

        assert result["success"] is True
        assert result["duration"] == 10

    def test_get_device_info_success(self):
        """测试获取设备信息成功"""
        service = ShokzService()
        device = ShokzDevice(
            device_id="device123",
            device_type=DeviceType.OPENCOMM_2,
            role=DeviceRole.FRONT_OF_HOUSE,
            user_id="user123",
            bluetooth_address="00:11:22:33:44:55"
        )
        service.devices["device123"] = device

        info = service.get_device_info("device123")

        assert info is not None
        assert info["device_id"] == "device123"
        assert info["device_type"] == "opencomm_2"
        assert info["role"] == "front_of_house"
        assert info["user_id"] == "user123"
        assert info["bluetooth_address"] == "00:11:22:33:44:55"
        assert info["is_connected"] is False
        assert info["battery_level"] == 100
        assert info["last_activity"] is None

    def test_get_device_info_not_found(self):
        """测试获取不存在设备的信息"""
        service = ShokzService()

        info = service.get_device_info("nonexistent")

        assert info is None

    def test_list_devices_empty(self):
        """测试列出空设备列表"""
        service = ShokzService()

        devices = service.list_devices()

        assert devices == []

    def test_list_devices_all(self):
        """测试列出所有设备"""
        service = ShokzService()
        service.devices["device1"] = ShokzDevice(
            "device1", DeviceType.OPENCOMM_2, DeviceRole.FRONT_OF_HOUSE,
            "user1", "00:11:22:33:44:55"
        )
        service.devices["device2"] = ShokzDevice(
            "device2", DeviceType.OPENRUN_PRO_2, DeviceRole.KITCHEN,
            "user2", "AA:BB:CC:DD:EE:FF"
        )

        devices = service.list_devices()

        assert len(devices) == 2
        assert devices[0]["device_id"] in ["device1", "device2"]
        assert devices[1]["device_id"] in ["device1", "device2"]

    def test_list_devices_by_role(self):
        """测试按角色筛选设备"""
        service = ShokzService()
        service.devices["device1"] = ShokzDevice(
            "device1", DeviceType.OPENCOMM_2, DeviceRole.FRONT_OF_HOUSE,
            "user1", "00:11:22:33:44:55"
        )
        service.devices["device2"] = ShokzDevice(
            "device2", DeviceType.OPENRUN_PRO_2, DeviceRole.KITCHEN,
            "user2", "AA:BB:CC:DD:EE:FF"
        )
        service.devices["device3"] = ShokzDevice(
            "device3", DeviceType.OPENCOMM_2, DeviceRole.CASHIER,
            "user3", "11:22:33:44:55:66"
        )

        kitchen_devices = service.list_devices(role=DeviceRole.KITCHEN)

        assert len(kitchen_devices) == 1
        assert kitchen_devices[0]["device_id"] == "device2"
        assert kitchen_devices[0]["role"] == "kitchen"

    def test_list_devices_connected_only(self):
        """测试只列出已连接设备"""
        service = ShokzService()
        device1 = ShokzDevice(
            "device1", DeviceType.OPENCOMM_2, DeviceRole.FRONT_OF_HOUSE,
            "user1", "00:11:22:33:44:55"
        )
        device1.is_connected = True
        service.devices["device1"] = device1

        device2 = ShokzDevice(
            "device2", DeviceType.OPENRUN_PRO_2, DeviceRole.KITCHEN,
            "user2", "AA:BB:CC:DD:EE:FF"
        )
        device2.is_connected = False
        service.devices["device2"] = device2

        connected_devices = service.list_devices(connected_only=True)

        assert len(connected_devices) == 1
        assert connected_devices[0]["device_id"] == "device1"
        assert connected_devices[0]["is_connected"] is True

    def test_list_devices_by_role_and_connected(self):
        """测试按角色和连接状态筛选设备"""
        service = ShokzService()
        device1 = ShokzDevice(
            "device1", DeviceType.OPENCOMM_2, DeviceRole.KITCHEN,
            "user1", "00:11:22:33:44:55"
        )
        device1.is_connected = True
        service.devices["device1"] = device1

        device2 = ShokzDevice(
            "device2", DeviceType.OPENRUN_PRO_2, DeviceRole.KITCHEN,
            "user2", "AA:BB:CC:DD:EE:FF"
        )
        device2.is_connected = False
        service.devices["device2"] = device2

        device3 = ShokzDevice(
            "device3", DeviceType.OPENCOMM_2, DeviceRole.FRONT_OF_HOUSE,
            "user3", "11:22:33:44:55:66"
        )
        device3.is_connected = True
        service.devices["device3"] = device3

        devices = service.list_devices(role=DeviceRole.KITCHEN, connected_only=True)

        assert len(devices) == 1
        assert devices[0]["device_id"] == "device1"


class TestGlobalInstance:
    """测试全局实例"""

    def test_shokz_service_instance(self):
        """测试shokz_service全局实例"""
        assert shokz_service is not None
        assert isinstance(shokz_service, ShokzService)
