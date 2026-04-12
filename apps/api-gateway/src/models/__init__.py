"""
Database Models
"""

# Phase 3-8 新增 model（后期添加，确保 Alembic autogenerate 能检测到）
from .action_plan import ActionOutcome, ActionPlan, DispatchStatus
from .ai_model import AIModel, DataContributionRecord, ModelLevel, ModelPurchaseRecord, ModelStatus, ModelType, PurchaseStatus
from .audit_log import AuditAction, AuditLog, ResourceType

# Batch 3 — 自动化闭环层
from .auto_procurement import ProcurementExecution, ProcurementRule
from .backup_job import BackupJob, BackupStatus, BackupType
from .bank_reconciliation import BankReconciliationBatch, BankStatement

# Phase 9 — Banquet Agent
from .banquet import (
    BanquetAgentActionLog,
    BanquetAgentRule,
    BanquetAgentTypeEnum,
    BanquetContract,
    BanquetCustomer,
    BanquetHall,
    BanquetHallBooking,
    BanquetHallType,
    BanquetKpiDaily,
    BanquetLead,
    BanquetOrder,
    BanquetPaymentRecord,
    BanquetProfitSnapshot,
    BanquetQuote,
    BanquetTypeEnum,
    DepositStatusEnum,
    ExecutionException,
    ExecutionTask,
    ExecutionTemplate,
    LeadFollowupRecord,
    LeadStageEnum,
    MenuPackage,
    MenuPackageItem,
    OrderStatusEnum,
    PaymentTypeEnum,
    TaskOwnerRoleEnum,
    TaskStatusEnum,
)
from .banquet_event_order import BanquetEventOrder, BEOStatus
from .banquet_lifecycle import BanquetStage, BanquetStageHistory
from .base import Base
from .bom import BOMItem, BOMTemplate

# AI经营合伙人 — Sprint 5-6
from .business_objective import (
    BscDimension,
    BusinessObjective,
    ObjectiveKeyResult,
    ObjectiveLevel,
    PeriodType,
)
from .operation_snapshot import OperationSnapshot, SnapshotPeriodType
from .store_pnl import BreakevenTracker, StorePnl
from .channel_config import SalesChannelConfig
from .competitor import CompetitorPrice, CompetitorStore
from .compliance import ComplianceLicense, LicenseStatus, LicenseType
from .compliance_engine import ComplianceAlert, ComplianceScore
from .cross_store import CrossStoreMetric, StorePeerGroup, StoreSimilarityCache
from .customer_key import CustomerKey, EncryptedField, KeyAlgorithm, KeyStatus
from .daily_report import DailyReport
from .decision_log import DecisionLog, DecisionOutcome, DecisionStatus, DecisionType
from .dianping_review import DianpingReview
from .dish import Dish, DishCategory, DishIngredient
from .dish_channel import DishChannelConfig
from .dish_master import BrandMenu, DishMaster, StoreMenu

# Month 1 (P0) — 外部集成模型
from .e_invoice import EInvoice, EInvoiceItem, InvoicePlatform, InvoiceStatus, InvoiceType
from .edge_hub import EdgeAlert, EdgeDevice, EdgeHub, HeadsetBinding
from .employee import Employee
from .employee_metric import EmployeeMetricRecord
from .execution_audit import ExecutionRecord
from .export_job import ExportJob, ExportStatus
from .fct import (
    CashFlowDirection,
    FCTApprovalRecord,
    FCTBudgetControl,
    FCTCashFlowItem,
    FCTPeriod,
    FCTPettyCash,
    FCTPettyCashRecord,
    FCTTaxRecord,
    TaxpayerType,
    TaxType,
    Voucher,
    VoucherLine,
)
from .federated_learning import FLModelUpload, FLTrainingRound, RoundStatus
from .finance import Budget, FinancialReport, FinancialTransaction, Invoice
from .financial_closing import DailyClosingReport

# Month 2 (P0+P1)
from .food_safety import FoodSafetyInspection, FoodTraceRecord
from .forecast import ForecastResult
from .health_certificate import HealthCertificate
from .ingredient_mapping import FusionAuditLog, FusionMethod, IngredientMapping
from .integration import (
    ExternalSystem,
    IntegrationStatus,
    IntegrationType,
    MemberSync,
    POSTransaction,
    ReservationSync,
    SupplierOrder,
    SyncLog,
    SyncStatus,
)

