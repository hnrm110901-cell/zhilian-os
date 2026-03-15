import React, { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import styles from './HQLayout.module.css';

const NAV_ITEMS = [
  { to: '/hq',             label: '总览',   icon: '🏢' },
  { to: '/hq/stores',      label: '门店',   icon: '🏪' },
  { to: '/hq/decisions',   label: '决策',   icon: '🎯' },
  { to: '/hq/finance',     label: '财务',   icon: '💰' },
  { to: '/hq/workforce',   label: '人力',   icon: '👥' },
  { to: '/hq/banquet',     label: '宴会',   icon: '🎊' },
];

const HR_SUB_ITEMS = [
  // 核心
  { to: '/hr-dashboard',        label: '人力仪表盘' },
  { to: '/employee-roster',     label: '员工花名册' },
  { to: '/employee-lifecycle',  label: '入离职管理' },
  { to: '/org-structure',       label: '组织架构' },
  // 薪酬
  { to: '/payroll',             label: '薪酬管理' },
  { to: '/commission',          label: '提成管理' },
  { to: '/reward-penalty',      label: '奖惩管理' },
  { to: '/social-insurance',    label: '社保公积金' },
  { to: '/settlement',          label: '离职结算' },
  { to: '/payslip-management',  label: '工资条管理' },
  // 考勤
  { to: '/leave-management',    label: '假勤管理' },
  { to: '/attendance-report',   label: '考勤报表' },
  { to: '/shift-templates',     label: '班次模板' },
  { to: '/attendance-rules',    label: '考勤规则' },
  // 培训
  { to: '/employee-growth',     label: '成长旅程' },
  { to: '/hr-training',         label: '培训课程' },
  { to: '/training-dashboard',  label: '培训看板' },
  { to: '/mentorship',          label: '师徒管理' },
  // 招聘 & 合同
  { to: '/recruitment',         label: '招聘管理' },
  { to: '/performance-review',  label: '绩效考核' },
  { to: '/contract-management', label: '合同管理' },
  // 合规 & 配置
  { to: '/compliance',          label: '合规看板' },
  { to: '/hr-monthly-report',   label: '月度报表' },
  { to: '/hr-approval',         label: '审批管理' },
  { to: '/business-rules',      label: '业务规则' },
  { to: '/roster-import',       label: '花名册导入' },
  { to: '/im-config',           label: 'IM通讯录同步' },
];

export default function HQLayout() {
  const [hrExpanded, setHrExpanded] = useState(false);

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <img src="/logo-icon.svg" alt="屯象" style={{ width: 28, height: 28 }} />
          <span className={styles.logoText}>屯象OS</span>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ to, label, icon }) => {
            if (to === '/hq/workforce') {
              return (
                <React.Fragment key={to}>
                  <button
                    className={`${styles.navItem} ${hrExpanded ? styles.active : ''}`}
                    onClick={() => setHrExpanded(v => !v)}
                    style={{ width: '100%', border: 'none', background: 'none', cursor: 'pointer', textAlign: 'left' }}
                  >
                    <span className={styles.navIcon}>{icon}</span>
                    <span>{label}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.5 }}>{hrExpanded ? '▼' : '▶'}</span>
                  </button>
                  {hrExpanded && (
                    <div style={{ paddingLeft: 20 }}>
                      {HR_SUB_ITEMS.map(sub => (
                        <NavLink
                          key={sub.to}
                          to={sub.to}
                          className={({ isActive }) =>
                            `${styles.navItem} ${isActive ? styles.active : ''}`
                          }
                          style={{ fontSize: 13, padding: '6px 12px' }}
                        >
                          <span>{sub.label}</span>
                        </NavLink>
                      ))}
                    </div>
                  )}
                </React.Fragment>
              );
            }
            return (
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
            );
          })}
        </nav>
        <div className={styles.sidebarFooter}>总部视图</div>
      </aside>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
