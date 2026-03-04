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
from .channel_config import SalesChannelConfig
from .dish_channel import DishChannelConfig
from .ai_model import AIModel, ModelPurchaseRecord, DataContributionRecord, ModelType, ModelLevel, ModelStatus, PurchaseStatus
from .federated_learning import FLTrainingRound, FLModelUpload, RoundStatus
from .marketing_campaign import MarketingCampaign
from .report_template import ReportTemplate, ScheduledReport, ReportFormat, ScheduleFrequency
from .competitor import CompetitorStore, CompetitorPrice
from .export_job import ExportJob, ExportStatus
from .backup_job import BackupJob, BackupType, BackupStatus
from .fct import FCTTaxRecord, FCTCashFlowItem, TaxType, TaxpayerType, CashFlowDirection, Voucher, VoucherLine
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
]
