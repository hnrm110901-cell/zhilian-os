import React from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useSwipe } from '../hooks/useSwipe';
import styles from './StoreManagerLayout.module.css';

const NAV_ITEMS = [
  { to: '/sm',             label: '首页',   icon: '🏠' },
  { to: '/sm/shifts',      label: '班次',   icon: '🕒' },
  { to: '/sm/tasks',       label: '任务',   icon: '✅' },
  { to: '/sm/alerts',      label: '告警',   icon: '🔔' },
  { to: '/sm/business',    label: '业务',   icon: '📊' },
];

export default function StoreManagerLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const currentIndex = NAV_ITEMS.findIndex(
    (item) => item.to !== '/sm' && location.pathname.startsWith(item.to) ||
              item.to === '/sm' && (location.pathname === '/sm' || location.pathname === '/sm/')
  );

  const { onTouchStart, onTouchEnd } = useSwipe({
    onSwipeLeft: () => {
      if (currentIndex < NAV_ITEMS.length - 1) {
        navigate(NAV_ITEMS[currentIndex + 1].to);
      }
    },
    onSwipeRight: () => {
      if (currentIndex > 0) {
        navigate(NAV_ITEMS[currentIndex - 1].to);
      }
    },
  });

  return (
    <div className={styles.shell}>
      <main
        className={styles.main}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
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
