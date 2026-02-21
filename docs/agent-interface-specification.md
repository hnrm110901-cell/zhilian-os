# Agent接口规范设计

## 1. 统一接口定义

### 1.1 基础Agent接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class AgentStatus(Enum):
    """Agent状态"""
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

class BaseAgent(ABC):
    """Agent基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作

        Args:
            action: 操作类型（如 "run", "analyze", "predict"）
            params: 操作参数

        Returns:
            AgentResponse: 统一的响应格式
        """
        pass

    @abstractmethod
    def get_supported_actions(self) -> list[str]:
        """返回支持的操作列表"""
        pass

    async def validate_params(self, action: str, params: Dict[str, Any]) -> bool:
        """验证参数"""
        return True
```

### 1.2 各Agent实现示例

#### 排班Agent
```python
class ScheduleAgent(BaseAgent):

    def get_supported_actions(self) -> list[str]:
        return ["run", "adjust", "get"]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        if action == "run":
            result = await self._run_schedule(
                store_id=params.get("store_id"),
                date=params.get("date"),
                employees=params.get("employees", [])
            )
            return AgentResponse(
                success=True,
                data=result,
                execution_time=0.0
            )
        # ... 其他action
```

## 2. 服务层简化

```python
class AgentService:

    async def execute_agent(
        self,
        agent_type: str,
        action: str,
        params: Dict[str, Any]
    ) -> AgentResponse:
        """统一的Agent执行接口"""

        if agent_type not in self._agents:
            return AgentResponse(
                success=False,
                error=f"未知的Agent类型: {agent_type}"
            )

        agent = self._agents[agent_type]

        # 验证action
        if action not in agent.get_supported_actions():
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}"
            )

        # 执行
        return await agent.execute(action, params)
```

## 3. API路由简化

```python
@router.post("/{agent_type}/{action}")
async def execute_agent(
    agent_type: str,
    action: str,
    params: Dict[str, Any]
):
    """统一的Agent API端点"""
    result = await agent_service.execute_agent(
        agent_type=agent_type,
        action=action,
        params=params
    )
    return result
```

## 4. 重构计划

### Phase 1: 基础设施（30分钟）
- [ ] 创建BaseAgent抽象类
- [ ] 定义AgentResponse数据类
- [ ] 更新agent_service.py使用新接口

### Phase 2: Agent重构（90分钟）
- [ ] 重构ScheduleAgent
- [ ] 重构OrderAgent
- [ ] 重构InventoryAgent
- [ ] 重构ServiceAgent
- [ ] 重构TrainingAgent
- [ ] 重构DecisionAgent
- [ ] 重构ReservationAgent

### Phase 3: 测试验证（30分钟）
- [ ] 单元测试
- [ ] 集成测试
- [ ] 业务流程测试

### Phase 4: 文档更新（15分钟）
- [ ] API文档
- [ ] Agent开发指南
- [ ] 示例代码

## 5. 迁移策略

### 渐进式迁移
1. 保留现有实现
2. 新增统一接口层
3. 逐个Agent迁移
4. 测试通过后删除旧代码

### 兼容性保证
- 保持API端点不变
- 保持响应格式兼容
- 添加版本标识

## 6. 预期收益

### 代码质量
- 减少重复代码60%
- 提高类型安全性
- 统一错误处理

### 开发效率
- 新增Agent时间减少70%
- 维护成本降低50%
- 测试覆盖率提升

### 系统稳定性
- 减少接口不匹配错误
- 统一的异常处理
- 更好的可观测性
