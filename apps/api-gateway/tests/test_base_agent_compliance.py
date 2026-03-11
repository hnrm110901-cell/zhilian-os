"""
BaseAgent 接口合规性测试
验证所有7个packages/agents已正确实现BaseAgent协议（P2）
"""
import sys
import inspect
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# 路径常量
AGENTS_ROOT = Path(__file__).parent.parent.parent.parent / "packages" / "agents"
CORE_PATH = Path(__file__).parent.parent / "src" / "core"

# 预先注入 core 路径（base_agent 所在位置）
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))


def _import_agent(agent_name: str):
    """动态导入 packages/agents/{name}/src/agent.py 的 agent 模块"""
    src_path = AGENTS_ROOT / agent_name / "src"
    for p in (str(src_path), str(CORE_PATH)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"agent_{agent_name}", str(src_path / "agent.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_agent(cls):
    """用最小 mock 参数构造 agent 实例（不依赖真实 DB/adapter）"""
    sig = inspect.signature(cls.__init__)
    params = {
        k: MagicMock()
        for k, p in sig.parameters.items()
        if k not in ("self", "kwargs")
        and p.default is inspect.Parameter.empty
    }
    return cls(**params)


# ── 核心接口合规性验证 ────────────────────────────────────────────────────────

class TestBaseAgentInterface:
    """BaseAgent 抽象类 + AgentResponse 基础测试"""

    def test_base_agent_class_exists(self):
        """BaseAgent 抽象类存在且可导入"""
        from base_agent import BaseAgent, AgentResponse, AgentStatus
        assert BaseAgent is not None
        assert AgentResponse is not None
        assert AgentStatus is not None

    def test_agent_response_fields(self):
        """AgentResponse 包含必要字段"""
        from base_agent import AgentResponse
        resp = AgentResponse(success=True, data={"key": "val"}, execution_time=0.1)
        assert resp.success is True
        assert resp.data == {"key": "val"}
        assert resp.execution_time == 0.1
        assert resp.error is None

    def test_agent_response_to_dict(self):
        """AgentResponse.to_dict() 返回完整字典"""
        from base_agent import AgentResponse
        resp = AgentResponse(success=False, error="出错了")
        d = resp.to_dict()
        assert "success" in d
        assert "error" in d
        assert d["success"] is False

    def test_base_agent_is_abstract(self):
        """BaseAgent 不可直接实例化"""
        from base_agent import BaseAgent
        with pytest.raises(TypeError):
            BaseAgent()

    def test_execute_with_timing_returns_agent_response(self):
        """_execute_with_timing 返回 AgentResponse 结构，execution_time > 0"""
        from base_agent import BaseAgent, AgentResponse
        import asyncio

        class ConcreteAgent(BaseAgent):
            def get_supported_actions(self):
                return ["ping"]

            async def execute(self, action, params):
                return AgentResponse(success=True, data={"pong": True})

        agent = ConcreteAgent()
        result = asyncio.run(agent._execute_with_timing("ping", {}))
        assert result.success is True
        assert result.execution_time >= 0

    def test_unsupported_action_returns_error(self):
        """不支持的 action 返回 success=False，包含友好错误消息"""
        from base_agent import BaseAgent, AgentResponse
        import asyncio

        class ConcreteAgent(BaseAgent):
            def get_supported_actions(self):
                return ["ping"]

            async def execute(self, action, params):
                return AgentResponse(success=True, data={})

        agent = ConcreteAgent()
        result = asyncio.run(agent._execute_with_timing("unknown_action", {}))
        assert result.success is False
        assert "不支持的操作" in result.error


# ── 7个 packages Agent 合规性检验 ────────────────────────────────────────────

AGENT_NAMES = ["schedule", "order", "inventory", "service", "training", "reservation", "decision"]


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_agent_inherits_base_agent(agent_name):
    """每个 Agent 继承 BaseAgent"""
    from base_agent import BaseAgent
    mod = _import_agent(agent_name)
    agent_classes = [
        obj for name, obj in vars(mod).items()
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent
    ]
    assert len(agent_classes) >= 1, f"{agent_name}: 未找到继承 BaseAgent 的类"


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_agent_implements_execute(agent_name):
    """每个 Agent 实现了 async execute() 方法"""
    from base_agent import BaseAgent
    mod = _import_agent(agent_name)
    agent_classes = [
        obj for name, obj in vars(mod).items()
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent
    ]
    assert agent_classes, f"{agent_name}: 无 BaseAgent 子类"
    for cls in agent_classes:
        assert hasattr(cls, "execute"), f"{agent_name}.{cls.__name__}: 缺少 execute 方法"
        assert inspect.iscoroutinefunction(cls.execute), \
            f"{agent_name}.{cls.__name__}: execute 必须是 async"


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_agent_implements_get_supported_actions(agent_name):
    """每个 Agent 实现了 get_supported_actions()，返回非空 list"""
    from base_agent import BaseAgent
    mod = _import_agent(agent_name)
    agent_classes = [
        obj for name, obj in vars(mod).items()
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent
    ]
    for cls in agent_classes:
        assert hasattr(cls, "get_supported_actions"), \
            f"{agent_name}.{cls.__name__}: 缺少 get_supported_actions 方法"
        agent = _make_agent(cls)
        actions = agent.get_supported_actions()
        assert isinstance(actions, list), f"{agent_name}: get_supported_actions 应返回 list"
        assert len(actions) > 0, f"{agent_name}: get_supported_actions 不应为空"


@pytest.mark.parametrize("agent_name", AGENT_NAMES)
def test_agent_get_info(agent_name):
    """每个 Agent 的 get_info() 返回包含 name/status/supported_actions 的字典"""
    from base_agent import BaseAgent
    mod = _import_agent(agent_name)
    agent_classes = [
        obj for name, obj in vars(mod).items()
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent
    ]
    for cls in agent_classes:
        agent = _make_agent(cls)
        info = agent.get_info()
        assert "name" in info
        assert "status" in info
        assert "supported_actions" in info
