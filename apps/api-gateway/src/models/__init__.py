"""
Database Models
"""
from .base import Base
from .user import User
from .store import Store
from .employee import Employee
from .order import Order, OrderItem
from .inventory import InventoryItem, InventoryTransaction
from .schedule import Schedule, Shift
from .reservation import Reservation
from .kpi import KPI, KPIRecord
from .supply_chain import Supplier, PurchaseOrder
from .finance import FinancialTransaction, Budget, Invoice, FinancialReport
from .task import Task, TaskStatus, TaskPriority
from .daily_report import DailyReport
from .reconciliation import ReconciliationRecord, ReconciliationStatus
from .notification import Notification, NotificationType, NotificationPriority, NotificationPreference, NotificationRule
from .audit_log import AuditLog, AuditAction, ResourceType
from .queue import Queue, QueueStatus
from .integration import (
    ExternalSystem,
    SyncLog,
    POSTransaction,
    SupplierOrder,
    MemberSync,
    ReservationSync,
    IntegrationType,
    IntegrationStatus,
    SyncStatus,
)
from .decision_log import DecisionLog, DecisionType, DecisionStatus, DecisionOutcome
from .compliance import ComplianceLicense, LicenseType, LicenseStatus
from .quality import QualityInspection, InspectionStatus
from .neural_event_log import NeuralEventLog, EventProcessingStatus
from .dish import DishCategory, Dish, DishIngredient
from .bom import BOMTemplate, BOMItem
from .dish_master import DishMaster, BrandMenu, StoreMenu
from .edge_hub import EdgeHub, EdgeDevice, EdgeAlert, HeadsetBinding
from .channel_config import SalesChannelConfig
from .dish_channel import DishChannelConfig
from .ai_model import AIModel, ModelPurchaseRecord, DataContributionRecord, ModelType, ModelLevel, ModelStatus, PurchaseStatus
from .federated_learning import FLTrainingRound, FLModelUpload, RoundStatus
from .marketing_campaign import MarketingCampaign
from .report_template import ReportTemplate, ScheduledReport, ReportFormat, ScheduleFrequency
from .competitor import CompetitorStore, CompetitorPrice
from .export_job import ExportJob, ExportStatus
from .backup_job import BackupJob, BackupType, BackupStatus
from .fct import (
    FCTTaxRecord,
    FCTCashFlowItem,
    FCTBudgetControl,
    FCTPettyCash,
    FCTPettyCashRecord,
    FCTApprovalRecord,
    FCTPeriod,
    TaxType,
    TaxpayerType,
    CashFlowDirection,
    Voucher,
    VoucherLine,
)
from .banquet_lifecycle import BanquetStage, BanquetStageHistory
from .banquet_event_order import BanquetEventOrder, BEOStatus
from .waste_event import WasteEvent, WasteEventType, WasteEventStatus
# Phase 3-8 新增 model（后期添加，确保 Alembic autogenerate 能检测到）
from .action_plan import ActionPlan, DispatchStatus, ActionOutcome
from .knowledge_rule import KnowledgeRule, RuleExecution, IndustryBenchmark, RuleCategory, RuleType, RuleStatus
from .private_domain import (
    PrivateDomainMember, PrivateDomainSignal, PrivateDomainJourney,
    StoreQuadrantRecord, RFMLevel, StoreQuadrant, SignalType, JourneyType, JourneyStatus,
)
from .ontology_action import OntologyAction, ActionStatus, ActionPriority
from .ops import OpsEvent, OpsAsset, OpsMaintenancePlan, OpsEventSeverity, OpsEventStatus, OpsAssetType, OpsMaintenancePriority
from .reasoning import ReasoningReport, SeverityLevel, ReasoningDimension
from .bom import BOMTemplate, BOMItem
from .cross_store import CrossStoreMetric, StoreSimilarityCache, StorePeerGroup
from .ingredient_mapping import IngredientMapping, FusionAuditLog, FusionMethod
from .execution_audit import ExecutionRecord
from .customer_key import CustomerKey, EncryptedField, KeyStatus, KeyAlgorithm
from .workflow import DailyWorkflow, WorkflowPhase, DecisionVersion, WorkflowStatus, PhaseStatus, GenerationMode
from .forecast import ForecastResult
from .meal_period import MealPeriod
from .employee_metric import EmployeeMetricRecord
from .member_lifecycle import (
    LifecycleState,
    StateTransitionTrigger,
    MemberLifecycleHistory,
)
from .workforce import (
    LaborDemandForecast,
    LaborCostSnapshot,
    StaffingAdvice,
    StaffingAdviceConfirmation,
    StoreLaborBudget,
    LaborCostRanking,
    StaffingPattern,
    MealPeriodType,
    StaffingAdviceStatus,
    ConfirmationAction,
    BudgetPeriodType,
    RankingPeriodType,
)
# Phase 11 — Supplier Agent
from .supplier_agent import (
    SupplierProfile,
    MaterialCatalog,
    SupplierQuote,
    SupplierContract,
    SupplierDelivery,
    PriceComparison,
    SupplierEvaluation,
    SourcingRecommendation,
    ContractAlert,
    SupplyRiskEvent,
    SupplierAgentLog,
    SupplierTierEnum,
    QuoteStatusEnum,
    ContractStatusEnum,
    DeliveryStatusEnum,
    RiskLevelEnum,
    AlertTypeEnum,
    SupplierAgentTypeEnum,
)
# Phase 9 — Banquet Agent
from .banquet import (
    BanquetHall,
    BanquetHallType,
    BanquetCustomer,
    BanquetLead,
    LeadFollowupRecord,
    BanquetQuote,
    MenuPackage,
    MenuPackageItem,
    BanquetOrder,
    BanquetHallBooking,
    ExecutionTemplate,
    ExecutionTask,
    ExecutionException,
    BanquetPaymentRecord,
    BanquetContract,
    BanquetProfitSnapshot,
    BanquetKpiDaily,
    BanquetAgentRule,
    BanquetAgentActionLog,
    BanquetTypeEnum,
    LeadStageEnum,
    OrderStatusEnum,
    DepositStatusEnum,
    TaskStatusEnum,
    TaskOwnerRoleEnum,
    PaymentTypeEnum,
    BanquetAgentTypeEnum,
)

