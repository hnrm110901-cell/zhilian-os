/**
 * PlatformAdminLayout — 屯象智能平台（Level 1）
 *
 * 四级管理体系第一级：管产品 · 管智能 · 管商户生命周期
 * 用户：屯象科技内部（产品/研发/测试/客户成功）
 * 路由：/platform
 */
import React, { useState, useMemo } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  BarChartOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BranchesOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  ExperimentOutlined,
  AuditOutlined,
  RobotOutlined,
  GlobalOutlined,
  HomeOutlined,
  SearchOutlined,
  ShopOutlined,
  KeyOutlined,
  SolutionOutlined,
  BookOutlined,
  DeploymentUnitOutlined,
  RocketOutlined,
  FundOutlined,
  SafetyOutlined,
  AlertOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from './PlatformAdminLayout.module.css';

// ── 类型 ──────────────────────────────────────────────────────
interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: React.ReactNode;
  badge?: 'new' | 'beta';
}

interface NavSection {
  sectionKey: string;
  title: string;
  icon: React.ReactNode;
  items: NavItem[];
}

// ── 菜单结构（4 分区，16 项） ─────────────────────────────────
const NAV_SECTIONS: NavSection[] = [
  {
    sectionKey: 'product',
    title: '产品工程',
    icon: <RocketOutlined />,
    items: [
      { key: 'home',          path: '/platform',               label: '控制台',     icon: <DashboardOutlined /> },
      { key: 'analytics',     path: '/platform/analytics',     label: '效能分析',   icon: <BarChartOutlined /> },
      { key: 'feature-flags', path: '/platform/feature-flags', label: '灰度发布',   icon: <BranchesOutlined /> },
    ],
  },
  {
    sectionKey: 'intelligence',
    title: '智能引擎',
    icon: <RobotOutlined />,
    items: [
      { key: 'agents',          path: '/platform/agents',          label: 'Agent 编排',   icon: <RobotOutlined /> },
      { key: 'ontology',        path: '/platform/ontology',        label: '本体图谱',     icon: <ExperimentOutlined /> },
      { key: 'model-versions',  path: '/platform/model-versions',  label: '模型版本',     icon: <DeploymentUnitOutlined />, badge: 'new' },
      { key: 'prompt-warehouse',path: '/platform/prompt-warehouse',label: '提示词仓库',   icon: <BookOutlined />, badge: 'new' },
      { key: 'cross-learning',  path: '/platform/cross-learning',  label: '全网学习',     icon: <FundOutlined />, badge: 'new' },
    ],
  },
  {
    sectionKey: 'lifecycle',
    title: '商户生命周期',
    icon: <ShopOutlined />,
    items: [
      { key: 'merchants',     path: '/platform/merchants',     label: '商户管理',   icon: <ShopOutlined /> },
      { key: 'module-auth',   path: '/platform/module-auth',   label: '模块授权',   icon: <KeyOutlined />, badge: 'new' },
      { key: 'key-mgmt',      path: '/platform/key-mgmt',      label: '密钥管理',   icon: <SafetyOutlined />, badge: 'new' },
      { key: 'delivery',      path: '/platform/delivery',      label: '实施跟踪',   icon: <SolutionOutlined />, badge: 'new' },
      { key: 'renewal-alert', path: '/platform/renewal-alert', label: '续费预警',   icon: <AlertOutlined />, badge: 'new' },
    ],
  },
  {
    sectionKey: 'ops',
    title: '平台运维',
    icon: <CloudServerOutlined />,
    items: [
      { key: 'monitoring', path: '/platform/monitoring', label: '系统监控', icon: <CloudServerOutlined /> },
      { key: 'audit-log',  path: '/platform/audit-log',  label: '审计日志', icon: <AuditOutlined /> },
      { key: 'backup',     path: '/platform/backup',     label: '备份管理', icon: <DatabaseOutlined /> },
      { key: 'open-platform', path: '/platform/open-platform', label: '开放平台', icon: <GlobalOutlined /> },
      { key: 'users',      path: '/platform/users',      label: '平台用户', icon: <TeamOutlined /> },
      { key: 'settings',   path: '/platform/settings',   label: '系统设置', icon: <SettingOutlined /> },
    ],
  },
];

// ── 面包屑映射 ────────────────────────────────────────────────
const BREADCRUMB_MAP: Record<string, string[]> = {};
NAV_SECTIONS.forEach((sec) => {
  sec.items.forEach((item) => {
    BREADCRUMB_MAP[item.path] = [sec.title, item.label];
  });
});

