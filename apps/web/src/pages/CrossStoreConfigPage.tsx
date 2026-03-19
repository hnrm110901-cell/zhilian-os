import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Select, Input, DatePicker, Button, Table, Tag, Alert,
  Space, Typography, Divider, Tabs, message,
} from 'antd';
import { SendOutlined, HistoryOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface Store {
  id: string;
  name: string;
}

const CONFIG_TYPES = [
  { value: 'business_hours', label: '营业时间' },
  { value: 'price', label: '菜品定价' },
  { value: 'policy', label: '营运政策' },
  { value: 'menu', label: '菜单结构' },
  { value: 'promotion', label: '促销活动' },
];

const STAFF_AVAILABLE_MOCK: { store_id: string; store_name: string; scheduled_count: number; available_for_transfer: number }[] = [];

export default function CrossStoreConfigPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [broadcastResult, setBroadcastResult] = useState<Record<string, unknown> | null>(null);
  const [transferResult, setTransferResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [broadcastForm] = Form.useForm();
  const [transferForm] = Form.useForm();

  const fetchStores = useCallback(async () => {
    try {
      const resp = await apiClient.get<{ stores: Store[] }>('/api/v1/multi-store/stores');
      setStores(resp.stores ?? []);
    } catch {
      // fail silently
    }
  }, []);

  useEffect(() => {
    fetchStores();
  }, [fetchStores]);

  const handleBroadcast = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      let configData: Record<string, unknown> = {};
      try { configData = JSON.parse(values.config_data as string); } catch { configData = { raw: values.config_data }; }
      const result = await apiClient.post('/api/v1/multi-store/hq/config/broadcast', {
        config_type: values.config_type,
        config_data: configData,
        target_store_ids: values.target_store_ids ?? null,
        effective_date: values.effective_date ? (values.effective_date as { format: (s: string) => string }).format('YYYY-MM-DD') : null,
        note: values.note,
      });
      setBroadcastResult(result as Record<string, unknown>);
      message.success('配置下发成功');
      broadcastForm.resetFields();
    } catch (e: unknown) {
      message.error((e as { message?: string })?.message ?? '下发失败');
    } finally {
      setLoading(false);
    }
  };

  const handleTransfer = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const result = await apiClient.post('/api/v1/multi-store/cross-store/shift-transfer', {
        from_store_id: values.from_store_id,
        to_store_id: values.to_store_id,
        employee_id: values.employee_id,
        shift_date: (values.shift_date as { format: (s: string) => string }).format('YYYY-MM-DD'),
        reason: values.reason,
      });
      setTransferResult(result as Record<string, unknown>);
      message.success('借调申请已提交');
      transferForm.resetFields();
    } catch (e: unknown) {
      message.error((e as { message?: string })?.message ?? '提交失败');
    } finally {
      setLoading(false);
    }
  };

  const staffColumns = [
    { title: '门店', dataIndex: 'store_name', key: 'name' },
    { title: '在班人数', dataIndex: 'scheduled_count', key: 'scheduled' },
    {
      title: '可借调',
      dataIndex: 'available_for_transfer',
      key: 'available',
      render: (v: number) => <Tag color={v > 0 ? 'success' : 'default'}>{v} 人</Tag>,
    },
  ];

  const storeOptions = stores.map((s) => ({ value: s.id, label: s.name }));

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <Title level={3}>跨店协调 & 配置下发</Title>
      <Tabs
        items={[
          {
            key: 'config',
            label: '📋 总部配置下发',
            children: (
              <Card>
                <Text type="secondary">将统一配置（营业时间、价格、政策等）下发到指定门店或全部门店</Text>
                <Divider />
                <Form form={broadcastForm} layout="vertical" onFinish={handleBroadcast}>
                  <Form.Item name="config_type" label="配置类型" rules={[{ required: true }]}>
                    <Select options={CONFIG_TYPES} placeholder="选择配置类型" />
                  </Form.Item>
                  <Form.Item
                    name="config_data"
                    label="配置内容（JSON 格式）"
                    rules={[{ required: true }]}
                  >
                    <TextArea rows={4} placeholder='{"key": "value"}' />
                  </Form.Item>
                  <Form.Item name="target_store_ids" label="目标门店（不选则下发全部）">
                    <Select
                      mode="multiple"
                      options={storeOptions}
                      placeholder="留空=全部门店"
                      allowClear
                    />
                  </Form.Item>
                  <Form.Item name="effective_date" label="生效日期">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="note" label="备注">
                    <Input placeholder="可选备注" />
                  </Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    icon={<SendOutlined />}
                  >
                    下发配置
                  </Button>
                </Form>
                {broadcastResult && (
                  <Alert
                    style={{ marginTop: 16 }}
                    type="success"
                    message={String(broadcastResult.message)}
                    description={`已下发至 ${broadcastResult.target_store_count} 家门店 · 下发ID: ${broadcastResult.broadcast_id}`}
                  />
                )}
              </Card>
            ),
          },
          {
            key: 'transfer',
            label: '🔄 跨店借调排班',
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Card title="各门店今日排班余量">
                  <Table
                    dataSource={STAFF_AVAILABLE_MOCK}
                    columns={staffColumns}
                    rowKey="store_id"
                    pagination={false}
                    size="small"
                  />
                </Card>
                <Card title="发起借调申请">
                  <Form form={transferForm} layout="vertical" onFinish={handleTransfer}>
                    <Form.Item name="from_store_id" label="借出门店" rules={[{ required: true }]}>
                      <Select options={storeOptions} placeholder="选择借出门店" />
                    </Form.Item>
                    <Form.Item name="to_store_id" label="借入门店" rules={[{ required: true }]}>
                      <Select options={storeOptions} placeholder="选择借入门店" />
                    </Form.Item>
                    <Form.Item name="employee_id" label="员工ID" rules={[{ required: true }]}>
                      <Input placeholder="输入员工工号或姓名" />
                    </Form.Item>
                    <Form.Item name="shift_date" label="借调日期" rules={[{ required: true }]}>
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="reason" label="借调原因">
                      <Input placeholder="例：分店一节假日人手不足" />
                    </Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      icon={<SendOutlined />}
                    >
                      提交申请
                    </Button>
                  </Form>
                  {transferResult && (
                    <Alert
                      style={{ marginTop: 16 }}
                      type="info"
                      message={String(transferResult.message)}
                      description={`申请ID: ${transferResult.transfer_id} · 状态: ${transferResult.status}`}
                    />
                  )}
                </Card>
              </Space>
            ),
          },
          {
            key: 'history',
            label: <span><HistoryOutlined /> 下发历史</span>,
            children: (
              <Card>
                <Alert
                  type="info"
                  message="配置下发历史"
                  description="历史记录将在接入 audit_log 服务后自动展示"
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
