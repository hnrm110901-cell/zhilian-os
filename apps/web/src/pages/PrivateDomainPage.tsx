import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Card, Col, Row, Select, Tabs, Statistic, Table, Tag, Button,
  Progress, Alert, Space, Badge, Modal, Form, Input, InputNumber,
} from 'antd';
import {
  UserOutlined, WarningOutlined, RocketOutlined,
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const rfmColor: Record<string, string> = {
  S1: 'gold', S2: 'blue', S3: 'orange', S4: 'volcano', S5: 'red',
};
const rfmLabel: Record<string, string> = {
  S1: '高价值', S2: '潜力', S3: '沉睡', S4: '流失预警', S5: '流失',
};
const signalColor: Record<string, string> = {
  consumption: 'green', churn_risk: 'red', bad_review: 'volcano',
  holiday: 'blue', competitor: 'orange', viral: 'purple',
};
const signalLabel: Record<string, string> = {
  consumption: '消费信号', churn_risk: '流失预警', bad_review: '差评信号',
  holiday: '节日', competitor: '竞品动态', viral: '裂变触发',
};
const quadrantIcon: Record<string, string> = {
  benchmark: '🏆', defensive: '🛡️', potential: '🚀', breakthrough: '⚔️',
};
const quadrantLabel: Record<string, string> = {
  benchmark: '标杆门店', defensive: '防守门店', potential: '潜力门店', breakthrough: '突围门店',
};
const journeyLabel: Record<string, string> = {
  new_customer: '新客激活', vip_retention: 'VIP保鲜',
  reactivation: '沉睡唤醒', review_repair: '差评修复',
};

const PrivateDomainPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [dashboard, setDashboard] = useState<any>(null);
  const [rfmData, setRfmData] = useState<any[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [journeys, setJourneys] = useState<any[]>([]);
  const [churnRisks, setChurnRisks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [reviewModal, setReviewModal] = useState(false);
  const [journeyModal, setJourneyModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, rfm, sig, jrn, churn] = await Promise.allSettled([
        apiClient.get(`/private-domain/dashboard/${selectedStore}`),
        apiClient.get(`/private-domain/rfm/${selectedStore}`),
        apiClient.get(`/private-domain/signals/${selectedStore}`, { params: { limit: 30 } }),
        apiClient.get(`/private-domain/journeys/${selectedStore}`),
        apiClient.get(`/private-domain/churn-risks/${selectedStore}`),
      ]);
      if (dash.status === 'fulfilled') setDashboard(dash.value.data);
      if (rfm.status === 'fulfilled') setRfmData(rfm.value.data?.segments || []);
      if (sig.status === 'fulfilled') setSignals(sig.value.data?.signals || []);
      if (jrn.status === 'fulfilled') setJourneys(jrn.value.data?.journeys || []);
      if (churn.status === 'fulfilled') setChurnRisks(churn.value.data?.users || []);
    } catch (err: any) { handleApiError(err, '加载私域数据失败'); }
    finally { setLoading(false); }
  }, [selectedStore]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => {
    loadAll();
    intervalRef.current = setInterval(loadAll, 60000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadAll]);

  const triggerJourney = async (values: any) => {
    try {
      await apiClient.post(`/private-domain/journeys/${selectedStore}/trigger`, values);
      showSuccess('旅程已触发');
      setJourneyModal(false);
      loadAll();
    } catch (err: any) { handleApiError(err, '触发旅程失败'); }
  };

  const processReview = async (values: any) => {
    try {
      await apiClient.post(`/private-domain/reviews/${selectedStore}/process`, values);
      showSuccess('差评修复旅程已启动');
      setReviewModal(false);
      loadAll();
    } catch (err: any) { handleApiError(err, '处理差评失败'); }
  };

  // RFM 饼图
  const rfmDist = dashboard?.rfm_distribution || {};
  const rfmPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: Object.entries(rfmDist).map(([k, v]) => ({
        name: `${k} ${rfmLabel[k] || k}`, value: v,
        itemStyle: { color: { S1: '#faad14', S2: '#1890ff', S3: '#fa8c16', S4: '#ff4d4f', S5: '#cf1322' }[k] || '#999' },
      })),
    }],
  };

  const rfmColumns: ColumnsType<any> = [
    { title: '用户ID', dataIndex: 'customer_id', key: 'customer_id' },
    { title: 'RFM层级', dataIndex: 'rfm_level', key: 'rfm_level', render: (v: string) => <Tag color={rfmColor[v]}>{rfmLabel[v] || v}</Tag> },
    { title: '最近消费', dataIndex: 'recency_days', key: 'recency_days', render: (v: number) => `${v}天前`, sorter: (a: any, b: any) => a.recency_days - b.recency_days },
    { title: '频次', dataIndex: 'frequency', key: 'frequency', sorter: (a: any, b: any) => a.frequency - b.frequency },
    { title: '消费金额', dataIndex: 'monetary', key: 'monetary', render: (v: number) => `¥${(v / 100).toFixed(0)}`, sorter: (a: any, b: any) => a.monetary - b.monetary },
    { title: '流失风险', dataIndex: 'risk_score', key: 'risk_score', render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" status={v >= 0.7 ? 'exception' : v >= 0.4 ? 'normal' : 'success'} /> },
    { title: '标签', dataIndex: 'dynamic_tags', key: 'dynamic_tags', render: (tags: string[]) => tags?.map(t => <Tag key={t}>{t}</Tag>) },
    {
      title: '操作', key: 'actions', render: (_: any, record: any) => (
        <Button size="small" onClick={() => { setSelectedUser(record); setJourneyModal(true); }}>触发旅程</Button>
      ),
    },
  ];

  const signalColumns: ColumnsType<any> = [
    { title: '信号类型', dataIndex: 'signal_type', key: 'signal_type', render: (v: string) => <Tag color={signalColor[v]}>{signalLabel[v] || v}</Tag> },
    { title: '用户', dataIndex: 'customer_id', key: 'customer_id', render: (v: string) => v || '-' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '严重程度', dataIndex: 'severity', key: 'severity', render: (v: string) => <Tag color={{ low: 'green', medium: 'orange', high: 'red', critical: 'purple' }[v] || 'default'}>{v}</Tag> },
    { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at', render: (v: string) => v?.slice(0, 16) },
    { title: '已处理', dataIndex: 'action_taken', key: 'action_taken', render: (v: string) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> },
  ];

  const journeyColumns: ColumnsType<any> = [
    { title: '旅程类型', dataIndex: 'journey_type', key: 'journey_type', render: (v: string) => journeyLabel[v] || v },
    { title: '用户', dataIndex: 'customer_id', key: 'customer_id' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={{ running: 'blue', completed: 'green', pending: 'orange', failed: 'red' }[v] || 'default'}>{v}</Tag> },
    { title: '进度', key: 'progress', render: (_: any, r: any) => <Progress percent={Math.round((r.current_step / r.total_steps) * 100)} size="small" /> },
    { title: '下次触达', dataIndex: 'next_action_at', key: 'next_action_at', render: (v: string) => v?.slice(0, 16) || '-' },
  ];

  const quadrant = dashboard?.store_quadrant || 'potential';

  const tabItems = [
    {
      key: 'overview', label: '运营概览',
      children: (
        <Row gutter={16}>
          <Col span={10}>
            <Card title="RFM用户分层" size="small">
              <ReactECharts option={rfmPieOption} style={{ height: 280 }} />
            </Card>
          </Col>
          <Col span={14}>
            <Card title="门店象限" size="small" style={{ marginBottom: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ fontSize: 24 }}>
                  {quadrantIcon[quadrant]} {quadrantLabel[quadrant]}
                </div>
                <Alert message={dashboard?.store_quadrant_strategy || '加载中...'} type="info" showIcon />
                <Row gutter={8}>
                  <Col span={12}><Statistic title="竞争密度" value={dashboard?.competition_density ?? '--'} suffix="家/km" /></Col>
                  <Col span={12}><Statistic title="会员渗透率" value={((dashboard?.member_penetration || 0) * 100).toFixed(1)} suffix="%" /></Col>
                </Row>
              </Space>
            </Card>
            <Card title="本月ROI估算" size="small">
              <Statistic value={dashboard?.roi_estimate ?? '--'} suffix=":1" prefix="≈" valueStyle={{ color: '#52c41a', fontSize: 32 }} />
              <div style={{ color: '#999', fontSize: 12 }}>目标 ≥ 8:1，签约承诺 ≥ 8:1 否则退费</div>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'rfm', label: 'RFM分层',
      children: <Table columns={rfmColumns} dataSource={rfmData} rowKey="customer_id" loading={loading} scroll={{ x: 900 }} />,
    },
    {
      key: 'signals', label: (
        <span>信号感知 <Badge count={signals.filter(s => !s.action_taken).length} size="small" /></span>
      ),
      children: <Table columns={signalColumns} dataSource={signals} rowKey="signal_id" loading={loading} />,
    },
    {
      key: 'journeys', label: '旅程引擎',
      children: (
        <div>
          <Space style={{ marginBottom: 12 }}>
            <Button type="primary" icon={<RocketOutlined />} onClick={() => { setSelectedUser(null); setJourneyModal(true); }}>手动触发旅程</Button>
            <Button icon={<WarningOutlined />} danger onClick={() => setReviewModal(true)}>处理差评</Button>
          </Space>
          <Table columns={journeyColumns} dataSource={journeys} rowKey="journey_id" loading={loading} />
        </div>
      ),
    },
    {
      key: 'churn', label: (
        <span>流失预警 <Badge count={churnRisks.length} size="small" status="error" /></span>
      ),
      children: (
        <Table
          columns={rfmColumns.filter(c => c.key !== 'actions').concat([{
            title: '操作', key: 'actions',
            render: (_: any, record: any) => (
              <Button size="small" type="primary" danger onClick={() => { setSelectedUser(record); setJourneyModal(true); }}>
                启动唤醒旅程
              </Button>
            ),
          }])}
          dataSource={churnRisks}
          rowKey="customer_id"
          loading={loading}
          scroll={{ x: 900 }}
        />
      ),
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
        <Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>
        <span style={{ color: '#999', fontSize: 12 }}>每60秒自动刷新</span>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="私域会员" value={dashboard?.total_members ?? '--'} prefix={<UserOutlined />} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="活跃会员" value={dashboard?.active_members ?? '--'} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="月复购率" value={((dashboard?.monthly_repurchase_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="流失预警" value={dashboard?.churn_risk_count ?? '--'} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="待处理信号" value={dashboard?.pending_signals ?? '--'} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="运行中旅程" value={dashboard?.running_journeys ?? '--'} valueStyle={{ color: '#1890ff' }} /></Card></Col>
      </Row>

      <Card><Tabs items={tabItems} /></Card>

      {/* 触发旅程 Modal */}
      <Modal title="触发用户旅程" open={journeyModal} onCancel={() => setJourneyModal(false)} footer={null}>
        <Form layout="vertical" onFinish={triggerJourney} initialValues={{ customer_id: selectedUser?.customer_id }}>
          <Form.Item name="customer_id" label="用户ID" rules={[{ required: true }]}>
            <Input placeholder="用户ID" />
          </Form.Item>
          <Form.Item name="journey_type" label="旅程类型" rules={[{ required: true }]}>
            <Select placeholder="选择旅程">
              <Option value="new_customer">新客激活（7天4触点）</Option>
              <Option value="vip_retention">VIP保鲜</Option>
              <Option value="reactivation">沉睡唤醒</Option>
              <Option value="review_repair">差评修复</Option>
            </Select>
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>触发旅程</Button></Form.Item>
        </Form>
      </Modal>

      {/* 处理差评 Modal */}
      <Modal title="处理差评" open={reviewModal} onCancel={() => setReviewModal(false)} footer={null}>
        <Form layout="vertical" onFinish={processReview}>
          <Form.Item name="review_id" label="评价ID" rules={[{ required: true }]}>
            <Input placeholder="评价ID" />
          </Form.Item>
          <Form.Item name="customer_id" label="用户ID"><Input placeholder="用户ID（可选）" /></Form.Item>
          <Form.Item name="rating" label="评分" initialValue={2}>
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="content" label="评价内容"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item><Button type="primary" danger htmlType="submit" block>启动差评修复旅程</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PrivateDomainPage;
