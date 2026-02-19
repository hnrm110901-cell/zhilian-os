import React, { useEffect, useState, useCallback } from 'react';
import { Card, List, Button, Tag, Statistic, Row, Col, Badge, Avatar, Space, Spin } from 'antd';
import {
  ShoppingOutlined,
  UserOutlined,
  BellOutlined,
  HomeOutlined,
  DollarOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const MobileApp: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [todayOrders, setTodayOrders] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('home');

  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/mobile/dashboard');
      setDashboard(response.data);
    } catch (err: any) {
      console.error('Dashboard loading error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTodayOrders = useCallback(async () => {
    try {
      const response = await apiClient.get('/mobile/orders/today');
      setTodayOrders(response.data);
    } catch (err: any) {
      console.error('Orders loading error:', err);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
    loadTodayOrders();

    // 自动刷新（每60秒）
    const intervalId = window.setInterval(() => {
      loadDashboardData();
      loadTodayOrders();
    }, 60000);

    return () => {
      clearInterval(intervalId);
    };
  }, [loadDashboardData, loadTodayOrders]);

  const renderHome = () => (
    <div>
      {/* 用户信息卡片 */}
      <Card style={{ marginBottom: 16, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
        <Space align="center">
          <Avatar size={64} icon={<UserOutlined />} style={{ backgroundColor: '#fff', color: '#667eea' }} />
          <div style={{ color: 'white' }}>
            <h2 style={{ color: 'white', margin: 0 }}>{dashboard?.user?.full_name}</h2>
            <p style={{ margin: 0, opacity: 0.9 }}>
              {dashboard?.user?.role} | {dashboard?.user?.store_name || '未分配门店'}
            </p>
          </div>
        </Space>
      </Card>

      {/* 今日统计 */}
      <Card title="今日数据" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title="订单"
              value={dashboard?.today_stats?.orders || 0}
              prefix={<ShoppingOutlined />}
              valueStyle={{ fontSize: 24 }}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="营收"
              value={(dashboard?.today_stats?.revenue || 0) / 100}
              prefix={<DollarOutlined />}
              precision={2}
              valueStyle={{ fontSize: 24 }}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="顾客"
              value={dashboard?.today_stats?.customers || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ fontSize: 24 }}
            />
          </Col>
        </Row>
      </Card>

      {/* 快捷操作 */}
      <Card title="快捷操作" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          {dashboard?.quick_actions?.map((action: any) => (
            <Col span={12} key={action.id}>
              <Button
                block
                size="large"
                style={{ height: 80, fontSize: 16 }}
                onClick={() => {
                  // 处理快捷操作点击
                  console.log('Quick action:', action);
                }}
              >
                {action.label}
              </Button>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 最新通知 */}
      <Card
        title={
          <Space>
            <span>最新通知</span>
            <Badge count={dashboard?.notifications?.unread_count || 0} />
          </Space>
        }
      >
        <List
          dataSource={dashboard?.notifications?.latest_notifications || []}
          renderItem={(item: any) => (
            <List.Item>
              <List.Item.Meta
                title={item.title}
                description={
                  <Space direction="vertical" size={4}>
                    <span>{item.message}</span>
                    <Space>
                      <Tag color={item.priority === 'high' ? 'red' : 'blue'}>{item.type}</Tag>
                      <span style={{ fontSize: 12, color: '#999' }}>
                        {new Date(item.created_at).toLocaleString('zh-CN')}
                      </span>
                    </Space>
                  </Space>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: '暂无通知' }}
        />
      </Card>
    </div>
  );

  const renderOrders = () => (
    <div>
      <Card
        title={`今日订单 (${todayOrders?.total || 0})`}
        extra={
          <Button size="small" onClick={loadTodayOrders}>
            刷新
          </Button>
        }
      >
        <List
          dataSource={todayOrders?.orders || []}
          renderItem={(order: any) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <span>订单 {order.order_no}</span>
                    <Tag color={order.status === 1 ? 'success' : 'processing'}>
                      {order.status === 1 ? '已完成' : '进行中'}
                    </Tag>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={4}>
                    <span>桌台: {order.table_no} | 人数: {order.people}</span>
                    <span style={{ fontSize: 16, fontWeight: 'bold', color: '#52c41a' }}>
                      ¥{order.amount.toFixed(2)}
                    </span>
                    <span style={{ fontSize: 12, color: '#999' }}>{order.time}</span>
                  </Space>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: '今日暂无订单' }}
        />
      </Card>
    </div>
  );

  const renderProfile = () => (
    <div>
      <Card title="个人信息" style={{ marginBottom: 16 }}>
        <List>
          <List.Item>
            <List.Item.Meta title="用户名" description={dashboard?.user?.username} />
          </List.Item>
          <List.Item>
            <List.Item.Meta title="姓名" description={dashboard?.user?.full_name} />
          </List.Item>
          <List.Item>
            <List.Item.Meta title="角色" description={dashboard?.user?.role} />
          </List.Item>
          <List.Item>
            <List.Item.Meta title="门店" description={dashboard?.user?.store_name || '未分配'} />
          </List.Item>
        </List>
      </Card>

      <Card title="系统信息" style={{ marginBottom: 16 }}>
        <List>
          <List.Item>
            <List.Item.Meta title="版本" description="1.0.0" />
          </List.Item>
          <List.Item>
            <List.Item.Meta title="最后更新" description={new Date().toLocaleString('zh-CN')} />
          </List.Item>
        </List>
      </Card>

      <Button danger block size="large" onClick={() => {
        // 处理退出登录
        localStorage.removeItem('token');
        window.location.href = '/login';
      }}>
        退出登录
      </Button>
    </div>
  );

  if (loading && !dashboard) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <p style={{ marginTop: 16 }}>正在加载...</p>
      </div>
    );
  }

  return (
    <div style={{ paddingBottom: 60, background: '#f0f2f5', minHeight: '100vh' }}>
      {/* 头部 */}
      <div
        style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'white',
          padding: '16px 20px',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20 }}>智链OS 移动端</h1>
        <p style={{ margin: 0, fontSize: 12, opacity: 0.9 }}>
          {new Date().toLocaleDateString('zh-CN')} {new Date().toLocaleTimeString('zh-CN')}
        </p>
      </div>

      {/* 内容区域 */}
      <div style={{ padding: 16 }}>
        {activeTab === 'home' && renderHome()}
        {activeTab === 'orders' && renderOrders()}
        {activeTab === 'profile' && renderProfile()}
      </div>

      {/* 底部导航栏 */}
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          background: 'white',
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          justifyContent: 'space-around',
          padding: '8px 0',
          zIndex: 100,
        }}
      >
        <div
          style={{
            textAlign: 'center',
            flex: 1,
            cursor: 'pointer',
            color: activeTab === 'home' ? '#667eea' : '#999',
          }}
          onClick={() => setActiveTab('home')}
        >
          <HomeOutlined style={{ fontSize: 24 }} />
          <div style={{ fontSize: 12, marginTop: 4 }}>首页</div>
        </div>
        <div
          style={{
            textAlign: 'center',
            flex: 1,
            cursor: 'pointer',
            color: activeTab === 'orders' ? '#667eea' : '#999',
          }}
          onClick={() => setActiveTab('orders')}
        >
          <Badge count={todayOrders?.total || 0} offset={[10, 0]}>
            <ShoppingOutlined style={{ fontSize: 24 }} />
          </Badge>
          <div style={{ fontSize: 12, marginTop: 4 }}>订单</div>
        </div>
        <div
          style={{
            textAlign: 'center',
            flex: 1,
            cursor: 'pointer',
            color: activeTab === 'notifications' ? '#667eea' : '#999',
          }}
          onClick={() => setActiveTab('notifications')}
        >
          <Badge count={dashboard?.notifications?.unread_count || 0} offset={[10, 0]}>
            <BellOutlined style={{ fontSize: 24 }} />
          </Badge>
          <div style={{ fontSize: 12, marginTop: 4 }}>通知</div>
        </div>
        <div
          style={{
            textAlign: 'center',
            flex: 1,
            cursor: 'pointer',
            color: activeTab === 'profile' ? '#667eea' : '#999',
          }}
          onClick={() => setActiveTab('profile')}
        >
          <UserOutlined style={{ fontSize: 24 }} />
          <div style={{ fontSize: 12, marginTop: 4 }}>我的</div>
        </div>
      </div>
    </div>
  );
};

export default MobileApp;