# Batch 1 — 数据融合层
from .integration_hub import IntegrationHubStatus
from .inventory import InventoryItem, InventoryTransaction
from .knowledge_rule import IndustryBenchmark, KnowledgeRule, RuleCategory, RuleExecution, RuleStatus, RuleType
from .kpi import KPI, KPIRecord
from .marketing_campaign import MarketingCampaign
from .meal_period import MealPeriod
from .member_lifecycle import LifecycleState, MemberLifecycleHistory, StateTransitionTrigger
from .neural_event_log import EventProcessingStatus, NeuralEventLog
from .notification import Notification, NotificationPreference, NotificationPriority, NotificationRule, NotificationType
from .ontology_action import ActionPriority, ActionStatus, OntologyAction
from .ops import OpsAsset, OpsAssetType, OpsEvent, OpsEventSeverity, OpsEventStatus, OpsMaintenancePlan, OpsMaintenancePriority
from .order import Order, OrderItem
from .payment_reconciliation import MatchStatus, PaymentChannel, PaymentRecord, ReconciliationBatch, ReconciliationDiff
from .private_domain import (
    JourneyStatus,
    JourneyType,
    PrivateDomainJourney,
    PrivateDomainMember,
    PrivateDomainSignal,
    RFMLevel,
    SignalType,
    StoreQuadrant,
    StoreQuadrantRecord,
)
from .quality import InspectionStatus, QualityInspection
from .queue import Queue, QueueStatus
from .reasoning import ReasoningDimension, ReasoningReport, SeverityLevel
from .reconciliation import ReconciliationRecord, ReconciliationStatus
from .report_template import ReportFormat, ReportTemplate, ScheduledReport, ScheduleFrequency
from .reservation import Reservation
from .review_action import ReviewActionLog, ReviewActionRule
from .schedule import Schedule, Shift
from .store import Store

# Phase 11 — Supplier Agent
from .supplier_agent import (
    AlertTypeEnum,
    ContractAlert,
    ContractStatusEnum,
    DeliveryStatusEnum,
    MaterialCatalog,
    PriceComparison,
    QuoteStatusEnum,
    RiskLevelEnum,
    SourcingRecommendation,
    SupplierAgentLog,
    SupplierAgentTypeEnum,
    SupplierContract,
    SupplierDelivery,
    SupplierEvaluation,
    SupplierProfile,
    SupplierQuote,
    SupplierTierEnum,
    SupplyRiskEvent,
)

# Month 3 (P1+P2)
from .supplier_b2b import B2BPurchaseItem, B2BPurchaseOrder

# Batch 2 — 智能决策层
from .supplier_intelligence import SupplierScorecard
from .review_action import ReviewActionRule, ReviewActionLog
from .compliance_engine import ComplianceScore, ComplianceAlert
# Batch 3 — 自动化闭环层
from .auto_procurement import ProcurementRule, ProcurementExecution
from .financial_closing import DailyClosingReport
# 岗位标准化知识库 + 员工成长
from .job_standard import JobStandard
from .job_sop import JobSOP
from .employee_job_binding import EmployeeJobBinding
from .employee_growth_trace import EmployeeGrowthTrace
from .org_permission import OrgPermission, OrgPermissionLevel
from .supply_chain import PurchaseOrder, Supplier
from .task import Task, TaskPriority, TaskStatus
from .tri_reconciliation import TriReconciliationRecord
from .user import User
from .waste_event import WasteEvent, WasteEventStatus, WasteEventType
from .workflow import DailyWorkflow, DecisionVersion, GenerationMode, PhaseStatus, WorkflowPhase, WorkflowStatus
from .workforce import (
    BudgetPeriodType,
    ConfirmationAction,
    LaborCostRanking,
    LaborCostSnapshot,
    LaborDemandForecast,
    MealPeriodType,
    RankingPeriodType,
    StaffingAdvice,
    StaffingAdviceConfirmation,
    StaffingAdviceStatus,
    StaffingPattern,
    StoreLaborBudget,
)

