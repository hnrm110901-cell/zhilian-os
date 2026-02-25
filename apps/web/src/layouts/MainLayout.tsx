import React, { useState } from 'react';
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
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { GlobalSearch } from '../components/GlobalSearch';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';

const { Header, Content, Sider } = Layout;

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
        key: '/users',
        icon: <TeamOutlined />,
        label: '用户管理',
      },
      {
        key: '/enterprise',
        icon: <ApiOutlined />,
        label: '企业集成',
      },
      {
        key: '/backup',
        icon: <DatabaseOutlined />,
        label: '数据备份',
      },
      {
        key: '/audit',
        icon: <FileTextOutlined />,
        label: '审计日志',
      },
      {
        key: '/data-import-export',
        icon: <FileExcelOutlined />,
        label: '数据导入导出',
      },
      {
        key: '/competitive-analysis',
        icon: <RiseOutlined />,
        label: '竞争分析',
      },
      {
        key: '/report-templates',
        icon: <FileTextOutlined />,
        label: '报表模板',
      }
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
