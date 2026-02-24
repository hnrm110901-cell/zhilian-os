"""
Shokz骨传导耳机集成服务
Shokz Bone Conduction Headset Integration Service

支持OpenComm 2（前厅/收银）和OpenRun Pro 2（后厨）深度对接
蓝牙连接：bleak（BLE管理）
音频流：PulseAudio/BlueZ（系统级A2DP/HFP）
"""
from typing import Dict, Any, Optional, List
import asyncio
import subprocess
import tempfile
import os
import structlog
from enum import Enum

logger = structlog.get_logger()


class DeviceType(Enum):
    """设备类型"""
    OPENCOMM_2 = "opencomm_2"  # 前厅/收银
    OPENRUN_PRO_2 = "openrun_pro_2"  # 后厨


class DeviceRole(Enum):
    """设备角色"""
    FRONT_OF_HOUSE = "front_of_house"  # 前厅
    CASHIER = "cashier"  # 收银
    KITCHEN = "kitchen"  # 后厨


class ShokzDevice:
    """Shokz设备"""

    def __init__(
        self,
        device_id: str,
        device_type: DeviceType,
        role: DeviceRole,
        user_id: str,
        bluetooth_address: str,
        store_id: str = "",
    ):
        self.device_id = device_id
        self.device_type = device_type
        self.role = role
        self.user_id = user_id
        self.bluetooth_address = bluetooth_address
        self.store_id = store_id
        self.is_connected = False
        self.battery_level = 100
        self.last_activity = None
        self._ble_client = None  # bleak.BleakClient 实例（运行时注入）