__all__ = [
    "Base",
    "User",
    "Store",
    "Employee",
    "Order",
    "OrderItem",
    "InventoryItem",
    "InventoryTransaction",
    "Schedule",
    "Shift",
    "Reservation",
    "KPI",
    "KPIRecord",
    "Supplier",
    "PurchaseOrder",
    "FinancialTransaction",
    "Budget",
    "Invoice",
    "FinancialReport",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "DailyReport",
    "ReconciliationRecord",
    "ReconciliationStatus",
    "Notification",
    "NotificationType",
    "NotificationPriority",
    "NotificationPreference",
    "NotificationRule",
    "AuditLog",
    "AuditAction",
    "ResourceType",
    "Queue",
    "QueueStatus",
    "ExternalSystem",
    "SyncLog",
    "POSTransaction",
    "SupplierOrder",
    "MemberSync",
    "ReservationSync",
    "IntegrationType",
    "IntegrationStatus",
    "SyncStatus",
    "DecisionLog",
    "DecisionType",
    "DecisionStatus",
    "DecisionOutcome",
    "ComplianceLicense",
    "LicenseType",
    "LicenseStatus",
    "QualityInspection",
    "InspectionStatus",
    "NeuralEventLog",
    "EventProcessingStatus",
    "DishCategory",
    "Dish",
    "DishIngredient",
    "BOMTemplate",
    "BOMItem",
    "DishMaster",
    "BrandMenu",
    "StoreMenu",
    "EdgeHub",
    "EdgeDevice",
    "EdgeAlert",
    "HeadsetBinding",
    "SalesChannelConfig",
    "DishChannelConfig",
    "AIModel",
    "ModelPurchaseRecord",
    "DataContributionRecord",
    "ModelType",
    "ModelLevel",
    "ModelStatus",
    "PurchaseStatus",
    "FLTrainingRound",
    "FLModelUpload",
    "RoundStatus",
    "MarketingCampaign",
    "ReportTemplate",
    "ScheduledReport",
    "ReportFormat",
    "ScheduleFrequency",
    "CompetitorStore",
    "CompetitorPrice",
    "ExportJob",
    "ExportStatus",
    "BackupJob",
    "BackupType",
    "BackupStatus",
    "FCTTaxRecord",
    "FCTCashFlowItem",
    "FCTBudgetControl",
    "FCTPettyCash",
    "FCTPettyCashRecord",
    "FCTApprovalRecord",
    "FCTPeriod",
    "TaxType",
    "TaxpayerType",
    "CashFlowDirection",
    "BanquetStage",
    "BanquetStageHistory",
    "BanquetEventOrder",
    "BEOStatus",
    "WasteEvent",
    "WasteEventType",
    "WasteEventStatus",
    # Phase 3-8
    "ActionPlan",
    "DispatchStatus",
    "ActionOutcome",
    "KnowledgeRule",
    "RuleExecution",
    "IndustryBenchmark",
    "RuleCategory",
    "RuleType",
    "RuleStatus",
    "PrivateDomainMember",
    "PrivateDomainSignal",
    "PrivateDomainJourney",
    "StoreQuadrantRecord",
    "RFMLevel",
    "StoreQuadrant",
    "SignalType",
    "JourneyType",
    "JourneyStatus",
    "OntologyAction",
    "ActionStatus",
    "ActionPriority",
    "OpsEvent",
    "OpsAsset",
    "OpsMaintenancePlan",
    "OpsEventSeverity",
    "OpsEventStatus",
    "OpsAssetType",
    "OpsMaintenancePriority",
    "ReasoningReport",
    "SeverityLevel",
    "ReasoningDimension",
    "BOMTemplate",
    "BOMItem",
    "CrossStoreMetric",
    "StoreSimilarityCache",
    "StorePeerGroup",
    "IngredientMapping",
    "FusionAuditLog",
    "FusionMethod",
    "ExecutionRecord",
    "CustomerKey",
    "EncryptedField",
    "KeyStatus",
    "KeyAlgorithm",
    "DailyWorkflow",
    "WorkflowPhase",
    "DecisionVersion",
    "WorkflowStatus",
    "PhaseStatus",
    "GenerationMode",
    "ForecastResult",
    "MealPeriod",
    "EmployeeMetricRecord",
    "LifecycleState",
    "StateTransitionTrigger",
    "MemberLifecycleHistory",
    # Phase 8 — Workforce
    "LaborDemandForecast",
    "LaborCostSnapshot",
    "StaffingAdvice",
    "StaffingAdviceConfirmation",
    "StoreLaborBudget",
    "LaborCostRanking",
    "StaffingPattern",
    "MealPeriodType",
    "StaffingAdviceStatus",
    "ConfirmationAction",
    "BudgetPeriodType",
    "RankingPeriodType",
    # Phase 9 — Banquet Agent
    "BanquetHall",
    "BanquetCustomer",
    "BanquetLead",
    "BanquetOrder",
    "BanquetAgentTypeEnum",
    # Phase 11 — Supplier Agent
    "SupplierProfile",
    "MaterialCatalog",
    "SupplierQuote",
    "SupplierContract",
    "SupplierDelivery",
    "PriceComparison",
    "SupplierEvaluation",
    "SourcingRecommendation",
    "ContractAlert",
    "SupplyRiskEvent",
    "SupplierAgentLog",
    "SupplierTierEnum",
    "QuoteStatusEnum",
    "ContractStatusEnum",
    "DeliveryStatusEnum",
    "RiskLevelEnum",
    "AlertTypeEnum",
    "SupplierAgentTypeEnum",
    # Phase 12 — BusinessIntel Agent
    "BizMetricSnapshot",
    "RevenueAlert",
    "KpiScorecard",
    "OrderForecast",
    "BizDecision",
    "ScenarioRecord",
    "BizIntelLog",
    "AnomalyLevelEnum",
    "KpiStatusEnum",
    "DecisionPriorityEnum",
    "ScenarioTypeEnum",
    "BizIntelAgentTypeEnum",
    "DecisionStatusEnum",
    # Phase 12B — PeopleAgent
    "PeopleShiftRecord",
    "PeoplePerformanceScore",
    "PeopleLaborCostRecord",
    "PeopleAttendanceAlert",
    "PeopleStaffingDecision",
    "PeopleAgentLog",
    # HR W1-2 — 敏感数据审计
    "SensitiveDataAuditLog",
    # HR W2-3 — 工资条推送记录
    "PayslipRecord",
    # HR — 操作审计日志
    "OperationAuditLog",
    # 组织层级
    "OrgNode",
    "OrgNodeType",
    "StoreType",
    "OperationMode",
    "OrgConfig",
    "ConfigKey",
    "OrgPermission",
    "OrgPermissionLevel",
    # Phase 1 — 集团层级数据模型
    "GroupTenant",
    "BrandConsumerProfile",
    # HR domain models (z54)
    "Person",
    "EmploymentAssignment",
    "EmploymentContract",
    "EmployeeIdMap",
    "AttendanceRule",
    "KpiTemplate",
    # HR Knowledge OS models (z55)
    "HrKnowledgeRule",
    "SkillNode",
    "BehaviorPattern",
    "PersonAchievement",
    "RetentionSignal",
    "KnowledgeCapture",
]

