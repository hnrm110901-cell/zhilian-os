import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Col, Row, Select, DatePicker, Tabs, Statistic, Table, Tag,
  Button, Space, Badge, Descriptions, Progress, Alert,
} from 'antd';
import { ReloadOutlined, SyncOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { RangePicker } = DatePicker;

const statusColor: Record<string, string> = {
  completed: 'green', pending: 'orange', cancelled: 'red', processing: 'blue',
};

const POSPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [inventory, setInventory] = useState<any[]>([]);
  const [salesSummary, setSalesSummary] = useState<any>(null);
  const [storeStatus, setStoreStatus] = useState<any>(null);
  const [queueData, setQueueData] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [dateRange, setDateRange] = useState<[string, string]>([
    dayjs().subtract(7, 'day').format('YYYY-MM-DD'),
    dayjs().format('YYYY-MM-DD'),
  ]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ord, inv, sales, status, queue, h] = await Promise.allSettled([
        apiClient.get('/pos/orders', { params: { store_id: selectedStore, start_date: dateRange[0], end_date: dateRange[1], limit: 100 } }),
        apiClient.get('/pos/inventory', { params: { store_id: selectedStore } }),
        apiClient.get('/pos/sales/summary', { params: { store_id: selectedStore, start_date: dateRange[0], end_date: dateRange[1] } }),
        apiClient.get(`/pos/stores/${selectedStore}/status`),
        apiClient.get('/pos/queue/current', { params: { store_id: selectedStore } }),
        apiClient.get('/pos/health', { params: { store_id: selectedStore } }),
      ]);
      if (ord.status === 'fulfilled') setOrders(ord.value.data?.data || []);
      if (inv.status === 'fulfilled') setInventory(inv.value.data?.data || []);
      if (sales.status === 'fulfilled') setSalesSummary(sales.value.data?.data || sales.value.data);
      if (status.status === 'fulfilled') setStoreStatus(status.value.data?.data || status.value.data);
      if (queue.status === 'fulfilled') setQueueData(queue.value.data?.data || queue.value.data);
      if (h.status === 'fulfilled') setHealth(h.value.data?.data || h.value.data);
    } catch (err: any) { handleApiError(err, '加载POS数据失败'); }
    finally { setLoading(false); }
  }, [selectedStore, dateRange]);

  const syncPOS = async (syncType = 'all') => {
    setSyncing(true);
    try {
      await apiClient.post('/pos/sync', null, { params: { store_id: selectedStore, sync_type: syncType } });
      showSuccess('同步完成');
      loadAll();
    } catch (err: any) { handleApiError(err, '同步失败'); }
    finally { setSyncing(false); }
  };

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadAll(); }, [loadAll]);

  const orderColumns: ColumnsType<any> = [
    { title: '订单号', dataIndex: 'order_id', key: 'order_id', ellipsis: true },
    { title: '金额', dataIndex: 'total_amount', key: 'total_amount', render: (v: number) => `¥${(v / 100).toFixed(2)}` },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v}</Tag> },
    { title: '支付方式', dataIndex: 'payment_method', key: 'payment_method', render: (v: string) => v || '-' },
    { title: '时间', dataIndex: 'order_time', key: 'order_time', render: (v: string) => v?.slice(0, 16) || '-' },
  ];

  const inventoryColumns: ColumnsType<any> = [
    { title: '商品名', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category', render: (v: string) => v || '-' },
    { title: '当前库存', dataIndex: 'current_stock', key: 'current_stock' },
    { title: '最低库存', dataIndex: 'min_stock', key: 'min_stock' },
    {
      title: '状态', key: 'stock_status',
      render: (_: any, r: any) => {
        if (r.current_stock === 0) return <Tag color="red">缺货</Tag>;
        if (r.current_stock <= r.min_stock) return <Tag color="orange">库存低</Tag>;
        return <Tag color="green">正常</Tag>;
      },
    },
  ];

  const invSummary = inventory.length > 0 ? {
    total: inventory.length,
    low: inventory.filter((i: any) => i.current_stock > 0 && i.current_stock <= i.min_stock).length,
    out: inventory.filter((i: any) => i.current_stock === 0).length,
  } : null;

  const tabItems = [
    {
      key: 'overview', label: '门店概览',
      children: (
        <Row gutter={16}>
          <Col span={12}>
            <Card size="small" title="门店状态" style={{ marginBottom: 12 }}>
              {storeStatus ? (
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="营业状态">
                    <Tag color={storeStatus.is_open ? 'green' : 'red'}>{storeStatus.is_open ? '营业中' : '已关闭'}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="当前订单">{storeStatus.active_orders ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="今日营收">¥{((storeStatus.today_revenue || 0) / 100).toFixed(2)}</Descriptions.Item>
                  <Descriptions.Item label="今日订单">{storeStatus.today_orders ?? '-'}</Descriptions.Item>
                </Descriptions>
              ) : <span style={{ color: '#999' }}>加载中...</span>}
            </Card>
            <Card size="small" title="系统健康">
              {health ? (
                <div>
                  <Tag color={health.status === 'healthy' ? 'green' : 'red'} style={{ marginBottom: 8 }}>
                    {health.status === 'healthy' ? '✅ 正常' : '❌ 异常'}
                  </Tag>
                  {health.message && <div style={{ color: '#666', fontSize: 12 }}>{health.message}</div>}
                </div>
              ) : <span style={{ color: '#999' }}>加载中...</span>}
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" title="销售汇总">
              {salesSummary ? (
                <Row gutter={8}>
                  <Col span={12}><Statistic title="总营收" value={((salesSummary.total_revenue || 0) / 100).toFixed(2)} prefix="¥" /></Col>
                  <Col span={12}><Statistic title="订单数" value={salesSummary.total_orders ?? '--'} /></Col>
                  <Col span={12} style={{ marginTop: 8 }}><Statistic title="均单价" value={((salesSummary.avg_order_value || 0) / 100).toFixed(2)} prefix="¥" /></Col>
                  <Col span={12} style={{ marginTop: 8 }}><Statistic title="退款数" value={salesSummary.refund_count ?? '--'} /></Col>
                </Row>
              ) : <span style={{ color: '#999' }}>加载中...</span>}
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'orders', label: `订单列表 (${orders.length})`,
      children: <Table columns={orderColumns} dataSource={orders} rowKey={(r, i) => `${r.order_id || i}`} loading={loading} size="small" />,
    },
    {
      key: 'inventory', label: (
        <span>
          库存状态
          {invSummary?.low ? <Badge count={invSummary.low} size="small" style={{ marginLeft: 4 }} /> : null}
        </span>
      ),
      children: (
        <div>
          {invSummary && (
            <Row gutter={12} style={{ marginBottom: 12 }}>
              <Col span={8}><Card size="small"><Statistic title="总品类" value={invSummary.total} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="库存低" value={invSummary.low} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
              <Col span={8}><Card size="small"><Statistic title="缺货" value={invSummary.out} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
            </Row>
          )}
          <Table columns={inventoryColumns} dataSource={inventory} rowKey={(r, i) => `${r.item_id || r.name || i}`} loading={loading} size="small" />
        </div>
      ),
    },
    {
      key: 'queue', label: '排队状态',
      children: queueData ? (
        <div>
          <Row gutter={12} style={{ marginBottom: 12 }}>
            <Col span={6}><Card size="small"><Statistic title="等待组数" value={queueData.stats?.waiting_groups ?? '--'} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="预计等待" value={queueData.stats?.estimated_wait_minutes ?? '--'} suffix="分钟" /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="今日叫号" value={queueData.stats?.total_called ?? '--'} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="放弃率" value={((queueData.stats?.abandon_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
          </Row>
          <Table
            columns={[
              { title: '号码', dataIndex: 'queue_number', key: 'queue_number' },
              { title: '人数', dataIndex: 'party_size', key: 'party_size' },
              { title: '等待时间', dataIndex: 'wait_minutes', key: 'wait_minutes', render: (v: number) => `${v}分钟` },
              { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag>{v}</Tag> },
            ]}
            dataSource={queueData.queues || []}
            rowKey={(r, i) => `${r.queue_number || i}`}
            size="small"
          />
        </div>
      ) : <span style={{ color: '#999' }}>暂无排队数据</span>,
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">STORE001</Option>}
        </Select>
        <RangePicker
          defaultValue={[dayjs().subtract(7, 'day'), dayjs()]}
          onChange={(_, ds) => ds[0] && ds[1] && setDateRange([ds[0], ds[1]])}
        />
        <Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>
        <Button icon={<SyncOutlined />} loading={syncing} onClick={() => syncPOS('all')}>同步POS数据</Button>
      </Space>

      <Card><Tabs items={tabItems} /></Card>
    </div>
  );
};

export default POSPage;