function getBreadcrumb(pathname: string): React.ReactNode {
  if (pathname.startsWith('/platform/merchants/') && pathname !== '/platform/merchants') {
    return (
      <>
        <span className={styles.breadcrumbItem}>商户生命周期</span>
        <span className={styles.breadcrumbSep}>/</span>
        <span className={styles.breadcrumbItem}>商户管理</span>
        <span className={styles.breadcrumbSep}>/</span>
        <span className={styles.breadcrumbCurrent}>商户详情</span>
      </>
    );
  }

  const crumbs = BREADCRUMB_MAP[pathname];
  if (!crumbs) {
    return <span className={styles.breadcrumbCurrent}>控制台</span>;
  }
  return (
    <>
      <span className={styles.breadcrumbItem}>{crumbs[0]}</span>
      <span className={styles.breadcrumbSep}>/</span>
      <span className={styles.breadcrumbCurrent}>{crumbs[1]}</span>
    </>
  );
}

// ── Layout ────────────────────────────────────────────────────
const PlatformAdminLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState('');

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const filteredSections = useMemo(() => {
    if (!search.trim()) return NAV_SECTIONS;
    const q = search.trim().toLowerCase();
    return NAV_SECTIONS
      .map((sec) => ({
        ...sec,
        items: sec.items.filter(
          (item) => item.label.toLowerCase().includes(q) || item.key.includes(q),
        ),
      }))
      .filter((sec) => sec.items.length > 0);
  }, [search]);

  const isItemActive = (path: string) =>
    path === '/platform'
      ? location.pathname === '/platform'
      : location.pathname.startsWith(path);

  return (
    <div className={styles.shell}>
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        <div className={styles.logoArea} onClick={() => navigate('/platform')}>
          <div className={styles.logoMark}>
            <img src="/logo-icon.svg" alt="屯象" className={styles.logoImg} />
          </div>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>屯象智能平台</span>
              <span className={styles.logoSub}>Platform Engine</span>
            </div>
          )}
        </div>

        {!collapsed && (
          <div className={styles.searchWrap}>
            <SearchOutlined className={styles.searchIcon} />
            <input
              className={styles.searchInput}
              placeholder="搜索菜单..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        )}

        <nav className={styles.nav}>
          {filteredSections.map((sec) => (
            <div key={sec.sectionKey} className={styles.section}>
              {collapsed ? (
                <div
                  className={`${styles.sectionIconOnly} ${
                    sec.items.some((i) => isItemActive(i.path)) ? styles.sectionIconActive : ''
                  }`}
                  title={sec.title}
                >
                  <span className={styles.iconWrap}>{sec.icon}</span>
                </div>
              ) : (
                <>
                  <div className={styles.sectionLabel}>
                    <span className={styles.iconWrap}>{sec.icon}</span>
                    <span>{sec.title}</span>
                  </div>
                  <div className={styles.sectionItems}>
                    {sec.items.map((item) => (
                      <NavLink
                        key={item.key}
                        to={item.path}
                        end={item.path === '/platform'}
                        className={({ isActive }) =>
                          `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                        }
                      >
                        <span className={styles.itemIcon}>{item.icon}</span>
                        <span className={styles.itemLabel}>{item.label}</span>
                        {item.badge && (
                          <span className={`${styles.badge} ${styles[`badge_${item.badge}`]}`}>
                            {item.badge}
                          </span>
                        )}
                      </NavLink>
                    ))}
                  </div>
                </>
              )}
            </div>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          {!collapsed && (
            <div className={styles.userCard}>
              <div className={styles.avatar}>
                {user?.full_name?.[0] || user?.username?.[0] || 'A'}
              </div>
              <div className={styles.userMeta}>
                <div className={styles.userName}>{user?.full_name || user?.username}</div>
                <div className={styles.userRole}>平台管理员</div>
              </div>
              <button className={styles.logoutBtn} onClick={handleLogout} title="退出登录">
                <LogoutOutlined />
              </button>
            </div>
          )}
          {collapsed && (
            <div className={styles.collapsedUser}>
              <div className={styles.avatarSm}>
                {user?.full_name?.[0] || user?.username?.[0] || 'A'}
              </div>
            </div>
          )}
        </div>
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <button
            className={styles.collapseBtn}
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? '展开侧栏' : '收起侧栏'}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
          <div className={styles.breadcrumb}>
            {getBreadcrumb(location.pathname)}
          </div>
          <div className={styles.topbarRight}>
            <span className={styles.envBadge}>PROD</span>
            <span className={styles.versionTag}>v0.1.0</span>
          </div>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default PlatformAdminLayout;
