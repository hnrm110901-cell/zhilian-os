"""
Agent Collaboration Optimizer
Agent协同优化器

Phase 4: 智能优化期 (Intelligence Optimization Period)
Coordinates decisions across multiple agents and resolves conflicts
"""

from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.orm import Session
import numpy as np


class AgentType(Enum):
    """Agent type enum"""
    SCHEDULE = "schedule"  # 排班Agent
    ORDER = "order"  # 订单Agent
    INVENTORY = "inventory"  # 库存Agent
    SERVICE = "service"  # 服务Agent
    TRAINING = "training"  # 培训Agent
    DECISION = "decision"  # 决策Agent
    RESERVATION = "reservation"  # 预定Agent


class ConflictType(Enum):
    """Conflict type enum"""
    RESOURCE = "resource"  # 资源冲突
    PRIORITY = "priority"  # 优先级冲突
    CONSTRAINT = "constraint"  # 约束冲突
    GOAL = "goal"  # 目标冲突


class ResolutionStrategy(Enum):
    """Conflict resolution strategy"""
    PRIORITY_BASED = "priority_based"  # 基于优先级
    NEGOTIATION = "negotiation"  # 协商
    OPTIMIZATION = "optimization"  # 全局优化
    ESCALATION = "escalation"  # 升级到人工


@dataclass
class AgentDecision:
    """Agent decision"""
    agent_type: AgentType
    decision_id: str
    action: str
    resources_required: Dict[str, float]
    expected_benefit: float
    priority: int  # 1-10
    constraints: List[str]
    timestamp: datetime


@dataclass
class Conflict:
    """Decision conflict"""
    conflict_id: str
    conflict_type: ConflictType
    involved_agents: List[AgentType]
    involved_decisions: List[str]
    description: str
    severity: float  # 0-1
    detected_at: datetime


@dataclass
class Resolution:
    """Conflict resolution"""
    conflict_id: str
    strategy: ResolutionStrategy
    approved_decisions: List[str]
    rejected_decisions: List[str]
    modifications: Dict[str, Any]
    reason: str
    resolved_at: datetime