# Month 1 (P0) — 外部集成模型
from .e_invoice import EInvoice, EInvoiceItem, InvoicePlatform, InvoiceType, InvoiceStatus
from .payment_reconciliation import (
    PaymentRecord, ReconciliationBatch, ReconciliationDiff,
    PaymentChannel, MatchStatus,
)
# Month 2 (P0+P1)
from .food_safety import FoodTraceRecord, FoodSafetyInspection
from .health_certificate import HealthCertificate
# Month 3 (P1+P2)
from .supplier_b2b import B2BPurchaseOrder, B2BPurchaseItem
from .dianping_review import DianpingReview
from .bank_reconciliation import BankStatement, BankReconciliationBatch
# Batch 1 — 数据融合层
from .integration_hub import IntegrationHubStatus
from .tri_reconciliation import TriReconciliationRecord
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
from .inventory_ext import InventoryBatch, InventoryCount
from .purchase_order_item import PurchaseOrderItem
from .daily_summary import DailyRevenueSummary, DailyWasteSummary, DailyPnlSummary
from .attendance import AttendanceLog
from .member_rfm import MemberRfmSnapshot
from .price_benchmark import PriceBenchmarkPool, PriceBenchmarkReport
from .decision_lifecycle import DecisionLifecycle
# Phase P1 — 预订Agent: 渠道中台 + 客户风控
from .reservation_channel import ReservationChannel, ChannelType
from .customer_ownership import (
    CustomerOwnership, TransferReason,
    CustomerRiskAlert, RiskLevel, RiskType,
)
# Phase P2 — 宴会销控
from .banquet_sales import (
    BanquetDateConfig, AuspiciousLevel, DateBookingStatus,
    SalesFunnelRecord, FunnelStage,
    BanquetCompetitor,
)
# Phase P3 — EO执行引擎
from .event_staff import EventStaff, StaffRole, StaffConfirmStatus
from .hall_showcase import HallShowcase
# 替换易订 — R3 桌台平面图 + R4 AI邀请函
from .floor_plan import TableDefinition, TableShape, TableStatus
from .invitation import Invitation, InvitationRSVP, InvitationTemplate, RSVPStatus
# P0 补齐 — 预排菜模型
from .reservation_pre_order import ReservationPreOrder, PreOrderStatus
# Sprint 1 — CDP 地基层
from .consumer_identity import ConsumerIdentity
from .consumer_id_mapping import ConsumerIdMapping, IdType
# HR 模块 — 薪酬/假勤/审批/招聘/绩效/合同/生命周期（部分 model 文件尚未实现，跳过缺失项）
try:
    from .payroll import (
        SalaryStructure, PayrollRecord, TaxDeclaration,
        PayrollStatus, SalaryType, TaxStatus,
    )
    from .approval_flow import (
        ApprovalFlowTemplate, ApprovalInstance, ApprovalNodeRecord,
        ApprovalType, ApprovalStatus as HRApprovalStatus, ApprovalNodeType,
    )
    from .leave import (
        LeaveTypeConfig, LeaveBalance, LeaveRequest, OvertimeRequest,
        LeaveCategory, LeaveRequestStatus, OvertimeType, OvertimeRequestStatus,
    )
    from .employee_lifecycle import EmployeeChange, ChangeType
    from .recruitment import (
        JobPosting, Candidate, Interview, Offer,
        JobStatus, CandidateStage, InterviewResult, OfferStatus,
    )
    from .performance_review import (
        PerformanceTemplate, PerformanceReview,
        ReviewCycle, ReviewStatus, ReviewLevel,
    )
    from .employee_contract import EmployeeContract, ContractType, ContractStatus
    # HR Phase 4 — 培训认证/师徒制
    from .training import TrainingCourse, TrainingEnrollment, TrainingExam, ExamAttempt
    from .mentorship import Mentorship
    # HR W1-2 — 敏感数据审计日志
    from .sensitive_audit_log import SensitiveDataAuditLog
    # HR W2-2 — 离职结算
    from .settlement import SettlementRecord, SettlementStatus, SeparationType, CompensationType
    # HR W2-3 — 工资条推送记录
    from .payslip import PayslipRecord
    # HR — 操作审计日志
    from .operation_audit_log import OperationAuditLog
except ImportError:
    pass  # HR model files not yet created — skip gracefully

# 组织层级
from .org_node import OrgNode, OrgNodeType, StoreType, OperationMode
from .org_config import OrgConfig, ConfigKey

# 日清日结 + 周复盘模块
from .daily_metric import StoreDailyMetric
from .daily_settlement import StoreDailySettlement
from .warning_rule import WarningRule
from .warning_record import WarningRecord
from .action_task import ActionTask
from .weekly_review import WeeklyReview, WeeklyReviewItem
from .data_quality_check import DataQualityCheckRecord
