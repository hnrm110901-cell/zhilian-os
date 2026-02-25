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
                    <ProtectedRoute requiredRole="admin"><RecommendationsPage /></ProtectedRoute>
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
                </Route>
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
