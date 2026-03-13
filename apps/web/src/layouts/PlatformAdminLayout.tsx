/**
 * PlatformAdminLayout — 屯象OS 企业管理后台专属布局
 *
 * 访问入口: www.admin.zlsjos.cn / admin.zlsjos.cn
 * 权限要求: admin 角色
 * 功能定位: 系统迭代 / 测试 / 灰度 / 商户配置 / 屯象工具管理
 */
import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ShopOutlined,
  ToolOutlined,
  BarChartOutlined,
  ApiOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BranchesOutlined,
  SafetyOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  ExperimentOutlined,
  AuditOutlined,
  RobotOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from './PlatformAdminLayout.module.css';

// ── 侧栏导航结构 ───────────────────────────────────────────────
interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: React.ReactNode;
  badge?: string; // 'new' | 'beta'
}

interface NavGroup {
  groupKey: string;
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    groupKey: 'overview',
    title: '概览',
    items: [
      { key: 'home', path: '/platform', label: '控制台', icon: <DashboardOutlined /> },
      { key: 'analytics', path: '/platform/analytics', label: '平台分析', icon: <BarChartOutlined /> },
    ],
  },
  {
    groupKey: 'merchants',
    title: '商户管理',
    items: [
      { key: 'merchants', path: '/platform/merchants', label: '商户列表', icon: <ShopOutlined /> },
      { key: 'integrations', path: '/platform/integrations', label: 'API 集成配置', icon: <ApiOutlined /> },
      { key: 'open-platform', path: '/platform/open-platform', label: '开放平台', icon: <GlobalOutlined /> },
    ],
  },
  {
    groupKey: 'system',
    title: '系统运维',
    items: [
      { key: 'monitoring', path: '/platform/monitoring', label: '系统监控', icon: <CloudServerOutlined /> },
      { key: 'feature-flags', path: '/platform/feature-flags', label: '灰度 & 特性开关', icon: <BranchesOutlined />, badge: 'new' },
      { key: 'audit-log', path: '/platform/audit-log', label: '审计日志', icon: <AuditOutlined /> },
      { key: 'backup', path: '/platform/backup', label: '备份管理', icon: <DatabaseOutlined /> },
    ],
  },
  {
    groupKey: 'tools',
    title: '屯象工具管理',
    items: [
      { key: 'agents', path: '/platform/agents', label: 'Agent 配置', icon: <RobotOutlined /> },
      { key: 'ontology', path: '/platform/ontology', label: '本体图管理', icon: <ExperimentOutlined /> },
      { key: 'data-sovereignty', path: '/platform/data-sovereignty', label: '数据主权', icon: <SafetyOutlined /> },
    ],
  },
  {
    groupKey: 'config',
    title: '平台配置',
    items: [
      { key: 'settings', path: '/platform/settings', label: '系统设置', icon: <SettingOutlined /> },
    ],
  },
];

// ── Layout 组件 ────────────────────────────────────────────────
const PlatformAdminLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className={styles.shell}>
      {/* ── 侧栏 ── */}
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        {/* Logo */}
        <div className={styles.logo}>
          <span className={styles.logoIcon}>🐘</span>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>屯象OS</span>
              <span className={styles.logoSub}>企业管理后台</span>
            </div>
          )}
        </div>

        {/* 导航 */}
        <nav className={styles.nav}>
          {NAV_GROUPS.map((group) => (
            <div key={group.groupKey} className={styles.navGroup}>
              {!collapsed && (
                <div className={styles.groupTitle}>{group.title}</div>
              )}
              {group.items.map((item) => (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.path === '/platform'}
                  className={({ isActive }) =>
                    `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                  }
                  title={collapsed ? item.label : undefined}
                >
                  <span className={styles.navIcon}>{item.icon}</span>
                  {!collapsed && (
                    <span className={styles.navLabel}>{item.label}</span>
                  )}
                  {!collapsed && item.badge && (
                    <span className={`${styles.badge} ${styles[`badge_${item.badge}`]}`}>
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* 用户信息 */}
        <div className={styles.userArea}>
          {!collapsed && (
            <div className={styles.userInfo}>
              <div className={styles.userAvatar}>
                {user?.full_name?.[0] || user?.username?.[0] || 'A'}
              </div>
              <div className={styles.userMeta}>
                <div className={styles.userName}>{user?.full_name || user?.username}</div>
                <div className={styles.userRole}>平台管理员</div>
              </div>
            </div>
          )}
          <button className={styles.logoutBtn} onClick={handleLogout} title="退出登录">
            <LogoutOutlined />
            {!collapsed && <span>退出</span>}
          </button>
        </div>
      </aside>

      {/* ── 主内容区 ── */}
      <div className={styles.main}>
        {/* 顶栏 */}
        <header className={styles.topbar}>
          <button
            className={styles.collapseBtn}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>

          <div className={styles.breadcrumb}>
            {getBreadcrumb(location.pathname)}
          </div>

          <div className={styles.topbarRight}>
            <span className={styles.envBadge}>PROD</span>
            <span className={styles.version}>v0.1.0</span>
          </div>
        </header>

        {/* 页面内容 */}
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

// ── 面包屑生成 ─────────────────────────────────────────────────
function getBreadcrumb(pathname: string): React.ReactNode {
  const map: Record<string, string> = {
    '/platform': '控制台',
    '/platform/analytics': '平台分析',
    '/platform/merchants': '商户列表',
    '/platform/integrations': 'API 集成配置',
    '/platform/open-platform': '开放平台',
    '/platform/monitoring': '系统监控',
    '/platform/feature-flags': '灰度 & 特性开关',
    '/platform/audit-log': '审计日志',
    '/platform/backup': '备份管理',
    '/platform/agents': 'Agent 配置',
    '/platform/ontology': '本体图管理',
    '/platform/data-sovereignty': '数据主权',
    '/platform/settings': '系统设置',
  };

  const label = map[pathname] || '屯象OS';
  return (
    <span className={styles.breadcrumbText}>
      企业管理后台 <span className={styles.breadcrumbSep}>/</span> {label}
    </span>
  );
}

export default PlatformAdminLayout;
