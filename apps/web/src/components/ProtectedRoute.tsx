import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'manager' | 'staff' | 'store_manager';
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh'
      }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    // 保存当前路径，登录后重定向回来
    const currentPath = window.location.pathname;
    return <Navigate to={`/login?redirect=${encodeURIComponent(currentPath)}`} replace />;
  }

  if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin') {
    return (
      <Navigate
        to="/unauthorized"
        replace
        state={{
          from: location.pathname,
          requiredRole,
          currentRole: user?.role,
        }}
      />
    );
  }

  return <>{children}</>;
};

export default ProtectedRoute;
