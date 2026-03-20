import React from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useSwipe } from '../hooks/useSwipe';
import styles from './StoreManagerLayout.module.css';

const NAV_ITEMS = [
  { to: '/sm',                    label: '简报',   icon: '📋' },
  { to: '/sm/daily-flow',          label: '流程',   icon: '⏱️' },
  { to: '/sm/daily-dashboard',    label: '日清',   icon: '📊' },
  { to: '/sm/patrol',             label: '巡店',   icon: '🔍' },
  { to: '/sm/hr',                 label: '人力',   icon: '👥' },
  { to: '/sm/decisions',          label: 'AI决策', icon: '🤖' },
  { to: '/sm/members',            label: '识客',   icon: '👤' },
  { to: '/sm/marketing-tasks',    label: '营销',   icon: '📣' },
  { to: '/sm/profile',            label: '我的',   icon: '🙍' },
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
      {/* Voice FAB — AI语音助手 */}
      <button className={styles.voiceFab} title="AI语音助手">
        🎙️
      </button>
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
