import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Tabs, Select, Modal, Form, Input, Alert } from 'antd';
import { PlusOutlined, SyncOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const typeColor: Record<string, string> = { pos: 'blue', supplier: 'orange', member: 'green', reservation: 'purple' };
const typeLabel: Record<string, string> = { pos: 'POS系统', supplier: '供应商', member: '会员系统', reservation: '预订系统' };
const statusColor: Record<string, string> = { active: 'green', inactive: 'red', error: 'red', pending: 'orange' };

const IntegrationsPage: React.FC = () => {
  const [systems, setSystems] = useState<any[]>([]);
  const [syncLogs, setSyncLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [registerVisible, setRegisterVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sysRes, logRes] = await Promise.allSettled([
        apiClient.get('/integrations/systems'),
        apiClient.get('/integrations/sync-logs'),
      ]);
      if (sysRes.status === 'fulfilled') setSystems(sysRes.value.data?.systems || sysRes.value.data || []);
      if (logRes.status === 'fulfilled') setSyncLogs(logRes.value.data?.logs || logRes.value.data || []);
    } catch (err: any) {
      handleApiError(err, '加载集成数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const registerSystem = async (values: any) => {
    setSubmitting(true);
    try {
      await apiClient.post('/integrations/systems', values);
      showSuccess('系统注册成功');
      setRegisterVisible(false);
      form.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '注册失败');
    } finally {
      setSubmitting(false);
    }
  };

  const testConnection = async (system: any) => {
    try {
      await apiClient.post(`/integrations/systems/${system.system_id || system.id}/test`);
      showSuccess('连接测试成功');
    } catch (err: any) {
      handleApiError(err, '连接测试失败');
    }
  };

  const deleteSystem = async (system: any) => {
    try {
      await apiClient.delete(`/integrations/systems/${system.system_id || system.id}`);
      showSuccess('已删除');
      loadData();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  const systemColumns: ColumnsType<any> = [
    { title: '系统名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型', dataIndex: 'type', key: 'type',
      render: (v: string) => <Tag color={typeColor[v] || 'default'}>{typeLabel[v] || v || '-'}</Tag>,
    },
    { title: '接入地址', dataIndex: 'endpoint', key: 'endpoint', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v === 'active' ? '正常' : v === 'error' ? '异常' : v || '-'}</Tag>,
    },
    { title: '最后同步', dataIndex: 'last_sync', key: 'sync', render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<SyncOutlined />} onClick={() => testConnection(record)}>测试</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteSystem(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  const logColumns: ColumnsType<any> = [
    { title: '系统', dataIndex: 'system_name', key: 'system', render: (v: string) => v || '-' },
    { title: '同步类型', dataIndex: 'sync_type', key: 'type', render: (v: string) => <Tag>{v || '-'}</Tag> },
    { title: '记录数', dataIndex: 'record_count', key: 'count' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v === 'success' ? '成功' : '失败'}</Tag>,
    },
    { title: '时间', dataIndex: 'created_at', key: 'time' },
    { title: '错误信息', dataIndex: 'error_message', key: 'error', ellipsis: true, render: (v: string) => v || '-' },
  ];

  const tabItems = [
    {
      key: 'systems',
      label: '已接入系统',
      children: (
        <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterVisible(true)}>注册系统</Button>}>
          <Table columns={systemColumns} dataSource={systems} rowKey={(r, i) => r.system_id || r.id || String(i)} loading={loading} />
        </Card>
      ),
    },
    {
      key: 'logs',
      label: '同步日志',
      children: (
        <Card>
          <Table columns={logColumns} dataSource={syncLogs} rowKey={(r, i) => r.log_id || r.id || String(i)} loading={loading} />
        </Card>
      ),
    },
  ];

  return (
    <div>
      <Alert message="此页面管理与外部系统（POS、供应商、会员、预订）的数据同步集成，与企业集成配置页面互补" type="info" style={{ marginBottom: 16 }} />
      <Tabs items={tabItems} />

      <Modal title="注册外部系统" open={registerVisible} onCancel={() => { setRegisterVisible(false); form.resetFields(); }} onOk={() => form.submit()} okText="注册" confirmLoading={submitting}>
        <Form form={form} layout="vertical" onFinish={registerSystem}>
          <Form.Item name="name" label="系统名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="type" label="系统类型" rules={[{ required: true }]}>
            <Select>
              <Option value="pos">POS系统</Option>
              <Option value="supplier">供应商系统</Option>
              <Option value="member">会员系统</Option>
              <Option value="reservation">预订系统</Option>
            </Select>
          </Form.Item>
          <Form.Item name="endpoint" label="接入地址" rules={[{ required: true }]}><Input placeholder="https://..." /></Form.Item>
          <Form.Item name="api_key" label="API Key"><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default IntegrationsPage;
