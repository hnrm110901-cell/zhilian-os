import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
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
const QueueManagementPage = lazy(() => import('./pages/QueueManagementPage'));
const AgentMemoryPage = lazy(() => import('./pages/AgentMemoryPage'));
const WeChatTriggersPage = lazy(() => import('./pages/WeChatTriggersPage'));
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
const BanquetLifecyclePage = lazy(() => import('./pages/BanquetLifecyclePage'));
const MarketingCampaignPage = lazy(() => import('./pages/MarketingCampaignPage'));
const FctPage = lazy(() => import('./pages/FctPage'));
const ApprovalListPage = lazy(() => import('./pages/ApprovalListPage'));
const DecisionStatisticsDashboard = lazy(() => import('./pages/DecisionStatisticsDashboard'));
const ProfitDashboard = lazy(() => import('./pages/ProfitDashboard'));
const AlertThresholdsPage = lazy(() => import('./pages/AlertThresholdsPage'));
const MonthlyReportPage = lazy(() => import('./pages/MonthlyReportPage'));
const OnboardingPage = lazy(() => import('./pages/onboarding/OnboardingPage'));
const DynamicPricingPage = lazy(() => import('./pages/DynamicPricingPage'));
const OpsMonitoringPage = lazy(() => import('./pages/OpsMonitoringPage'));

// Role-based views (Phase 1 — Store Manager /sm)
const StoreManagerLayout = lazy(() => import('./layouts/StoreManagerLayout'));
const SmHome      = lazy(() => import('./pages/sm/Home'));
const SmBusiness  = lazy(() => import('./pages/sm/Business'));
const SmDecisions = lazy(() => import('./pages/sm/Decisions'));
const SmAlerts    = lazy(() => import('./pages/sm/Alerts'));

// Role-based views (Phase 2 — Chef /chef, Floor /floor, HQ /hq)
const ChefLayout      = lazy(() => import('./layouts/ChefLayout'));
const ChefHome        = lazy(() => import('./pages/chef/Home'));
const ChefWaste       = lazy(() => import('./pages/chef/Waste'));
const ChefInventory   = lazy(() => import('./pages/chef/Inventory'));
const FloorLayout     = lazy(() => import('./layouts/FloorLayout'));
const FloorHome       = lazy(() => import('./pages/floor/Home'));
const FloorQueue      = lazy(() => import('./pages/floor/Queue'));
const FloorReservations = lazy(() => import('./pages/floor/Reservations'));
const HQLayout        = lazy(() => import('./layouts/HQLayout'));
const HQHome          = lazy(() => import('./pages/hq/Home'));
const HQStores        = lazy(() => import('./pages/hq/Stores'));
const HQDecisions     = lazy(() => import('./pages/hq/Decisions'));
const HQFinance       = lazy(() => import('./pages/hq/Finance'));

const PageLoader = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
    <Spin size="large" />
  </div>
);

const AppContent: React.FC = () => {
  const { isDark } = useTheme();

  return (
    <ConfigProvider locale={zhCN} theme={isDark ? darkTheme : lightTheme}>
      <AuthProvider>
        <BrowserRouter>
          <ErrorBoundary>
            <Suspense fallback={PageLoader}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/unauthorized" element={<UnauthorizedPage />} />
                <Route path="/onboarding" element={<OnboardingPage />} />
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
                    <ProtectedRoute requiredRole="admin"><TaxCashflowPage /></ProtectedRoute>
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
                    <ProtectedRoute requiredRole="admin"><StoreManagementPage /></ProtectedRoute>
                  } />
                  <Route path="export-jobs" element={
                    <ProtectedRoute requiredRole="admin"><ExportJobsPage /></ProtectedRoute>
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
                </Route>
                <Route path="*" element={<NotFoundPage />} />

                {/* Role-based views — Store Manager (手机) */}
                <Route path="/sm" element={
                  <ProtectedRoute>
                    <StoreManagerLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<SmHome />} />
                  <Route path="home"      element={<SmHome />} />
                  <Route path="business"  element={<SmBusiness />} />
                  <Route path="decisions" element={<SmDecisions />} />
                  <Route path="alerts"    element={<SmAlerts />} />
                </Route>

                {/* Role-based views — Chef (手机) */}
                <Route path="/chef" element={
                  <ProtectedRoute>
                    <ChefLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<ChefHome />} />
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
                  <Route path="queue"        element={<FloorQueue />} />
                  <Route path="reservations" element={<FloorReservations />} />
                </Route>

                {/* Role-based views — HQ (桌面) */}
                <Route path="/hq" element={
                  <ProtectedRoute>
                    <HQLayout />
                  </ProtectedRoute>
                }>
                  <Route index element={<HQHome />} />
                  <Route path="stores"    element={<HQStores />} />
                  <Route path="decisions" element={<HQDecisions />} />
                  <Route path="finance"   element={<HQFinance />} />
                </Route>
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
