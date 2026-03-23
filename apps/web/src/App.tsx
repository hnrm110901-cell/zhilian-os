import React, { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { lightTheme, darkTheme } from './config/theme';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import MainLayout from './layouts/MainLayout';

// Eagerly loaded (always needed)
import LoginPage from './pages/LoginPage';
import UnauthorizedPage from './pages/UnauthorizedPage';
import NotFoundPage from './pages/NotFoundPage';
import Dashboard from './pages/Dashboard';

// Lazily loaded pages
const SchedulePage = lazy(() => import('./pages/SchedulePage'));
const OrderPage = lazy(() => import('./pages/OrderPage'));
const InventoryPage = lazy(() => import('./pages/InventoryPage'));
const ServicePage = lazy(() => import('./pages/ServicePage'));
const TrainingPage = lazy(() => import('./pages/TrainingPage'));
const DecisionPage = lazy(() => import('./pages/DecisionPage'));
const ReservationPage = lazy(() => import('./pages/ReservationPage'));
const UserManagementPage = lazy(() => import('./pages/UserManagementPage'));
const EnterpriseIntegrationPage = lazy(() => import('./pages/EnterpriseIntegrationPage'));
const MultiStoreManagement = lazy(() => import('./pages/MultiStoreManagement'));
const CrossStoreConfigPage = lazy(() => import('./pages/CrossStoreConfigPage'));
const SupplyChainManagement = lazy(() => import('./pages/SupplyChainManagement'));
const DataVisualizationScreen = lazy(() => import('./pages/DataVisualizationScreen'));
const MonitoringPage = lazy(() => import('./pages/MonitoringPage'));
const MobileApp = lazy(() => import('./pages/MobileApp'));
const FinanceManagement = lazy(() => import('./pages/FinanceManagement'));
const BackupManagement = lazy(() => import('./pages/BackupManagement'));
const AdvancedAnalytics = lazy(() => import('./pages/AdvancedAnalytics'));
const NotificationCenter = lazy(() => import('./pages/NotificationCenter'));
const AuditLogPage = lazy(() => import('./pages/AuditLogPage'));
const DataSovereigntyPage = lazy(() => import('./pages/DataSovereigntyPage'));
const DataImportExportPage = lazy(() => import('./pages/DataImportExportPage'));
const CompetitiveAnalysis = lazy(() => import('./pages/CompetitiveAnalysis'));
const ReportTemplates = lazy(() => import('./pages/ReportTemplates'));
const ForecastPage = lazy(() => import('./pages/ForecastPage'));
const CrossStoreInsights = lazy(() => import('./pages/CrossStoreInsights'));
const HumanInTheLoop = lazy(() => import('./pages/HumanInTheLoop'));
const RecommendationsPage = lazy(() => import('./pages/RecommendationsPage'));
const PrivateDomainPage = lazy(() => import('./pages/PrivateDomainPage'));
const MemberSystemPage = lazy(() => import('./pages/MemberSystemPage'));
const KPIDashboardPage = lazy(() => import('./pages/KPIDashboardPage'));
const Customer360Page = lazy(() => import('./pages/Customer360Page'));
const POSPage = lazy(() => import('./pages/POSPage'));
const QualityManagementPage = lazy(() => import('./pages/QualityManagementPage'));
const CompliancePage = lazy(() => import('./pages/CompliancePage'));
const AIEvolutionPage = lazy(() => import('./pages/AIEvolutionPage'));
const EdgeNodePage = lazy(() => import('./pages/EdgeNodePage'));
const DecisionValidatorPage = lazy(() => import('./pages/DecisionValidatorPage'));
const FederatedLearningPage = lazy(() => import('./pages/FederatedLearningPage'));
const AgentCollaborationPage = lazy(() => import('./pages/AgentCollaborationPage'));
const OpenPlatformPage = lazy(() => import('./pages/OpenPlatformPage'));
const DeveloperDocsPage = lazy(() => import('./pages/DeveloperDocsPage'));
const ISVEcosystemPage = lazy(() => import('./pages/ISVEcosystemPage'));
const ISVManagementPage = lazy(() => import('./pages/ISVManagementPage'));
const PluginMarketplacePage = lazy(() => import('./pages/PluginMarketplacePage'));
const RevenueSharePage = lazy(() => import('./pages/RevenueSharePage'));
const ISVDashboardPage = lazy(() => import('./pages/ISVDashboardPage'));
const PlatformAnalyticsPage = lazy(() => import('./pages/PlatformAnalyticsPage'));
const WebhookManagementPage = lazy(() => import('./pages/WebhookManagementPage'));
const ApiBillingPage = lazy(() => import('./pages/ApiBillingPage'));
const DeveloperConsolePage = lazy(() => import('./pages/DeveloperConsolePage'));
const BusinessEventsPage = lazy(() => import('./pages/BusinessEventsPage'));
const TaxCashflowPage = lazy(() => import('./pages/TaxCashflowPage'));
const SettlementRiskPage = lazy(() => import('./pages/SettlementRiskPage'));
const CeoDashboardPage = lazy(() => import('./pages/CeoDashboardPage'));
const BudgetManagementPage = lazy(() => import('./pages/BudgetManagementPage'));
const FinancialAlertsPage = lazy(() => import('./pages/FinancialAlertsPage'));
const FinanceHealthPage = lazy(() => import('./pages/FinanceHealthPage'));
const CFODashboardPage  = lazy(() => import('./pages/CFODashboardPage'));
const FinancialForecastPage = lazy(() => import('./pages/FinancialForecastPage'));
const FinancialAnomalyPage  = lazy(() => import('./pages/FinancialAnomalyPage'));
const PerformanceRankingPage = lazy(() => import('./pages/PerformanceRankingPage'));
const FinancialRecommendationPage = lazy(() => import('./pages/FinancialRecommendationPage'));
const DishProfitabilityPage = lazy(() => import('./pages/DishProfitabilityPage'));
const MenuOptimizationPage = lazy(() => import('./pages/MenuOptimizationPage'));
const DishCostAlertPage = lazy(() => import('./pages/DishCostAlertPage'));
const DishBenchmarkPage = lazy(() => import('./pages/DishBenchmarkPage'));
const DishPricingPage = lazy(() => import('./pages/DishPricingPage'));
const DishLifecyclePage = lazy(() => import('./pages/DishLifecyclePage'));
const DishForecastPage  = lazy(() => import('./pages/DishForecastPage'));
const DishHealthPage       = lazy(() => import('./pages/DishHealthPage'));
const DishAttributionPage  = lazy(() => import('./pages/DishAttributionPage'));
const MenuMatrixPage       = lazy(() => import('./pages/MenuMatrixPage'));
const CostCompressionPage  = lazy(() => import('./pages/CostCompressionPage'));
const DishMonthlySummaryPage = lazy(() => import('./pages/DishMonthlySummaryPage'));
const IndustrySolutionsPage = lazy(() => import('./pages/IndustrySolutionsPage'));
const I18nPage = lazy(() => import('./pages/I18nPage'));
const TaskManagementPage = lazy(() => import('./pages/TaskManagementPage'));
const ReconciliationPage = lazy(() => import('./pages/ReconciliationPage'));
const DishManagementPage = lazy(() => import('./pages/DishManagementPage'));
const EmployeeManagementPage = lazy(() => import('./pages/EmployeeManagementPage'));
const RaaSPage = lazy(() => import('./pages/RaaSPage'));
const ModelMarketplacePage = lazy(() => import('./pages/ModelMarketplacePage'));
const LLMConfigPage = lazy(() => import('./pages/LLMConfigPage'));
const HardwarePage = lazy(() => import('./pages/HardwarePage'));
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage'));
const NeuralSystemPage = lazy(() => import('./pages/NeuralSystemPage'));
const EmbeddingPage = lazy(() => import('./pages/EmbeddingPage'));
const SchedulerPage = lazy(() => import('./pages/SchedulerPage'));
const BenchmarkPage = lazy(() => import('./pages/BenchmarkPage'));
const ApprovalManagementPage = lazy(() => import('./pages/ApprovalManagementPage'));
const StoreManagementPage = lazy(() => import('./pages/StoreManagementPage'));
const ExportJobsPage = lazy(() => import('./pages/ExportJobsPage'));
const RoleManagementPage = lazy(() => import('./pages/RoleManagementPage'));
const QueueManagementPage = lazy(() => import('./pages/QueueManagementPage'));
const AgentMemoryPage = lazy(() => import('./pages/AgentMemoryPage'));
const WeChatTriggersPage = lazy(() => import('./pages/WeChatTriggersPage'));
const IMChannelPage = lazy(() => import('./pages/IMChannelPage'));
const EventSourcingPage = lazy(() => import('./pages/EventSourcingPage'));
const MeituanQueuePage = lazy(() => import('./pages/MeituanQueuePage'));
const VectorIndexPage = lazy(() => import('./pages/VectorIndexPage'));
const AdaptersPage = lazy(() => import('./pages/AdaptersPage'));
const VoiceDevicePage = lazy(() => import('./pages/VoiceDevicePage'));
const SystemHealthPage = lazy(() => import('./pages/SystemHealthPage'));
const UserProfilePage = lazy(() => import('./pages/UserProfilePage'));
const VoiceWebSocketPage = lazy(() => import('./pages/VoiceWebSocketPage'));
const OpsAgentPage = lazy(() => import('./pages/OpsAgentPage'));
const DailyHubPage = lazy(() => import('./pages/DailyHubPage'));
const BulkImportPage = lazy(() => import('./pages/BulkImportPage'));
const MySchedulePage = lazy(() => import('./pages/MySchedulePage'));
const HQDashboardPage = lazy(() => import('./pages/HQDashboardPage'));
const AIAccuracyPage = lazy(() => import('./pages/AIAccuracyPage'));
const GovDashboardPage = lazy(() => import('./pages/GovDashboardPage'));
const AgentHubPage     = lazy(() => import('./pages/AgentHubPage'));
const OpsHubPage       = lazy(() => import('./pages/OpsHubPage'));
const ProductsHubPage  = lazy(() => import('./pages/ProductsHubPage'));
const CrmHubPage       = lazy(() => import('./pages/CrmHubPage'));
const PlatformHubPage  = lazy(() => import('./pages/PlatformHubPage'));
const DishCostPage = lazy(() => import('./pages/DishCostPage'));
const ChannelProfitPage = lazy(() => import('./pages/ChannelProfitPage'));
const EmployeePerformancePage = lazy(() => import('./pages/EmployeePerformancePage'));
const OrderAnalyticsPage = lazy(() => import('./pages/OrderAnalyticsPage'));
const DashboardPreferencesPage = lazy(() => import('./pages/DashboardPreferencesPage'));
const NotificationPreferencesPage = lazy(() => import('./pages/NotificationPreferencesPage'));
const NLQueryPage = lazy(() => import('./pages/NLQueryPage'));
const MenuRecommendationPage = lazy(() => import('./pages/MenuRecommendationPage'));
const WasteReasoningPage = lazy(() => import('./pages/WasteReasoningPage'));
const OntologyGraphPage = lazy(() => import('./pages/OntologyGraphPage'));
const KnowledgeRulePage = lazy(() => import('./pages/KnowledgeRulePage'));
const OntologyAdminPage = lazy(() => import('./pages/OntologyAdminPage'));
const BOMManagementPage = lazy(() => import('./pages/BOMManagementPage'));
const WasteEventPage = lazy(() => import('./pages/WasteEventPage'));

const DataSecurityPage = lazy(() => import('./pages/DataSecurityPage'));
const BanquetLifecyclePage = lazy(() => import('./pages/BanquetAgentPage'));
const DishRdPage = lazy(() => import('./pages/DishRdPage'));
const DishRdDetailPage = lazy(() => import('./pages/DishRdDetailPage'));
const SupplierAgentPage = lazy(() => import('./pages/SupplierAgentPage'));
const BusinessIntelPage = lazy(() => import('./pages/BusinessIntelPage'));
const PeopleAgentPage = lazy(() => import('./pages/PeopleAgentPage'));
const OpsFlowAgentPage = lazy(() => import('./pages/OpsFlowAgentPage'));
const AgentOKRPage = lazy(() => import('./pages/AgentOKRPage'));
const AgentCollabPage = lazy(() => import('./pages/AgentCollabPage'));
const FctAdvancedPage = lazy(() => import('./pages/FctAdvancedPage'));
const MarketingCampaignPage = lazy(() => import('./pages/MarketingCampaignPage'));
const FctPage = lazy(() => import('./pages/FctPage'));
const ApprovalListPage = lazy(() => import('./pages/ApprovalListPage'));
const ActionPlansPage = lazy(() => import('./pages/ActionPlansPage'));
const WorkforcePage = lazy(() => import('./pages/WorkforcePage'));
const DecisionStatisticsDashboard = lazy(() => import('./pages/DecisionStatisticsDashboard'));
const ProfitDashboard = lazy(() => import('./pages/ProfitDashboard'));
const AlertThresholdsPage = lazy(() => import('./pages/AlertThresholdsPage'));
const MonthlyReportPage = lazy(() => import('./pages/MonthlyReportPage'));
const OnboardingPage = lazy(() => import('./pages/onboarding/OnboardingPage'));
const DynamicPricingPage = lazy(() => import('./pages/DynamicPricingPage'));
const OpsMonitoringPage = lazy(() => import('./pages/OpsMonitoringPage'));
const MerchantManagementPage = lazy(() => import('./pages/MerchantManagementPage'));
const MerchantListPage = lazy(() => import('./pages/platform/MerchantListPage'));
const MerchantDetailPage = lazy(() => import('./pages/platform/MerchantDetailPage'));
// Phase P1 — 预订Agent: 渠道中台 + 客户风控
const ChannelAnalyticsPage = lazy(() => import('./pages/ChannelAnalyticsPage'));
const CustomerRiskPage = lazy(() => import('./pages/CustomerRiskPage'));
const BanquetSalesPage = lazy(() => import('./pages/BanquetSalesPage'));
const EventOrderPage = lazy(() => import('./pages/EventOrderPage'));
const ReservationAIPage = lazy(() => import('./pages/ReservationAIPage'));

// CDP 监控面板
const CDPMonitorPage = lazy(() => import('./pages/CDPMonitorPage'));

// 替换易订 — R1 客户自助预订H5 / R3 桌台平面图 / R4 AI邀请函
const BookingH5 = lazy(() => import('./pages/public/BookingH5'));
const BookingLookup = lazy(() => import('./pages/public/BookingLookup'));
const FloorPlanPage = lazy(() => import('./pages/FloorPlanPage'));
const InvitationView = lazy(() => import('./pages/public/InvitationView'));
const InvitationManagerPage = lazy(() => import('./pages/InvitationManagerPage'));
// 预订数据分析仪表板
const ReservationAnalyticsPage = lazy(() => import('./pages/ReservationAnalyticsPage'));

// Role-based views (Phase 1 — Store Manager /sm)
const StoreManagerLayout = lazy(() => import('./layouts/StoreManagerLayout'));
const SmHome      = lazy(() => import('./pages/sm/Home'));
const SmShifts    = lazy(() => import('./pages/sm/Shifts'));
const SmTasks     = lazy(() => import('./pages/sm/Tasks'));
const SmBusiness  = lazy(() => import('./pages/sm/Business'));
const SmDecisions = lazy(() => import('./pages/sm/Decisions'));
const SmAlerts    = lazy(() => import('./pages/sm/Alerts'));
const SmWorkforce = lazy(() => import('./pages/sm/Workforce'));
const SmPrepSuggestion = lazy(() => import('./pages/sm/PrepSuggestion'));
const SmPatrol    = lazy(() => import('./pages/sm/Patrol'));
const SmProfile   = lazy(() => import('./pages/sm/Profile'));

// Platform Admin layout + pages (admin.zlsjos.cn / www.admin.zlsjos.cn)
const PlatformAdminLayout        = lazy(() => import('./layouts/PlatformAdminLayout'));
const PlatformAdminHome          = lazy(() => import('./pages/platform/PlatformAdminHome'));
// Level 1 — 平台新增页面
const ModelVersionPage           = lazy(() => import('./pages/platform/ModelVersionPage'));
const PromptWarehousePage        = lazy(() => import('./pages/platform/PromptWarehousePage'));
const CrossMerchantLearningPage  = lazy(() => import('./pages/platform/CrossMerchantLearningPage'));
const ModuleAuthPage             = lazy(() => import('./pages/platform/ModuleAuthPage'));
const KeyManagementPage          = lazy(() => import('./pages/platform/KeyManagementPage'));
const DeliveryTrackingPage       = lazy(() => import('./pages/platform/DeliveryTrackingPage'));
const RenewalAlertPage           = lazy(() => import('./pages/platform/RenewalAlertPage'));

// Ops Admin layout + pages (Level 2 — 商户管理运维后台)
const OpsAdminLayout             = lazy(() => import('./layouts/OpsAdminLayout'));
const OpsHomePage                = lazy(() => import('./pages/ops/OpsHomePage'));
const DataPipelinePage           = lazy(() => import('./pages/ops/DataPipelinePage'));
const MenuImportPage             = lazy(() => import('./pages/ops/MenuImportPage'));
const BomImportPage              = lazy(() => import('./pages/ops/BomImportPage'));
const ChannelDataPage            = lazy(() => import('./pages/ops/ChannelDataPage'));
const OpsBusinessRulesPage       = lazy(() => import('./pages/ops/BusinessRulesPage'));
const StoreTemplatePage          = lazy(() => import('./pages/ops/StoreTemplatePage'));
const AgentTrainingPage          = lazy(() => import('./pages/ops/AgentTrainingPage'));
const DataIsolationPage          = lazy(() => import('./pages/ops/DataIsolationPage'));
const IoTDevicesPage             = lazy(() => import('./pages/ops/IoTDevicesPage'));
const ModelMonitorPage           = lazy(() => import('./pages/ops/ModelMonitorPage'));
const PushStrategyPage           = lazy(() => import('./pages/ops/PushStrategyPage'));
const PlatformIntegrationsPage   = lazy(() => import('./pages/platform/PlatformIntegrationsPage'));
const EdgeNodeManagementPage     = lazy(() => import('./pages/platform/EdgeNodeManagementPage'));
const PlatformAgentsPage         = lazy(() => import('./pages/platform/PlatformAgentsPage'));
const PlatformFeatureFlagsPage   = lazy(() => import('./pages/platform/PlatformFeatureFlagsPage'));
const PlatformOntologyPage       = lazy(() => import('./pages/platform/PlatformOntologyPage'));
const PlatformAuditLogPage       = lazy(() => import('./pages/platform/PlatformAuditLogPage'));
const PlatformDataSovereigntyPage  = lazy(() => import('./pages/platform/PlatformDataSovereigntyPage'));
const PlatformSystemMonitorPage    = lazy(() => import('./pages/platform/PlatformSystemMonitorPage'));
const PlatformBackupPage           = lazy(() => import('./pages/platform/PlatformBackupPage'));
const SystemSettingsPage         = lazy(() => import('./pages/platform/SystemSettingsPage'));
// Month 1 (P0) — 外部集成页面
const EInvoicePage               = lazy(() => import('./pages/platform/EInvoicePage'));
const ElemePage                  = lazy(() => import('./pages/platform/ElemePage'));
const PaymentReconciliationPage  = lazy(() => import('./pages/platform/PaymentReconciliationPage'));
// Month 2 (P0+P1) — 抖音 / 食品安全 / 健康证
const DouyinPage                 = lazy(() => import('./pages/platform/DouyinPage'));
const FoodSafetyPage             = lazy(() => import('./pages/platform/FoodSafetyPage'));
const HealthCertPage             = lazy(() => import('./pages/platform/HealthCertPage'));
// Month 3 (P1+P2) — 供应商B2B / 大众点评 / 银行对账
const SupplierB2BPage            = lazy(() => import('./pages/platform/SupplierB2BPage'));
const DianpingPage               = lazy(() => import('./pages/platform/DianpingPage'));
const BankReconciliationPage     = lazy(() => import('./pages/platform/BankReconciliationPage'));
// Batch 1 — 数据融合层
const IntegrationHubPage         = lazy(() => import('./pages/platform/IntegrationHubPage'));
const OmniChannelPage            = lazy(() => import('./pages/platform/OmniChannelPage'));
const TriReconciliationPage      = lazy(() => import('./pages/platform/TriReconciliationPage'));
// Batch 2 — 智能决策层
const SupplierIntelPage          = lazy(() => import('./pages/platform/SupplierIntelPage'));
const ReviewActionPage           = lazy(() => import('./pages/platform/ReviewActionPage'));
const ComplianceEnginePage       = lazy(() => import('./pages/platform/ComplianceEnginePage'));
// Batch 3 — 自动化闭环层
const AutoProcurementPage       = lazy(() => import('./pages/platform/AutoProcurementPage'));
const FinancialClosingPage      = lazy(() => import('./pages/platform/FinancialClosingPage'));
const CommandCenterPage         = lazy(() => import('./pages/platform/CommandCenterPage'));

// HR 模块页面
const PayrollPage = lazy(() => import('./pages/hr/PayrollPage'));
const LeaveManagementPage = lazy(() => import('./pages/hr/LeaveManagementPage'));
const RecruitmentHRPage = lazy(() => import('./pages/hr/RecruitmentPage'));
const PerformanceReviewPage = lazy(() => import('./pages/hr/PerformanceReviewPage'));
const ContractManagementPage = lazy(() => import('./pages/hr/ContractManagementPage'));
const HRDashboardPage = lazy(() => import('./pages/hr/HRDashboardPage'));
const EmployeeRosterPage = lazy(() => import('./pages/hr/EmployeeRosterPage'));
const EmployeeLifecyclePage = lazy(() => import('./pages/hr/EmployeeLifecyclePage'));
const AttendanceReportPage = lazy(() => import('./pages/hr/AttendanceReportPage'));
const SmHRQuick = lazy(() => import('./pages/sm/HRQuick'));
const CommissionPage = lazy(() => import('./pages/hr/CommissionPage'));
const RewardPenaltyPage = lazy(() => import('./pages/hr/RewardPenaltyPage'));
const SocialInsurancePage = lazy(() => import('./pages/hr/SocialInsurancePage'));
const EmployeeGrowthPage = lazy(() => import('./pages/hr/EmployeeGrowthPage'));
const IMConfigPage = lazy(() => import('./pages/hr/IMConfigPage'));
const RosterImportPage = lazy(() => import('./pages/hr/RosterImportPage'));
const OrgStructurePage = lazy(() => import('./pages/hr/OrgStructurePage'));
const ComplianceDashboard = lazy(() => import('./pages/hr/ComplianceDashboard'));
const HRTrainingPage = lazy(() => import('./pages/hr/TrainingPage'));
const TrainingDashboard = lazy(() => import('./pages/hr/TrainingDashboard'));
const MentorshipPage = lazy(() => import('./pages/hr/MentorshipPage'));
const HRMonthlyReportPage = lazy(() => import('./pages/hr/MonthlyReportPage'));
const HRApprovalManagementPage = lazy(() => import('./pages/hr/ApprovalManagementPage'));
const SettlementPage = lazy(() => import('./pages/hr/SettlementPage'));
const PayslipManagementPage = lazy(() => import('./pages/hr/PayslipManagementPage'));
const BusinessRulesPage = lazy(() => import('./pages/hr/BusinessRulesPage'));
const ShiftTemplatePage = lazy(() => import('./pages/hr/ShiftTemplatePage'));
const AttendanceRulePage = lazy(() => import('./pages/hr/AttendanceRulePage'));

// Role-based views (Phase 2 — Chef /chef, Floor /floor, HQ /hq)
const ChefLayout      = lazy(() => import('./layouts/ChefLayout'));
const ChefHome        = lazy(() => import('./pages/chef/Home'));
const ChefSoldout     = lazy(() => import('./pages/chef/Soldout'));
const ChefWaste       = lazy(() => import('./pages/chef/Waste'));
const ChefInventory   = lazy(() => import('./pages/chef/Inventory'));
const FloorLayout     = lazy(() => import('./layouts/FloorLayout'));
const FloorHome       = lazy(() => import('./pages/floor/Home'));
const FloorQueue      = lazy(() => import('./pages/floor/Queue'));
const FloorReservations = lazy(() => import('./pages/floor/Reservations'));
const FloorTables    = lazy(() => import('./pages/floor/Tables'));
const FloorCheckout  = lazy(() => import('./pages/floor/Checkout'));
const FloorKitchen   = lazy(() => import('./pages/floor/Kitchen'));
const HQLayout        = lazy(() => import('./layouts/HQLayout'));
const HQHome          = lazy(() => import('./pages/hq/Home'));
const HQStores        = lazy(() => import('./pages/hq/Stores'));
const HQDecisions     = lazy(() => import('./pages/hq/Decisions'));
const HQFinance       = lazy(() => import('./pages/hq/Finance'));
const HQWorkforce     = lazy(() => import('./pages/hq/Workforce'));
const HQBanquet       = lazy(() => import('./pages/hq/Banquet'));
const HQHr                = lazy(() => import('./pages/hq/HR'));
const HQHrKnowledge       = lazy(() => import('./pages/hq/HRKnowledge'));
const HQHrTalentPipeline  = lazy(() => import('./pages/hq/HRTalentPipeline'));
const HQHrLifecycle       = lazy(() => import('./pages/hq/HRLifecycle'));
const HQHrApprovals       = lazy(() => import('./pages/hq/HRApprovals'));
const HQHrAttendance      = lazy(() => import('./pages/hq/HRAttendance'));
const HQHrPayroll         = lazy(() => import('./pages/hq/HRPayroll'));
const HQHrImport          = lazy(() => import('./pages/hq/HRImport'));
const SmHRTeam            = lazy(() => import('./pages/sm/HRTeam'));
const SmHRPerson          = lazy(() => import('./pages/sm/HRPerson'));
const SmHRSelf            = lazy(() => import('./pages/sm/HRSelf'));
const SmHRMyAttendance    = lazy(() => import('./pages/sm/HRMyAttendance'));
const SmHRLeave           = lazy(() => import('./pages/sm/HRLeave'));
const SmHRGrowth          = lazy(() => import('./pages/sm/HRGrowth'));
const SmBanquet       = lazy(() => import('./pages/sm/Banquet'));
const SmBanquetLeads       = lazy(() => import('./pages/sm/BanquetLeads'));
const SmBanquetLeadDetail  = lazy(() => import('./pages/sm/BanquetLeadDetail'));
const SmBanquetOrders      = lazy(() => import('./pages/sm/BanquetOrders'));
const SmBanquetOrderDetail = lazy(() => import('./pages/sm/BanquetOrderDetail'));
const SmBanquetTasks       = lazy(() => import('./pages/sm/BanquetTasks'));
const SmBanquetPush        = lazy(() => import('./pages/sm/BanquetPush'));
const SmBanquetFollowups   = lazy(() => import('./pages/sm/BanquetFollowups'));
const SmBanquetSearch      = lazy(() => import('./pages/sm/BanquetSearch'));
const SmPrivateDomainHealth = lazy(() => import('./pages/sm/PrivateDomainHealthPage'));
const SmDailyDashboard  = lazy(() => import('./pages/sm/DailyDashboard'));
const SmDailySettlement = lazy(() => import('./pages/sm/DailySettlement'));
const SmAbnormalTasks   = lazy(() => import('./pages/sm/AbnormalTasks'));
const SmWeeklyReview    = lazy(() => import('./pages/sm/WeeklyReview'));
const SmDailyFlow       = lazy(() => import('./pages/sm/DailyFlow'));
const SmPosTerminal     = lazy(() => import('./pages/sm/PosTerminal'));
const SmPurchaseWorkbench = lazy(() => import('./pages/sm/PurchaseWorkbench'));
const SmMobileStocktake = lazy(() => import('./pages/sm/MobileStocktake'));
const HqParetoAnalysis  = lazy(() => import('./pages/hq/ParetoAnalysis'));
const HqFlowInspection  = lazy(() => import('./pages/hq/FlowInspection'));
const HqDataFusionWizard = lazy(() => import('./pages/hq/DataFusionWizard'));
const HqShadowModeDashboard = lazy(() => import('./pages/hq/ShadowModeDashboard'));

// 岗位标准化知识库 + 员工成长溯源 (Phase 2-3 HR知识OS)
const JobStandardLibrary  = lazy(() => import('./pages/hr/JobStandardLibrary'));
const EmployeeGrowthTrace = lazy(() => import('./pages/hr/EmployeeGrowthTrace'));
const JobStandardDetail   = lazy(() => import('./pages/hr/JobStandardDetail'));
const SmMemberProfile = lazy(() => import('./pages/sm/MemberProfile'));
const HqMarketingTasks = lazy(() => import('./pages/hq/MarketingTasks'));
const HqMarketingTaskCreate = lazy(() => import('./pages/hq/MarketingTaskCreate'));
const SmMarketingTasks = lazy(() => import('./pages/sm/MarketingTasks'));
const SmStoreHealthIndex    = lazy(() => import('./pages/sm/StoreHealthIndexPage'));
const HQWeightEvolution     = lazy(() => import('./pages/hq/WeightEvolutionPage'));

// Role-based views — Employee H5 Self-Service (/emp)
const EmployeeLayout    = lazy(() => import('./pages/employee/EmployeeLayout'));
const EmployeePortal    = lazy(() => import('./pages/employee/EmployeePortal'));
const MyPayslipPage     = lazy(() => import('./pages/employee/MyPayslipPage'));
const MyAttendancePage  = lazy(() => import('./pages/employee/MyAttendancePage'));
const LeaveRequestPage  = lazy(() => import('./pages/employee/LeaveRequestPage'));
const MyTrainingPage    = lazy(() => import('./pages/employee/MyTrainingPage'));

const EdgeHubDashboardPage = lazy(() => import('./pages/EdgeHubDashboardPage'));
const EdgeHubStorePage     = lazy(() => import('./pages/EdgeHubStorePage'));
const EdgeHubBindingsPage  = lazy(() => import('./pages/EdgeHubBindingsPage'));
const EdgeHubNodesPage     = lazy(() => import('./pages/EdgeHubNodesPage'));
const EdgeHubAlertsPage    = lazy(() => import('./pages/EdgeHubAlertsPage'));

const PageLoader = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
    <Spin size="large" />
  </div>
);