from .business_intel import (
    BizMetricSnapshot, RevenueAlert, KpiScorecard, OrderForecast,
    BizDecision, ScenarioRecord, BizIntelLog,
    AnomalyLevelEnum, KpiStatusEnum, DecisionPriorityEnum,
    ScenarioTypeEnum, BizIntelAgentTypeEnum, DecisionStatusEnum,
)
from .people_agent import (
    PeopleShiftRecord, PeoplePerformanceScore, PeopleLaborCostRecord,
    PeopleAttendanceAlert, PeopleStaffingDecision, PeopleAgentLog,
)
from .ops_flow_agent import (
    OpsChainEvent, OpsChainLinkage, OpsOrderAnomaly,
    OpsInventoryAlert, OpsQualityRecord, OpsFlowDecision, OpsFlowAgentLog,
)
from .agent_okr import AgentResponseLog, AgentOKRSnapshot
from .agent_collab import AgentConflict, GlobalOptimizationLog, AgentCollabSnapshot
from .cost_truth import CostTruthDaily, CostTruthDishDetail, CostVarianceAttribution
from .fct_advanced import (
    FCTBankAccount, FCTBankTransaction, FCTBankMatchRule,
    FCTEntity, FCTConsolidationRun, FCTIntercompanyItem,
    FCTTaxDeclaration, FCTTaxExtractRule,
)
# Data Dictionary models — 数据字典补齐
from .organization import Group, Brand, Region
from .ingredient_master import IngredientMaster
# Phase 1 — 集团层级数据模型
from .group_tenant import GroupTenant
from .brand_consumer_profile import BrandConsumerProfile
from .inventory_ext import InventoryBatch, InventoryCount
from .purchase_order_item import PurchaseOrderItem
from .daily_summary import DailyRevenueSummary, DailyWasteSummary, DailyPnlSummary

