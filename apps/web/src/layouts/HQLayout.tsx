import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import styles from './HQLayout.module.css';

const NAV_ITEMS = [
  { to: '/hq',             label: '总览',   icon: '🏢' },
  { to: '/hq/stores',      label: '门店',   icon: '🏪' },
  { to: '/hq/decisions',   label: '决策',   icon: '🎯' },
  { to: '/hq/finance',     label: '财务',   icon: '💰' },
  { to: '/hq/workforce',   label: '人力',   icon: '👥' },
];

export default function HQLayout() {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <span className={styles.logoIcon}>⚡</span>
          <span className={styles.logoText}>智链OS</span>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/hq'}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.navIcon}>{icon}</span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={styles.sidebarFooter}>总部视图</div>
      </aside>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
