"""
WebSocket Connection Manager
管理WebSocket连接和消息推送
"""
from typing import Dict, List, Set
from fastapi import WebSocket
import json
import structlog
from datetime import datetime

logger = structlog.get_logger()


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        # 存储活跃连接: {user_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # 存储用户角色: {user_id: role}
        self.user_roles: Dict[str, str] = {}
        # 存储用户门店: {user_id: store_id}
        self.user_stores: Dict[str, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str, role: str, store_id: str = None):
        """建立WebSocket连接"""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)
        self.user_roles[user_id] = role
        if store_id:
            self.user_stores[user_id] = store_id

        logger.info(
            "WebSocket连接建立",
            user_id=user_id,
            role=role,
            store_id=store_id,
            total_connections=sum(len(conns) for conns in self.active_connections.values()),
        )

    def disconnect(self, websocket: WebSocket, user_id: str):
        """断开WebSocket连接"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)

            # 如果用户没有活跃连接了,清理数据
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.user_roles:
                    del self.user_roles[user_id]
                if user_id in self.user_stores:
                    del self.user_stores[user_id]

        logger.info(
            "WebSocket连接断开",
            user_id=user_id,
            remaining_connections=sum(len(conns) for conns in self.active_connections.values()),
        )

    async def send_personal_message(self, message: dict, user_id: str):
        """发送个人消息"""
        if user_id in self.active_connections:
            message_json = json.dumps(message, ensure_ascii=False)
            disconnected = []

            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message_json)
                except Exception as e:
                    logger.error("发送消息失败", user_id=user_id, error=str(e))
                    disconnected.append(connection)

            # 清理断开的连接
            for conn in disconnected:
                self.disconnect(conn, user_id)

    async def send_to_role(self, message: dict, role: str, store_id: str = None):
        """发送消息给特定角色的所有用户"""
        message_json = json.dumps(message, ensure_ascii=False)
        sent_count = 0

        for user_id, user_role in self.user_roles.items():
            # 检查角色匹配
            if user_role != role:
                continue

            # 如果指定了门店,检查门店匹配
            if store_id and self.user_stores.get(user_id) != store_id:
                continue

            # 发送消息
            if user_id in self.active_connections:
                for connection in self.active_connections[user_id]:
                    try:
                        await connection.send_text(message_json)
                        sent_count += 1
                    except Exception as e:
                        logger.error("发送消息失败", user_id=user_id, error=str(e))

        logger.info("角色消息发送完成", role=role, store_id=store_id, sent_count=sent_count)

    async def send_to_store(self, message: dict, store_id: str):
        """发送消息给特定门店的所有用户"""
        message_json = json.dumps(message, ensure_ascii=False)
        sent_count = 0

        for user_id, user_store_id in self.user_stores.items():
            if user_store_id == store_id and user_id in self.active_connections:
                for connection in self.active_connections[user_id]:
                    try:
                        await connection.send_text(message_json)
                        sent_count += 1
                    except Exception as e:
                        logger.error("发送消息失败", user_id=user_id, error=str(e))

        logger.info("门店消息发送完成", store_id=store_id, sent_count=sent_count)

    async def broadcast(self, message: dict):
        """广播消息给所有连接的用户"""
        message_json = json.dumps(message, ensure_ascii=False)
        sent_count = 0

        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_text(message_json)
                    sent_count += 1
                except Exception as e:
                    logger.error("广播消息失败", user_id=user_id, error=str(e))

        logger.info("广播消息发送完成", sent_count=sent_count)

    def get_active_users(self) -> List[str]:
        """获取所有活跃用户ID"""
        return list(self.active_connections.keys())

    def get_connection_count(self) -> int:
        """获取总连接数"""
        return sum(len(conns) for conns in self.active_connections.values())


# 全局连接管理器实例
manager = ConnectionManager()