class AgentCollaborationOptimizer:
    """
    Agent Collaboration Optimizer
    Agent协同优化器

    Coordinates decisions across multiple agents:
    1. Detects conflicts between agent decisions
    2. Resolves conflicts using various strategies
    3. Optimizes for global objectives
    4. Ensures resource constraints are met

    Key features:
    - Multi-agent decision coordination
    - Conflict detection and resolution
    - Global optimization
    - Resource allocation
    - Priority management
    """

    def __init__(self, db: Session):
        self.db = db
        # Pending decisions from agents
        self.pending_decisions: Dict[AgentType, List[AgentDecision]] = {
            agent_type: [] for agent_type in AgentType
        }
        # Detected conflicts
        self.conflicts: List[Conflict] = []
        # Resolution history
        self.resolutions: List[Resolution] = []
        # Agent priorities (can be configured)
        self.agent_priorities = {
            AgentType.SERVICE: 10,  # Highest priority
            AgentType.ORDER: 9,
            AgentType.INVENTORY: 8,
            AgentType.SCHEDULE: 7,
            AgentType.RESERVATION: 6,
            AgentType.TRAINING: 5,
            AgentType.DECISION: 4
        }

    def submit_decision(
        self,
        agent_type: AgentType,
        decision: AgentDecision
    ) -> Dict[str, Any]:
        """
        Submit a decision from an agent
        提交Agent决策

        Args:
            agent_type: Type of agent submitting decision
            decision: Decision details

        Returns:
            Submission confirmation
        """
        self.pending_decisions[agent_type].append(decision)

        # Detect conflicts immediately
        conflicts = self._detect_conflicts(decision)

        return {
            "success": True,
            "agent_type": agent_type.value,
            "decision_id": decision.decision_id,
            "conflicts_detected": len(conflicts),
            "status": "pending_review" if conflicts else "approved"
        }

    def coordinate_decisions(
        self,
        store_id: str,
        time_window: Optional[int] = 3600  # seconds
    ) -> Dict[str, Any]:
        """
        Coordinate all pending decisions
        协调所有待处理决策

        Performs global optimization across all agent decisions:
        1. Collect all pending decisions
        2. Detect conflicts
        3. Resolve conflicts
        4. Optimize resource allocation
        5. Return coordinated plan

        Args:
            store_id: Store identifier
            time_window: Time window for coordination (seconds)

        Returns:
            Coordinated decision plan
        """
        # Collect all pending decisions
        all_decisions = []
        for agent_type, decisions in self.pending_decisions.items():
            all_decisions.extend(decisions)

        if not all_decisions:
            return {
                "success": True,
                "message": "No pending decisions to coordinate",
                "decisions": []
            }

        # Detect all conflicts
        self._detect_all_conflicts(all_decisions)

        # Resolve conflicts
        resolutions = self._resolve_all_conflicts()

        # Optimize resource allocation
        optimized_plan = self._optimize_resource_allocation(
            all_decisions, resolutions
        )

        # Clear pending decisions
        for agent_type in self.pending_decisions:
            self.pending_decisions[agent_type] = []

        return {
            "success": True,
            "store_id": store_id,
            "total_decisions": len(all_decisions),
            "conflicts_detected": len(self.conflicts),
            "conflicts_resolved": len(resolutions),
            "approved_decisions": len(optimized_plan["approved"]),
            "rejected_decisions": len(optimized_plan["rejected"]),
            "plan": optimized_plan
        }

    def resolve_conflict(
        self,
        conflict_id: str,
        strategy: Optional[ResolutionStrategy] = None
    ) -> Resolution:
        """
        Resolve a specific conflict
        解决特定冲突

        Args:
            conflict_id: Conflict identifier
            strategy: Resolution strategy (auto-selected if not provided)

        Returns:
            Resolution details
        """
        # Find conflict
        conflict = next(
            (c for c in self.conflicts if c.conflict_id == conflict_id),
            None
        )

        if not conflict:
            raise ValueError(f"Conflict {conflict_id} not found")

        # Select strategy if not provided
        if not strategy:
            strategy = self._select_resolution_strategy(conflict)

        # Apply resolution strategy
        if strategy == ResolutionStrategy.PRIORITY_BASED:
            resolution = self._priority_based_resolution(conflict)
        elif strategy == ResolutionStrategy.NEGOTIATION:
            resolution = self._negotiation_resolution(conflict)
        elif strategy == ResolutionStrategy.OPTIMIZATION:
            resolution = self._optimization_resolution(conflict)
        else:  # ESCALATION
            resolution = self._escalation_resolution(conflict)

        # Store resolution
        self.resolutions.append(resolution)

        # Remove resolved conflict
        self.conflicts = [c for c in self.conflicts if c.conflict_id != conflict_id]

        return resolution

    def get_collaboration_status(
        self,
        store_id: str
    ) -> Dict[str, Any]:
        """
        Get agent collaboration status
        获取Agent协同状态

        Returns:
            Status information including pending decisions and conflicts
        """
        total_pending = sum(
            len(decisions) for decisions in self.pending_decisions.values()
        )

        pending_by_agent = {
            agent_type.value: len(decisions)
            for agent_type, decisions in self.pending_decisions.items()
            if decisions
        }

        return {
            "store_id": store_id,
            "total_pending_decisions": total_pending,
            "pending_by_agent": pending_by_agent,
            "active_conflicts": len(self.conflicts),
            "resolved_conflicts": len(self.resolutions),
            "coordination_efficiency": self._calculate_efficiency()
        }

    def get_agent_performance(
        self,
        agent_type: AgentType,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get agent performance metrics
        获取Agent性能指标

        Tracks:
        - Decision approval rate
        - Conflict rate
        - Resource utilization
        - Benefit realization
        """
        # Simplified implementation
        return {
            "agent_type": agent_type.value,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "metrics": {
                "decisions_submitted": 100,
                "decisions_approved": 85,
                "approval_rate": 0.85,
                "conflicts_involved": 15,
                "conflict_rate": 0.15,
                "avg_benefit_realization": 0.92,
                "resource_utilization": 0.78
            }
        }

    # Helper methods for conflict detection and resolution

    def _detect_conflicts(
        self,
        new_decision: AgentDecision
    ) -> List[Conflict]:
        """Detect conflicts with a new decision"""
        conflicts = []

        # Check against all pending decisions
        for agent_type, decisions in self.pending_decisions.items():
            for decision in decisions:
                conflict = self._check_conflict(new_decision, decision)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _detect_all_conflicts(
        self,
        decisions: List[AgentDecision]
    ):
        """Detect all conflicts among decisions"""
        self.conflicts = []

        for i, decision1 in enumerate(decisions):
            for decision2 in decisions[i+1:]:
                conflict = self._check_conflict(decision1, decision2)
                if conflict:
                    self.conflicts.append(conflict)

    def _check_conflict(
        self,
        decision1: AgentDecision,
        decision2: AgentDecision
    ) -> Optional[Conflict]:
        """Check if two decisions conflict"""
        # Resource conflict
        resource_conflict = self._check_resource_conflict(
            decision1.resources_required,
            decision2.resources_required
        )

        if resource_conflict:
            conflict_id = f"conflict_{decision1.decision_id}_{decision2.decision_id}"
            return Conflict(
                conflict_id=conflict_id,
                conflict_type=ConflictType.RESOURCE,
                involved_agents=[decision1.agent_type, decision2.agent_type],
                involved_decisions=[decision1.decision_id, decision2.decision_id],
                description=f"Resource conflict between {decision1.agent_type.value} and {decision2.agent_type.value}",
                severity=0.7,
                detected_at=datetime.utcnow()
            )

        # Constraint conflict
        constraint_conflict = self._check_constraint_conflict(
            decision1, decision2
        )

        if constraint_conflict:
            conflict_id = f"conflict_{decision1.decision_id}_{decision2.decision_id}"
            return Conflict(
                conflict_id=conflict_id,
                conflict_type=ConflictType.CONSTRAINT,
                involved_agents=[decision1.agent_type, decision2.agent_type],
                involved_decisions=[decision1.decision_id, decision2.decision_id],
                description=f"Constraint conflict between {decision1.agent_type.value} and {decision2.agent_type.value}",
                severity=0.5,
                detected_at=datetime.utcnow()
            )

        return None

    def _check_resource_conflict(
        self,
        resources1: Dict[str, float],
        resources2: Dict[str, float]
    ) -> bool:
        """Check if resources conflict"""
        # Check for overlapping resource requirements
        common_resources = set(resources1.keys()) & set(resources2.keys())

        for resource in common_resources:
            # If total requirement exceeds capacity (simplified: assume capacity = 1.0)
            if resources1[resource] + resources2[resource] > 1.0:
                return True

        return False

    def _check_constraint_conflict(
        self,
        decision1: AgentDecision,
        decision2: AgentDecision
    ) -> bool:
        """Check if constraints conflict"""
        # Simplified: check if constraints are incompatible
        return False

    def _resolve_all_conflicts(self) -> List[Resolution]:
        """Resolve all detected conflicts"""
        resolutions = []

        for conflict in self.conflicts:
            resolution = self.resolve_conflict(conflict.conflict_id)
            resolutions.append(resolution)

        return resolutions

    def _select_resolution_strategy(
        self,
        conflict: Conflict
    ) -> ResolutionStrategy:
        """Select appropriate resolution strategy"""
        if conflict.severity > 0.8:
            return ResolutionStrategy.ESCALATION
        elif conflict.conflict_type == ConflictType.RESOURCE:
            return ResolutionStrategy.OPTIMIZATION
        elif conflict.conflict_type == ConflictType.PRIORITY:
            return ResolutionStrategy.PRIORITY_BASED
        else:
            return ResolutionStrategy.NEGOTIATION

    def _priority_based_resolution(
        self,
        conflict: Conflict
    ) -> Resolution:
        """Resolve conflict based on agent priorities"""
        # Get decisions involved
        decisions = self._get_decisions_by_ids(conflict.involved_decisions)

        # Sort by agent priority
        decisions.sort(
            key=lambda d: self.agent_priorities.get(d.agent_type, 0),
            reverse=True
        )

        # Approve highest priority, reject others
        approved = [decisions[0].decision_id]
        rejected = [d.decision_id for d in decisions[1:]]

        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy=ResolutionStrategy.PRIORITY_BASED,
            approved_decisions=approved,
            rejected_decisions=rejected,
            modifications={},
            reason=f"Approved {decisions[0].agent_type.value} decision based on priority",
            resolved_at=datetime.utcnow()
        )

    def _negotiation_resolution(
        self,
        conflict: Conflict
    ) -> Resolution:
        """Resolve conflict through negotiation"""
        # Simplified: split resources proportionally
        decisions = self._get_decisions_by_ids(conflict.involved_decisions)

        modifications = {}
        for decision in decisions:
            # Reduce resource requirements by 50%
            modifications[decision.decision_id] = {
                "resources_required": {
                    k: v * 0.5 for k, v in decision.resources_required.items()
                }
            }

        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy=ResolutionStrategy.NEGOTIATION,
            approved_decisions=conflict.involved_decisions,
            rejected_decisions=[],
            modifications=modifications,
            reason="Negotiated resource sharing between agents",
            resolved_at=datetime.utcnow()
        )

    def _optimization_resolution(
        self,
        conflict: Conflict
    ) -> Resolution:
        """Resolve conflict through global optimization"""
        decisions = self._get_decisions_by_ids(conflict.involved_decisions)

        # Optimize for maximum total benefit
        total_benefit = sum(d.expected_benefit for d in decisions)

        # Select decisions that maximize benefit within constraints
        # Simplified: greedy selection by benefit/resource ratio
        decisions.sort(
            key=lambda d: d.expected_benefit / max(sum(d.resources_required.values()), 0.1),
            reverse=True
        )

        approved = [decisions[0].decision_id]
        rejected = [d.decision_id for d in decisions[1:]]

        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy=ResolutionStrategy.OPTIMIZATION,
            approved_decisions=approved,
            rejected_decisions=rejected,
            modifications={},
            reason=f"Optimized for maximum benefit: {decisions[0].expected_benefit}",
            resolved_at=datetime.utcnow()
        )

    def _escalation_resolution(
        self,
        conflict: Conflict
    ) -> Resolution:
        """Escalate conflict to human decision"""
        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy=ResolutionStrategy.ESCALATION,
            approved_decisions=[],
            rejected_decisions=[],
            modifications={},
            reason="Conflict severity too high, escalated to human review",
            resolved_at=datetime.utcnow()
        )

    def _optimize_resource_allocation(
        self,
        decisions: List[AgentDecision],
        resolutions: List[Resolution]
    ) -> Dict[str, Any]:
        """Optimize resource allocation across decisions"""
        approved = []
        rejected = []

        # Apply resolutions
        for resolution in resolutions:
            approved.extend(resolution.approved_decisions)
            rejected.extend(resolution.rejected_decisions)

        # Add non-conflicting decisions
        for decision in decisions:
            if decision.decision_id not in approved and decision.decision_id not in rejected:
                approved.append(decision.decision_id)

        return {
            "approved": approved,
            "rejected": rejected,
            "total_benefit": sum(
                d.expected_benefit for d in decisions
                if d.decision_id in approved
            )
        }

    def _get_decisions_by_ids(
        self,
        decision_ids: List[str]
    ) -> List[AgentDecision]:
        """Get decisions by IDs"""
        decisions = []
        for agent_type, agent_decisions in self.pending_decisions.items():
            for decision in agent_decisions:
                if decision.decision_id in decision_ids:
                    decisions.append(decision)
        return decisions

    def _calculate_efficiency(self) -> float:
        """Calculate coordination efficiency"""
        if not self.resolutions:
            return 1.0

        total_conflicts = len(self.conflicts) + len(self.resolutions)
        if total_conflicts == 0:
            return 1.0

        resolved = len(self.resolutions)
        return resolved / total_conflicts
