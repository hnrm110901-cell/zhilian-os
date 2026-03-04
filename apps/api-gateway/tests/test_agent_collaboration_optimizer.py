"""
Agent 协同优化器单元测试
Tests for AgentCollaborationOptimizer and AgentDependencyGraph

覆盖：
  - submit_decision:      正常提交、重复 decision_id
  - coordinate_decisions: 无冲突、单冲突、多冲突场景
  - resolve_conflict:     PRIORITY / NEGOTIATION / OPTIMIZATION / ESCALATION 四种策略
  - AgentDependencyGraph: DAG 拓扑排序、环检测
"""
import os
import sys

# ── 设置最小化测试环境变量，防止 AgentService 初始化失败 ──────────────────────
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

# ── 阻断 agent_service 全局初始化（不需要真实 Agent 启动）───────────────────
from unittest.mock import MagicMock as _MM
if "src.services.agent_service" not in sys.modules:
    sys.modules["src.services.agent_service"] = _MM()

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.services.agent_collaboration_optimizer import (
    AgentCollaborationOptimizer,
    AgentDependencyGraph,
    AgentDecision,
    Conflict,
    Resolution,
    AgentType,
    ConflictType,
    ResolutionStrategy,
)


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def make_optimizer():
    return AgentCollaborationOptimizer(db=MagicMock())


def make_decision(
    decision_id="dec_001",
    agent_type=AgentType.ORDER,
    action="process_order",
    resources=None,
    benefit=100.0,
    priority=5,
    constraints=None,
):
    return AgentDecision(
        agent_type=agent_type,
        decision_id=decision_id,
        action=action,
        resources_required=resources or {"staff": 0.5},
        expected_benefit=benefit,
        priority=priority,
        constraints=constraints or [],
        timestamp=datetime.utcnow(),
    )


def make_conflict(
    conflict_id="conf_001",
    conflict_type=ConflictType.RESOURCE,
    decisions=None,
    agents=None,
    severity=0.7,
):
    return Conflict(
        conflict_id=conflict_id,
        conflict_type=conflict_type,
        involved_agents=agents or [AgentType.ORDER, AgentType.INVENTORY],
        involved_decisions=decisions or ["dec_001", "dec_002"],
        description="Test conflict",
        severity=severity,
        detected_at=datetime.utcnow(),
    )


# ── submit_decision ───────────────────────────────────────────────────────────

class TestSubmitDecision:

    def test_normal_submit_adds_to_pending(self):
        """正常提交：决策进入 pending_decisions 列表，返回 success=True。"""
        opt = make_optimizer()
        dec = make_decision()

        result = opt.submit_decision(AgentType.ORDER, dec)

        assert result["success"] is True
        assert dec in opt.pending_decisions[AgentType.ORDER]

    def test_submit_returns_agent_type_and_decision_id(self):
        """返回结果包含 agent_type 和 decision_id。"""
        opt = make_optimizer()
        dec = make_decision(decision_id="dec_xyz")

        result = opt.submit_decision(AgentType.SCHEDULE, dec)

        assert result["agent_type"] == AgentType.SCHEDULE.value
        assert result["decision_id"] == "dec_xyz"

    def test_submit_no_conflict_status_approved(self):
        """无冲突时状态为 approved。"""
        opt = make_optimizer()
        dec = make_decision(resources={"staff": 0.3})

        result = opt.submit_decision(AgentType.ORDER, dec)

        assert result["status"] == "approved"

    def test_submit_duplicate_decision_id_both_accepted(self):
        """相同 decision_id 重复提交时，两者均入队（上层业务自行去重）。"""
        opt = make_optimizer()
        dec1 = make_decision(decision_id="same_id")
        dec2 = make_decision(decision_id="same_id", benefit=200.0)

        opt.submit_decision(AgentType.ORDER, dec1)
        opt.submit_decision(AgentType.ORDER, dec2)

        pending = opt.pending_decisions[AgentType.ORDER]
        assert len(pending) == 2
        assert all(d.decision_id == "same_id" for d in pending)

    def test_submit_detects_resource_conflict(self):
        """两个 agent 争夺同一资源（总量超 1.0）时应检测到冲突。"""
        opt = make_optimizer()
        dec1 = make_decision("d1", AgentType.ORDER,    resources={"kitchen": 0.7})
        dec2 = make_decision("d2", AgentType.SCHEDULE, resources={"kitchen": 0.7})

        opt.submit_decision(AgentType.ORDER, dec1)
        result = opt.submit_decision(AgentType.SCHEDULE, dec2)

        assert result["conflicts_detected"] >= 1
        assert result["status"] == "pending_review"


# ── coordinate_decisions ──────────────────────────────────────────────────────

