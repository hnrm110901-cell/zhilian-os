/**
 * 个人中心 — 店长移动端
 * 个人信息、菜单导航、退出登录
 */
import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import styles from './Profile.module.css';

const MENU_ITEMS = [
  { label: '门店切换',    icon: '🏪', action: 'switch-store' },
  { label: '通知设置',    icon: '🔔', action: 'notification-settings' },
  { label: '操作日志',    icon: '📝', action: 'activity-log' },
  { label: '帮助与反馈',  icon: '💬', action: 'help' },
  { label: '关于屯象OS', icon: 'ℹ️',  action: 'about' },
];

export default function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const displayName = user?.full_name || user?.username || '店长';
  const initials = displayName[0]?.toUpperCase() ?? 'U';

  return (
    <div className={styles.container}>
      {/* 用户信息卡 */}
      <ZCard className={styles.userCard}>
        <div className={styles.userRow}>
          <div className={styles.avatar}>{initials}</div>
          <div className={styles.userInfo}>
            <div className={styles.userName}>{displayName}</div>
            <div className={styles.userRole}>门店管理员</div>
          </div>
          <ZBadge type="success" text="在线" />
        </div>
      </ZCard>

      {/* 菜单列表 */}
      <ZCard className={styles.menuCard}>
        {MENU_ITEMS.map((item, idx) => (
          <div
            key={item.action}
            className={`${styles.menuItem} ${idx < MENU_ITEMS.length - 1 ? styles.menuItemBorder : ''}`}
          >
            <span className={styles.menuIcon}>{item.icon}</span>
            <span className={styles.menuLabel}>{item.label}</span>
            <span className={styles.menuArrow}>›</span>
          </div>
        ))}
      </ZCard>

      {/* 退出登录 */}
      <button className={styles.logoutBtn} onClick={handleLogout}>
        退出登录
      </button>
    </div>
  );
}
