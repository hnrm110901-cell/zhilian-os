import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Space, Statistic, Row, Col, Switch, Modal, Form, Input } from 'antd';
import { SendOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TextArea } = Input;

const WeChatTriggersPage: React.FC = () => {
  const [rules, setRules] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [testVisible, setTestVisible] = useState(false);
  const [manualVisible, setManualVisible] = useState(false);
  const [testForm] = Form.useForm();
  const [manualForm] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [toggleLoading, setToggleLoading] = useState<Record<string, boolean>>({});

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesRes, statsRes] = await Promise.allSettled([
        apiClient.get('/wechat/triggers/rules'),
        apiClient.get('/wechat/triggers/stats'),
      ]);
      if (rulesRes.status === 'fulfilled') setRules(rulesRes.value.data?.rules || rulesRes.value.data || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载触发规则失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const toggleRule = async (record: any, enabled: boolean) => {
    const key = record.event_type;
    setToggleLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.put(`/wechat/triggers/rules/${record.event_type}/toggle`, { enabled });
      showSuccess(enabled ? '已启用' : '已禁用');
      loadData();
    } catch (err: any) {
      handleApiError(err, '操作失败');
    } finally {
      setToggleLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const testTrigger = async (values: any) => {
    setSubmitting(true);
    try {
      await apiClient.post('/wechat/triggers/test', {
        event_type: values.event_type,
        event_data: JSON.parse(values.event_data || '{}'),
        store_id: values.store_id,
      });
      showSuccess('测试推送已发送');
      setTestVisible(false);
      testForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '测试失败');
    } finally {
      setSubmitting(false);
    }
  };

  const manualSend = async (values: any) => {
    setSubmitting(true);
    try {
      await apiClient.post('/wechat/triggers/manual-send', values);
      showSuccess('消息已发送');
      setManualVisible(false);
      manualForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '发送失败');
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<any> = [
    { title: '事件类型', dataIndex: 'event_type', key: 'event_type' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '消息模板', dataIndex: 'template', key: 'template', ellipsis: true },
    { title: '触发次数', dataIndex: 'trigger_count', key: 'trigger_count', render: (v: number) => v ?? 0 },
    {
      title: '状态', dataIndex: 'enabled', key: 'enabled',
      render: (v: boolean, record: any) => (
        <Switch checked={v} loading={toggleLoading[record.event_type]} onChange={(checked) => toggleRule(record, checked)} />
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="规则总数" value={rules.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="已启用" value={rules.filter((r: any) => r.enabled).length} /></Card></Col>
        <Col span={6}><Card><Statistic title="总触发次数" value={stats?.total_triggers ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="成功率" suffix="%" value={((stats?.success_rate || 0) * 100).toFixed(1)} /></Card></Col>
      </Row>

      <Card
        title="微信推送触发规则"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button icon={<SendOutlined />} onClick={() => setTestVisible(true)}>测试推送</Button>
            <Button type="primary" icon={<SendOutlined />} onClick={() => setManualVisible(true)}>手动发送</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={rules} rowKey={(r) => r.event_type} loading={loading} />
      </Card>

      <Modal title="测试触发推送" open={testVisible} onCancel={() => setTestVisible(false)} onOk={() => testForm.submit()} okText="发送" confirmLoading={submitting}>
        <Form form={testForm} layout="vertical" onFinish={testTrigger}>
          <Form.Item name="event_type" label="事件类型" rules={[{ required: true }]}><Input placeholder="如 order.created" /></Form.Item>
          <Form.Item name="event_data" label="事件数据（JSON）" initialValue="{}"><TextArea rows={3} /></Form.Item>
          <Form.Item name="store_id" label="门店ID"><Input placeholder="可选" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="手动发送消息" open={manualVisible} onCancel={() => setManualVisible(false)} onOk={() => manualForm.submit()} okText="发送" confirmLoading={submitting}>
        <Form form={manualForm} layout="vertical" onFinish={manualSend}>
          <Form.Item name="content" label="消息内容" rules={[{ required: true }]}><TextArea rows={4} /></Form.Item>
          <Form.Item name="touser" label="接收用户（| 分隔）"><Input /></Form.Item>
          <Form.Item name="toparty" label="接收部门（| 分隔）"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WeChatTriggersPage;