class ShokzService:
    """Shokz设备管理服务"""

    def __init__(self):
        """初始化Shokz服务"""
        self.devices: Dict[str, ShokzDevice] = {}
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        logger.info("ShokzService初始化完成")

    async def register_device(
        self,
        device_id: str,
        device_type: DeviceType,
        role: DeviceRole,
        user_id: str,
        bluetooth_address: str,
        store_id: str = "",
    ) -> Dict[str, Any]:
        """
        注册Shokz设备

        Args:
            device_id: 设备ID
            device_type: 设备类型
            role: 设备角色
            user_id: 用户ID
            bluetooth_address: 蓝牙地址
            store_id: 门店ID

        Returns:
            注册结果
        """
        try:
            device = ShokzDevice(
                device_id=device_id,
                device_type=device_type,
                role=role,
                user_id=user_id,
                bluetooth_address=bluetooth_address,
                store_id=store_id,
            )

            self.devices[device_id] = device

            logger.info(
                "Shokz设备注册成功",
                device_id=device_id,
                device_type=device_type.value,
                role=role.value,
            )

            return {
                "success": True,
                "device_id": device_id,
                "message": "设备注册成功",
            }

        except Exception as e:
            logger.error("Shokz设备注册失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def connect_device(self, device_id: str) -> Dict[str, Any]:
        """
        连接Shokz设备

        Args:
            device_id: 设备ID

        Returns:
            连接结果
        """
        if device_id not in self.devices:
            return {
                "success": False,
                "error": "设备不存在",
            }

        device = self.devices[device_id]

        try:
            # 使用 bleak 建立 BLE 连接（管理连接状态、电量等）
            # 音频流由系统 BlueZ/PulseAudio 通过 A2DP/HFP profile 处理
            try:
                from bleak import BleakClient
                client = BleakClient(device.bluetooth_address)
                await client.connect()
                device._ble_client = client
            except ImportError:
                # bleak 未安装时（非 Linux/树莓派环境），仅标记连接状态
                logger.warning("bleak 未安装，跳过 BLE 连接", device_id=device_id)
            except Exception as ble_err:
                logger.warning("BLE 连接失败，设备可能通过经典蓝牙连接", error=str(ble_err))

            device.is_connected = True

            logger.info("Shokz设备连接成功", device_id=device_id)

            return {
                "success": True,
                "device_id": device_id,
                "message": "设备连接成功",
            }

        except Exception as e:
            logger.error("Shokz设备连接失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def disconnect_device(self, device_id: str) -> Dict[str, Any]:
        """
        断开Shokz设备

        Args:
            device_id: 设备ID

        Returns:
            断开结果
        """
        if device_id not in self.devices:
            return {
                "success": False,
                "error": "设备不存在",
            }

        device = self.devices[device_id]

        try:
            # 断开 BLE 连接
            if device._ble_client is not None:
                try:
                    await device._ble_client.disconnect()
                except Exception as e:
                    logger.warning("ble_disconnect_failed", error=str(e))

            device.is_connected = False

            logger.info("Shokz设备断开成功", device_id=device_id)

            return {
                "success": True,
                "device_id": device_id,
                "message": "设备断开成功",
            }

        except Exception as e:
            logger.error("Shokz设备断开失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def send_audio(
        self,
        device_id: str,
        audio_data: bytes,
        format: str = "pcm",
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        """
        发送音频到Shokz设备

        Args:
            device_id: 设备ID
            audio_data: 音频数据 (PCM s16le)
            format: 音频格式
            sample_rate: 采样率 (讯飞TTS输出16000Hz)

        Returns:
            发送结果
        """
        if device_id not in self.devices:
            return {
                "success": False,
                "error": "设备不存在",
            }

        device = self.devices[device_id]

        if not device.is_connected:
            return {
                "success": False,
                "error": "设备未连接",
            }

        try:
            # 通过 PulseAudio 将音频数据发送到蓝牙 A2DP sink
            bt_addr_clean = device.bluetooth_address.replace(":", "_")
            sink_name = f"bluez_sink.{bt_addr_clean}.a2dp_sink"

            with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    "paplay",
                    "--device", sink_name,
                    "--format=s16le",
                    f"--rate={sample_rate}",
                    "--channels=1",
                    tmp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode != 0:
                    raise RuntimeError(f"paplay 失败: {stderr.decode()[:200]}")
            finally:
                os.unlink(tmp_path)

            logger.info("音频发送成功", device_id=device_id, audio_size=len(audio_data))

            return {
                "success": True,
                "device_id": device_id,
                "bytes_sent": len(audio_data),
            }

        except Exception as e:
            logger.error("音频发送失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def receive_audio(
        self,
        device_id: str,
        duration_seconds: int = 5,
    ) -> Dict[str, Any]:
        """
        从Shokz设备接收音频

        Args:
            device_id: 设备ID
            duration_seconds: 录音时长（秒）

        Returns:
            接收结果（包含音频数据）
        """
        if device_id not in self.devices:
            return {
                "success": False,
                "error": "设备不存在",
            }

        device = self.devices[device_id]

        if not device.is_connected:
            return {
                "success": False,
                "error": "设备未连接",
            }

        try:
            # 通过 PulseAudio 从蓝牙 HFP/HSP source 录音
            # parec 持续运行不会自动退出，需要在录音时长后主动终止
            bt_addr_clean = device.bluetooth_address.replace(":", "_")
            source_name = f"bluez_source.{bt_addr_clean}.handsfree_head_unit"
            sample_rate = int(os.getenv("SHOKZ_AUDIO_SAMPLE_RATE", "16000"))
            channels = int(os.getenv("SHOKZ_AUDIO_CHANNELS", "1"))

            with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                proc = await asyncio.create_subprocess_exec(
                    "parec",
                    "--device", source_name,
                    "--format=s16le",
                    f"--rate={sample_rate}",
                    f"--channels={channels}",
                    "--latency-msec=100",
                    tmp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                # 等待录音时长后终止 parec（它不会自动退出）
                await asyncio.sleep(duration_seconds)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()

                with open(tmp_path, "rb") as f:
                    audio_data = f.read()
            finally:
                os.unlink(tmp_path)

            logger.info("音频接收成功", device_id=device_id, duration=duration_seconds,
                        bytes_received=len(audio_data))

            return {
                "success": True,
                "device_id": device_id,
                "audio_data": audio_data,
                "duration": duration_seconds,
                "format": "pcm",
                "sample_rate": sample_rate,
            }

        except Exception as e:
            logger.error("音频接收失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        获取设备信息

        Args:
            device_id: 设备ID

        Returns:
            设备信息
        """
        if device_id not in self.devices:
            return None

        device = self.devices[device_id]

        return {
            "device_id": device.device_id,
            "device_type": device.device_type.value,
            "role": device.role.value,
            "user_id": device.user_id,
            "store_id": device.store_id,
            "bluetooth_address": device.bluetooth_address,
            "is_connected": device.is_connected,
            "battery_level": device.battery_level,
            "last_activity": device.last_activity,
        }

    def list_devices(
        self,
        role: Optional[DeviceRole] = None,
        connected_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        列出设备

        Args:
            role: 按角色筛选
            connected_only: 只显示已连接设备

        Returns:
            设备列表
        """
        devices = []

        for device in self.devices.values():
            # 角色筛选
            if role and device.role != role:
                continue

            # 连接状态筛选
            if connected_only and not device.is_connected:
                continue

            devices.append({
                "device_id": device.device_id,
                "device_type": device.device_type.value,
                "role": device.role.value,
                "user_id": device.user_id,
                "is_connected": device.is_connected,
                "battery_level": device.battery_level,
            })

        return devices


# 创建全局实例
shokz_service = ShokzService()
