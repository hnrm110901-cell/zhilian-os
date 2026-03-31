/**
 * OpsAdminLayout — 商户管理运维后台（Level 2）
 *
 * 四级管理体系第二级：数据接入 · 配置中台 · 设备运维 · AI运维 · 数据治理 · 外部集成
 * 用户：运维管理员（商户实施/运维团队）
 * 路由：/ops
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
  DatabaseOutlined,
  CloudServerOutlined,
  ExperimentOutlined,
  RobotOutlined,
  SearchOutlined,
  ShopOutlined,
  SafetyOutlined,
  ApiOutlined,
  UploadOutlined,
  FunnelPlotOutlined,
  ToolOutlined,
  CopyOutlined,
  LockOutlined,
  ClusterOutlined,
  DesktopOutlined,
  SoundOutlined,
  NotificationOutlined,
  LinkOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  ShoppingOutlined,
  VideoCameraOutlined,
  StarOutlined,
  AccountBookOutlined,
  BankOutlined,
  ImportOutlined,
  ExportOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from './OpsAdminLayout.module.css';

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

// ── 菜单结构（6 分区，26 项） ─────────────────────────────────
const NAV_SECTIONS: NavSection[] = [
  {
    sectionKey: 'data-ingest',
    title: '数据接入',
    icon: <DatabaseOutlined />,
    items: [
      { key: 'home',         path: '/ops',              label: '控制台',     icon: <DashboardOutlined /> },
      { key: 'pos',          path: '/ops/pos',          label: 'POS对接',    icon: <ApiOutlined /> },
      { key: 'menu-import',  path: '/ops/menu-import',  label: '菜单导入',   icon: <UploadOutlined /> },
      { key: 'bom-import',   path: '/ops/bom-import',   label: 'BOM导入',    icon: <UploadOutlined /> },
      { key: 'channels',     path: '/ops/channels',     label: '渠道数据',   icon: <FunnelPlotOutlined /> },
    ],
  },
  {
    sectionKey: 'config-hub',
    title: '配置中台',
    icon: <SettingOutlined />,
    items: [
      { key: 'rules',              path: '/ops/rules',              label: '业务规则',   icon: <ToolOutlined /> },
      { key: 'store-tpl',          path: '/ops/store-tpl',          label: '门店模板',   icon: <CopyOutlined /> },
      { key: 'agent-train',        path: '/ops/agent-train',        label: 'Agent训练',  icon: <ExperimentOutlined /> },
      { key: 'isolation',          path: '/ops/isolation',          label: '数据隔离',   icon: <LockOutlined /> },
      { key: 'config-management',  path: '/ops/config-management',  label: '运维配置',   icon: <SettingOutlined />, badge: 'new' as const },
    ],
  },
  {
    sectionKey: 'device-ops',
    title: '设备运维',
    icon: <CloudServerOutlined />,
    items: [
      { key: 'edge-nodes',   path: '/ops/edge-nodes',   label: '边缘节点',   icon: <ClusterOutlined /> },
      { key: 'iot',          path: '/ops/iot',           label: 'IoT设备',    icon: <DesktopOutlined /> },
      { key: 'voice',        path: '/ops/voice',         label: '语音终端',   icon: <SoundOutlined /> },
    ],
  },
  {
    sectionKey: 'ai-ops',
    title: 'AI运维',
    icon: <RobotOutlined />,
    items: [
      { key: 'llm-config',     path: '/ops/llm-config',     label: 'LLM配置',    icon: <SettingOutlined /> },
      { key: 'model-monitor',  path: '/ops/model-monitor',  label: '模型监控',    icon: <BarChartOutlined /> },
      { key: 'push',           path: '/ops/push',           label: '推送策略',    icon: <NotificationOutlined /> },
    ],
  },
  {
    sectionKey: 'data-gov',
    title: '数据治理',
    icon: <SafetyOutlined />,
    items: [
      { key: 'data-sovereignty', path: '/ops/data-sovereignty', label: '数据主权', icon: <SafetyOutlined /> },
      { key: 'data-import',      path: '/ops/data-import',      label: '数据导入', icon: <ImportOutlined /> },
      { key: 'data-export',      path: '/ops/data-export',      label: '数据导出', icon: <ExportOutlined /> },
    ],
  },
  {
    sectionKey: 'external',
    title: '外部集成',
    icon: <LinkOutlined />,
    items: [
      { key: 'integrations',   path: '/ops/integrations',   label: '集成中心',   icon: <AppstoreOutlined /> },
      { key: 'e-invoices',     path: '/ops/e-invoices',     label: '电子发票',   icon: <FileTextOutlined /> },
      { key: 'eleme',          path: '/ops/eleme',          label: '饿了么',     icon: <ShoppingOutlined /> },
      { key: 'douyin',         path: '/ops/douyin',         label: '抖音',       icon: <VideoCameraOutlined /> },
      { key: 'dianping',       path: '/ops/dianping',       label: '大众点评',   icon: <StarOutlined /> },
      { key: 'supplier-b2b',   path: '/ops/supplier-b2b',   label: '供应商B2B',  icon: <ShopOutlined /> },
      { key: 'payment-recon',  path: '/ops/payment-recon',  label: '支付对账',   icon: <AccountBookOutlined /> },
      { key: 'bank-recon',     path: '/ops/bank-recon',     label: '银行对账',   icon: <BankOutlined /> },
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
const OpsAdminLayout: React.FC = () => {
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
    path === '/ops'
      ? location.pathname === '/ops'
      : location.pathname.startsWith(path);

  return (
    <div className={styles.shell}>
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        <div className={styles.logoArea} onClick={() => navigate('/ops')}>
          <div className={styles.logoMark}>
            <img src="/logo-icon.svg" alt="屯象" className={styles.logoImg} />
          </div>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>商户管理运维</span>
              <span className={styles.logoSub}>Merchant Ops</span>
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
                        end={item.path === '/ops'}
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
                <div className={styles.userRole}>运维管理员</div>
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

export default OpsAdminLayout;
