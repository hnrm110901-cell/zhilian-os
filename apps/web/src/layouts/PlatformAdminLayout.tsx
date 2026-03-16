/**
 * PlatformAdminLayout — 屯象OS 企业管理后台专属布局
 *
 * 访问入口: www.admin.zlsjos.cn / admin.zlsjos.cn
 * 权限要求: admin 角色
 * 功能定位: 系统迭代 / 测试 / 灰度 / 商户配置 / 屯象工具管理
 *
 * 导航结构: 二级 Accordion 折叠菜单
 *   - 点击一级分组 → 展开/收起子菜单
 *   - 折叠侧边栏 → 只显示分组图标（native tooltip）
 *   - 当前路由命中的分组自动展开
 */
import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ShopOutlined,
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
  HomeOutlined,
  DownOutlined,
  HddOutlined,
  WifiOutlined,
  UserOutlined,
  TeamOutlined,
  AppstoreOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from './PlatformAdminLayout.module.css';

// ── 导航类型 ───────────────────────────────────────────────
interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: React.ReactNode;
  badge?: string;
}

interface NavGroup {
  groupKey: string;
  title: string;
  groupIcon: React.ReactNode;
  items: NavItem[];
}

// ── 导航结构（6 分组 18 项） ───────────────────────────────
const NAV_GROUPS: NavGroup[] = [
  {
    groupKey: 'overview',
    title: '平台概览',
    groupIcon: <HomeOutlined />,
    items: [
      { key: 'home',      path: '/platform',           label: '实时控制台', icon: <DashboardOutlined /> },
      { key: 'analytics', path: '/platform/analytics', label: '效能分析',   icon: <BarChartOutlined /> },
    ],
  },
  {
    groupKey: 'merchants',
    title: '商户运营',
    groupIcon: <ShopOutlined />,
    items: [
      { key: 'merchants',     path: '/platform/merchants',     label: '商户管理', icon: <ShopOutlined /> },
      { key: 'stores',        path: '/platform/stores',        label: '门店管理', icon: <AppstoreOutlined /> },
      { key: 'integrations',  path: '/platform/integrations',  label: '接入配置', icon: <ApiOutlined /> },
      { key: 'edge-nodes',    path: '/platform/edge-nodes',    label: '边缘节点', icon: <HddOutlined />, badge: 'new' },
      { key: 'open-platform', path: '/platform/open-platform', label: '开放平台', icon: <GlobalOutlined /> },
    ],
  },
  {
    groupKey: 'users',
    title: '用户权限',
    groupIcon: <TeamOutlined />,
    items: [
      { key: 'users', path: '/platform/users', label: '用户管理', icon: <UserOutlined /> },
      { key: 'roles', path: '/platform/roles', label: '角色权限', icon: <KeyOutlined /> },
    ],
  },
  {
    groupKey: 'ai',
    title: 'AI 引擎',
    groupIcon: <RobotOutlined />,
    items: [
      { key: 'agents',           path: '/platform/agents',           label: 'Agent 监控', icon: <RobotOutlined /> },
      { key: 'ontology',         path: '/platform/ontology',         label: '本体图管理', icon: <ExperimentOutlined /> },
      { key: 'data-sovereignty', path: '/platform/data-sovereignty', label: '数据主权',   icon: <SafetyOutlined /> },
    ],
  },
  {
    groupKey: 'system',
    title: '平台运维',
    groupIcon: <CloudServerOutlined />,
    items: [
      { key: 'monitoring',    path: '/platform/monitoring',    label: '系统监控', icon: <CloudServerOutlined /> },
      { key: 'feature-flags', path: '/platform/feature-flags', label: '灰度发布', icon: <BranchesOutlined />, badge: 'new' },
      { key: 'audit-log',     path: '/platform/audit-log',     label: '审计日志', icon: <AuditOutlined /> },
      { key: 'backup',        path: '/platform/backup',        label: '备份管理', icon: <DatabaseOutlined /> },
    ],
  },
  {
    groupKey: 'integrations-ext',
    title: '外部集成',
    groupIcon: <ApiOutlined />,
    items: [
      { key: 'e-invoices',    path: '/platform/e-invoices',    label: '电子发票',   icon: <BarChartOutlined /> },
      { key: 'eleme',         path: '/platform/eleme',         label: '饿了么',     icon: <ShopOutlined /> },
      { key: 'payment-recon', path: '/platform/payment-recon', label: '支付对账',   icon: <SafetyOutlined /> },
      { key: 'douyin',        path: '/platform/douyin',        label: '抖音团购',   icon: <AppstoreOutlined /> },
      { key: 'food-safety',   path: '/platform/food-safety',   label: '食品安全',   icon: <SafetyOutlined /> },
      { key: 'health-certs',  path: '/platform/health-certs',  label: '健康证',     icon: <UserOutlined /> },
      { key: 'supplier-b2b', path: '/platform/supplier-b2b', label: '供应商B2B',  icon: <GlobalOutlined /> },
      { key: 'dianping',     path: '/platform/dianping',     label: '点评监控',   icon: <BarChartOutlined /> },
      { key: 'bank-recon',   path: '/platform/bank-recon',   label: '银行对账',   icon: <DatabaseOutlined /> },
      { key: 'integration-hub', path: '/platform/integration-hub', label: '集成中心', icon: <WifiOutlined /> },
      { key: 'omni-channel',    path: '/platform/omni-channel',    label: '全渠道营收', icon: <BarChartOutlined /> },
      { key: 'tri-recon',       path: '/platform/tri-recon',       label: '三角对账',   icon: <SafetyOutlined /> },
      { key: 'supplier-intel',  path: '/platform/supplier-intel',  label: '供应商智能', icon: <ExperimentOutlined /> },
      { key: 'review-actions',  path: '/platform/review-actions',  label: '评论行动',   icon: <RobotOutlined /> },
      { key: 'compliance-engine', path: '/platform/compliance-engine', label: '合规引擎', icon: <SafetyOutlined /> },
      { key: 'auto-procurement',  path: '/platform/auto-procurement',  label: '智能采购', icon: <RobotOutlined /> },
      { key: 'financial-closing', path: '/platform/financial-closing', label: '日清日结', icon: <DatabaseOutlined /> },
      { key: 'command-center',    path: '/platform/command-center',    label: '指挥中心', icon: <DashboardOutlined />, badge: 'new' },
    ],
  },
  {
    groupKey: 'config',
    title: '系统配置',
    groupIcon: <SettingOutlined />,
    items: [
      { key: 'settings', path: '/platform/settings', label: '系统设置', icon: <SettingOutlined /> },
    ],
  },
];

