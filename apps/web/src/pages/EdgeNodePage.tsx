import React, { useState, useEffect, useCallback } from 'react';
import { Form, Input, Select } from 'antd';
import { SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZSelect } from '../design-system/components';
import styles from './EdgeNodePage.module.css';

const { Option } = Select;

interface EdgeMode    { store_id: string; mode: string; }
interface NetworkStatus { store_id: string; is_connected: boolean; latency_ms: number; }
interface CacheInfo   { store_id: string; cache_size: number; pending_sync: number; cache_keys: string[]; }

const modeBadgeType: Record<string, 'success' | 'warning' | 'info'> = {
  online:  'success',
  offline: 'warning',
  hybrid:  'info',
};
const modeLabel: Record<string, string> = {
  online:  '在线',
  offline: '离线',
  hybrid:  '混合',
};

const EdgeNodePage: React.FC = () => {
  const [loading, setLoading]         = useState(false);
  const [storeId, setStoreId]         = useState('STORE001');
  const [stores, setStores]           = useState<any[]>([]);
  const [edgeMode, setEdgeMode]       = useState<EdgeMode | null>(null);
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus | null>(null);
  const [cacheInfo, setCacheInfo]     = useState<CacheInfo | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [offlineForm]                 = Form.useForm();
  const [offlineResult, setOfflineResult] = useState<Record<string, unknown> | null>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.stores || res || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [modeRes, cacheRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/edge/mode/${storeId}`),
        apiClient.get(`/api/v1/edge/cache/${storeId}`),
      ]);
      if (modeRes.status === 'fulfilled') setEdgeMode(modeRes.value);
      if (cacheRes.status === 'fulfilled') setCacheInfo(cacheRes.value);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [storeId]);

  useEffect(() => { loadStores(); loadData(); }, [loadStores, loadData]);

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
      setNetworkStatus(res);
      showSuccess('网络状态已更新');
    } catch (err) { handleApiError(err); }
  };

  const handleSync = async () => {
    setSyncLoading(true);
    try {
      const res = await apiClient.post('/api/v1/edge/sync', { store_id: storeId });
      showSuccess(`同步完成，共同步 ${res.synced_operations} 条操作`);
      loadData();
    } catch (err) { handleApiError(err); }
    finally { setSyncLoading(false); }
  };

  const handleOfflineExecute = async (values: Record<string, unknown>) => {
    try {
      const res = await apiClient.post('/api/v1/edge/offline/execute', {
        store_id: storeId, ...values,
      });
      setOfflineResult(res.result);
      showSuccess('离线操作执行成功');
    } catch (err) { handleApiError(err); }
  };

  const storeOptions = stores.length > 0
    ? stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id }))
    : [{ value: 'STORE001', label: '门店 001' }];

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <h2 className={styles.pageTitle}>边缘节点管理</h2>
        <div className={styles.headerActions}>
          <ZSelect
            value={storeId}
            options={storeOptions}
            onChange={(v) => setStoreId(v as string)}
            style={{ width: 160 }}
          />
          <ZButton icon={<SyncOutlined />} onClick={loadData}>刷新</ZButton>
        </div>
      </div>

      {loading ? (
        <ZSkeleton rows={4} block />
      ) : (
        <>
          {/* 状态卡片行 */}
          <div className={styles.statusGrid}>
            {/* 运行模式 */}
            <ZCard title="运行模式" extra={
              edgeMode && <ZBadge type={modeBadgeType[edgeMode.mode]} text={modeLabel[edgeMode.mode]} />
            }>
              <div className={styles.modeButtons}>
                {(['online', 'offline', 'hybrid'] as const).map(m => (
                  <ZButton
                    key={m}
                    variant={edgeMode?.mode === m ? 'primary' : 'default'}
                    onClick={() => handleSetMode(m)}
                  >
                    {modeLabel[m]}
                  </ZButton>
                ))}
              </div>
            </ZCard>

            {/* 网络状态 */}
            <ZCard title="网络状态">
              <div className={styles.networkRow}>
                <ZBadge
                  type={networkStatus?.is_connected ? 'success' : 'critical'}
                  text={networkStatus?.is_connected ? '已连接' : '未连接'}
                />
                {networkStatus?.latency_ms && (
                  <span className={styles.latency}>延迟: {networkStatus.latency_ms}ms</span>
                )}
              </div>
              <div className={styles.networkButtons}>
                <ZButton variant="primary" onClick={() => handleNetworkStatus(true)}>模拟上线</ZButton>
                <ZButton
                  onClick={() => handleNetworkStatus(false)}
                  style={{ color: 'var(--red)', borderColor: 'var(--red)' }}
                >
                  模拟断线
                </ZButton>
              </div>
            </ZCard>

            {/* 缓存状态 */}
            <ZCard title="缓存状态">
              {cacheInfo && (
                <dl className={styles.descList}>
                  <div className={styles.descRow}><dt>缓存大小</dt><dd>{cacheInfo.cache_size} 条</dd></div>
                  <div className={styles.descRow}><dt>待同步</dt><dd>{cacheInfo.pending_sync} 条</dd></div>
                  <div className={styles.descRow}><dt>缓存键数</dt><dd>{cacheInfo.cache_keys?.length || 0}</dd></div>
                </dl>
              )}
              <ZButton
                icon={<SyncOutlined spin={syncLoading} />}
                disabled={syncLoading}
                onClick={handleSync}
                style={{ marginTop: 12, width: '100%' }}
              >
                立即同步
              </ZButton>
            </ZCard>
          </div>

          {/* 离线操作执行 */}
          <ZCard title="离线操作执行" style={{ marginTop: 14 }}>
            <div className={styles.offlineGrid}>
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
                <ZButton variant="primary" icon={<ThunderboltOutlined />} onClick={() => offlineForm.submit()}>
                  执行离线操作
                </ZButton>
              </Form>

              {offlineResult && (
                <ZCard style={{ background: 'rgba(26,122,82,0.08)', borderColor: 'rgba(26,122,82,0.3)' }} title="执行结果">
                  <pre className={styles.resultPre}>{JSON.stringify(offlineResult, null, 2)}</pre>
                </ZCard>
              )}
            </div>
          </ZCard>
        </>
      )}
    </div>
  );
};

export default EdgeNodePage;
