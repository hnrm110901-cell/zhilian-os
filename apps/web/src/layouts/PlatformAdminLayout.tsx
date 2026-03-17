/**
 * PlatformAdminLayout — 屯象OS 企业管理后台
 *
 * TOAST-style: 扁平分区导航 + 侧栏搜索 + 清晰视觉层级
 * 访问入口: admin.zlsjos.cn
 * 权限: admin 角色
 */
import React, { useState, useMemo } from 'react';
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
  HddOutlined,
  UserOutlined,
  TeamOutlined,
  AppstoreOutlined,
  KeyOutlined,
  SearchOutlined,
  FileTextOutlined,
  TransactionOutlined,
  BankOutlined,
  AccountBookOutlined,
  ReconciliationOutlined,
  ShoppingCartOutlined,
  StarOutlined,
  SolutionOutlined,
  MedicineBoxOutlined,
  ThunderboltOutlined,
  FundProjectionScreenOutlined,
  NodeIndexOutlined,
  LinkOutlined,
  RadarChartOutlined,
  AlertOutlined,
  CheckCircleOutlined,
  ControlOutlined,
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

// ── 菜单结构（9 分区，34 项） ─────────────────────────────────
const NAV_SECTIONS: NavSection[] = [
  {
    sectionKey: 'workspace',
    title: '工作台',
    icon: <HomeOutlined />,
    items: [
      { key: 'home',      path: '/platform',           label: '控制台',   icon: <DashboardOutlined /> },
      { key: 'analytics', path: '/platform/analytics', label: '效能分析', icon: <BarChartOutlined /> },
    ],
  },
  {
    sectionKey: 'merchants',
    title: '商户',
    icon: <ShopOutlined />,
    items: [
      { key: 'merchants',     path: '/platform/merchants',     label: '商户管理', icon: <ShopOutlined /> },
      { key: 'stores',        path: '/platform/stores',        label: '门店管理', icon: <AppstoreOutlined /> },
      { key: 'integrations',  path: '/platform/integrations',  label: '接入配置', icon: <ApiOutlined /> },
      { key: 'open-platform', path: '/platform/open-platform', label: '开放平台', icon: <GlobalOutlined /> },
    ],
  },
  {
    sectionKey: 'users',
    title: '用户',
    icon: <TeamOutlined />,
    items: [
      { key: 'users', path: '/platform/users', label: '用户管理', icon: <UserOutlined /> },
      { key: 'roles', path: '/platform/roles', label: '角色权限', icon: <KeyOutlined /> },
    ],
  },
  {
    sectionKey: 'finance',
    title: '财务对账',
    icon: <AccountBookOutlined />,
    items: [
      { key: 'e-invoices',        path: '/platform/e-invoices',        label: '电子发票',   icon: <FileTextOutlined /> },
      { key: 'payment-recon',     path: '/platform/payment-recon',     label: '支付对账',   icon: <TransactionOutlined /> },
      { key: 'bank-recon',        path: '/platform/bank-recon',        label: '银行对账',   icon: <BankOutlined /> },
      { key: 'tri-recon',         path: '/platform/tri-recon',         label: '三角对账',   icon: <ReconciliationOutlined /> },
      { key: 'financial-closing', path: '/platform/financial-closing', label: '日清日结',   icon: <AccountBookOutlined /> },
      { key: 'omni-channel',     path: '/platform/omni-channel',      label: '全渠道营收', icon: <FundProjectionScreenOutlined /> },
    ],
  },
  {
    sectionKey: 'channels',
    title: '渠道运营',
    icon: <RadarChartOutlined />,
    items: [
      { key: 'eleme',          path: '/platform/eleme',          label: '饿了么',   icon: <ShoppingCartOutlined /> },
      { key: 'douyin',         path: '/platform/douyin',         label: '抖音团购', icon: <ThunderboltOutlined /> },
      { key: 'dianping',       path: '/platform/dianping',       label: '点评监控', icon: <StarOutlined /> },
      { key: 'review-actions', path: '/platform/review-actions', label: '评论行动', icon: <AlertOutlined /> },
    ],
  },
  {
    sectionKey: 'supply-chain',
    title: '供应链',
    icon: <NodeIndexOutlined />,
    items: [
      { key: 'supplier-b2b',      path: '/platform/supplier-b2b',      label: '供应商B2B', icon: <LinkOutlined /> },
      { key: 'supplier-intel',     path: '/platform/supplier-intel',    label: '供应商智能', icon: <ExperimentOutlined /> },
      { key: 'auto-procurement',   path: '/platform/auto-procurement',  label: '智能采购',   icon: <ShoppingCartOutlined /> },
      { key: 'food-safety',       path: '/platform/food-safety',       label: '食品安全',   icon: <SafetyOutlined /> },
      { key: 'health-certs',      path: '/platform/health-certs',      label: '健康证管理', icon: <MedicineBoxOutlined /> },
    ],
  },
  {
    sectionKey: 'ai',
    title: 'AI 引擎',
    icon: <RobotOutlined />,
    items: [
      { key: 'agents',            path: '/platform/agents',            label: 'Agent 监控',   icon: <RobotOutlined /> },
      { key: 'ontology',          path: '/platform/ontology',          label: '本体图谱',     icon: <ExperimentOutlined /> },
      { key: 'data-sovereignty',  path: '/platform/data-sovereignty',  label: '数据主权',     icon: <SafetyOutlined /> },
      { key: 'compliance-engine', path: '/platform/compliance-engine', label: '合规引擎',     icon: <CheckCircleOutlined /> },
      { key: 'command-center',    path: '/platform/command-center',    label: '指挥中心',     icon: <ControlOutlined />, badge: 'new' },
    ],
  },
  {
    sectionKey: 'ops',
    title: '平台运维',
    icon: <CloudServerOutlined />,
    items: [
      { key: 'monitoring',      path: '/platform/monitoring',      label: '系统监控', icon: <CloudServerOutlined /> },
      { key: 'feature-flags',   path: '/platform/feature-flags',   label: '灰度发布', icon: <BranchesOutlined />, badge: 'new' },
      { key: 'audit-log',       path: '/platform/audit-log',       label: '审计日志', icon: <AuditOutlined /> },
      { key: 'backup',          path: '/platform/backup',          label: '备份管理', icon: <DatabaseOutlined /> },
      { key: 'edge-nodes',      path: '/platform/edge-nodes',      label: '边缘节点', icon: <HddOutlined />, badge: 'new' },
      { key: 'integration-hub', path: '/platform/integration-hub', label: '集成中心', icon: <SolutionOutlined /> },
    ],
  },
  {
    sectionKey: 'settings',
    title: '设置',
    icon: <SettingOutlined />,
    items: [
      { key: 'settings', path: '/platform/settings', label: '系统设置', icon: <SettingOutlined /> },
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
        <span className={styles.breadcrumbItem}>商户</span>
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

  // 搜索过滤菜单项
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
      {/* ── 侧栏 ── */}
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        {/* Logo */}
        <div className={styles.logoArea} onClick={() => navigate('/platform')}>
          <div className={styles.logoMark}>
            <img src="/logo-icon.svg" alt="屯象" className={styles.logoImg} />
          </div>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>屯象OS</span>
              <span className={styles.logoSub}>Enterprise Admin</span>
            </div>
          )}
        </div>

        {/* 搜索 */}
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

        {/* 导航 */}
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

        {/* 底部用户 */}
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

      {/* ── 主区域 ── */}
      <div className={styles.main}>
        {/* 顶栏 */}
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

        {/* 内容 */}
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default PlatformAdminLayout;
