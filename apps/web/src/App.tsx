import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { lightTheme, darkTheme } from './config/theme';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import MainLayout from './layouts/MainLayout';
import NotFoundPage from './pages/NotFoundPage';
import Dashboard from './pages/Dashboard';
import SchedulePage from './pages/SchedulePage';
import OrderPage from './pages/OrderPage';
import InventoryPage from './pages/InventoryPage';
import ServicePage from './pages/ServicePage';
import TrainingPage from './pages/TrainingPage';
import DecisionPage from './pages/DecisionPage';
import ReservationPage from './pages/ReservationPage';
import UserManagementPage from './pages/UserManagementPage';
import EnterpriseIntegrationPage from './pages/EnterpriseIntegrationPage';
import MultiStoreManagement from './pages/MultiStoreManagement';
import SupplyChainManagement from './pages/SupplyChainManagement';
import DataVisualizationScreen from './pages/DataVisualizationScreen';
import MonitoringPage from './pages/MonitoringPage';
import MobileApp from './pages/MobileApp';
import FinanceManagement from './pages/FinanceManagement';
import BackupManagement from './pages/BackupManagement';
import AdvancedAnalytics from './pages/AdvancedAnalytics';
import NotificationCenter from './pages/NotificationCenter';
import AuditLogPage from './pages/AuditLogPage';
import DataImportExportPage from './pages/DataImportExportPage';
import CompetitiveAnalysis from './pages/CompetitiveAnalysis';
import ReportTemplates from './pages/ReportTemplates';
import ForecastPage from './pages/ForecastPage';
import CrossStoreInsights from './pages/CrossStoreInsights';
import HumanInTheLoop from './pages/HumanInTheLoop';
import RecommendationsPage from './pages/RecommendationsPage';
import PrivateDomainPage from './pages/PrivateDomainPage';
import MemberSystemPage from './pages/MemberSystemPage';
import KPIDashboardPage from './pages/KPIDashboardPage';
import Customer360Page from './pages/Customer360Page';
import POSPage from './pages/POSPage';
import QualityManagementPage from './pages/QualityManagementPage';
import CompliancePage from './pages/CompliancePage';
import AIEvolutionPage from './pages/AIEvolutionPage';
import EdgeNodePage from './pages/EdgeNodePage';
import DecisionValidatorPage from './pages/DecisionValidatorPage';
import FederatedLearningPage from './pages/FederatedLearningPage';
import AgentCollaborationPage from './pages/AgentCollaborationPage';
import OpenPlatformPage from './pages/OpenPlatformPage';
import IndustrySolutionsPage from './pages/IndustrySolutionsPage';
import I18nPage from './pages/I18nPage';
import LoginPage from './pages/LoginPage';
import UnauthorizedPage from './pages/UnauthorizedPage';

