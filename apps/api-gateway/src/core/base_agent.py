"""
Agent基础接口定义
定义所有Agent必须遵循的统一接口规范
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import time


class AgentStatus(Enum):
    """Agent状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class AgentResponse:
    """统一的Agent响应格式"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)


class BaseAgent(ABC):
    """
    Agent基类
    所有Agent必须继承此类并实现抽象方法
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Agent

        Args:
            config: Agent配置字典（可选）
        """
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.logger = None  # 子类可以设置logger

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作（核心方法）

        Args:
            action: 操作类型（如 "run", "analyze", "predict"）
            params: 操作参数字典

        Returns:
            AgentResponse: 统一的响应格式

        Raises:
            ValueError: 当action不支持时
        """
        pass

    @abstractmethod
    def get_supported_actions(self) -> List[str]:
        """
        返回此Agent支持的所有操作列表

        Returns:
            List[str]: 支持的操作名称列表
        """
        pass

    async def validate_params(self, action: str, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证参数是否有效（可选重写）

        Args:
            action: 操作类型
            params: 参数字典

        Returns:
            tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        return True, None

    def get_info(self) -> Dict[str, Any]:
        """
        获取Agent信息（可选重写）

        Returns:
            Dict[str, Any]: Agent信息字典
        """
        return {
            "name": self.__class__.__name__,
            "status": self.status.value,
            "supported_actions": self.get_supported_actions(),
        }

    async def _execute_with_timing(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行操作并记录时间（内部方法）

        Args:
            action: 操作类型
            params: 参数字典

        Returns:
            AgentResponse: 响应对象
        """
        start_time = time.time()
        self.status = AgentStatus.RUNNING

        try:
            # 验证action
            if action not in self.get_supported_actions():
                self.status = AgentStatus.ERROR
                return AgentResponse(
                    success=False,
                    error=f"不支持的操作: {action}。支持的操作: {', '.join(self.get_supported_actions())}",
                    execution_time=time.time() - start_time
                )

            # 验证参数
            valid, error_msg = await self.validate_params(action, params)
            if not valid:
                self.status = AgentStatus.ERROR
                return AgentResponse(
                    success=False,
                    error=f"参数验证失败: {error_msg}",
                    execution_time=time.time() - start_time
                )

            # 执行操作
            response = await self.execute(action, params)
            response.execution_time = time.time() - start_time

            self.status = AgentStatus.SUCCESS if response.success else AgentStatus.ERROR
            return response

        except Exception as e:
            self.status = AgentStatus.ERROR
            return AgentResponse(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
