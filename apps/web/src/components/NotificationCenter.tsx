import React, { useState, useCallback, useEffect } from 'react';
import { Badge, Button, Dropdown, List, Typography, Tag, Empty, Spin, Divider } from 'antd';
import { BellOutlined, CheckOutlined } from '@ant-design/icons';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WsMessage } from '../hooks/useWebSocket';
import { apiClient } from '../services/api';

const { Text } = Typography;

interface Notification {
  id: string;
  title: string;
  message: string;
  type: string;
  priority: 'low' | 'normal' | 'high' | 'urgent';
  is_read: boolean;
  created_at: string;
  store_id?: string;
}

const priorityColor: Record<string, string> = {
  urgent: 'red',
  high: 'orange',
  normal: 'blue',
  low: 'default',
};

const typeLabel: Record<string, string> = {
  inventory_alert: '库存预警',
  abnormal_order: '异常订单',
  approval_pending: '待审批',
  performance_alert: '绩效超阈值',
  system: '系统',
};

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const token = localStorage.getItem('token');
  const wsUrl = token
    ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/v1/ws?token=${token}`
    : null;

  const handleWsMessage = useCallback((msg: WsMessage) => {
    if (msg.type === 'notification' && msg.data) {
      const n = msg.data as Notification;
      setNotifications((prev) => [n, ...prev.slice(0, 49)]);
      setUnread((c) => c + 1);
    }
  }, []);

  useWebSocket(wsUrl, { onMessage: handleWsMessage });

  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [list, countResp] = await Promise.all([
        apiClient.get<{ items: Notification[] }>('/api/v1/notifications?limit=20'),
        apiClient.get<{ unread_count: number }>('/api/v1/notifications/unread-count'),
      ]);
      setNotifications(list.items ?? []);
      setUnread(countResp.unread_count ?? 0);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const markAllRead = async () => {
    try {
      await apiClient.put('/api/v1/notifications/read-all');
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnread(0);
    } catch {
      // fail silently
    }
  };

  const markRead = async (id: string) => {
    try {
      await apiClient.put(`/api/v1/notifications/${id}/read`);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnread((c) => Math.max(0, c - 1));
    } catch {
      // fail silently
    }
  };

  const dropdownContent = (
    <div style={{ width: 360, maxHeight: 480, overflowY: 'auto', background: '#fff', borderRadius: 8, boxShadow: '0 4px 20px rgba(0,0,0,.15)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
        <Text strong>通知中心 {unread > 0 && <Tag color="red">{unread} 未读</Tag>}</Text>
        {unread > 0 && (
          <Button type="link" size="small" icon={<CheckOutlined />} onClick={markAllRead}>
            全部已读
          </Button>
        )}
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
      ) : notifications.length === 0 ? (
        <Empty description="暂无通知" style={{ padding: 24 }} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          dataSource={notifications}
          renderItem={(n) => (
            <List.Item
              style={{ padding: '10px 16px', cursor: 'pointer', background: n.is_read ? undefined : 'rgba(24,144,255,.04)' }}
              onClick={() => !n.is_read && markRead(n.id)}
            >
              <List.Item.Meta
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {!n.is_read && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#1677ff', display: 'inline-block' }} />}
                    <Tag color={priorityColor[n.priority]} style={{ margin: 0 }}>{typeLabel[n.type] ?? n.type}</Tag>
                    <Text style={{ fontSize: 13 }}>{n.title}</Text>
                  </div>
                }
                description={
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>{n.message}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>{new Date(n.created_at).toLocaleString('zh-CN')}</Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      )}
      <Divider style={{ margin: 0 }} />
      <div style={{ textAlign: 'center', padding: 8 }}>
        <Button type="link" size="small" onClick={() => { setOpen(false); window.location.href = '/notifications'; }}>
          查看全部通知
        </Button>
      </div>
    </div>
  );

  return (
    <Dropdown
      open={open}
      onOpenChange={(v) => { setOpen(v); if (v) fetchNotifications(); }}
      dropdownRender={() => dropdownContent}
      placement="bottomRight"
      trigger={['click']}
    >
      <Badge count={unread} size="small" overflowCount={99}>
        <Button type="text" icon={<BellOutlined style={{ fontSize: 17 }} />} />
      </Badge>
    </Dropdown>
  );
}
