"""
Shokz设备集成服务 (Shokz Device Integration Service)
骨传导耳机集成 - 语音交互、蓝牙连接、异常驱动管理

硬件规格：
- 设备：Shokz OpenComm2 UC（商务版）
- 连接：Bluetooth 5.1
- 续航：16小时通话
- 防水：IP55
- 成本：¥1,200/个

核心功能：
1. 蓝牙配对与连接管理
2. 语音输入（ASR - 自动语音识别）
3. 语音输出（TTS - 文本转语音）
4. 异常驱动通知（外卖催单、VIP到店、客诉预警）
5. 多设备管理（店长、副店长、厨师长）
"""
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class ShokzDeviceModel(str, Enum):
    """Shokz设备型号"""
    OPENCOMM2_UC = "OpenComm2 UC"  # 商务版（推荐）
    OPENRUN_PRO = "OpenRun Pro"  # 运动版
    OPENMOVE = "OpenMove"  # 入门版


class DeviceStatus(str, Enum):
    """设备状态"""
    CONNECTED = "connected"  # 已连接
    DISCONNECTED = "disconnected"  # 已断开
    PAIRING = "pairing"  # 配对中
    LOW_BATTERY = "low_battery"  # 电量低
    CHARGING = "charging"  # 充电中


class VoiceCommand(str, Enum):
    """语音命令"""
    QUERY_REVENUE = "query_revenue"  # 查询营业额
    QUERY_ORDERS = "query_orders"  # 查询订单
    QUERY_INVENTORY = "query_inventory"  # 查询库存
    ALERT_TAKEOUT = "alert_takeout"  # 外卖催单
    ALERT_VIP = "alert_vip"  # VIP到店
    ALERT_COMPLAINT = "alert_complaint"  # 客诉预警
    ALERT_KITCHEN = "alert_kitchen"  # 后厨异常


class ShokzDeviceInfo(BaseModel):
    """Shokz设备信息"""
    device_id: str
    device_name: str  # 例如："店长-张三-Shokz"
    device_model: ShokzDeviceModel
    mac_address: str
    store_id: str
    user_id: str  # 佩戴者ID（店长、副店长等）
    user_role: str  # 角色（manager, assistant_manager, chef）
    edge_node_id: str  # 连接的树莓派5节点ID
    status: DeviceStatus
    battery_level: int  # 电量（%）
    signal_strength: int  # 信号强度（-100 to 0 dBm）
    connected_at: Optional[datetime] = None
    last_command_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VoiceInteraction(BaseModel):
    """语音交互记录"""
    interaction_id: str
    device_id: str
    store_id: str
    user_id: str
    # 输入
    audio_input: str  # 音频数据（base64）
    text_input: str  # ASR识别结果
    intent: str  # 意图识别
    confidence: float  # 置信度
    # 输出
    text_output: str  # 响应文本
    audio_output: str  # TTS合成音频（base64）
    # 元数据
    interaction_time: datetime
    processing_time_ms: int  # 处理时长（毫秒）
    success: bool


