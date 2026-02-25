import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Tabs, Table, Tag, Space, Select,
  Button, Form, Input, InputNumber, Spin, Typography, Badge, Descriptions, Modal, message
} from 'antd';
import {
  CloudOutlined, WifiOutlined, SyncOutlined, DatabaseOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import { apiClient, handleApiError, showSuccess } from '../utils/api';

const { Title, Text } = Typography;
const { Option } = Select;

interface EdgeMode { store_id: string; mode: string; }
interface NetworkStatus { store_id: string; is_connected: boolean; latency_ms: number; }
interface CacheInfo { store_id: string; cache_size: number; pending_sync: number; cache_keys: string[]; }

const modeColor: Record<string, string> = { online: 'green', offline: 'orange', hybrid: 'blue' };
const modeLabel: Record<string, string> = { online: '在线', offline: '离线', hybrid: '混合' };

const EdgeNodePage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [storeId, setStoreId] = useState('STORE001');
  const [edgeMode, setEdgeMode] = useState<EdgeMode | null>(null);
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus | null>(null);
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [offlineForm] = Form.useForm();
  const [offlineResult, setOfflineResult] = useState<Record<string, unknown> | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [modeRes, cacheRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/edge/mode/${storeId}`),
        apiClient.get(`/api/v1/edge/cache/${storeId}`),
      ]);
      if (modeRes.status === 'fulfilled') setEdgeMode(modeRes.value.data);
      if (cacheRes.status === 'fulfilled') setCacheInfo(cacheRes.value.data);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSetMode = async (mode: string) => {
    try {
      await apiClient.post('/api/v1/edge/mode/set', { mode, store_id: storeId });
      showSuccess(`已切换到${modeLabel[mode]}模式`);
      loadData();
    } catch (err) { handleApiError(err); }
  };

  const handleNetworkStatus = async (isConnected: boolean) => {
    try {
      const res = await apiClient.post('/api/v1/edge/network/status', {
        store_id: storeId, is_connected: isConnected, latency_ms: isConnected ? 50 : null,
      });
      setNetworkStatus(res.data);
      showSuccess('网络状态已更新');
    } catch (err) { handleApiError(err); }
  };

  const handleSync = async () => {
    setSyncLoading(true);
    try {
      const res = await apiClient.post('/api/v1/edge/sync', { store_id: storeId });
      showSuccess(`同步完成，共同步 ${res.data.synced_operations} 条操作`);
      loadData();
    } catch (err) { handleApiError(err); }
    finally { setSyncLoading(false); }
  };

  const handleOfflineExecute = async (values: Record<string, unknown>) => {
    try {
      const res = await apiClient.post('/api/v1/edge/offline/execute', {
        store_id: storeId, ...values,
      });
      setOfflineResult(res.data.result);
      showSuccess('离线操作执行成功');
    } catch (err) { handleApiError(err); }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>边缘节点管理</Title>
          <Space>
            <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
              <Option value="STORE001">门店 001</Option>
              <Option value="STORE002">门店 002</Option>
              <Option value="STORE003">门店 003</Option>
            </Select>
            <Button icon={<SyncOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        </div>

        <Row gutter={16}>
          <Col span={8}>
            <Card title="运行模式" extra={
              edgeMode && <Tag color={modeColor[edgeMode.mode]}>{modeLabel[edgeMode.mode]}</Tag>
            }>
              <Space>
                {['online', 'offline', 'hybrid'].map(m => (
                  <Button
                    key={m}
                    type={edgeMode?.mode === m ? 'primary' : 'default'}
                    onClick={() => handleSetMode(m)}
                  >
                    {modeLabel[m]}
                  </Button>
                ))}
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card title="网络状态">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <Badge status={networkStatus?.is_connected ? 'success' : 'error'} />
                  <Text>{networkStatus?.is_connected ? '已连接' : '未连接'}</Text>
                  {networkStatus?.latency_ms && <Text type="secondary">延迟: {networkStatus.latency_ms}ms</Text>}
                </Space>
                <Space>
                  <Button size="small" type="primary" onClick={() => handleNetworkStatus(true)}>模拟上线</Button>
                  <Button size="small" danger onClick={() => handleNetworkStatus(false)}>模拟断线</Button>
                </Space>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card title="缓存状态">
              {cacheInfo && (
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="缓存大小">{cacheInfo.cache_size} 条</Descriptions.Item>
                  <Descriptions.Item label="待同步">{cacheInfo.pending_sync} 条</Descriptions.Item>
                  <Descriptions.Item label="缓存键数">{cacheInfo.cache_keys?.length || 0}</Descriptions.Item>
                </Descriptions>
              )}
              <Button
                icon={<SyncOutlined spin={syncLoading} />}
                loading={syncLoading}
                onClick={handleSync}
                style={{ marginTop: 8 }}
                block
              >
                立即同步
              </Button>
            </Card>
          </Col>
        </Row>

        <Card title="离线操作执行">
          <Row gutter={24}>
            <Col span={12}>
              <Form form={offlineForm} layout="vertical" onFinish={handleOfflineExecute}>
                <Form.Item name="operation_type" label="操作类型" rules={[{ required: true }]}>
                  <Select placeholder="选择操作类型">
                    <Option value="order_create">创建订单</Option>
                    <Option value="inventory_update">更新库存</Option>
                    <Option value="member_checkin">会员签到</Option>
                    <Option value="payment_record">记录支付</Option>
                  </Select>
                </Form.Item>
                <Form.Item name="data" label="操作数据（JSON）" rules={[{ required: true }]}>
                  <Input.TextArea rows={4} placeholder='{"key": "value"}' />
                </Form.Item>
                <Button type="primary" htmlType="submit" icon={<ThunderboltOutlined />}>执行离线操作</Button>
              </Form>
            </Col>
            <Col span={12}>
              {offlineResult && (
                <Card size="small" title="执行结果" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
                  <pre style={{ fontSize: 12, margin: 0 }}>{JSON.stringify(offlineResult, null, 2)}</pre>
                </Card>
              )}
            </Col>
          </Row>
        </Card>
      </Space>
    </Spin>
  );
};

export default EdgeNodePage;