const AppContent: React.FC = () => {
  const { isDark } = useTheme();

  return (
    <ConfigProvider locale={zhCN} theme={isDark ? darkTheme : lightTheme}>
      <AuthProvider>
        <BrowserRouter>
          <ErrorBoundary>
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
                <ProtectedRoute requiredRole="admin">
                  <DecisionPage />
                </ProtectedRoute>
              } />
              <Route path="reservation" element={<ReservationPage />} />
              <Route path="users" element={
                <ProtectedRoute requiredRole="admin">
                  <UserManagementPage />
                </ProtectedRoute>
              } />
              <Route path="enterprise" element={
                <ProtectedRoute requiredRole="admin">
                  <EnterpriseIntegrationPage />
                </ProtectedRoute>
              } />
              <Route path="multi-store" element={
                <ProtectedRoute requiredRole="admin">
                  <MultiStoreManagement />
                </ProtectedRoute>
              } />
              <Route path="supply-chain" element={
                <ProtectedRoute requiredRole="admin">
                  <SupplyChainManagement />
                </ProtectedRoute>
              } />
              <Route path="data-visualization" element={
                <ProtectedRoute>
                  <DataVisualizationScreen />
                </ProtectedRoute>
              } />
              <Route path="monitoring" element={
                <ProtectedRoute requiredRole="admin">
                  <MonitoringPage />
                </ProtectedRoute>
              } />
              <Route path="finance" element={
                <ProtectedRoute requiredRole="admin">
                  <FinanceManagement />
                </ProtectedRoute>
              } />
              <Route path="backup" element={
                <ProtectedRoute requiredRole="admin">
                  <BackupManagement />
                </ProtectedRoute>
              } />
              <Route path="analytics" element={
                <ProtectedRoute>
                  <AdvancedAnalytics />
                </ProtectedRoute>
              } />
              <Route path="notifications" element={
                <ProtectedRoute>
                  <NotificationCenter />
                </ProtectedRoute>
              } />
              <Route path="audit" element={
                <ProtectedRoute requiredRole="admin">
                  <AuditLogPage />
                </ProtectedRoute>
              } />
              <Route path="data-import-export" element={
                <ProtectedRoute requiredRole="admin">
                  <DataImportExportPage />
                </ProtectedRoute>
              } />
              <Route path="competitive-analysis" element={
                <ProtectedRoute requiredRole="admin">
                  <CompetitiveAnalysis />
                </ProtectedRoute>
              } />
              <Route path="report-templates" element={
                <ProtectedRoute requiredRole="admin">
                  <ReportTemplates />
                </ProtectedRoute>
              } />
              <Route path="forecast" element={
                <ProtectedRoute requiredRole="admin">
                  <ForecastPage />
                </ProtectedRoute>
              } />
              <Route path="cross-store-insights" element={
                <ProtectedRoute requiredRole="admin">
                  <CrossStoreInsights />
                </ProtectedRoute>
              } />
              <Route path="human-in-the-loop" element={
                <ProtectedRoute requiredRole="admin">
                  <HumanInTheLoop />
                </ProtectedRoute>
              } />
              <Route path="recommendations" element={
                <ProtectedRoute requiredRole="admin">
                  <RecommendationsPage />
                </ProtectedRoute>
              } />
              <Route path="private-domain" element={
                <ProtectedRoute requiredRole="admin">
                  <PrivateDomainPage />
                </ProtectedRoute>
              } />
              <Route path="members" element={
                <ProtectedRoute requiredRole="admin">
                  <MemberSystemPage />
                </ProtectedRoute>
              } />
              <Route path="kpi-dashboard" element={
                <ProtectedRoute requiredRole="admin">
                  <KPIDashboardPage />
                </ProtectedRoute>
              } />
              <Route path="customer360" element={
                <ProtectedRoute requiredRole="admin">
                  <Customer360Page />
                </ProtectedRoute>
              } />
              <Route path="pos" element={
                <ProtectedRoute requiredRole="admin">
                  <POSPage />
                </ProtectedRoute>
              } />
              <Route path="quality" element={
                <ProtectedRoute requiredRole="admin">
                  <QualityManagementPage />
                </ProtectedRoute>
              } />
              <Route path="compliance" element={
                <ProtectedRoute requiredRole="admin">
                  <CompliancePage />
                </ProtectedRoute>
              } />
              <Route path="ai-evolution" element={
                <ProtectedRoute requiredRole="admin">
                  <AIEvolutionPage />
                </ProtectedRoute>
              } />
              <Route path="edge-node" element={
                <ProtectedRoute requiredRole="admin">
                  <EdgeNodePage />
                </ProtectedRoute>
              } />
              <Route path="decision-validator" element={
                <ProtectedRoute requiredRole="admin">
                  <DecisionValidatorPage />
                </ProtectedRoute>
              } />
              <Route path="federated-learning" element={
                <ProtectedRoute requiredRole="admin">
                  <FederatedLearningPage />
                </ProtectedRoute>
              } />
              <Route path="agent-collaboration" element={
                <ProtectedRoute requiredRole="admin">
                  <AgentCollaborationPage />
                </ProtectedRoute>
              } />
              <Route path="open-platform" element={
                <ProtectedRoute requiredRole="admin">
                  <OpenPlatformPage />
                </ProtectedRoute>
              } />
              <Route path="industry-solutions" element={
                <ProtectedRoute requiredRole="admin">
                  <IndustrySolutionsPage />
                </ProtectedRoute>
              } />
              <Route path="i18n" element={
                <ProtectedRoute requiredRole="admin">
                  <I18nPage />
                </ProtectedRoute>
              } />
            </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
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