class ShokzDeviceService:
    """Shokz设备集成服务"""

    # 设备规格
    DEVICE_SPECS = {
        ShokzDeviceModel.OPENCOMM2_UC: {
            "name": "Shokz OpenComm2 UC",
            "bluetooth": "Bluetooth 5.1",
            "battery_life_hours": 16,
            "waterproof": "IP55",
            "weight_grams": 35,
            "cost": 1200.0,  # 人民币
            "features": [
                "DSP降噪",
                "多点连接",
                "快充（5分钟充电2小时使用）",
                "NFC快速配对"
            ]
        },
        ShokzDeviceModel.OPENRUN_PRO: {
            "name": "Shokz OpenRun Pro",
            "bluetooth": "Bluetooth 5.1",
            "battery_life_hours": 10,
            "waterproof": "IP67",
            "weight_grams": 29,
            "cost": 1000.0,
            "features": [
                "运动防汗",
                "快充",
                "轻量化设计"
            ]
        }
    }

    # 推荐配置
    RECOMMENDED_SETUP = {
        "manager": {  # 店长
            "device_model": ShokzDeviceModel.OPENCOMM2_UC,
            "quantity": 1,
            "priority": "high",
            "notifications": ["all"]  # 接收所有通知
        },
        "assistant_manager": {  # 副店长
            "device_model": ShokzDeviceModel.OPENCOMM2_UC,
            "quantity": 1,
            "priority": "medium",
            "notifications": ["takeout", "vip", "complaint"]
        },
        "chef": {  # 厨师长
            "device_model": ShokzDeviceModel.OPENRUN_PRO,
            "quantity": 1,
            "priority": "medium",
            "notifications": ["kitchen", "inventory"]
        }
    }

    def __init__(self):
        self.devices: Dict[str, ShokzDeviceInfo] = {}
        self.interactions: List[VoiceInteraction] = []

    async def register_device(
        self,
        device_name: str,
        device_model: ShokzDeviceModel,
        mac_address: str,
        store_id: str,
        user_id: str,
        user_role: str,
        edge_node_id: str
    ) -> ShokzDeviceInfo:
        """
        注册Shokz设备

        门店部署时，将Shokz耳机与树莓派5配对
        """
        logger.info(
            "注册Shokz设备",
            device_name=device_name,
            mac_address=mac_address,
            store_id=store_id
        )

        device_id = f"shokz_{store_id}_{mac_address.replace(':', '')}"

        device = ShokzDeviceInfo(
            device_id=device_id,
            device_name=device_name,
            device_model=device_model,
            mac_address=mac_address,
            store_id=store_id,
            user_id=user_id,
            user_role=user_role,
            edge_node_id=edge_node_id,
            status=DeviceStatus.DISCONNECTED,
            battery_level=100,
            signal_strength=-50,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.devices[device_id] = device

        logger.info("Shokz设备注册成功", device_id=device_id)
        return device

    async def connect_device(
        self,
        device_id: str
    ) -> ShokzDeviceInfo:
        """
        连接设备

        通过蓝牙连接Shokz耳机到树莓派5
        """
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        device = self.devices[device_id]
        device.status = DeviceStatus.CONNECTED
        device.connected_at = datetime.now()
        device.updated_at = datetime.now()

        logger.info(
            "Shokz设备已连接",
            device_id=device_id,
            device_name=device.device_name
        )

        return device

    async def disconnect_device(
        self,
        device_id: str
    ) -> ShokzDeviceInfo:
        """断开设备连接"""
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        device = self.devices[device_id]
        device.status = DeviceStatus.DISCONNECTED
        device.updated_at = datetime.now()

        logger.info("Shokz设备已断开", device_id=device_id)
        return device

    async def update_battery_level(
        self,
        device_id: str,
        battery_level: int
    ) -> ShokzDeviceInfo:
        """
        更新电量

        Shokz耳机每10分钟上报一次电量
        """
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        device = self.devices[device_id]
        device.battery_level = battery_level
        device.updated_at = datetime.now()

        # 低电量预警
        if battery_level < 20:
            device.status = DeviceStatus.LOW_BATTERY
            logger.warning(
                "Shokz设备电量低",
                device_id=device_id,
                battery_level=battery_level
            )

        return device

    async def voice_input(
        self,
        device_id: str,
        audio_data: str
    ) -> VoiceInteraction:
        """
        语音输入

        店长通过Shokz耳机说话，系统识别并处理
        """
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        device = self.devices[device_id]
        start_time = datetime.now()

        logger.info(
            "接收语音输入",
            device_id=device_id,
            user_role=device.user_role
        )

        # 模拟ASR识别
        text_input = "帮我查一下今天的营业额"
        intent = "query_revenue"
        confidence = 0.95

        # 生成响应
        text_output = "今天截至目前营业额为5.2万元，同比昨天增长15%"

        # 模拟TTS合成
        audio_output = "base64_encoded_audio_data"

        processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        interaction = VoiceInteraction(
            interaction_id=f"interaction_{device_id}_{int(datetime.now().timestamp())}",
            device_id=device_id,
            store_id=device.store_id,
            user_id=device.user_id,
            audio_input=audio_data,
            text_input=text_input,
            intent=intent,
            confidence=confidence,
            text_output=text_output,
            audio_output=audio_output,
            interaction_time=datetime.now(),
            processing_time_ms=processing_time_ms,
            success=True
        )

        self.interactions.append(interaction)
        device.last_command_time = datetime.now()

        logger.info(
            "语音交互完成",
            device_id=device_id,
            intent=intent,
            processing_time_ms=processing_time_ms
        )

        return interaction

    async def voice_output(
        self,
        device_id: str,
        text: str,
        priority: str = "normal"
    ) -> Dict:
        """
        语音输出

        系统主动推送语音通知到Shokz耳机

        场景：
        - 外卖催单："小李，美团外卖3单催单，优先处理"
        - VIP到店："张总到店，上次点的剁椒鱼头，今天推荐香辣蟹"
        - 异常预警："3号桌等待超过30分钟，需要安抚"
        """
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        device = self.devices[device_id]

        logger.info(
            "推送语音通知",
            device_id=device_id,
            text=text,
            priority=priority
        )

        # 模拟TTS合成
        audio_data = "base64_encoded_audio_data"

        # 通过蓝牙发送到Shokz耳机
        result = {
            "device_id": device_id,
            "text": text,
            "audio_data": audio_data,
            "priority": priority,
            "sent_at": datetime.now(),
            "success": True
        }

        return result

    async def send_alert(
        self,
        store_id: str,
        alert_type: VoiceCommand,
        message: str,
        target_roles: List[str] = None
    ) -> List[Dict]:
        """
        发送异常驱动通知

        根据角色筛选，推送到对应的Shokz设备

        示例：
        - 外卖催单 → 店长、副店长
        - VIP到店 → 店长
        - 后厨异常 → 厨师长
        """
        logger.info(
            "发送异常驱动通知",
            store_id=store_id,
            alert_type=alert_type,
            target_roles=target_roles
        )

        # 筛选目标设备
        target_devices = [
            device for device in self.devices.values()
            if device.store_id == store_id
            and device.status == DeviceStatus.CONNECTED
            and (target_roles is None or device.user_role in target_roles)
        ]

        results = []
        for device in target_devices:
            result = await self.voice_output(
                device_id=device.device_id,
                text=message,
                priority="high"
            )
            results.append(result)

        logger.info(
            "异常驱动通知已发送",
            store_id=store_id,
            alert_type=alert_type,
            devices_count=len(results)
        )

        return results

    async def get_device_info(
        self,
        device_id: str
    ) -> ShokzDeviceInfo:
        """获取设备信息"""
        if device_id not in self.devices:
            raise ValueError(f"设备不存在: {device_id}")

        return self.devices[device_id]

    async def list_store_devices(
        self,
        store_id: str
    ) -> List[ShokzDeviceInfo]:
        """列出门店的所有Shokz设备"""
        devices = [
            device for device in self.devices.values()
            if device.store_id == store_id
        ]
        return devices

    async def get_interaction_history(
        self,
        device_id: str,
        limit: int = 100
    ) -> List[VoiceInteraction]:
        """获取语音交互历史"""
        interactions = [
            interaction for interaction in self.interactions
            if interaction.device_id == device_id
        ]
        return interactions[-limit:]

    async def get_device_specs(
        self,
        device_model: ShokzDeviceModel
    ) -> Dict:
        """获取设备规格"""
        return self.DEVICE_SPECS.get(device_model, {})

    async def get_recommended_setup(self) -> Dict:
        """
        获取推荐配置

        用于门店部署指导
        """
        return self.RECOMMENDED_SETUP

    async def get_deployment_cost(self) -> Dict:
        """
        获取部署成本

        用于向投资人证明轻量化部署
        """
        return {
            "hardware": {
                "shokz_opencomm2_uc": 1200.0,  # 店长
                "shokz_opencomm2_uc_2": 1200.0,  # 副店长
                "total": 2400.0
            },
            "accessories": {
                "charging_cables": 50.0,
                "carrying_case": 50.0,
                "total": 100.0
            },
            "implementation": {
                "bluetooth_pairing": 100.0,  # 蓝牙配对（30分钟）
                "voice_training": 200.0,  # 语音训练（1小时）
                "total": 300.0
            },
            "total_cost_per_store": 2800.0,  # 每店总成本（2个设备）
            "deployment_time_hours": 1.5  # 部署时长
        }


# 全局服务实例
shokz_device_service: Optional[ShokzDeviceService] = None


def get_shokz_device_service() -> ShokzDeviceService:
    """获取Shokz设备服务实例"""
    global shokz_device_service
    if shokz_device_service is None:
        shokz_device_service = ShokzDeviceService()
    return shokz_device_service
