import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './layouts/MainLayout';
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
import LoginPage from './pages/LoginPage';
import UnauthorizedPage from './pages/UnauthorizedPage';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/unauthorized" element={<UnauthorizedPage />} />
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
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
};

export default App;
