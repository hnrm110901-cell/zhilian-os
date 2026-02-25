import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Form, Input, InputNumber, Select } from 'antd';
import { UserAddOutlined, SoundOutlined, CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const statusColor: Record<string, string> = { waiting: 'orange', called: 'blue', seated: 'green', cancelled: 'default' };
const statusLabel: Record<string, string> = { waiting: '等待中', called: '已叫号', seated: '已入座', cancelled: '已取消' };

const QueueManagementPage: React.FC = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [callLoading, setCallLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState('waiting');
  const [form] = Form.useForm();

  const loadQueue = useCallback(async () => {
    setLoading(true);
    try {
      const [queueRes, statsRes] = await Promise.allSettled([
        apiClient.get('/queue/list', { params: { status: statusFilter || undefined, limit: 100 } }),
        apiClient.get('/queue/stats'),
      ]);
      if (queueRes.status === 'fulfilled') setQueue(queueRes.value.data?.queue || queueRes.value.data || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载排队数据失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const addToQueue = async (values: any) => {
    try {
      await apiClient.post('/queue/add', values);
      showSuccess('已加入排队');
      setAddVisible(false);
      form.resetFields();
      loadQueue();
    } catch (err: any) {
      handleApiError(err, '加入排队失败');
    }
  };

  const callNext = async () => {
    setCallLoading(true);
    try {
      const res = await apiClient.post('/queue/call-next');
      showSuccess(`已叫号：${res.data?.customer_name || '下一位'}`);
      loadQueue();
    } catch (err: any) {
      handleApiError(err, '叫号失败');
    } finally {
      setCallLoading(false);
    }
  };

  const markSeated = async (record: any) => {
    const key = `seat-${record.queue_id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.put(`/queue/${record.queue_id}/seated`, { table_number: '待分配' });
      showSuccess('已标记入座');
      loadQueue();
    } catch (err: any) {
      handleApiError(err, '操作失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const cancelQueue = async (record: any) => {
    const key = `cancel-${record.queue_id}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.delete(`/queue/${record.queue_id}`);
      showSuccess('已取消');
      loadQueue();
    } catch (err: any) {
      handleApiError(err, '取消失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const columns: ColumnsType<any> = [
    { title: '号码', dataIndex: 'queue_number', key: 'queue_number', width: 70 },
    { title: '姓名', dataIndex: 'customer_name', key: 'customer_name' },
    { title: '电话', dataIndex: 'customer_phone', key: 'customer_phone' },
    { title: '人数', dataIndex: 'party_size', key: 'party_size', width: 60 },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel[v] || v}</Tag> },
    { title: '等待时间', dataIndex: 'wait_time', key: 'wait_time', render: (v: number) => v ? `${v}分钟` : '-' },
    { title: '特殊需求', dataIndex: 'special_requests', key: 'special_requests', ellipsis: true },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => record.status === 'waiting' || record.status === 'called' ? (
        <Space>
          {record.status === 'called' && (
            <Button size="small" type="primary" icon={<CheckOutlined />} loading={actionLoading[`seat-${record.queue_id}`]} onClick={() => markSeated(record)}>入座</Button>
          )}
          <Button size="small" danger icon={<CloseOutlined />} loading={actionLoading[`cancel-${record.queue_id}`]} onClick={() => cancelQueue(record)}>取消</Button>
        </Space>
      ) : null,
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="等待中" value={stats?.waiting_count ?? queue.filter((q: any) => q.status === 'waiting').length} /></Card></Col>
        <Col span={6}><Card><Statistic title="已叫号" value={stats?.called_count ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="今日入座" value={stats?.seated_today ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均等待" suffix="分钟" value={stats?.avg_wait_time ?? 0} /></Card></Col>
      </Row>

      <Card
        title="排队列表"
        extra={
          <Space>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
              <Option value="">全部</Option>
              <Option value="waiting">等待中</Option>
              <Option value="called">已叫号</Option>
              <Option value="seated">已入座</Option>
              <Option value="cancelled">已取消</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={loadQueue}>刷新</Button>
            <Button type="primary" icon={<SoundOutlined />} loading={callLoading} onClick={callNext}>叫下一位</Button>
            <Button icon={<UserAddOutlined />} onClick={() => setAddVisible(true)}>加入排队</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={queue} rowKey={(r) => r.queue_id || r.id} loading={loading} />
      </Card>

      <Modal title="加入排队" open={addVisible} onCancel={() => { setAddVisible(false); form.resetFields(); }} onOk={() => form.submit()} okText="确认">
        <Form form={form} layout="vertical" onFinish={addToQueue}>
          <Form.Item name="customer_name" label="顾客姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="customer_phone" label="手机号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="party_size" label="用餐人数" rules={[{ required: true }]} initialValue={2}>
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="special_requests" label="特殊需求"><TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default QueueManagementPage;
