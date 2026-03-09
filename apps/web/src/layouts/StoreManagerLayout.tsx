import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import styles from './StoreManagerLayout.module.css';

const NAV_ITEMS = [
  { to: '/sm',             label: '首页',   icon: '🏠' },
  { to: '/sm/shifts',      label: '班次',   icon: '🕒' },
  { to: '/sm/tasks',       label: '任务',   icon: '✅' },
  { to: '/sm/workforce',   label: '人力',   icon: '👥' },
  { to: '/sm/alerts',      label: '告警',   icon: '🔔' },
];

export default function StoreManagerLayout() {
  return (
    <div className={styles.shell}>
      <main className={styles.main}>
        <Outlet />
      </main>
      <nav className={styles.tabBar}>
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/sm'}
            className={({ isActive }) =>
              `${styles.tabItem} ${isActive ? styles.active : ''}`
            }
          >
            <span className={styles.tabIcon}>{icon}</span>
            <span className={styles.tabLabel}>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