// ── hostname 自动识别 ──────────────────────────────────────────
// 访问 admin.zlsjos.cn / www.admin.zlsjos.cn 时，自动跳转到 /platform
const ADMIN_HOSTNAMES = ['admin.zlsjos.cn', 'www.admin.zlsjos.cn'];

const HostnameRedirect: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const host = window.location.hostname;
    const isAdminHost = ADMIN_HOSTNAMES.includes(host);
    const isAlreadyOnPlatform = location.pathname.startsWith('/platform');
    const isLoginPage = location.pathname === '/login';

    if (isAdminHost && !isAlreadyOnPlatform && !isLoginPage) {
      navigate('/platform', { replace: true });
    }
  }, [navigate, location.pathname]);

  return null;
};

const AppContent: React.FC = () => {
  const { isDark } = useTheme();

  return (
    <ConfigProvider locale={zhCN} theme={isDark ? darkTheme : lightTheme}>
      <AuthProvider>
        <BrowserRouter>
          <HostnameRedirect />
          <ErrorBoundary>
            <Suspense fallback={PageLoader}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/unauthorized" element={<UnauthorizedPage />} />
                <Route path="/onboarding" element={<OnboardingPage />} />
                {/* 替换易订 — 公开路由（无需登录） */}
                <Route path="/book" element={<BookingH5 />} />
                <Route path="/my-booking" element={<BookingLookup />} />
                <Route path="/invitation/:token" element={<InvitationView />} />
                <Route path="/mobile" element={
                  <ProtectedRoute>
                    <MobileApp />
                  </ProtectedRoute>
                } />
                <Route path="/" element={
                  <ProtectedRoute>
                    <MainLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<Dashboard />} />
                  <Route path="schedule" element={<SchedulePage />} />
                  <Route path="order" element={<OrderPage />} />
                  <Route path="inventory" element={<InventoryPage />} />
                  <Route path="service" element={<ServicePage />} />
                  <Route path="training" element={<TrainingPage />} />
                  <Route path="decision" element={
                    <ProtectedRoute requiredRole="admin"><DecisionPage /></ProtectedRoute>
                  } />
                  <Route path="reservation" element={<ReservationPage />} />
                  <Route path="users" element={
                    <ProtectedRoute requiredRole="admin"><UserManagementPage /></ProtectedRoute>
                  } />
                  <Route path="enterprise" element={
                    <ProtectedRoute requiredRole="admin"><EnterpriseIntegrationPage /></ProtectedRoute>
                  } />
                  <Route path="multi-store" element={
                    <ProtectedRoute requiredRole="admin"><MultiStoreManagement /></ProtectedRoute>
                  } />
                  <Route path="cross-store-config" element={
                    <ProtectedRoute requiredRole="admin"><CrossStoreConfigPage /></ProtectedRoute>
                  } />
                  <Route path="supply-chain" element={
                    <ProtectedRoute requiredRole="admin"><SupplyChainManagement /></ProtectedRoute>
                  } />
                  <Route path="data-visualization" element={
                    <ProtectedRoute><DataVisualizationScreen /></ProtectedRoute>
                  } />
                  <Route path="monitoring" element={
                    <ProtectedRoute requiredRole="admin"><MonitoringPage /></ProtectedRoute>
                  } />
                  <Route path="finance" element={
                    <ProtectedRoute requiredRole="admin"><FinanceManagement /></ProtectedRoute>
                  } />
                  <Route path="backup" element={
                    <ProtectedRoute requiredRole="admin"><BackupManagement /></ProtectedRoute>
                  } />
                  <Route path="analytics" element={
                    <ProtectedRoute><AdvancedAnalytics /></ProtectedRoute>
                  } />
                  <Route path="notifications" element={
                    <ProtectedRoute><NotificationCenter /></ProtectedRoute>
                  } />
                  <Route path="audit" element={
                    <ProtectedRoute requiredRole="admin"><AuditLogPage /></ProtectedRoute>
                  } />
                  <Route path="data-sovereignty" element={
                    <ProtectedRoute requiredRole="admin"><DataSovereigntyPage /></ProtectedRoute>
                  } />
                  <Route path="data-import-export" element={
                    <ProtectedRoute requiredRole="admin"><DataImportExportPage /></ProtectedRoute>
                  } />
                  <Route path="competitive-analysis" element={
                    <ProtectedRoute requiredRole="admin"><CompetitiveAnalysis /></ProtectedRoute>
                  } />
                  <Route path="report-templates" element={
                    <ProtectedRoute requiredRole="admin"><ReportTemplates /></ProtectedRoute>
                  } />
                  <Route path="forecast" element={
                    <ProtectedRoute requiredRole="admin"><ForecastPage /></ProtectedRoute>
                  } />
                  <Route path="cross-store-insights" element={
                    <ProtectedRoute requiredRole="admin"><CrossStoreInsights /></ProtectedRoute>
                  } />
                  <Route path="human-in-the-loop" element={
                    <ProtectedRoute requiredRole="admin"><HumanInTheLoop /></ProtectedRoute>
                  } />
                  <Route path="recommendations" element={
                    <ProtectedRoute requiredRole="store_manager"><RecommendationsPage /></ProtectedRoute>
                  } />
                  <Route path="private-domain" element={
                    <ProtectedRoute requiredRole="admin"><PrivateDomainPage /></ProtectedRoute>
                  } />
                  <Route path="members" element={
                    <ProtectedRoute requiredRole="admin"><MemberSystemPage /></ProtectedRoute>
                  } />
                  <Route path="cdp-monitor" element={
                    <ProtectedRoute requiredRole="admin"><CDPMonitorPage /></ProtectedRoute>
                  } />
                  <Route path="kpi-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><KPIDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="customer360" element={
                    <ProtectedRoute requiredRole="admin"><Customer360Page /></ProtectedRoute>
                  } />
                  <Route path="pos" element={
                    <ProtectedRoute requiredRole="admin"><POSPage /></ProtectedRoute>
                  } />
                  <Route path="quality" element={
                    <ProtectedRoute requiredRole="admin"><QualityManagementPage /></ProtectedRoute>
                  } />
                  <Route path="compliance" element={
                    <ProtectedRoute requiredRole="admin"><CompliancePage /></ProtectedRoute>
                  } />
                  <Route path="ai-evolution" element={
                    <ProtectedRoute requiredRole="admin"><AIEvolutionPage /></ProtectedRoute>
                  } />
                  <Route path="edge-node" element={
                    <ProtectedRoute requiredRole="admin"><EdgeNodePage /></ProtectedRoute>
                  } />
                  <Route path="decision-validator" element={
                    <ProtectedRoute requiredRole="admin"><DecisionValidatorPage /></ProtectedRoute>
                  } />
                  <Route path="federated-learning" element={
                    <ProtectedRoute requiredRole="admin"><FederatedLearningPage /></ProtectedRoute>
                  } />
                  <Route path="agent-collaboration" element={
                    <ProtectedRoute requiredRole="admin"><AgentCollaborationPage /></ProtectedRoute>
                  } />
                  <Route path="open-platform" element={
                    <ProtectedRoute requiredRole="admin"><OpenPlatformPage /></ProtectedRoute>
                  } />
                  <Route path="developer-docs" element={
                    <ProtectedRoute requiredRole="admin"><DeveloperDocsPage /></ProtectedRoute>
                  } />
                  <Route path="isv-ecosystem" element={
                    <ProtectedRoute requiredRole="admin"><ISVEcosystemPage /></ProtectedRoute>
                  } />
                  <Route path="isv-management" element={
                    <ProtectedRoute requiredRole="admin"><ISVManagementPage /></ProtectedRoute>
                  } />
                  <Route path="plugin-marketplace" element={
                    <ProtectedRoute requiredRole="admin"><PluginMarketplacePage /></ProtectedRoute>
                  } />
                  <Route path="revenue-share" element={
                    <ProtectedRoute requiredRole="admin"><RevenueSharePage /></ProtectedRoute>
                  } />
                  <Route path="isv-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><ISVDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="platform-analytics" element={
                    <ProtectedRoute requiredRole="admin"><PlatformAnalyticsPage /></ProtectedRoute>
                  } />
                  <Route path="webhook-management" element={
                    <ProtectedRoute requiredRole="admin"><WebhookManagementPage /></ProtectedRoute>
                  } />
                  <Route path="api-billing" element={
                    <ProtectedRoute requiredRole="admin"><ApiBillingPage /></ProtectedRoute>
                  } />
                  <Route path="developer-console" element={
                    <ProtectedRoute requiredRole="admin"><DeveloperConsolePage /></ProtectedRoute>
                  } />
                  <Route path="business-events" element={
                    <ProtectedRoute requiredRole="admin"><BusinessEventsPage /></ProtectedRoute>
                  } />
                  <Route path="cfo-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><CFODashboardPage /></ProtectedRoute>
                  } />
                  <Route path="settlement-risk" element={
                    <ProtectedRoute requiredRole="admin"><SettlementRiskPage /></ProtectedRoute>
                  } />
                  <Route path="ceo-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><CeoDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="budget-management" element={
                    <ProtectedRoute requiredRole="admin"><BudgetManagementPage /></ProtectedRoute>
                  } />
                  <Route path="financial-alerts" element={
                    <ProtectedRoute requiredRole="admin"><FinancialAlertsPage /></ProtectedRoute>
                  } />
                  <Route path="finance-health" element={
                    <ProtectedRoute requiredRole="admin"><FinanceHealthPage /></ProtectedRoute>
                  } />
                  <Route path="financial-forecast" element={
                    <ProtectedRoute requiredRole="admin"><FinancialForecastPage /></ProtectedRoute>
                  } />
                  <Route path="financial-anomaly" element={
                    <ProtectedRoute requiredRole="admin"><FinancialAnomalyPage /></ProtectedRoute>
                  } />
                  <Route path="performance-ranking" element={
                    <ProtectedRoute requiredRole="admin"><PerformanceRankingPage /></ProtectedRoute>
                  } />
                  <Route path="edge-hub" element={
                    <ProtectedRoute requiredRole="admin"><EdgeHubDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="edge-hub/nodes" element={
                    <ProtectedRoute requiredRole="admin"><EdgeHubNodesPage /></ProtectedRoute>
                  } />
                  <Route path="edge-hub/alerts" element={
                    <ProtectedRoute requiredRole="admin"><EdgeHubAlertsPage /></ProtectedRoute>
                  } />
                  <Route path="edge-hub/stores/:storeId" element={
                    <ProtectedRoute requiredRole="admin"><EdgeHubStorePage /></ProtectedRoute>
                  } />
                  <Route path="edge-hub/bindings" element={
                    <ProtectedRoute requiredRole="admin"><EdgeHubBindingsPage /></ProtectedRoute>
                  } />
                  <Route path="financial-recommendation" element={
                    <ProtectedRoute requiredRole="admin"><FinancialRecommendationPage /></ProtectedRoute>
                  } />
                  <Route path="dish-profitability" element={
                    <ProtectedRoute requiredRole="admin"><DishProfitabilityPage /></ProtectedRoute>
                  } />
                  <Route path="menu-optimization" element={
                    <ProtectedRoute requiredRole="admin"><MenuOptimizationPage /></ProtectedRoute>
                  } />
                  <Route path="dish-cost-alert" element={
                    <ProtectedRoute requiredRole="admin"><DishCostAlertPage /></ProtectedRoute>
                  } />
                  <Route path="dish-benchmark" element={
                    <ProtectedRoute requiredRole="admin"><DishBenchmarkPage /></ProtectedRoute>
                  } />
                  <Route path="dish-pricing" element={
                    <ProtectedRoute requiredRole="admin"><DishPricingPage /></ProtectedRoute>
                  } />
                  <Route path="dish-lifecycle" element={
                    <ProtectedRoute requiredRole="admin"><DishLifecyclePage /></ProtectedRoute>
                  } />
                  <Route path="dish-forecast" element={
                    <ProtectedRoute requiredRole="admin"><DishForecastPage /></ProtectedRoute>
                  } />
                  <Route path="dish-health" element={
                    <ProtectedRoute requiredRole="admin"><DishHealthPage /></ProtectedRoute>
                  } />
                  <Route path="dish-attribution" element={
                    <ProtectedRoute requiredRole="admin"><DishAttributionPage /></ProtectedRoute>
                  } />
                  <Route path="menu-matrix" element={
                    <ProtectedRoute requiredRole="admin"><MenuMatrixPage /></ProtectedRoute>
                  } />
                  <Route path="cost-compression" element={
                    <ProtectedRoute requiredRole="admin"><CostCompressionPage /></ProtectedRoute>
                  } />
                  <Route path="dish-monthly-summary" element={
                    <ProtectedRoute requiredRole="admin"><DishMonthlySummaryPage /></ProtectedRoute>
                  } />
                  <Route path="industry-solutions" element={
                    <ProtectedRoute requiredRole="admin"><IndustrySolutionsPage /></ProtectedRoute>
                  } />
                  <Route path="i18n" element={
                    <ProtectedRoute requiredRole="admin"><I18nPage /></ProtectedRoute>
                  } />
                  <Route path="tasks" element={
                    <ProtectedRoute requiredRole="admin"><TaskManagementPage /></ProtectedRoute>
                  } />
                  <Route path="reconciliation" element={
                    <ProtectedRoute requiredRole="admin"><ReconciliationPage /></ProtectedRoute>
                  } />
                  <Route path="dishes" element={
                    <ProtectedRoute requiredRole="admin"><DishManagementPage /></ProtectedRoute>
                  } />
                  <Route path="employees" element={
                    <ProtectedRoute requiredRole="admin"><EmployeeManagementPage /></ProtectedRoute>
                  } />
                  <Route path="raas" element={
                    <ProtectedRoute requiredRole="admin"><RaaSPage /></ProtectedRoute>
                  } />
                  <Route path="model-marketplace" element={
                    <ProtectedRoute requiredRole="admin"><ModelMarketplacePage /></ProtectedRoute>
                  } />
                  <Route path="llm-config" element={
                    <ProtectedRoute requiredRole="admin"><LLMConfigPage /></ProtectedRoute>
                  } />
                  <Route path="hardware" element={
                    <ProtectedRoute requiredRole="admin"><HardwarePage /></ProtectedRoute>
                  } />
                  <Route path="integrations" element={
                    <ProtectedRoute requiredRole="admin"><IntegrationsPage /></ProtectedRoute>
                  } />
                  <Route path="neural" element={
                    <ProtectedRoute requiredRole="admin"><NeuralSystemPage /></ProtectedRoute>
                  } />
                  <Route path="embedding" element={
                    <ProtectedRoute requiredRole="admin"><EmbeddingPage /></ProtectedRoute>
                  } />
                  <Route path="scheduler" element={
                    <ProtectedRoute requiredRole="admin"><SchedulerPage /></ProtectedRoute>
                  } />
                  <Route path="benchmark" element={
                    <ProtectedRoute requiredRole="admin"><BenchmarkPage /></ProtectedRoute>
                  } />
                  <Route path="approval" element={
                    <ProtectedRoute requiredRole="admin"><ApprovalManagementPage /></ProtectedRoute>
                  } />
                  <Route path="stores" element={
                    <ProtectedRoute><StoreManagementPage /></ProtectedRoute>
                  } />
                  <Route path="export-jobs" element={
                    <ProtectedRoute requiredRole="admin"><ExportJobsPage /></ProtectedRoute>
                  } />
                  <Route path="roles" element={
                    <ProtectedRoute requiredRole="admin"><RoleManagementPage /></ProtectedRoute>
                  } />
                  <Route path="queue" element={
                    <ProtectedRoute requiredRole="admin"><QueueManagementPage /></ProtectedRoute>
                  } />
                  <Route path="agent-memory" element={
                    <ProtectedRoute requiredRole="admin"><AgentMemoryPage /></ProtectedRoute>
                  } />
                  <Route path="wechat-triggers" element={
                    <ProtectedRoute requiredRole="admin"><WeChatTriggersPage /></ProtectedRoute>
                  } />
                  <Route path="im-channels" element={
                    <ProtectedRoute requiredRole="admin"><IMChannelPage /></ProtectedRoute>
                  } />
                  <Route path="event-sourcing" element={
                    <ProtectedRoute requiredRole="admin"><EventSourcingPage /></ProtectedRoute>
                  } />
                  <Route path="meituan-queue" element={
                    <ProtectedRoute requiredRole="admin"><MeituanQueuePage /></ProtectedRoute>
                  } />
                  <Route path="vector-index" element={
                    <ProtectedRoute requiredRole="admin"><VectorIndexPage /></ProtectedRoute>
                  } />
                  <Route path="adapters" element={
                    <ProtectedRoute requiredRole="admin"><AdaptersPage /></ProtectedRoute>
                  } />
                  <Route path="voice-devices" element={
                    <ProtectedRoute requiredRole="admin"><VoiceDevicePage /></ProtectedRoute>
                  } />
                  <Route path="system-health" element={
                    <ProtectedRoute requiredRole="admin"><SystemHealthPage /></ProtectedRoute>
                  } />
                  <Route path="profile" element={
                    <ProtectedRoute><UserProfilePage /></ProtectedRoute>
                  } />
                  <Route path="voice-ws" element={
                    <ProtectedRoute requiredRole="admin"><VoiceWebSocketPage /></ProtectedRoute>
                  } />
                  <Route path="ops-agent" element={
                    <ProtectedRoute requiredRole="admin"><OpsAgentPage /></ProtectedRoute>
                  } />
                  <Route path="daily-hub" element={
                    <ProtectedRoute><DailyHubPage /></ProtectedRoute>
                  } />
                  <Route path="bulk-import" element={
                    <ProtectedRoute requiredRole="admin"><BulkImportPage /></ProtectedRoute>
                  } />
                  <Route path="my-schedule" element={
                    <ProtectedRoute><MySchedulePage /></ProtectedRoute>
                  } />
                  <Route path="hq-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><HQDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="ai-accuracy" element={
                    <ProtectedRoute requiredRole="admin"><AIAccuracyPage /></ProtectedRoute>
                  } />
                  <Route path="governance" element={
                    <ProtectedRoute requiredRole="admin"><GovDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="merchants" element={
                    <ProtectedRoute requiredRole="admin"><MerchantManagementPage /></ProtectedRoute>
                  } />
                  <Route path="channel-analytics" element={<ChannelAnalyticsPage />} />
                  <Route path="customer-risk" element={<CustomerRiskPage />} />
                  <Route path="banquet-sales" element={<BanquetSalesPage />} />
                  <Route path="event-orders" element={<EventOrderPage />} />
                  <Route path="reservation-ai" element={<ReservationAIPage />} />
                  <Route path="agent-hub" element={
                    <ProtectedRoute requiredRole="admin"><AgentHubPage /></ProtectedRoute>
                  } />
                  <Route path="ops-hub" element={
                    <ProtectedRoute><OpsHubPage /></ProtectedRoute>
                  } />
                  <Route path="products-hub" element={
                    <ProtectedRoute><ProductsHubPage /></ProtectedRoute>
                  } />
                  <Route path="crm-hub" element={
                    <ProtectedRoute><CrmHubPage /></ProtectedRoute>
                  } />
                  <Route path="platform-hub" element={
                    <ProtectedRoute requiredRole="admin"><PlatformHubPage /></ProtectedRoute>
                  } />
                  <Route path="dish-cost" element={
                    <ProtectedRoute requiredRole="store_manager"><DishCostPage /></ProtectedRoute>
                  } />
                  <Route path="channel-profit" element={
                    <ProtectedRoute requiredRole="store_manager"><ChannelProfitPage /></ProtectedRoute>
                  } />
                  <Route path="employee-performance" element={
                    <ProtectedRoute requiredRole="store_manager"><EmployeePerformancePage /></ProtectedRoute>
                  } />
                  <Route path="order-analytics" element={
                    <ProtectedRoute><OrderAnalyticsPage /></ProtectedRoute>
                  } />
                  <Route path="dashboard-preferences" element={
                    <ProtectedRoute><DashboardPreferencesPage /></ProtectedRoute>
                  } />
                  <Route path="notification-preferences" element={
                    <ProtectedRoute><NotificationPreferencesPage /></ProtectedRoute>
                  } />
                  <Route path="nl-query" element={
                    <ProtectedRoute requiredRole="admin"><NLQueryPage /></ProtectedRoute>
                  } />
                  <Route path="menu-recommendations" element={
                    <ProtectedRoute><MenuRecommendationPage /></ProtectedRoute>
                  } />
                  <Route path="waste-reasoning" element={
                    <ProtectedRoute requiredRole="store_manager"><WasteReasoningPage /></ProtectedRoute>
                  } />
                  <Route path="ontology-graph" element={
                    <ProtectedRoute requiredRole="admin"><OntologyGraphPage /></ProtectedRoute>
                  } />
                  <Route path="knowledge-rules" element={
                    <ProtectedRoute requiredRole="admin"><KnowledgeRulePage /></ProtectedRoute>
                  } />
                  <Route path="ontology-admin" element={
                    <ProtectedRoute requiredRole="admin"><OntologyAdminPage /></ProtectedRoute>
                  } />
                  <Route path="bom-management" element={
                    <ProtectedRoute requiredRole="store_manager"><BOMManagementPage /></ProtectedRoute>
                  } />
                  <Route path="waste-events" element={
                    <ProtectedRoute requiredRole="store_manager"><WasteEventPage /></ProtectedRoute>
                  } />
                  <Route path="data-security" element={
                    <ProtectedRoute requiredRole="admin"><DataSecurityPage /></ProtectedRoute>
                  } />
                  <Route path="banquet-lifecycle" element={
                    <ProtectedRoute requiredRole="store_manager"><BanquetLifecyclePage /></ProtectedRoute>
                  } />
                  <Route path="marketing" element={
                    <ProtectedRoute requiredRole="store_manager"><MarketingCampaignPage /></ProtectedRoute>
                  } />
                  <Route path="fct" element={
                    <ProtectedRoute requiredRole="store_manager"><FctPage /></ProtectedRoute>
                  } />
                  <Route path="approval-list" element={
                    <ProtectedRoute requiredRole="admin"><ApprovalListPage /></ProtectedRoute>
                  } />
                  <Route path="action-plans" element={
                    <ProtectedRoute requiredRole="store_manager"><ActionPlansPage /></ProtectedRoute>
                  } />
                  <Route path="workforce" element={
                    <ProtectedRoute requiredRole="store_manager"><WorkforcePage /></ProtectedRoute>
                  } />
                  <Route path="decision-stats" element={
                    <ProtectedRoute requiredRole="admin"><DecisionStatisticsDashboard /></ProtectedRoute>
                  } />
                  <Route path="profit-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><ProfitDashboard /></ProtectedRoute>
                  } />
                  <Route path="alert-thresholds" element={
                    <ProtectedRoute requiredRole="store_manager"><AlertThresholdsPage /></ProtectedRoute>
                  } />
                  <Route path="monthly-report" element={
                    <ProtectedRoute requiredRole="admin"><MonthlyReportPage /></ProtectedRoute>
                  } />
                  <Route path="dynamic-pricing" element={
                    <ProtectedRoute requiredRole="admin"><DynamicPricingPage /></ProtectedRoute>
                  } />
                  <Route path="ops-monitoring" element={
                    <ProtectedRoute requiredRole="admin"><OpsMonitoringPage /></ProtectedRoute>
                  } />
                  <Route path="dish-rd" element={
                    <ProtectedRoute requiredRole="admin"><DishRdPage /></ProtectedRoute>
                  } />
                  <Route path="dish-rd/:dishId" element={
                    <ProtectedRoute requiredRole="admin"><DishRdDetailPage /></ProtectedRoute>
                  } />
                  <Route path="supplier-agent" element={
                    <ProtectedRoute requiredRole="admin"><SupplierAgentPage /></ProtectedRoute>
                  } />
                  <Route path="business-intel" element={
                    <ProtectedRoute requiredRole="admin"><BusinessIntelPage /></ProtectedRoute>
                  } />
                  <Route path="people-agent" element={
                    <ProtectedRoute requiredRole="admin"><PeopleAgentPage /></ProtectedRoute>
                  } />
                  <Route path="ops-flow-agent" element={
                    <ProtectedRoute requiredRole="admin"><OpsFlowAgentPage /></ProtectedRoute>
                  } />
                  <Route path="agent-okr" element={
                    <ProtectedRoute requiredRole="admin"><AgentOKRPage /></ProtectedRoute>
                  } />
                  <Route path="agent-collab" element={
                    <ProtectedRoute requiredRole="admin"><AgentCollabPage /></ProtectedRoute>
                  } />
                  <Route path="fct-advanced" element={
                    <ProtectedRoute requiredRole="admin"><FctAdvancedPage /></ProtectedRoute>
                  } />
                  {/* HR模块 — 薪酬/假勤/招聘/绩效/合同/仪表盘 */}
                  <Route path="hr-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><HRDashboardPage /></ProtectedRoute>
                  } />
                  <Route path="payroll" element={
                    <ProtectedRoute requiredRole="admin"><PayrollPage /></ProtectedRoute>
                  } />
                  <Route path="leave-management" element={
                    <ProtectedRoute requiredRole="store_manager"><LeaveManagementPage /></ProtectedRoute>
                  } />
                  <Route path="recruitment" element={
                    <ProtectedRoute requiredRole="admin"><RecruitmentHRPage /></ProtectedRoute>
                  } />
                  <Route path="performance-review" element={
                    <ProtectedRoute requiredRole="admin"><PerformanceReviewPage /></ProtectedRoute>
                  } />
                  <Route path="contract-management" element={
                    <ProtectedRoute requiredRole="admin"><ContractManagementPage /></ProtectedRoute>
                  } />
                  <Route path="employee-roster" element={
                    <ProtectedRoute requiredRole="store_manager"><EmployeeRosterPage /></ProtectedRoute>
                  } />
                  <Route path="employee-lifecycle" element={
                    <ProtectedRoute requiredRole="store_manager"><EmployeeLifecyclePage /></ProtectedRoute>
                  } />
                  <Route path="attendance-report" element={
                    <ProtectedRoute requiredRole="store_manager"><AttendanceReportPage /></ProtectedRoute>
                  } />
                  <Route path="commission" element={
                    <ProtectedRoute requiredRole="admin"><CommissionPage /></ProtectedRoute>
                  } />
                  <Route path="reward-penalty" element={
                    <ProtectedRoute requiredRole="admin"><RewardPenaltyPage /></ProtectedRoute>
                  } />
                  <Route path="social-insurance" element={
                    <ProtectedRoute requiredRole="admin"><SocialInsurancePage /></ProtectedRoute>
                  } />
                  <Route path="employee-growth" element={
                    <ProtectedRoute requiredRole="admin"><EmployeeGrowthPage /></ProtectedRoute>
                  } />
                  <Route path="im-config" element={
                    <ProtectedRoute requiredRole="admin"><IMConfigPage /></ProtectedRoute>
                  } />
                  <Route path="roster-import" element={
                    <ProtectedRoute requiredRole="admin"><RosterImportPage /></ProtectedRoute>
                  } />
                  <Route path="org-structure" element={
                    <ProtectedRoute requiredRole="admin"><OrgStructurePage /></ProtectedRoute>
                  } />
                  <Route path="compliance" element={
                    <ProtectedRoute requiredRole="admin"><ComplianceDashboard /></ProtectedRoute>
                  } />
                  <Route path="hr-training" element={
                    <ProtectedRoute requiredRole="admin"><HRTrainingPage /></ProtectedRoute>
                  } />
                  <Route path="training-dashboard" element={
                    <ProtectedRoute requiredRole="admin"><TrainingDashboard /></ProtectedRoute>
                  } />
                  <Route path="mentorship" element={
                    <ProtectedRoute requiredRole="admin"><MentorshipPage /></ProtectedRoute>
                  } />
                  <Route path="hr-monthly-report" element={
                    <ProtectedRoute requiredRole="admin"><HRMonthlyReportPage /></ProtectedRoute>
                  } />
                  <Route path="hr-approval" element={
                    <ProtectedRoute requiredRole="admin"><HRApprovalManagementPage /></ProtectedRoute>
                  } />
                  <Route path="settlement" element={
                    <ProtectedRoute requiredRole="admin"><SettlementPage /></ProtectedRoute>
                  } />
                  <Route path="payslip-management" element={
                    <ProtectedRoute requiredRole="admin"><PayslipManagementPage /></ProtectedRoute>
                  } />
                  <Route path="business-rules" element={
                    <ProtectedRoute requiredRole="admin"><BusinessRulesPage /></ProtectedRoute>
                  } />
                  <Route path="shift-templates" element={
                    <ProtectedRoute requiredRole="admin"><ShiftTemplatePage /></ProtectedRoute>
                  } />
                  <Route path="attendance-rules" element={
                    <ProtectedRoute requiredRole="admin"><AttendanceRulePage /></ProtectedRoute>
                  } />
                  {/* 岗位标准化知识库 + 员工成长溯源 */}
                  <Route path="job-standard-library" element={
                    <ProtectedRoute requiredRole="admin"><JobStandardLibrary /></ProtectedRoute>
                  } />
                  <Route path="employee-growth-trace" element={
                    <ProtectedRoute requiredRole="store_manager"><EmployeeGrowthTrace /></ProtectedRoute>
                  } />
                  <Route path="job-standard/:jobCode" element={
                    <ProtectedRoute><JobStandardDetail /></ProtectedRoute>
                  } />
                  {/* 替换易订 — R3 桌台平面图 / R4 AI邀请函 */}
                  <Route path="floor-plan" element={
                    <ProtectedRoute><FloorPlanPage /></ProtectedRoute>
                  } />
                  <Route path="invitation-manager" element={
                    <ProtectedRoute><InvitationManagerPage /></ProtectedRoute>
                  } />
                  <Route path="reservation-analytics" element={
                    <ProtectedRoute><ReservationAnalyticsPage /></ProtectedRoute>
                  } />
                </Route>

                {/* ── Level 1: 屯象智能平台 /platform (admin.zlsjos.cn) ── */}
                <Route path="/platform" element={
                  <ProtectedRoute requiredRole="admin">
                    <PlatformAdminLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<PlatformAdminHome />} />
                  {/* 产品工程 */}
                  <Route path="analytics" element={<PlatformAnalyticsPage />} />
                  <Route path="feature-flags" element={<PlatformFeatureFlagsPage />} />
                  {/* 智能引擎 */}
                  <Route path="agents" element={<PlatformAgentsPage />} />
                  <Route path="ontology" element={<PlatformOntologyPage />} />
                  <Route path="model-versions" element={<ModelVersionPage />} />
                  <Route path="prompt-warehouse" element={<PromptWarehousePage />} />
                  <Route path="cross-learning" element={<CrossMerchantLearningPage />} />
                  {/* 商户生命周期 */}
                  <Route path="merchants" element={<MerchantListPage />} />
                  <Route path="merchants/:brandId" element={<MerchantDetailPage />} />
                  <Route path="module-auth" element={<ModuleAuthPage />} />
                  <Route path="key-mgmt" element={<KeyManagementPage />} />
                  <Route path="delivery" element={<DeliveryTrackingPage />} />
                  <Route path="renewal-alert" element={<RenewalAlertPage />} />
                  {/* 平台运维 */}
                  <Route path="monitoring" element={<PlatformSystemMonitorPage />} />
                  <Route path="audit-log" element={<PlatformAuditLogPage />} />
                  <Route path="backup" element={<PlatformBackupPage />} />
                  <Route path="open-platform" element={<OpenPlatformPage />} />
                  <Route path="users" element={<UserManagementPage />} />
                  <Route path="settings" element={<SystemSettingsPage />} />
                </Route>

                {/* ── Level 2: 商户管理运维后台 /ops ── */}
                <Route path="/ops" element={
                  <ProtectedRoute requiredRole="admin">
                    <OpsAdminLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<OpsHomePage />} />
                  {/* 数据接入 */}
                  <Route path="pos" element={<POSPage />} />
                  <Route path="menu-import" element={<MenuImportPage />} />
                  <Route path="bom-import" element={<BomImportPage />} />
                  <Route path="channels" element={<ChannelDataPage />} />
                  {/* 配置中台 */}
                  <Route path="rules" element={<OpsBusinessRulesPage />} />
                  <Route path="store-tpl" element={<StoreTemplatePage />} />
                  <Route path="agent-train" element={<AgentTrainingPage />} />
                  <Route path="isolation" element={<DataIsolationPage />} />
                  {/* 设备运维 */}
                  <Route path="edge-nodes" element={<EdgeNodeManagementPage />} />
                  <Route path="iot" element={<IoTDevicesPage />} />
                  <Route path="voice" element={<VoiceDevicePage />} />
                  {/* AI运维 */}
                  <Route path="llm-config" element={<LLMConfigPage />} />
                  <Route path="model-monitor" element={<ModelMonitorPage />} />
                  <Route path="push" element={<PushStrategyPage />} />
                  {/* 数据治理 */}
                  <Route path="data-sovereignty" element={<PlatformDataSovereigntyPage />} />
                  <Route path="data-import" element={<DataImportExportPage />} />
                  <Route path="data-export" element={<ExportJobsPage />} />
                  {/* 外部集成 */}
                  <Route path="integrations" element={<PlatformIntegrationsPage />} />
                  <Route path="e-invoices" element={<EInvoicePage />} />
                  <Route path="eleme" element={<ElemePage />} />
                  <Route path="douyin" element={<DouyinPage />} />
                  <Route path="dianping" element={<DianpingPage />} />
                  <Route path="supplier-b2b" element={<SupplierB2BPage />} />
                  <Route path="payment-recon" element={<PaymentReconciliationPage />} />
                  <Route path="bank-recon" element={<BankReconciliationPage />} />
                </Route>

                {/* Role-based views — Store Manager (手机) */}
                <Route path="/sm" element={
                  <ProtectedRoute>
                    <StoreManagerLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<SmHome />} />
                  <Route path="home"      element={<SmHome />} />
                  <Route path="shifts"    element={<SmShifts />} />
                  <Route path="tasks"     element={<SmTasks />} />
                  <Route path="business"  element={<SmBusiness />} />
                  <Route path="decisions" element={<SmDecisions />} />
                  <Route path="alerts"    element={<SmAlerts />} />
                  <Route path="workforce" element={<SmWorkforce />} />
                  <Route path="banquet"              element={<SmBanquet />} />
                  <Route path="banquet-leads"        element={<SmBanquetLeads />} />
                  <Route path="banquet-leads/:leadId" element={<SmBanquetLeadDetail />} />
                  <Route path="banquet-orders"       element={<SmBanquetOrders />} />
                  <Route path="banquet-orders/:orderId" element={<SmBanquetOrderDetail />} />
                  <Route path="banquet-tasks"        element={<SmBanquetTasks />} />
                  <Route path="banquet-push"         element={<SmBanquetPush />} />
                  <Route path="banquet-followups"    element={<SmBanquetFollowups />} />
                  <Route path="banquet-search"       element={<SmBanquetSearch />} />
                  <Route path="private-domain-health" element={<SmPrivateDomainHealth />} />
                  <Route path="prep" element={<SmPrepSuggestion />} />
                  <Route path="hr"             element={<SmHRQuick />} />
                  <Route path="hr/team"        element={<SmHRTeam />} />
                  <Route path="hr/person/:id"  element={<SmHRPerson />} />
                  <Route path="hr/self"          element={<SmHRSelf />} />
                  <Route path="hr/my-attendance" element={<SmHRMyAttendance />} />
                  <Route path="hr/leave"         element={<SmHRLeave />} />
                  <Route path="hr/growth"        element={<SmHRGrowth />} />
                  <Route path="patrol"   element={<SmPatrol />} />
                  <Route path="members"  element={<SmMemberProfile />} />
                  <Route path="profile"  element={<SmProfile />} />
                  {/* 日清日结 + 周复盘 */}
                  <Route path="daily-dashboard"  element={<SmDailyDashboard />} />
                  <Route path="daily-settlement" element={<SmDailySettlement />} />
                  <Route path="tasks-abnormal"   element={<SmAbnormalTasks />} />
                  <Route path="weekly-review"    element={<SmWeeklyReview />} />
                  <Route path="daily-flow"      element={<SmDailyFlow />} />
                  <Route path="marketing-tasks" element={<SmMarketingTasks />} />
                  <Route path="health-index"          element={<SmStoreHealthIndex />} />
                  {/* Phase 2.2 — 功能平权：收银/采购/盘点 */}
                  <Route path="pos"        element={<SmPosTerminal />} />
                  <Route path="purchase"   element={<SmPurchaseWorkbench />} />
                  <Route path="stocktake"  element={<SmMobileStocktake />} />
                </Route>

                {/* Role-based views — Chef (手机) */}
                <Route path="/chef" element={
                  <ProtectedRoute>
                    <ChefLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<ChefHome />} />
                  <Route path="soldout"   element={<ChefSoldout />} />
                  <Route path="waste"     element={<ChefWaste />} />
                  <Route path="inventory" element={<ChefInventory />} />
                </Route>

                {/* Role-based views — Floor Manager (平板) */}
                <Route path="/floor" element={
                  <ProtectedRoute>
                    <FloorLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<FloorHome />} />
                  <Route path="tables"       element={<FloorTables />} />
                  <Route path="queue"        element={<FloorQueue />} />
                  <Route path="reservations" element={<FloorReservations />} />
                  <Route path="checkout"     element={<FloorCheckout />} />
                  <Route path="kitchen"      element={<FloorKitchen />} />
                </Route>

                {/* ── Level 3: 商户经营决策中心 /hq (桌面) ── */}
                <Route path="/hq" element={
                  <ProtectedRoute>
                    <HQLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<HQHome />} />
                  {/* 营收增长 */}
                  <Route path="stores" element={<HQStores />} />
                  <Route path="dishes" element={<DishProfitabilityPage />} />
                  <Route path="channels" element={<ChannelProfitPage />} />
                  <Route path="members" element={<MemberSystemPage />} />
                  <Route path="pricing" element={<DynamicPricingPage />} />
                  {/* 成本管控 */}
                  <Route path="inventory" element={<InventoryPage />} />
                  <Route path="supply" element={<SupplyChainManagement />} />
                  <Route path="waste" element={<WasteReasoningPage />} />
                  <Route path="bom" element={<BOMManagementPage />} />
                  <Route path="workforce" element={<HQWorkforce />} />
                  {/* 品质合规 */}
                  <Route path="food-safety" element={<FoodSafetyPage />} />
                  <Route path="quality" element={<QualityManagementPage />} />
                  <Route path="training" element={<TrainingPage />} />
                  <Route path="compliance" element={<CompliancePage />} />
                  {/* 财务结算 */}
                  <Route path="finance" element={<HQFinance />} />
                  <Route path="recon" element={<ReconciliationPage />} />
                  <Route path="settlement" element={<SettlementRiskPage />} />
                  <Route path="tax" element={<TaxCashflowPage />} />
                  <Route path="budget" element={<BudgetManagementPage />} />
                  {/* 经营洞察 */}
                  <Route path="decisions" element={<HQDecisions />} />
                  <Route path="competitive" element={<CompetitiveAnalysis />} />
                  <Route path="forecast" element={<ForecastPage />} />
                  <Route path="reports" element={<ReportTemplates />} />
                  <Route path="banquet" element={<HQBanquet />} />
                  {/* 营销任务 */}
                  <Route path="marketing-tasks" element={<HqMarketingTasks />} />
                  <Route path="marketing-tasks/create" element={<HqMarketingTaskCreate />} />
                  <Route path="weight-evolution"  element={<HQWeightEvolution />} />
                  {/* v3.0 全天流程 + 帕累托分析 */}
                  <Route path="flow-inspection"  element={<HqFlowInspection />} />
                  <Route path="pareto-analysis"  element={<HqParetoAnalysis />} />
                  {/* Phase P1/P2 — 数据融合 + SaaS渐进替换 */}
                  <Route path="data-fusion"  element={<HqDataFusionWizard />} />
                  <Route path="shadow-mode"  element={<HqShadowModeDashboard />} />
                </Route>

                {/* Role-based views — Employee H5 Self-Service (手机) */}
                <Route path="/emp" element={<EmployeeLayout />}>
                  <Route index element={<EmployeePortal />} />
                  <Route path="payslip"    element={<MyPayslipPage />} />
                  <Route path="attendance" element={<MyAttendancePage />} />
                  <Route path="leave"      element={<LeaveRequestPage />} />
                  <Route path="training"   element={<MyTrainingPage />} />
                  <Route path="profile"    element={<EmployeePortal />} />
                </Route>

                {/* 404 通配符必须放在所有路由最后 */}
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
};

export default App;
