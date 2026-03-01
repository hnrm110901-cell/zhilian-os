import React, { useState, useEffect } from 'react';
import { Card, Table, Switch, Select, Button, message, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Title, Text } = Typography;

interface NotificationPreference {
  notification_type: string;
  enabled: boolean;
  channel: string;
  frequency: string;
}

const CHANNEL_OPTIONS = [
  { value: 'in_app', label: '站内' },
  { value: 'email', label: '邮件' },
  { value: 'sms', label: '短信' },
  { value: 'wechat', label: '微信' },
];

const FREQUENCY_OPTIONS = [
  { value: 'realtime', label: '实时' },
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
];

const TYPE_LABELS: Record<string, string> = {
  inventory_alert: '库存预警',
  order_update: '订单更新',
  schedule_change: '排班变更',
  approval_request: '审批请求',
  system_alert: '系统告警',
  ai_recommendation: 'AI建议',
  daily_report: '日报',
  kpi_threshold: 'KPI阈值告警',
};

const NotificationPreferencesPage: React.FC = () => {
  const [preferences, setPreferences] = useState<NotificationPreference[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);

  const fetchPreferences = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/notifications/preferences');
      setPreferences(res.data);
    } catch {
      message.error('加载通知偏好失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPreferences(); }, []);

  const handleUpdate = async (record: NotificationPreference, field: string, value: unknown) => {
    const updated = { ...record, [field]: value };
    setSaving(record.notification_type);
    try {
      await apiClient.put('/api/v1/notifications/preferences', updated);
      setPreferences(prev => prev.map(p =>
        p.notification_type === record.notification_type ? updated : p
      ));
      message.success('已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(null);
    }
  };

  const columns = [
    {
      title: '通知类型',
      dataIndex: 'notification_type',
      render: (type: string) => (
        <Space>
          <Text strong>{TYPE_LABELS[type] || type}</Text>
          <Tag color="blue" style={{ fontSize: 11 }}>{type}</Tag>
        </Space>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: NotificationPreference) => (
        <Switch
          checked={enabled}
          loading={saving === record.notification_type}
          onChange={val => handleUpdate(record, 'enabled', val)}
        />
      ),
    },
    {
      title: '渠道',
      dataIndex: 'channel',
      width: 140,
      render: (channel: string, record: NotificationPreference) => (
        <Select
          value={channel}
          options={CHANNEL_OPTIONS}
          style={{ width: 120 }}
          disabled={!record.enabled}
          onChange={val => handleUpdate(record, 'channel', val)}
        />
      ),
    },
    {
      title: '频率',
      dataIndex: 'frequency',
      width: 140,
      render: (frequency: string, record: NotificationPreference) => (
        <Select
          value={frequency}
          options={FREQUENCY_OPTIONS}
          style={{ width: 120 }}
          disabled={!record.enabled}
          onChange={val => handleUpdate(record, 'frequency', val)}
        />
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>通知偏好设置</Title>
        <Button icon={<ReloadOutlined />} onClick={fetchPreferences} loading={loading}>刷新</Button>
      </div>
      <Card>
        <Table
          rowKey="notification_type"
          columns={columns}
          dataSource={preferences}
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无通知偏好配置' }}
        />
      </Card>
    </div>
  );
};

export default NotificationPreferencesPage;
