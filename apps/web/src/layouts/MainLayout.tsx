import React, { useState, useEffect } from 'react';
import { Layout, Menu, theme, Dropdown, Avatar, Space, Tag, Breadcrumb, Badge, Tooltip, Button } from 'antd';
import type { MenuProps } from 'antd';
import {
  DashboardOutlined,
  ScheduleOutlined,
  ShoppingCartOutlined,
  InboxOutlined,
  CustomerServiceOutlined,
  ReadOutlined,
  BarChartOutlined,
  CalendarOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
  ApiOutlined,
  LineChartOutlined,
  MobileOutlined,
  ShopOutlined,
  ShoppingOutlined,
  MonitorOutlined,
  DatabaseOutlined,
  BellOutlined,
  DollarOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  HomeOutlined,
  BulbOutlined,
  BulbFilled,
  SearchOutlined,
  RiseOutlined,
  GlobalOutlined,
  SafetyOutlined,
  CheckCircleOutlined,
  RobotOutlined,
  CloudOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  TranslationOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { GlobalSearch } from '../components/GlobalSearch';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';

const { Header, Content, Sider } = Layout;

// 路由 → 所属子菜单 key 的映射（定义在组件外，避免每次渲染重建）
const ROUTE_TO_GROUP: Record<string, string> = {
  '/schedule': 'agents', '/order': 'agents', '/inventory': 'agents',
  '/service': 'agents', '/training': 'agents', '/decision': 'agents', '/reservation': 'agents',
  '/multi-store': 'business', '/supply-chain': 'business', '/finance': 'business',
  '/data-visualization': 'analytics', '/analytics': 'analytics', '/monitoring': 'analytics',
  '/users': 'admin-system', '/enterprise': 'admin-system', '/backup': 'admin-system',
  '/audit': 'admin-system', '/data-import-export': 'admin-system',
  '/open-platform': 'admin-system', '/industry-solutions': 'admin-system', '/i18n': 'admin-system',
  '/forecast': 'admin-analytics', '/cross-store-insights': 'admin-analytics',
  '/recommendations': 'admin-analytics', '/competitive-analysis': 'admin-analytics',
  '/report-templates': 'admin-analytics', '/kpi-dashboard': 'admin-analytics',
  '/private-domain': 'admin-crm', '/members': 'admin-crm', '/customer360': 'admin-crm',
  '/pos': 'admin-store', '/quality': 'admin-store', '/compliance': 'admin-store',
  '/human-in-the-loop': 'admin-store',
  '/ai-evolution': 'admin-ai', '/edge-node': 'admin-ai', '/decision-validator': 'admin-ai',
  '/federated-learning': 'admin-ai', '/agent-collaboration': 'admin-ai',
  '/tasks': 'business', '/reconciliation': 'business', '/dishes': 'business', '/employees': 'business',
  '/raas': 'admin-system', '/model-marketplace': 'admin-system',
  '/llm-config': 'admin-ai', '/hardware': 'admin-ai',
  '/integrations': 'admin-system', '/neural': 'admin-ai', '/embedding': 'admin-ai',
  '/scheduler': 'admin-system', '/benchmark': 'admin-analytics',
};

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [searchVisible, setSearchVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  // openKeys：始终保持当前路由所属分组展开，用户手动展开/折叠其他分组也保留
  const [openKeys, setOpenKeys] = useState<string[]>(() => {
    const g = ROUTE_TO_GROUP[window.location.pathname];
    return g ? [g] : [];
  });

  // 路由变化时确保当前分组展开（不重复添加，不清除其他已展开分组）
  useEffect(() => {
    const groupKey = ROUTE_TO_GROUP[location.pathname];
    if (groupKey) {
      setOpenKeys(prev => prev.includes(groupKey) ? prev : [...prev, groupKey]);
    }
  }, [location.pathname]);

  // 全局快捷键
  useKeyboardShortcuts([
    {
      key: 'k',
      ctrl: true,
      callback: () => setSearchVisible(true),
      description: '打开搜索',
    },
    {
      key: 't',
      ctrl: true,
      shift: true,
      callback: toggleTheme,
      description: '切换主题',
    },
    {
      key: 'h',
      ctrl: true,
      callback: () => navigate('/'),
      description: '返回首页',
    },
    {
      key: 'n',
      ctrl: true,
      callback: () => navigate('/notifications'),
      description: '打开通知',
    },
  ]);

  const roleMap: Record<string, { text: string; color: string }> = {
    admin: { text: '管理员', color: 'red' },
    store_manager: { text: '店长', color: 'blue' },
    manager: { text: '经理', color: 'blue' },
    staff: { text: '员工', color: 'green' },
    waiter: { text: '服务员', color: 'green' }
  };

  // 路由到面包屑映射
  const breadcrumbNameMap: Record<string, string> = {
    '/': '控制台',
    '/schedule': '智能排班',
    '/order': '订单协同',
    '/inventory': '库存预警',
    '/service': '服务质量',
    '/training': '培训辅导',
    '/decision': '决策支持',
    '/reservation': '预定宴会',
    '/multi-store': '多门店管理',
    '/supply-chain': '供应链管理',
    '/finance': '财务管理',
    '/data-visualization': '数据大屏',
    '/analytics': '高级分析',
    '/monitoring': '系统监控',
    '/mobile': '移动端',
    '/notifications': '通知中心',
    '/users': '用户管理',
    '/enterprise': '企业集成',
    '/backup': '数据备份',
    '/audit': '审计日志',
    '/data-import-export': '数据导入导出',
    '/competitive-analysis': '竞争分析',
    '/report-templates': '报表模板',
    '/forecast': '需求预测',
    '/cross-store-insights': '跨门店洞察',
    '/human-in-the-loop': '人工审批',
    '/recommendations': '推荐引擎',
    '/private-domain': '私域运营',
    '/members': '会员系统',
    '/kpi-dashboard': 'KPI看板',
    '/customer360': '客户360',
    '/pos': 'POS系统',
    '/quality': '质量管理',
    '/compliance': '合规管理',
    '/ai-evolution': 'AI进化看板',
    '/edge-node': '边缘节点',
    '/decision-validator': '决策验证',
    '/federated-learning': '联邦学习',
    '/agent-collaboration': 'Agent协作',
    '/open-platform': '开放平台',
    '/industry-solutions': '行业解决方案',
    '/i18n': '国际化',
    '/tasks': '任务管理',
    '/reconciliation': '对账管理',
    '/dishes': '菜品管理',
    '/employees': '员工管理',
    '/raas': 'RaaS定价',
    '/model-marketplace': '模型市场',
    '/llm-config': 'LLM配置',
    '/hardware': '硬件管理',
    '/integrations': '外部集成',
    '/neural': '神经系统',
    '/embedding': '嵌入模型',
    '/scheduler': '调度管理',
    '/benchmark': '基准测试',
  };

  // 生成面包屑项
  const breadcrumbItems = () => {
    const pathSnippets = location.pathname.split('/').filter(i => i);
    const extraBreadcrumbItems = pathSnippets.map((_, index) => {
      const url = `/${pathSnippets.slice(0, index + 1).join('/')}`;
      return {
        key: url,
        title: (
          <a onClick={() => navigate(url)}>
            {breadcrumbNameMap[url] || url}
          </a>
        ),
      };
    });

    return [
      {
        key: 'home',
        title: (
          <a onClick={() => navigate('/')}>
            <HomeOutlined /> 首页
          </a>
        ),
      },
      ...extraBreadcrumbItems,
    ];
  };

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
    },
  ];

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      logout();
      navigate('/login');
    } else if (key === 'profile') {
      // Navigate to profile page
    } else if (key === 'settings') {
      // Navigate to settings page
    }
  };

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: '控制台',
    },
    {
      key: 'agents',
      icon: <ApiOutlined />,
      label: 'Agent系统',
      children: [
        {
          key: '/schedule',
          icon: <ScheduleOutlined />,
          label: '智能排班',
        },
        {
          key: '/order',
          icon: <ShoppingCartOutlined />,
          label: '订单协同',
        },
        {
          key: '/inventory',
          icon: <InboxOutlined />,
          label: '库存预警',
        },
        {
          key: '/service',
          icon: <CustomerServiceOutlined />,
          label: '服务质量',
        },
        {
          key: '/training',
          icon: <ReadOutlined />,
          label: '培训辅导',
        },
        {
          key: '/decision',
          icon: <BarChartOutlined />,
          label: '决策支持',
        },
        {
          key: '/reservation',
          icon: <CalendarOutlined />,
          label: '预定宴会',
        },
      ],
    },
    {
      key: 'business',
      icon: <ShopOutlined />,
      label: '业务管理',
      children: [
        {
          key: '/multi-store',
          icon: <ShopOutlined />,
          label: '多门店管理',
        },
        {
          key: '/supply-chain',
          icon: <ShoppingOutlined />,
          label: '供应链管理',
        },
        {
          key: '/finance',
          icon: <DollarOutlined />,
          label: '财务管理',
        },
        { key: '/dishes', icon: <ShoppingOutlined />, label: '菜品管理' },
        { key: '/employees', icon: <TeamOutlined />, label: '员工管理' },
        { key: '/tasks', icon: <FileTextOutlined />, label: '任务管理' },
        { key: '/reconciliation', icon: <FileExcelOutlined />, label: '对账管理' },
      ],
    },
    {
      key: 'analytics',
      icon: <LineChartOutlined />,
      label: '数据分析',
      children: [
        {
          key: '/data-visualization',
          icon: <LineChartOutlined />,
          label: '数据大屏',
        },
        {
          key: '/analytics',
          icon: <BarChartOutlined />,
          label: '高级分析',
        },
        {
          key: '/monitoring',
          icon: <MonitorOutlined />,
          label: '系统监控',
        },
      ],
    },
    {
      key: '/mobile',
      icon: <MobileOutlined />,
      label: '移动端',
    },
    {
      key: '/notifications',
      icon: <BellOutlined />,
      label: '通知中心',
    },
    ...(user?.role === 'admin' ? [
      {
        key: 'admin-system',
        icon: <SettingOutlined />,
        label: '系统管理',
        children: [
          { key: '/users', icon: <TeamOutlined />, label: '用户管理' },
          { key: '/enterprise', icon: <ApiOutlined />, label: '企业集成' },
          { key: '/backup', icon: <DatabaseOutlined />, label: '数据备份' },
          { key: '/audit', icon: <FileTextOutlined />, label: '审计日志' },
          { key: '/data-import-export', icon: <FileExcelOutlined />, label: '数据导入导出' },
          { key: '/open-platform', icon: <AppstoreOutlined />, label: '开放平台' },
          { key: '/industry-solutions', icon: <GlobalOutlined />, label: '行业解决方案' },
          { key: '/i18n', icon: <TranslationOutlined />, label: '国际化' },
          { key: '/raas', icon: <DollarOutlined />, label: 'RaaS定价' },
          { key: '/model-marketplace', icon: <AppstoreOutlined />, label: '模型市场' },
          { key: '/integrations', icon: <ApiOutlined />, label: '外部集成' },
          { key: '/scheduler', icon: <CalendarOutlined />, label: '调度管理' },
        ],
      },
      {
        key: 'admin-analytics',
        icon: <LineChartOutlined />,
        label: '智能分析',
        children: [
          { key: '/forecast', icon: <LineChartOutlined />, label: '需求预测' },
          { key: '/cross-store-insights', icon: <GlobalOutlined />, label: '跨门店洞察' },
          { key: '/recommendations', icon: <BulbOutlined />, label: '推荐引擎' },
          { key: '/competitive-analysis', icon: <RiseOutlined />, label: '竞争分析' },
          { key: '/report-templates', icon: <FileTextOutlined />, label: '报表模板' },
          { key: '/kpi-dashboard', icon: <BarChartOutlined />, label: 'KPI看板' },
          { key: '/benchmark', icon: <BarChartOutlined />, label: '基准测试' },
        ],
      },
      {
        key: 'admin-crm',
        icon: <UserOutlined />,
        label: '客户运营',
        children: [
          { key: '/private-domain', icon: <TeamOutlined />, label: '私域运营' },
          { key: '/members', icon: <UserOutlined />, label: '会员系统' },
          { key: '/customer360', icon: <UserOutlined />, label: '客户360' },
        ],
      },
      {
        key: 'admin-store',
        icon: <ShopOutlined />,
        label: '门店运营',
        children: [
          { key: '/pos', icon: <ShoppingCartOutlined />, label: 'POS系统' },
          { key: '/quality', icon: <CheckCircleOutlined />, label: '质量管理' },
          { key: '/compliance', icon: <SafetyOutlined />, label: '合规管理' },
          { key: '/human-in-the-loop', icon: <SafetyOutlined />, label: '人工审批' },
        ],
      },
      {
        key: 'admin-ai',
        icon: <RobotOutlined />,
        label: 'AI基础设施',
        children: [
          { key: '/ai-evolution', icon: <RobotOutlined />, label: 'AI进化看板' },
          { key: '/edge-node', icon: <CloudOutlined />, label: '边缘节点' },
          { key: '/decision-validator', icon: <CheckCircleOutlined />, label: '决策验证' },
          { key: '/federated-learning', icon: <ExperimentOutlined />, label: '联邦学习' },
          { key: '/agent-collaboration', icon: <ApartmentOutlined />, label: 'Agent协作' },
          { key: '/llm-config', icon: <SettingOutlined />, label: 'LLM配置' },
          { key: '/hardware', icon: <CloudOutlined />, label: '硬件管理' },
          { key: '/neural', icon: <ApartmentOutlined />, label: '神经系统' },
          { key: '/embedding', icon: <ExperimentOutlined />, label: '嵌入模型' },
        ],
      },
    ] : []),
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <GlobalSearch visible={searchVisible} onClose={() => setSearchVisible(false)} />
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: collapsed ? 18 : 24,
            fontWeight: 'bold',
            background: 'rgba(255, 255, 255, 0.1)',
            transition: 'all 0.2s',
          }}
        >
          {collapsed ? '智链' : '🍜 智链OS'}
        </div>
        <Menu
          theme="dark"
          selectedKeys={[location.pathname]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={setOpenKeys}
          mode="inline"
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'all 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
            position: 'sticky',
            top: 0,
            zIndex: 1,
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 500, color: '#1890ff' }}>
            中餐连锁品牌门店运营智能体操作系统
          </div>
          <Space size="large">
            <Tooltip title="搜索 (Ctrl+K)">
              <Button
                type="text"
                icon={<SearchOutlined />}
                onClick={() => setSearchVisible(true)}
                style={{ fontSize: 18 }}
              />
            </Tooltip>
            <Tooltip title={isDark ? '切换到亮色模式' : '切换到暗色模式'}>
              <Button
                type="text"
                icon={isDark ? <BulbFilled style={{ color: '#faad14' }} /> : <BulbOutlined />}
                onClick={toggleTheme}
                style={{ fontSize: 18 }}
              />
            </Tooltip>
            <Tooltip title="通知中心">
              <Badge count={5} size="small">
                <BellOutlined
                  style={{ fontSize: 20, cursor: 'pointer', color: '#666' }}
                  onClick={() => navigate('/notifications')}
                />
              </Badge>
            </Tooltip>
            <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar
                  icon={<UserOutlined />}
                  style={{ backgroundColor: '#1890ff' }}
                />
                <span style={{ fontWeight: 500 }}>{user?.username}</span>
                <Tag color={roleMap[user?.role || 'staff']?.color || 'green'}>
                  {roleMap[user?.role || 'staff']?.text || '员工'}
                </Tag>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ margin: '16px 16px 0' }}>
          <Breadcrumb
            items={breadcrumbItems()}
            style={{
              marginBottom: 16,
              padding: '8px 16px',
              background: colorBgContainer,
              borderRadius: 8,
            }}
          />
          <div
            style={{
              padding: 24,
              minHeight: 360,
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
              boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
            }}
          >
            <Outlet />
          </div>
        </Content>
        <Layout.Footer style={{ textAlign: 'center', color: '#999' }}>
          智链OS ©{new Date().getFullYear()} - 让餐饮管理更智能
        </Layout.Footer>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