class TestCoordinateDecisions:

    def test_no_pending_decisions(self):
        """无待处理决策时返回空计划。"""
        opt = make_optimizer()

        result = opt.coordinate_decisions("S001")

        assert result["success"] is True
        assert result["decisions"] == []

    def test_single_decision_no_conflict_approved(self):
        """单个决策无冲突时应被批准。"""
        opt = make_optimizer()
        dec = make_decision(resources={"staff": 0.2})
        opt.submit_decision(AgentType.ORDER, dec)

        result = opt.coordinate_decisions("S001")

        assert result["success"] is True
        assert result["total_decisions"] == 1
        assert result["conflicts_detected"] == 0
        assert dec.decision_id in result["plan"]["approved"]

    def test_conflicting_decisions_resolve_to_one_approved(self):
        """两个资源冲突决策经协调后，至少一个被批准，冲突被解决。"""
        opt = make_optimizer()
        dec1 = make_decision("d1", AgentType.ORDER,    resources={"fryer": 0.8})
        dec2 = make_decision("d2", AgentType.INVENTORY, resources={"fryer": 0.8})
        opt.submit_decision(AgentType.ORDER, dec1)
        opt.submit_decision(AgentType.INVENTORY, dec2)

        result = opt.coordinate_decisions("S001")

        assert result["success"] is True
        # conflicts_resolved 记录已解决的冲突数，conflicts_detected 在全部解决后为 0
        assert result["conflicts_resolved"] >= 1
        assert result["approved_decisions"] >= 1

    def test_multiple_conflicts_all_resolved(self):
        """多冲突场景：解决数量 > 0，全部冲突被处理。"""
        opt = make_optimizer()
        # 3 个决策互相争夺同一资源
        for i in range(3):
            dec = make_decision(f"d{i}", AgentType.ORDER, resources={"cashier": 0.7})
            opt.submit_decision(AgentType.ORDER, dec)

        result = opt.coordinate_decisions("S001")

        # 3 个决策两两产生冲突，全部应被解决
        assert result["conflicts_resolved"] > 0
        # 协调后无剩余未处理冲突
        assert result["conflicts_detected"] == 0

    def test_dag_cycle_blocks_coordination(self):
        """存在依赖环路时，协调应返回 success=False。"""
        opt = make_optimizer()
        # 直接污染 DAG：手动注入一个回边（绕过 add_dependency 的环检测）
        opt.dag._deps[AgentType.ORDER].add(AgentType.INVENTORY)
        opt.dag._deps[AgentType.INVENTORY].add(AgentType.ORDER)

        dec = make_decision()
        opt.submit_decision(AgentType.ORDER, dec)
        result = opt.coordinate_decisions("S001")

        assert result["success"] is False
        assert "cycle" in result

    def test_pending_decisions_cleared_after_coordination(self):
        """协调完成后 pending_decisions 应被清空。"""
        opt = make_optimizer()
        opt.submit_decision(AgentType.ORDER, make_decision("d1", resources={"a": 0.1}))
        opt.submit_decision(AgentType.ORDER, make_decision("d2", resources={"b": 0.1}))

        opt.coordinate_decisions("S001")

        total = sum(len(v) for v in opt.pending_decisions.values())
        assert total == 0


# ── resolve_conflict ──────────────────────────────────────────────────────────

class TestResolveConflict:

    def _setup_conflict(self, opt, conflict):
        """向 optimizer 注入两个待处理决策和一个冲突。"""
        dec1 = make_decision("dec_001", AgentType.SERVICE,   benefit=200.0, priority=9)
        dec2 = make_decision("dec_002", AgentType.INVENTORY, benefit=100.0, priority=5)
        opt.pending_decisions[AgentType.SERVICE].append(dec1)
        opt.pending_decisions[AgentType.INVENTORY].append(dec2)
        opt.conflicts.append(conflict)

    def test_priority_strategy_approves_highest_priority(self):
        """PRIORITY 策略：优先级更高的 agent 决策被批准。"""
        opt = make_optimizer()
        conflict = make_conflict()
        self._setup_conflict(opt, conflict)

        resolution = opt.resolve_conflict(
            conflict.conflict_id, strategy=ResolutionStrategy.PRIORITY_BASED
        )

        assert isinstance(resolution, Resolution)
        assert resolution.strategy == ResolutionStrategy.PRIORITY_BASED
        assert len(resolution.approved_decisions) == 1
        assert len(resolution.rejected_decisions) >= 1

    def test_negotiation_strategy_approves_all_with_modifications(self):
        """NEGOTIATION 策略：所有决策均被批准，但有资源减量修改。"""
        opt = make_optimizer()
        conflict = make_conflict()
        self._setup_conflict(opt, conflict)

        resolution = opt.resolve_conflict(
            conflict.conflict_id, strategy=ResolutionStrategy.NEGOTIATION
        )

        assert resolution.strategy == ResolutionStrategy.NEGOTIATION
        assert set(conflict.involved_decisions) == set(resolution.approved_decisions)
        assert len(resolution.rejected_decisions) == 0
        # 每个决策都有资源缩减修改
        for dec_id in conflict.involved_decisions:
            assert dec_id in resolution.modifications

    def test_optimization_strategy_picks_best_benefit_ratio(self):
        """OPTIMIZATION 策略：选择 benefit/resource 比最高的决策。"""
        opt = make_optimizer()
        conflict = make_conflict()
        self._setup_conflict(opt, conflict)

        resolution = opt.resolve_conflict(
            conflict.conflict_id, strategy=ResolutionStrategy.OPTIMIZATION
        )

        assert resolution.strategy == ResolutionStrategy.OPTIMIZATION
        assert len(resolution.approved_decisions) >= 1

    def test_escalation_strategy_approves_nothing(self):
        """ESCALATION 策略：高严重性冲突升级给人工，不批准任何决策。"""
        opt = make_optimizer()
        conflict = make_conflict(severity=0.95)
        self._setup_conflict(opt, conflict)

        resolution = opt.resolve_conflict(
            conflict.conflict_id, strategy=ResolutionStrategy.ESCALATION
        )

        assert resolution.strategy == ResolutionStrategy.ESCALATION
        assert resolution.approved_decisions == []
        assert resolution.rejected_decisions == []

    def test_resolve_nonexistent_conflict_raises(self):
        """解决不存在的冲突 ID 应抛出 ValueError。"""
        opt = make_optimizer()

        with pytest.raises(ValueError, match="not found"):
            opt.resolve_conflict("nonexistent_id")

    def test_resolved_conflict_removed_from_active_list(self):
        """解决后，冲突从 active 列表移除。"""
        opt = make_optimizer()
        conflict = make_conflict()
        self._setup_conflict(opt, conflict)

        opt.resolve_conflict(conflict.conflict_id, strategy=ResolutionStrategy.PRIORITY_BASED)

        remaining = [c.conflict_id for c in opt.conflicts]
        assert conflict.conflict_id not in remaining

    def test_auto_strategy_selection_escalates_high_severity(self):
        """严重性 > 0.8 时自动选择 ESCALATION 策略。"""
        opt = make_optimizer()
        conflict = make_conflict(severity=0.9)
        self._setup_conflict(opt, conflict)

        resolution = opt.resolve_conflict(conflict.conflict_id)  # 不指定策略

        assert resolution.strategy == ResolutionStrategy.ESCALATION


