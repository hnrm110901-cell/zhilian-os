/**
 * 员工H5自助端 — 布局组件
 * 底部4个Tab：首页、工资条、考勤、我的
 */
import React from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import styles from './EmployeeLayout.module.css';

const NAV_ITEMS = [
  { to: '/emp',            label: '首页',   icon: '🏠' },
  { to: '/emp/payslip',    label: '工资条', icon: '💰' },
  { to: '/emp/attendance', label: '考勤',   icon: '📅' },
  { to: '/emp/profile',    label: '我的',   icon: '👤' },
];

const EmployeeLayout: React.FC = () => {
  const location = useLocation();

  return (
    <div className={styles.shell}>
      <main className={styles.main}>
        <Outlet />
      </main>
      <nav className={styles.tabBar}>
        {NAV_ITEMS.map(({ to, label, icon }) => {
          const isActive =
            to === '/emp'
              ? location.pathname === '/emp' || location.pathname === '/emp/'
              : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/emp'}
              className={`${styles.tabItem} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.tabIcon}>{icon}</span>
              <span className={styles.tabLabel}>{label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
};

export default EmployeeLayout;
