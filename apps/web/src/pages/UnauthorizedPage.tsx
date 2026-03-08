import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ZButton } from '../design-system/components';
import styles from './NotFoundPage.module.css';

const UnauthorizedPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state || {}) as {
    from?: string;
    requiredRole?: string;
    currentRole?: string;
  };
  const roleMap: Record<string, string> = {
    admin: '管理员',
    store_manager: '店长',
    manager: '经理',
    staff: '员工',
    waiter: '服务员',
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.code}>403</div>
      <div className={styles.title}>抱歉，您没有权限访问此页面。</div>
      {state.from && (
        <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
          页面：{state.from}
          {state.requiredRole ? `，需要角色：${roleMap[state.requiredRole] || state.requiredRole}` : ''}
          {state.currentRole ? `，当前角色：${roleMap[state.currentRole] || state.currentRole}` : ''}
        </div>
      )}
      <ZButton variant="primary" onClick={() => navigate('/')}>返回首页</ZButton>
    </div>
  );
};

export default UnauthorizedPage;
