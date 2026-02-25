import React, { useEffect, useState, useCallback } from 'react';
import { Card, List, Button, Tag, Row, Col, Badge, Avatar, Space, Divider } from 'antd';
import {
  ShoppingOutlined,
  UserOutlined,
  BellOutlined,
  HomeOutlined,
  TeamOutlined,
  ReloadOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import { DataCard, LoadingSkeleton, EmptyState } from '../components';

const MobileApp: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [todayOrders, setTodayOrders] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('home');
  const [refreshing, setRefreshing] = useState(false);

  const loadDashboardData = useCallback(async () => {
    try {
      setRefreshing(true);
      const response = await apiClient.get('/mobile/dashboard');
      setDashboard(response.data);
    } catch (err: any) {
      handleApiError(err, '加载仪表盘失败');
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  const loadTodayOrders = useCallback(async () => {
    try {
      const response = await apiClient.get('/mobile/orders/today');
      setTodayOrders(response.data);
    } catch (err: any) {
      handleApiError(err, '加载今日订单失败');
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
    <div className="fade-in">
      {/* 用户信息卡片 */}
      <Card
        style={{
          marginBottom: 16,
          background: 'var(--primary-gradient)',
          border: 'none',
        }}
        bodyStyle={{ padding: '20px' }}
      >
        <Space align="center" size={16}>
          <Avatar
            size={56}
            icon={<UserOutlined />}
            style={{ backgroundColor: 'white', color: 'var(--primary-color)' }}
          />
          <div style={{ color: 'white', flex: 1 }}>
            <h2 style={{ color: 'white', margin: 0, fontSize: 18 }}>
              {dashboard?.user?.full_name || '用户'}
            </h2>
            <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: 13 }}>
              {dashboard?.user?.role} | {dashboard?.user?.store_name || '未分配门店'}
            </p>
          </div>
        </Space>
      </Card>

      {/* 今日统计 */}
      <Card title="今日数据" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          <Col span={8}>
            <DataCard
              title="订单"
              value={dashboard?.today_stats?.orders || 0}
              prefix={<ShoppingOutlined style={{ color: 'var(--primary-color)' }} />}
              style={{ textAlign: 'center' }}
            />
          </Col>
          <Col span={8}>
            <DataCard
              title="营收"
              value={((dashboard?.today_stats?.revenue || 0) / 100).toFixed(0)}
              prefix="¥"
              style={{ textAlign: 'center' }}
            />
          </Col>
          <Col span={8}>
            <DataCard
              title="顾客"
              value={dashboard?.today_stats?.customers || 0}
              prefix={<TeamOutlined style={{ color: 'var(--success-color)' }} />}
              style={{ textAlign: 'center' }}
            />
          </Col>
        </Row>
      </Card>

      {/* 快捷操作 */}
      <Card title="快捷操作" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          {dashboard?.quick_actions?.map((action: any) => (
            <Col span={12} key={action.id}>
              <Button
                block
                size="large"
                style={{
                  height: 72,
                  fontSize: 15,
                  borderRadius: 'var(--radius-md)',
                  fontWeight: 500,
                }}
                onClick={() => {
                  console.log('Quick action:', action);
                }}
              >
                {action.label}
              </Button>
            </Col>
          )) || (
            <>
              <Col span={12}>
                <Button
                  block
                  size="large"
                  type="primary"
                  style={{ height: 72, fontSize: 15, borderRadius: 'var(--radius-md)' }}
                >
                  新建订单
                </Button>
              </Col>
              <Col span={12}>
                <Button
                  block
                  size="large"
                  style={{ height: 72, fontSize: 15, borderRadius: 'var(--radius-md)' }}
                >
                  查看报表
                </Button>
              </Col>
            </>
          )}
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
        {dashboard?.notifications?.latest_notifications?.length > 0 ? (
          <List
            dataSource={dashboard.notifications.latest_notifications.slice(0, 3)}
            renderItem={(item: any) => (
              <List.Item style={{ padding: '12px 0' }}>
                <List.Item.Meta
                  title={<span style={{ fontSize: 14 }}>{item.title}</span>}
                  description={
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <span style={{ fontSize: 13 }}>{item.message}</span>
                      <Space size={8}>
                        <Tag
                          color={item.priority === 'high' ? 'red' : 'blue'}
                          style={{ fontSize: 11 }}
                        >
                          {item.type}
                        </Tag>
                        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                          {new Date(item.created_at).toLocaleString('zh-CN')}
                        </span>
                      </Space>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <EmptyState title="暂无通知" description="您目前没有新的通知消息" />
        )}
      </Card>
    </div>
  );

  const renderOrders = () => (
    <div className="fade-in">
      <Card
        title={`今日订单 (${todayOrders?.total || 0})`}
        extra={
          <Button
            size="small"
            icon={<ReloadOutlined spin={refreshing} />}
            onClick={loadTodayOrders}
            loading={refreshing}
          >
            刷新
          </Button>
        }
      >
        {todayOrders?.orders?.length > 0 ? (
          <List
            dataSource={todayOrders.orders}
            renderItem={(order: any) => (
              <List.Item style={{ padding: '12px 0' }}>
                <List.Item.Meta
                  title={
                    <Space>
                      <span style={{ fontSize: 14 }}>订单 {order.order_no}</span>
                      <Tag color={order.status === 1 ? 'success' : 'processing'}>
                        {order.status === 1 ? '已完成' : '进行中'}
                      </Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <span style={{ fontSize: 13 }}>
                        桌台: {order.table_no} | 人数: {order.people}
                      </span>
                      <span
                        style={{
                          fontSize: 16,
                          fontWeight: 'bold',
                          color: 'var(--success-color)',
                        }}
                      >
                        ¥{order.amount.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                        {order.time}
                      </span>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <EmptyState
            title="今日暂无订单"
            description="今天还没有新的订单"
            action={{
              text: '新建订单',
              onClick: () => console.log('Create order'),
            }}
          />
        )}
      </Card>
    </div>
  );

  const renderNotifications = () => (
    <div className="fade-in">
      <Card
        title={`通知中心 (${dashboard?.notifications?.unread_count || 0}条未读)`}
        extra={
          <Button
            size="small"
            onClick={() => {
              console.log('Mark all as read');
            }}
          >
            全部已读
          </Button>
        }
      >
        {dashboard?.notifications?.latest_notifications?.length > 0 ? (
          <List
            dataSource={dashboard.notifications.latest_notifications}
            renderItem={(item: any) => (
              <List.Item
                onClick={() => {
                  console.log('Notification clicked:', item);
                }}
                style={{
                  cursor: 'pointer',
                  padding: '12px 0',
                  transition: 'background var(--transition-fast)',
                }}
              >
                <List.Item.Meta
                  avatar={
                    <Badge dot={!item.is_read}>
                      <Avatar
                        icon={<BellOutlined />}
                        style={{
                          backgroundColor:
                            item.priority === 'high' ? 'var(--error-color)' : 'var(--info-color)',
                        }}
                      />
                    </Badge>
                  }
                  title={<span style={{ fontSize: 14 }}>{item.title}</span>}
                  description={
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <span style={{ fontSize: 13 }}>{item.message}</span>
                      <Space size={8}>
                        <Tag
                          color={item.priority === 'high' ? 'red' : 'blue'}
                          style={{ fontSize: 11 }}
                        >
                          {item.type}
                        </Tag>
                        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                          {new Date(item.created_at).toLocaleString('zh-CN')}
                        </span>
                      </Space>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <EmptyState title="暂无通知" description="您目前没有新的通知消息" />
        )}
      </Card>
    </div>
  );

  const renderProfile = () => (
    <div className="fade-in">
      <Card title="个人信息" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>用户名</span>
            <span style={{ fontWeight: 500 }}>{dashboard?.user?.username || '-'}</span>
          </div>
          <Divider style={{ margin: 0 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>姓名</span>
            <span style={{ fontWeight: 500 }}>{dashboard?.user?.full_name || '-'}</span>
          </div>
          <Divider style={{ margin: 0 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>角色</span>
            <Tag color="blue">{dashboard?.user?.role || '-'}</Tag>
          </div>
          <Divider style={{ margin: 0 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>门店</span>
            <span style={{ fontWeight: 500 }}>{dashboard?.user?.store_name || '未分配'}</span>
          </div>
        </Space>
      </Card>

      <Card title="系统信息" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>版本</span>
            <span style={{ fontWeight: 500 }}>1.0.0</span>
          </div>
          <Divider style={{ margin: 0 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
            <span style={{ color: 'var(--text-secondary)' }}>最后更新</span>
            <span style={{ fontWeight: 500, fontSize: 13 }}>
              {new Date().toLocaleString('zh-CN')}
            </span>
          </div>
        </Space>
      </Card>

      <Button
        danger
        block
        size="large"
        icon={<LogoutOutlined />}
        style={{ borderRadius: 'var(--radius-md)', height: 48, fontSize: 15 }}
        onClick={() => {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }}
      >
        退出登录
      </Button>
    </div>
  );

  if (loading && !dashboard) {
    return <LoadingSkeleton type="list" rows={5} />;
  }

  return (
    <div
      style={{
        paddingBottom: 60,
        background: 'var(--bg-secondary)',
        minHeight: '100vh',
      }}
    >
      {/* 头部 */}
      <div
        style={{
          background: 'var(--primary-gradient)',
          color: 'white',
          padding: '16px 20px',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          boxShadow: 'var(--shadow-md)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>智链OS 移动端</h1>
            <p style={{ margin: '4px 0 0', fontSize: 12, opacity: 0.9 }}>
              {new Date().toLocaleDateString('zh-CN')} {new Date().toLocaleTimeString('zh-CN')}
            </p>
          </div>
          <Button
            type="text"
            icon={<ReloadOutlined spin={refreshing} style={{ color: 'white', fontSize: 18 }} />}
            onClick={loadDashboardData}
            loading={refreshing}
          />
        </div>
      </div>

      {/* 内容区域 */}
      <div style={{ padding: 16 }}>
        {activeTab === 'home' && renderHome()}
        {activeTab === 'orders' && renderOrders()}
        {activeTab === 'notifications' && renderNotifications()}
        {activeTab === 'profile' && renderProfile()}
      </div>

      {/* 底部导航栏 */}
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          background: 'var(--bg-elevated)',
          borderTop: '1px solid var(--border-light)',
          display: 'flex',
          justifyContent: 'space-around',
          padding: '8px 0 calc(8px + env(safe-area-inset-bottom))',
          zIndex: 100,
          boxShadow: '0 -2px 8px rgba(0,0,0,0.04)',
        }}
      >
        {[
          { key: 'home', icon: HomeOutlined, label: '首页' },
          { key: 'orders', icon: ShoppingOutlined, label: '订单', badge: todayOrders?.total },
          {
            key: 'notifications',
            icon: BellOutlined,
            label: '通知',
            badge: dashboard?.notifications?.unread_count,
          },
          { key: 'profile', icon: UserOutlined, label: '我的' },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <div
              key={tab.key}
              style={{
                textAlign: 'center',
                flex: 1,
                cursor: 'pointer',
                color: isActive ? 'var(--primary-color)' : 'var(--text-tertiary)',
                transition: 'color var(--transition-fast)',
              }}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.badge ? (
                <Badge count={tab.badge} offset={[10, 0]} size="small">
                  <Icon style={{ fontSize: 22 }} />
                </Badge>
              ) : (
                <Icon style={{ fontSize: 22 }} />
              )}
              <div
                style={{
                  fontSize: 11,
                  marginTop: 4,
                  fontWeight: isActive ? 500 : 400,
                }}
              >
                {tab.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default MobileApp;
