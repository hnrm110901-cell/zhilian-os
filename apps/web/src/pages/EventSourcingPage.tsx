import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Select, InputNumber, Modal } from 'antd';
import { ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;

const statusColor: Record<string, string> = { completed: 'green', processing: 'blue', failed: 'red', pending: 'orange' };

const EventSourcingPage: React.FC = () => {
  const [events, setEvents] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [eventType] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [hours, setHours] = useState(24);
  const [chainVisible, setChainVisible] = useState(false);
  const [chainData, setChainData] = useState<any>(null);
  const [chainLoading, setChainLoading] = useState(false);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { hours, limit: 100 };
      if (eventType) params.event_type = eventType;
      if (statusFilter) params.status = statusFilter;
      const [eventsRes, statsRes] = await Promise.allSettled([
        apiClient.get(`/event-sourcing/events/${selectedStore}`, { params }),
        apiClient.get(`/event-sourcing/stats/${selectedStore}`, { params: { hours } }),
      ]);
      if (eventsRes.status === 'fulfilled') setEvents(eventsRes.value.data?.events || eventsRes.value.data || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载事件数据失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore, eventType, statusFilter, hours]);

  useEffect(() => { loadStores(); loadEvents(); }, [loadStores, loadEvents]);

  const viewChain = async (record: any) => {
    setChainLoading(true);
    setChainVisible(true);
    try {
      const res = await apiClient.get(`/event-sourcing/events/${selectedStore}/${record.event_id || record.id}`);
      setChainData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载处理链失败');
    } finally {
      setChainLoading(false);
    }
  };

  const columns: ColumnsType<any> = [
    { title: '事件ID', dataIndex: 'event_id', key: 'event_id', ellipsis: true, width: 200 },
    { title: '事件类型', dataIndex: 'event_type', key: 'event_type' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v}</Tag> },
    { title: '处理时间', dataIndex: 'processed_at', key: 'processed_at', ellipsis: true },
    { title: '耗时(ms)', dataIndex: 'duration_ms', key: 'duration_ms', render: (v: number) => v ?? '-' },
    {
      title: '操作', key: 'actions', width: 80,
      render: (_: any, record: any) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => viewChain(record)}>处理链</Button>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="总事件数" value={stats?.total ?? events.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="已完成" value={stats?.completed ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="处理中" value={stats?.processing ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="失败" value={stats?.failed ?? 0} /></Card></Col>
      </Row>

      <Card
        title="神经系统事件溯源"
        extra={
          <Space>
            <span>门店：</span>
            <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 140 }}>
              {stores.length > 0 ? stores.map((s: any) => (
                <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
              )) : <Option value="STORE001">STORE001</Option>}
            </Select>
            <span>状态：</span>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 110 }} allowClear placeholder="全部">
              <Option value="completed">已完成</Option>
              <Option value="processing">处理中</Option>
              <Option value="failed">失败</Option>
              <Option value="pending">等待中</Option>
            </Select>
            <span>时间范围：</span>
            <InputNumber value={hours} onChange={(v) => setHours(v || 24)} min={1} max={720} addonAfter="小时" style={{ width: 120 }} />
            <Button icon={<ReloadOutlined />} onClick={loadEvents}>刷新</Button>
          </Space>
        }
      >
        <Table columns={columns} dataSource={events} rowKey={(r) => r.event_id || r.id} loading={loading} pagination={{ pageSize: 20 }} />
      </Card>

      <Modal
        title="事件处理链"
        open={chainVisible}
        onCancel={() => setChainVisible(false)}
        footer={null}
        width={700}
      >
        {chainLoading ? <Card loading /> : chainData ? (
          <div>
            <p><strong>事件ID：</strong>{chainData.event_id}</p>
            <p><strong>类型：</strong>{chainData.event_type}</p>
            <p><strong>状态：</strong><Tag color={statusColor[chainData.status] || 'default'}>{chainData.status}</Tag></p>
            <p><strong>处理步骤：</strong></p>
            <Table
              size="small"
              dataSource={chainData.processing_chain || []}
              rowKey={(_r, i) => String(i)}
              columns={[
                { title: '步骤', dataIndex: 'step', key: 'step' },
                { title: '处理器', dataIndex: 'processor', key: 'processor' },
                { title: '结果', dataIndex: 'result', key: 'result', ellipsis: true },
              ]}
              pagination={false}
            />
          </div>
        ) : null}
      </Modal>
    </div>
  );
};

export default EventSourcingPage;
