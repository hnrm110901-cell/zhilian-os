import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Form, Input, Select, Modal, Alert, InputNumber, Statistic, Row, Col, Tooltip } from 'antd';
import { PlusOutlined, SyncOutlined, ReloadOutlined, PlayCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const SYSTEMS = ['tiancai', 'meituan', 'aoqiwei', 'pinzhi', 'yiding'];
const systemLabel: Record<string, string> = { tiancai: '天财商龙', meituan: '美团', aoqiwei: '奥琦玮', pinzhi: '品智', yiding: '易订' };

interface AdapterItem {
  adapter_name: string;
  status?: string;
  registered_at?: string;
  last_sync?: string;
}

interface AdapterStatusItem {
  adapter: string;
  status: string;
  last_sync: string;
  error_rate: number;
  sync_count_today: number;
  last_error: string | null;
}

const AdaptersPage: React.FC = () => {
  const [adapters, setAdapters] = useState<AdapterItem[]>([]);
  const [adapterStatuses, setAdapterStatuses] = useState<AdapterStatusItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggeringSync, setTriggeringSync] = useState<Record<string, boolean>>({});
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
      const res = await apiClient.get('/api/adapters/adapters');
      setAdapters(res?.adapters || res || []);
    } catch (err) {
      handleApiError(err, '加载适配器列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAdapterStatuses = useCallback(async () => {
    try {
      const res = await apiClient.get<{ adapters: AdapterStatusItem[] }>('/api/v1/adapters/status');
      setAdapterStatuses(res.adapters ?? []);
    } catch {
      // fail silently — status endpoint may not be available
    }
  }, []);

  const triggerSync = async (adapterName: string, storeId = 'all') => {
    setTriggeringSync((prev) => ({ ...prev, [adapterName]: true }));
    try {
      await apiClient.post(`/api/v1/adapters/${adapterName}/${storeId}/trigger-sync?sync_type=all`);
      showSuccess(`${adapterName} 同步已触发`);
      await loadAdapterStatuses();
    } catch (err) {
      handleApiError(err, '触发同步失败');
    } finally {
      setTriggeringSync((prev) => ({ ...prev, [adapterName]: false }));
    }
  };

  useEffect(() => { loadAdapters(); loadAdapterStatuses(); }, [loadAdapters, loadAdapterStatuses]);

  const registerAdapter = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      let config: Record<string, unknown> = {};
      if (values.adapter_name === 'pinzhi') {
        config = {
          base_url: values.base_url,
          token: values.token,
          timeout: values.timeout ?? 30,
          retry_times: values.retry_times ?? 3,
          ...(values.ognid ? { ognid: values.ognid } : {}),
        };
      } else if (values.adapter_name === 'tiancai') {
        config = {
          app_id: values.app_id,
          app_secret: values.app_secret,
          timeout: values.timeout ?? 30,
          retry_times: values.retry_times ?? 3,
          ...(values.base_url ? { base_url: values.base_url } : {}),
          ...(values.store_id ? { store_id: values.store_id } : {}),
        };
      } else if (values.adapter_name === 'meituan') {
        config = {
          app_key: values.app_key,
          app_secret: values.app_secret,
          timeout: values.timeout ?? 30,
          retry_times: values.retry_times ?? 3,
          ...(values.base_url ? { base_url: values.base_url } : {}),
          ...(values.poi_id ? { poi_id: values.poi_id } : {}),
        };
      } else if (values.adapter_name === 'aoqiwei') {
        config = {
          app_key: values.app_key,
          app_secret: values.app_secret,
          timeout: values.timeout ?? 30,
          retry_times: values.retry_times ?? 3,
          ...(values.base_url ? { base_url: values.base_url } : {}),
        };
      } else if (values.adapter_name === 'yiding') {
        config = {
          base_url: values.base_url,
          app_id: values.app_id,
          app_secret: values.app_secret,
          timeout: values.timeout ?? 30,
          max_retries: values.retry_times ?? 3,
          ...(values.cache_ttl ? { cache_ttl: values.cache_ttl } : {}),
        };
      } else {
        try { config = JSON.parse(String(values.config ?? '{}')); } catch { config = {}; }
      }
      await apiClient.post('/api/adapters/register', { adapter_name: values.adapter_name, config });
      showSuccess('适配器注册成功');
      setRegisterVisible(false);
      registerForm.resetFields();
      setSelectedAdapter('');
      loadAdapters();
    } catch (err) {
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

  const submitSync = async (values: Record<string, unknown>) => {
    const key = `${syncType}-${values.source_system}`;
    setSyncLoading(prev => ({ ...prev, [key]: true }));
    setSyncSubmitting(true);
    try {
      if (syncType === 'all') {
        await apiClient.post(`/api/adapters/sync/all/${values.source_system}/${values.store_id}`);
      } else if (syncType === 'dishes') {
        await apiClient.post('/api/adapters/sync/dishes', { store_id: values.store_id, source_system: values.source_system });
      } else if (syncType === 'order') {
        await apiClient.post('/api/adapters/sync/order', { order_id: values.order_id, store_id: values.store_id, source_system: values.source_system });
      } else {
        await apiClient.post('/api/adapters/sync/inventory', { item_id: values.item_id, quantity: parseFloat(String(values.quantity)), target_system: values.source_system });
      }
      showSuccess('同步成功');
      setSyncVisible(false);
    } catch (err) {
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
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: AdapterItem) => (
        <Tooltip title="手动触发全量同步">
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={triggeringSync[record.adapter_name]}
            onClick={() => triggerSync(record.adapter_name)}
          >
            同步
          </Button>
        </Tooltip>
      ),
    },
  ];

  const statusColumns = [
    { title: '适配器', dataIndex: 'adapter', key: 'adapter', render: (v: string) => <Tag>{systemLabel[v] || v}</Tag> },
    {
      title: '健康状态', dataIndex: 'status', key: 'status',
      render: (v: string) => v === 'connected'
        ? <Tag icon={<CheckCircleOutlined />} color="success">正常</Tag>
        : <Tag icon={<ExclamationCircleOutlined />} color="error">异常</Tag>,
    },
    { title: '今日同步次数', dataIndex: 'sync_count_today', key: 'count' },
    {
      title: '错误率', dataIndex: 'error_rate', key: 'error',
      render: (v: number) => <Tag color={v > 0.1 ? 'red' : v > 0 ? 'orange' : 'green'}>{(v * 100).toFixed(1)}%</Tag>,
    },
    { title: '最后同步', dataIndex: 'last_sync', key: 'last_sync', ellipsis: true, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
  ];

  const syncTitle: Record<string, string> = { order: '同步订单', dishes: '同步菜品', inventory: '同步库存', all: '全量同步' };

  return (
    <div>
      {adapterStatuses.length > 0 && (
        <Card title="适配器健康状态" size="small" style={{ marginBottom: 12 }}
          extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadAdapterStatuses}>刷新</Button>}
        >
          <Row gutter={12} style={{ marginBottom: 12 }}>
            <Col span={6}>
              <Statistic title="已连接" value={adapterStatuses.filter(a => a.status === 'connected').length} suffix={`/ ${adapterStatuses.length}`} />
            </Col>
            <Col span={6}>
              <Statistic title="今日同步总次数" value={adapterStatuses.reduce((s, a) => s + a.sync_count_today, 0)} />
            </Col>
          </Row>
          <Table
            columns={statusColumns}
            dataSource={adapterStatuses}
            rowKey="adapter"
            size="small"
            pagination={false}
          />
        </Card>
      )}
      <Card
        title="第三方适配器管理"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadAdapters(); loadAdapterStatuses(); }}>刷新</Button>
            <Button icon={<SyncOutlined />} onClick={() => openSync('dishes')}>同步菜品</Button>
            <Button icon={<SyncOutlined />} onClick={() => openSync('all')}>全量同步</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterVisible(true)}>注册适配器</Button>
          </Space>
        }
      >
        <Alert message="支持天财商龙、美团、奥琦玮、品智、易订等第三方 POS/外卖/预订平台数据同步" type="info" style={{ marginBottom: 12 }} />
        <Table columns={columns} dataSource={adapters} rowKey={(r, i) => r.adapter_name || String(i)} loading={loading} />
      </Card>

      <Modal title="注册适配器" open={registerVisible} onCancel={() => { setRegisterVisible(false); setSelectedAdapter(''); registerForm.resetFields(); }} onOk={() => registerForm.submit()} okText="注册" confirmLoading={submitting}>
        <Form form={registerForm} layout="vertical" onFinish={registerAdapter}>
          <Form.Item name="adapter_name" label="适配器" rules={[{ required: true }]}>
            <Select onChange={v => setSelectedAdapter(v as string)}>
              {SYSTEMS.map(s => <Option key={s} value={s}>{systemLabel[s]}</Option>)}
            </Select>
          </Form.Item>
          {selectedAdapter === 'tiancai' && (
            <>
              <Form.Item name="app_id" label="应用ID（AppID）" rules={[{ required: true }]}>
                <Input placeholder="天财商龙开放平台申请的AppID" />
              </Form.Item>
              <Form.Item name="app_secret" label="应用密钥（AppSecret）" rules={[{ required: true }]}>
                <Input.Password placeholder="天财商龙开放平台申请的AppSecret" />
              </Form.Item>
              <Form.Item name="store_id" label="门店ID（留空则对接所有门店）">
                <Input placeholder="如：STORE001" />
              </Form.Item>
              <Form.Item name="base_url" label="API地址（选填）">
                <Input placeholder="默认：https://api.tiancai.com" />
              </Form.Item>
              <Form.Item name="timeout" label="超时（秒）" initialValue={30}>
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="retry_times" label="重试次数" initialValue={3}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {selectedAdapter === 'meituan' && (
            <>
              <Form.Item name="app_key" label="AppKey" rules={[{ required: true }]}>
                <Input placeholder="美团开放平台申请的AppKey" />
              </Form.Item>
              <Form.Item name="app_secret" label="AppSecret" rules={[{ required: true }]}>
                <Input.Password placeholder="美团开放平台申请的AppSecret" />
              </Form.Item>
              <Form.Item name="poi_id" label="门店POI ID（留空则对接所有门店）">
                <Input placeholder="美团门店唯一标识" />
              </Form.Item>
              <Form.Item name="base_url" label="API地址（选填）">
                <Input placeholder="默认：https://waimaiopen.meituan.com" />
              </Form.Item>
              <Form.Item name="timeout" label="超时（秒）" initialValue={30}>
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="retry_times" label="重试次数" initialValue={3}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {selectedAdapter === 'aoqiwei' && (
            <>
              <Form.Item name="app_key" label="AppKey" rules={[{ required: true }]}>
                <Input placeholder="奥琦玮开放平台申请的AppKey" />
              </Form.Item>
              <Form.Item name="app_secret" label="AppSecret" rules={[{ required: true }]}>
                <Input.Password placeholder="奥琦玮开放平台申请的AppSecret" />
              </Form.Item>
              <Form.Item name="base_url" label="API地址（选填）">
                <Input placeholder="默认：https://openapi.acescm.cn" />
              </Form.Item>
              <Form.Item name="timeout" label="超时（秒）" initialValue={30}>
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="retry_times" label="重试次数" initialValue={3}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {selectedAdapter === 'pinzhi' && (
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
          )}
          {selectedAdapter === 'yiding' && (
            <>
              <Form.Item name="base_url" label="API地址" rules={[{ required: true }]}>
                <Input placeholder="https://api.yiding.com" />
              </Form.Item>
              <Form.Item name="app_id" label="AppID" rules={[{ required: true }]}>
                <Input placeholder="易订开放平台申请的AppID" />
              </Form.Item>
              <Form.Item name="app_secret" label="AppSecret" rules={[{ required: true }]}>
                <Input.Password placeholder="易订开放平台申请的AppSecret" />
              </Form.Item>
              <Form.Item name="timeout" label="超时（秒）" initialValue={30}>
                <InputNumber min={5} max={120} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="retry_times" label="重试次数" initialValue={3}>
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="cache_ttl" label="缓存时间（秒，选填）">
                <InputNumber min={60} max={3600} style={{ width: '100%' }} placeholder="默认300" />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>

      <Modal title={syncTitle[syncType]} open={syncVisible} onCancel={() => setSyncVisible(false)} onOk={() => syncForm.submit()} okText="同步" confirmLoading={syncSubmitting}>
        <Form form={syncForm} layout="vertical" onFinish={submitSync}>
          <Form.Item name="source_system" label={syncType === 'inventory' ? '目标系统' : '来源系统'} rules={[{ required: true }]}>
            <Select>{SYSTEMS.map(s => <Option key={s} value={s}>{systemLabel[s]}</Option>)}</Select>
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