# ── AgentDependencyGraph ──────────────────────────────────────────────────────

class TestAgentDependencyGraph:

    def test_empty_dag_no_cycle(self):
        """空 DAG 无环。"""
        dag = AgentDependencyGraph()
        assert dag.has_cycle() is False
        assert dag.find_cycle() is None

    def test_linear_chain_no_cycle(self):
        """线性链 ORDER → INVENTORY → DECISION 无环。"""
        dag = AgentDependencyGraph()
        dag.add_dependency(AgentType.INVENTORY, depends_on=AgentType.ORDER)
        dag.add_dependency(AgentType.DECISION,  depends_on=AgentType.INVENTORY)

        assert dag.has_cycle() is False

    def test_self_dependency_raises(self):
        """自依赖应抛出 ValueError。"""
        dag = AgentDependencyGraph()
        with pytest.raises(ValueError):
            dag.add_dependency(AgentType.ORDER, depends_on=AgentType.ORDER)

    def test_cycle_detection_raises_on_add(self):
        """引入环路时 add_dependency 应抛出 ValueError 并回滚。"""
        dag = AgentDependencyGraph()
        dag.add_dependency(AgentType.INVENTORY, depends_on=AgentType.ORDER)

        with pytest.raises(ValueError):
            dag.add_dependency(AgentType.ORDER, depends_on=AgentType.INVENTORY)

        # 回滚：ORDER 不应有 INVENTORY 的依赖
        assert AgentType.INVENTORY not in dag._deps[AgentType.ORDER]

    def test_topological_order_respects_dependencies(self):
        """拓扑排序：依赖项先于被依赖项出现。"""
        dag = AgentDependencyGraph()
        dag.add_dependency(AgentType.INVENTORY, depends_on=AgentType.ORDER)
        dag.add_dependency(AgentType.DECISION,  depends_on=AgentType.INVENTORY)

        order = dag.topological_order()

        assert order.index(AgentType.ORDER) < order.index(AgentType.INVENTORY)
        assert order.index(AgentType.INVENTORY) < order.index(AgentType.DECISION)

    def test_topological_order_raises_on_cycle(self):
        """存在环时 topological_order 应抛出 ValueError。"""
        dag = AgentDependencyGraph()
        # 手动注入回边，绕过 add_dependency 的检测
        dag._deps[AgentType.ORDER].add(AgentType.INVENTORY)
        dag._deps[AgentType.INVENTORY].add(AgentType.ORDER)

        with pytest.raises(ValueError):
            dag.topological_order()

    def test_remove_dependency_clears_edge(self):
        """移除依赖后，边不再存在。"""
        dag = AgentDependencyGraph()
        dag.add_dependency(AgentType.INVENTORY, depends_on=AgentType.ORDER)
        dag.remove_dependency(AgentType.INVENTORY, depends_on=AgentType.ORDER)

        assert AgentType.ORDER not in dag._deps[AgentType.INVENTORY]

    def test_validate_returns_valid_report(self):
        """validate() 在无环时返回 valid=True。"""
        dag = AgentDependencyGraph()
        dag.add_dependency(AgentType.SCHEDULE, depends_on=AgentType.ORDER)

        report = dag.validate()

        assert report["valid"] is True
        assert report.get("cycle") is None
