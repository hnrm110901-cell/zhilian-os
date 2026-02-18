import React, { useState } from 'react';
import { Layout, Menu, theme, Dropdown, Avatar, Space, Tag } from 'antd';
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
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const { Header, Content, Sider } = Layout;

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const roleMap = {
    admin: { text: '管理员', color: 'red' },
    manager: { text: '经理', color: 'blue' },
    staff: { text: '员工', color: 'green' }
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
      }
    ] : []),
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div
          style={{
            height: 32,
            margin: 16,
            color: 'white',
            fontSize: 20,
            fontWeight: 'bold',
            textAlign: 'center',
          }}
        >
          {collapsed ? '智链' : '智链OS'}
        </div>
        <Menu
          theme="dark"
          selectedKeys={[location.pathname]}
          mode="inline"
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: colorBgContainer, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 18, fontWeight: 500 }}>
            中餐连锁品牌门店运营智能体操作系统
          </div>
          <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar src={user?.avatar} icon={<UserOutlined />} />
              <span>{user?.username}</span>
              <Tag color={roleMap[user?.role || 'staff'].color}>
                {roleMap[user?.role || 'staff'].text}
              </Tag>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: '16px' }}>
          <div
            style={{
              padding: 24,
              minHeight: 360,
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
            }}
          >
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