// ── 根据路由初始化展开分组 ─────────────────────────────────
function getInitialOpenGroups(pathname: string): Set<string> {
  const open = new Set<string>(['overview']);
  NAV_GROUPS.forEach((group) => {
    if (
      group.items.some((item) =>
        item.path === '/platform'
          ? pathname === '/platform'
          : pathname.startsWith(item.path),
      )
    ) {
      open.add(group.groupKey);
    }
  });
  return open;
}

// ── Layout 组件 ────────────────────────────────────────────
const PlatformAdminLayout: React.FC = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => getInitialOpenGroups(location.pathname),
  );
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const toggleGroup = (groupKey: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) { next.delete(groupKey); } else { next.add(groupKey); }
      return next;
    });
  };

  const groupHasActive = (group: NavGroup): boolean =>
    group.items.some((item) =>
      item.path === '/platform'
        ? location.pathname === '/platform'
        : location.pathname.startsWith(item.path),
    );

  return (
    <div className={styles.shell}>
      {/* ── 侧栏 ── */}
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        {/* Logo */}
        <div className={styles.logo}>
          <img src="/logo-icon.svg" alt="屯象" style={{ width: 28, height: 28 }} />
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>屯象OS</span>
              <span className={styles.logoSub}>企业管理后台</span>
            </div>
          )}
        </div>

        {/* 二级 Accordion 导航 */}
        <nav className={styles.nav}>
          {NAV_GROUPS.map((group) => {
            const isOpen = !collapsed && openGroups.has(group.groupKey);
            const hasActive = groupHasActive(group);

            return (
              <div key={group.groupKey} className={styles.navGroup}>
                {collapsed ? (
                  /* 折叠态：仅显示图标 + native tooltip */
                  <div
                    className={`${styles.groupIconOnly} ${hasActive ? styles.groupIconActive : ''}`}
                    title={group.title}
                  >
                    <span className={styles.navIcon}>{group.groupIcon}</span>
                  </div>
                ) : (
                  /* 展开态：可点击的分组标题 */
                  <button
                    className={`${styles.groupHeader} ${
                      hasActive && !isOpen ? styles.groupHeaderActive : ''
                    }`}
                    onClick={() => toggleGroup(group.groupKey)}
                  >
                    <span className={styles.navIcon}>{group.groupIcon}</span>
                    <span className={styles.groupTitle}>{group.title}</span>
                    <DownOutlined
                      className={`${styles.groupArrow} ${isOpen ? styles.groupArrowOpen : ''}`}
                    />
                  </button>
                )}

                {/* 子菜单（CSS max-height 动画） */}
                <div className={`${styles.subMenu} ${isOpen ? styles.subMenuOpen : ''}`}>
                  {group.items.map((item) => (
                    <NavLink
                      key={item.key}
                      to={item.path}
                      end={item.path === '/platform'}
                      className={({ isActive }) =>
                        `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                      }
                    >
                      <span className={styles.navIcon}>{item.icon}</span>
                      <span className={styles.navLabel}>{item.label}</span>
                      {item.badge && (
                        <span
                          className={`${styles.badge} ${
                            item.badge === 'new' ? styles.badge_new : styles.badge_beta
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* 用户信息区 */}
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

        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

// ── 面包屑 ─────────────────────────────────────────────────
function getBreadcrumb(pathname: string): React.ReactNode {
  // 商户详情页动态路由
  if (pathname.startsWith('/platform/merchants/') && pathname !== '/platform/merchants') {
    return (
      <span className={styles.breadcrumbText}>
        企业管理后台 <span className={styles.breadcrumbSep}>/</span> 商户管理 <span className={styles.breadcrumbSep}>/</span> 商户详情
      </span>
    );
  }

  const map: Record<string, string> = {
    '/platform':                  '实时控制台',
    '/platform/analytics':        '效能分析',
    '/platform/merchants':        '商户管理',
    '/platform/stores':           '门店管理',
    '/platform/integrations':     '接入配置',
    '/platform/edge-nodes':       '边缘节点管理',
    '/platform/open-platform':    '开放平台',
    '/platform/users':            '用户管理',
    '/platform/roles':            '角色权限',
    '/platform/monitoring':       '系统监控',
    '/platform/feature-flags':    '灰度发布',
    '/platform/audit-log':        '审计日志',
    '/platform/backup':           '备份管理',
    '/platform/agents':           'Agent 监控',
    '/platform/ontology':         '本体图管理',
    '/platform/data-sovereignty': '数据主权',
    '/platform/settings':         '系统设置',
  };
  const label = map[pathname] || '屯象OS';
  return (
    <span className={styles.breadcrumbText}>
      企业管理后台 <span className={styles.breadcrumbSep}>/</span> {label}
    </span>
  );
}

export default PlatformAdminLayout;
