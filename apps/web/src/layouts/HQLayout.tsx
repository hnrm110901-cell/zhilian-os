/**
 * HQLayout — 商户经营决策中心（Level 3）
 *
 * 四级管理体系第三级：营收增长 · 成本管控 · 品质合规 · 财务结算 · 经营洞察
 * 用户：总部管理员（品牌老板 / 运营总监 / 财务总监）
 * 路由：/hq
 */
import React, { useState, useMemo } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ShopOutlined,
  CoffeeOutlined,
  FunnelPlotOutlined,
  TeamOutlined,
  DollarOutlined,
  DatabaseOutlined,
  ShoppingCartOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  UsergroupAddOutlined,
  MedicineBoxOutlined,
  StarOutlined,
  ReadOutlined,
  AuditOutlined,
  PieChartOutlined,
  ReconciliationOutlined,
  WarningOutlined,
  MoneyCollectOutlined,
  FundOutlined,
  AimOutlined,
  RadarChartOutlined,
  LineChartOutlined,
  FileSearchOutlined,
  CrownOutlined,
  RiseOutlined,
  FallOutlined,
  SafetyCertificateOutlined,
  AccountBookOutlined,
  BulbOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SearchOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import styles from './HQLayout.module.css';

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

// ── 菜单结构（5 决策域，25 项） ─────────────────────────────────
const NAV_SECTIONS: NavSection[] = [
  {
    sectionKey: 'revenue',
    title: '营收增长',
    icon: <RiseOutlined />,
    items: [
      { key: 'overview',  path: '/hq',             label: '经营总览',   icon: <DashboardOutlined /> },
      { key: 'stores',    path: '/hq/stores',      label: '门店管理',   icon: <ShopOutlined /> },
      { key: 'dishes',    path: '/hq/dishes',      label: '菜品分析',   icon: <CoffeeOutlined /> },
      { key: 'channels',  path: '/hq/channels',    label: '渠道利润',   icon: <FunnelPlotOutlined /> },
      { key: 'members',   path: '/hq/members',     label: '会员营销',   icon: <TeamOutlined /> },
      { key: 'pricing',   path: '/hq/pricing',     label: '动态定价',   icon: <DollarOutlined />, badge: 'new' },
    ],
  },
  {
    sectionKey: 'cost',
    title: '成本管控',
    icon: <FallOutlined />,
    items: [
      { key: 'inventory', path: '/hq/inventory',   label: '库存管理',   icon: <DatabaseOutlined /> },
      { key: 'supply',    path: '/hq/supply',      label: '采购管理',   icon: <ShoppingCartOutlined /> },
      { key: 'waste',     path: '/hq/waste',       label: '损耗分析',   icon: <ExperimentOutlined /> },
      { key: 'bom',       path: '/hq/bom',         label: 'BOM管理',    icon: <ApartmentOutlined /> },
      { key: 'workforce', path: '/hq/workforce',   label: '人力预算',   icon: <UsergroupAddOutlined /> },
    ],
  },
  {
    sectionKey: 'quality',
    title: '品质合规',
    icon: <SafetyCertificateOutlined />,
    items: [
      { key: 'food-safety', path: '/hq/food-safety', label: '食品安全', icon: <MedicineBoxOutlined /> },
      { key: 'quality',     path: '/hq/quality',     label: '服务质量', icon: <StarOutlined /> },
      { key: 'training',    path: '/hq/training',    label: '培训管理', icon: <ReadOutlined /> },
      { key: 'compliance',  path: '/hq/compliance',  label: '合规看板', icon: <AuditOutlined /> },
    ],
  },
  {
    sectionKey: 'finance',
    title: '财务结算',
    icon: <AccountBookOutlined />,
    items: [
      { key: 'finance',    path: '/hq/finance',     label: '财务总览',   icon: <PieChartOutlined /> },
      { key: 'recon',      path: '/hq/recon',       label: '对账中心',   icon: <ReconciliationOutlined /> },
      { key: 'settlement', path: '/hq/settlement',  label: '结算风险',   icon: <WarningOutlined /> },
      { key: 'tax',        path: '/hq/tax',         label: '税务现金流', icon: <MoneyCollectOutlined /> },
      { key: 'budget',     path: '/hq/budget',      label: '预算管理',   icon: <FundOutlined /> },
    ],
  },
  {
    sectionKey: 'insight',
    title: '经营洞察',
    icon: <BulbOutlined />,
    items: [
      { key: 'decisions',   path: '/hq/decisions',   label: '决策中心',   icon: <AimOutlined /> },
      { key: 'competitive', path: '/hq/competitive', label: '竞品分析',   icon: <RadarChartOutlined /> },
      { key: 'forecast',    path: '/hq/forecast',    label: '预测分析',   icon: <LineChartOutlined /> },
      { key: 'reports',     path: '/hq/reports',     label: '报表模板',   icon: <FileSearchOutlined /> },
      { key: 'banquet',     path: '/hq/banquet',     label: '宴会管理',   icon: <CrownOutlined /> },
      { key: 'pareto',      path: '/hq/pareto-analysis', label: '帕累托分析', icon: <FundOutlined /> },
      { key: 'flow-inspect', path: '/hq/flow-inspection', label: '流程巡检',  icon: <ClockCircleOutlined /> },
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
  if (pathname.startsWith('/hq/stores/') && pathname !== '/hq/stores') {
    return (
      <>
        <span className={styles.breadcrumbItem}>营收增长</span>
        <span className={styles.breadcrumbSep}>/</span>
        <span className={styles.breadcrumbItem}>门店管理</span>
        <span className={styles.breadcrumbSep}>/</span>
        <span className={styles.breadcrumbCurrent}>门店详情</span>
      </>
    );
  }

  const crumbs = BREADCRUMB_MAP[pathname];
  if (!crumbs) {
    return <span className={styles.breadcrumbCurrent}>经营总览</span>;
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
const HQLayout: React.FC = () => {
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
    path === '/hq'
      ? location.pathname === '/hq'
      : location.pathname.startsWith(path);

  return (
    <div className={styles.shell}>
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        <div className={styles.logoArea} onClick={() => navigate('/hq')}>
          <div className={styles.logoMark}>
            <img src="/logo-icon.svg" alt="屯象" className={styles.logoImg} />
          </div>
          {!collapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoName}>经营决策中心</span>
              <span className={styles.logoSub}>Decision Center</span>
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
                        end={item.path === '/hq'}
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
                <div className={styles.userRole}>总部管理员</div>
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
            <span className={styles.envBadge}>总部视图</span>
            <span className={styles.versionTag}>v0.1.0-beta</span>
          </div>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default HQLayout;
