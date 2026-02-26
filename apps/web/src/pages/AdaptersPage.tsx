import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Form, Input, Select, Modal, Alert, InputNumber } from 'antd';
import { PlusOutlined, SyncOutlined, ReloadOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const SYSTEMS = ['tiancai', 'meituan', 'aoqiwei', 'pinzhi'];
const systemLabel: Record<string, string> = { tiancai: '天才', meituan: '美团', aoqiwei: '傲旗威', pinzhi: '品智' };

const AdaptersPage: React.FC = () => {
  const [adapters, setAdapters] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [registerVisible, setRegisterVisible] = useState(false);
  const [, setSyncLoading] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [syncSubmitting, setSyncSubmitting] = useState(false);
  const [registerForm] = Form.useForm();
  const [syncForm] = Form.useForm();
  const [syncVisible, setSyncVisible] = useState(false);
  const [syncType, setSyncType] = useState<'order' | 'dishes' | 'inventory' | 'all'>('all');
  const [selectedAdapter, setSelectedAdapter] = useState<string>('');

  const loadAdapters = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/adapters/adapters');
      setAdapters(res.data?.adapters || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载适配器列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAdapters(); }, [loadAdapters]);

  const registerAdapter = async (values: any) => {
    setSubmitting(true);
    try {
      let config: any = {};
      if (values.adapter_name === 'pinzhi') {
        config = {
          base_url: values.base_url,
          token: values.token,
          timeout: values.timeout ?? 30,
          retry_times: values.retry_times ?? 3,
          ...(values.ognid ? { ognid: values.ognid } : {}),
        };
      } else {
        try { config = JSON.parse(values.config || '{}'); } catch { config = {}; }
      }
      await apiClient.post('/adapters/register', { adapter_name: values.adapter_name, config });
      showSuccess('适配器注册成功');
      setRegisterVisible(false);
      registerForm.resetFields();
      setSelectedAdapter('');
      loadAdapters();
    } catch (err: any) {
      handleApiError(err, '注册失败');
    } finally {
      setSubmitting(false);
    }
  };

  const openSync = (type: 'order' | 'dishes' | 'inventory' | 'all') => {
    setSyncType(type);
    syncForm.resetFields();
    setSyncVisible(true);
  };

  const submitSync = async (values: any) => {
    const key = `${syncType}-${values.source_system}`;
    setSyncLoading(prev => ({ ...prev, [key]: true }));
    setSyncSubmitting(true);
    try {
      if (syncType === 'all') {
        await apiClient.post(`/adapters/sync/all/${values.source_system}/${values.store_id}`);
      } else if (syncType === 'dishes') {
        await apiClient.post('/adapters/sync/dishes', { store_id: values.store_id, source_system: values.source_system });
      } else if (syncType === 'order') {
        await apiClient.post('/adapters/sync/order', { order_id: values.order_id, store_id: values.store_id, source_system: values.source_system });
      } else {
        await apiClient.post('/adapters/sync/inventory', { item_id: values.item_id, quantity: parseFloat(values.quantity), target_system: values.source_system });
      }
      showSuccess('同步成功');
      setSyncVisible(false);
    } catch (err: any) {
      handleApiError(err, '同步失败');
    } finally {
      setSyncLoading(prev => ({ ...prev, [key]: false }));
      setSyncSubmitting(false);
    }
  };

  const columns = [
    { title: '适配器名称', dataIndex: 'adapter_name', key: 'adapter_name', render: (v: string) => <Tag>{systemLabel[v] || v}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'active' ? 'green' : 'orange'}>{v === 'active' ? '已激活' : v || '-'}</Tag> },
    { title: '注册时间', dataIndex: 'registered_at', key: 'registered_at', ellipsis: true },
    { title: '最后同步', dataIndex: 'last_sync', key: 'last_sync', ellipsis: true },
  ];

  const syncTitle: Record<string, string> = { order: '同步订单', dishes: '同步菜品', inventory: '同步库存', all: '全量同步' };

  return (
    <div>
      <Card
        title="第三方适配器管理"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadAdapters}>刷新</Button>
            <Button icon={<SyncOutlined />} onClick={() => openSync('dishes')}>同步菜品</Button>
            <Button icon={<SyncOutlined />} onClick={() => openSync('all')}>全量同步</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterVisible(true)}>注册适配器</Button>
          </Space>
        }
      >
        <Alert message="支持天才、美团、傲旗威、品智等第三方 POS/外卖平台数据同步" type="info" style={{ marginBottom: 12 }} />
        <Table columns={columns} dataSource={adapters} rowKey={(r, i) => r.adapter_name || String(i)} loading={loading} />
      </Card>

      <Modal title="注册适配器" open={registerVisible} onCancel={() => { setRegisterVisible(false); setSelectedAdapter(''); registerForm.resetFields(); }} onOk={() => registerForm.submit()} okText="注册" confirmLoading={submitting}>
        <Form form={registerForm} layout="vertical" onFinish={registerAdapter}>
          <Form.Item name="adapter_name" label="适配器" rules={[{ required: true }]}>
            <Select onChange={v => setSelectedAdapter(v as string)}>
              {SYSTEMS.map(s => <Option key={s} value={s}>{systemLabel[s]}</Option>)}
            </Select>
          </Form.Item>
          {selectedAdapter === 'pinzhi' ? (
            <>
              <Form.Item name="base_url" label="API地址" rules={[{ required: true }]}>
                <Input placeholder="http://ip:port/pzcatering-gateway" />
              </Form.Item>
              <Form.Item name="token" label="商户Token" rules={[{ required: true }]}>
                <Input.Password placeholder="品智客户运维系统申请的Token" />
              </Form.Item>
              <Form.Item name="ognid" label="门店omsID（留空则对接所有门店）">
                <Input placeholder="如：12345" />
              </Form.Item>
              <Form.Item name="timeout" label="超时（秒）" initialValue={30}>
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="retry_times" label="重试次数" initialValue={3}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </>
          ) : (
            <Form.Item name="config" label="配置（JSON）" initialValue="{}">
              <TextArea rows={4} placeholder='{"api_key": "xxx", "store_id": "yyy"}' />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal title={syncTitle[syncType]} open={syncVisible} onCancel={() => setSyncVisible(false)} onOk={() => syncForm.submit()} okText="同步" confirmLoading={syncSubmitting}>
        <Form form={syncForm} layout="vertical" onFinish={submitSync}>
          <Form.Item name="source_system" label={syncType === 'inventory' ? '目标系统' : '来源系统'} rules={[{ required: true }]}>
            <Select>{['tiancai', 'meituan'].map(s => <Option key={s} value={s}>{systemLabel[s]}</Option>)}</Select>
          </Form.Item>
          <Form.Item name="store_id" label="门店ID" rules={[{ required: syncType !== 'inventory' }]}><Input /></Form.Item>
          {syncType === 'order' && <Form.Item name="order_id" label="订单ID" rules={[{ required: true }]}><Input /></Form.Item>}
          {syncType === 'inventory' && (
            <>
              <Form.Item name="item_id" label="商品ID" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="quantity" label="数量" rules={[{ required: true }]}><Input type="number" /></Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default AdaptersPage;
