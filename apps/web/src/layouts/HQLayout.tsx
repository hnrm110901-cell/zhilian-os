import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import styles from './HQLayout.module.css';

const NAV_ITEMS = [
  { to: '/hq',             label: '总览',   icon: '🏢' },
  { to: '/hq/stores',      label: '门店',   icon: '🏪' },
  { to: '/hq/decisions',   label: '决策',   icon: '🎯' },
  { to: '/hq/finance',     label: '财务',   icon: '💰' },
  { to: '/hq/workforce',   label: '人力成本', icon: '👥' },
  { to: '/hq/hr',                  label: 'HR智能',  icon: '🧠' },
  { to: '/hq/hr/talent-pipeline',  label: '人才梯队', icon: '🌱' },
  { to: '/hq/hr/lifecycle',  label: '生命周期', icon: '🔄' },
  { to: '/hq/hr/approvals',  label: '审批中心', icon: '✅' },
  { to: '/hq/hr/attendance',  label: '考勤', icon: '⏰' },
  { to: '/hq/banquet',     label: '宴会',    icon: '🎊' },
];

export default function HQLayout() {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <img src="/logo-icon.svg" alt="屯象" style={{ width: 28, height: 28 }} />
          <span className={styles.logoText}>屯象OS</span>
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
