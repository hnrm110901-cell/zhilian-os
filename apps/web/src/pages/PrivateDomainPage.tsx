import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Card, Col, Row, Select, Tabs, Statistic, Table, Tag, Button,
  Progress, Alert, Space, Badge, Modal, Form, Input, InputNumber,
  Popconfirm, Tooltip, Drawer, Checkbox,
} from 'antd';
import {
  UserOutlined, WarningOutlined, RocketOutlined,
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
  SettingOutlined, ThunderboltOutlined, LineChartOutlined,
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
  const [trendData, setTrendData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [reviewModal, setReviewModal] = useState(false);
  const [journeyModal, setJourneyModal] = useState(false);
  const [quadrantDrawer, setQuadrantDrawer] = useState(false);
  const [batchModal, setBatchModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [activeTab, setActiveTab] = useState('overview');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) { handleApiError(err, '加载门店失败'); }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, rfm, sig, jrn, churn, trend] = await Promise.allSettled([
        apiClient.get(`/api/v1/private-domain/dashboard/${selectedStore}`),
        apiClient.get(`/api/v1/private-domain/rfm/${selectedStore}`),
        apiClient.get(`/api/v1/private-domain/signals/${selectedStore}`, { params: { limit: 30 } }),
        apiClient.get(`/api/v1/private-domain/journeys/${selectedStore}`),
        apiClient.get(`/api/v1/private-domain/churn-risks/${selectedStore}`),
        apiClient.get(`/api/v1/private-domain/stats/trend/${selectedStore}`, { params: { days: 30 } }),
      ]);
      if (dash.status === 'fulfilled') setDashboard(dash.value.data);
      if (rfm.status === 'fulfilled') setRfmData(rfm.value.data?.segments || []);
      if (sig.status === 'fulfilled') setSignals(sig.value.data?.signals || []);
      if (jrn.status === 'fulfilled') setJourneys(jrn.value.data?.journeys || []);
      if (churn.status === 'fulfilled') setChurnRisks(churn.value.data?.users || []);
      if (trend.status === 'fulfilled') setTrendData(trend.value.data?.trend || []);
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
      await apiClient.post(`/api/v1/private-domain/journeys/${selectedStore}/trigger`, values);
      showSuccess('旅程已触发');
      setJourneyModal(false);
      loadAll();
    } catch (err: any) { handleApiError(err, '触发旅程失败'); }
  };

  const batchTrigger = async (values: any) => {
    const ids = selectedRowKeys as string[];
    if (ids.length === 0) return;
    try {
      const res = await apiClient.post(`/api/v1/private-domain/journeys/${selectedStore}/batch-trigger`, {
        customer_ids: ids,
        journey_type: values.journey_type,
      });
      showSuccess(`已批量触发 ${res.data?.triggered} 个旅程`);
      setBatchModal(false);
      setSelectedRowKeys([]);
      loadAll();
    } catch (err: any) { handleApiError(err, '批量触发失败'); }
  };

  const processReview = async (values: any) => {
    try {
      await apiClient.post(`/api/v1/private-domain/reviews/${selectedStore}/process`, values);
      showSuccess('差评修复旅程已启动');
      setReviewModal(false);
      loadAll();
    } catch (err: any) { handleApiError(err, '处理差评失败'); }
  };

  const markSignalHandled = async (signalId: string) => {
    try {
      await apiClient.patch(`/api/v1/private-domain/signals/${selectedStore}/${signalId}/mark-handled`, { action: 'handled' });
      showSuccess('已标记处理');
      setSignals(prev => prev.map(s => s.signal_id === signalId ? { ...s, action_taken: 'handled' } : s));
    } catch (err: any) { handleApiError(err, '标记失败'); }
  };

  const updateQuadrant = async (values: any) => {
    try {
      await apiClient.post(`/api/v1/private-domain/quadrant/${selectedStore}`, values);
      showSuccess('四象限已更新');
      setQuadrantDrawer(false);
      loadAll();
    } catch (err: any) { handleApiError(err, '更新失败'); }
  };

  // ── Charts ──
  const rfmDist = dashboard?.rfm_distribution || {};
  const rfmPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: Object.entries(rfmDist).map(([k, v]) => ({
        name: `${k} ${rfmLabel[k] || k}`, value: v,
        itemStyle: { color: { S1: '#faad14', S2: '#1890ff', S3: '#fa8c16', S4: '#ff4d4f', S5: '#cf1322' }[k as string] || '#999' },
      })),
    }],
  };

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增会员', '复购率%', '旅程完成率%'] },
    xAxis: { type: 'category', data: trendData.map(d => d.date?.slice(5)) },
    yAxis: [
      { type: 'value', name: '人数', min: 0 },
      { type: 'value', name: '比率%', min: 0, max: 100 },
    ],
    series: [
      { name: '新增会员', type: 'bar', data: trendData.map(d => d.new_members), itemStyle: { color: '#1890ff' } },
      { name: '复购率%', type: 'line', yAxisIndex: 1, data: trendData.map(d => +(d.repurchase_rate * 100).toFixed(1)), smooth: true, itemStyle: { color: '#52c41a' } },
      { name: '旅程完成率%', type: 'line', yAxisIndex: 1, data: trendData.map(d => +(d.journey_completion * 100).toFixed(1)), smooth: true, itemStyle: { color: '#faad14' } },
    ],
  };

  // ── Columns ──
  const rfmColumns: ColumnsType<any> = [
    { title: '用户ID', dataIndex: 'customer_id', key: 'customer_id', width: 100 },
    { title: 'RFM层级', dataIndex: 'rfm_level', key: 'rfm_level', width: 90, render: (v: string) => <Tag color={rfmColor[v]}>{rfmLabel[v] || v}</Tag> },
    { title: '最近消费', dataIndex: 'recency_days', key: 'recency_days', width: 90, render: (v: number) => `${v}天前`, sorter: (a: any, b: any) => a.recency_days - b.recency_days },
    { title: '频次', dataIndex: 'frequency', key: 'frequency', width: 70, sorter: (a: any, b: any) => a.frequency - b.frequency },
    { title: '消费金额', dataIndex: 'monetary', key: 'monetary', width: 100, render: (v: number) => `¥${(v / 100).toFixed(0)}`, sorter: (a: any, b: any) => a.monetary - b.monetary },
    { title: '流失风险', dataIndex: 'risk_score', key: 'risk_score', width: 130, render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" status={v >= 0.7 ? 'exception' : v >= 0.4 ? 'normal' : 'success'} /> },
    { title: '标签', dataIndex: 'dynamic_tags', key: 'dynamic_tags', render: (tags: string[]) => tags?.map(t => <Tag key={t}>{t}</Tag>) },
    {
      title: '操作', key: 'actions', width: 100,
      render: (_: any, record: any) => (
        <Button size="small" onClick={() => { setSelectedUser(record); setJourneyModal(true); }}>触发旅程</Button>
      ),
    },
  ];

  const signalColumns: ColumnsType<any> = [
    { title: '信号类型', dataIndex: 'signal_type', key: 'signal_type', width: 100, render: (v: string) => <Tag color={signalColor[v]}>{signalLabel[v] || v}</Tag> },
    { title: '用户', dataIndex: 'customer_id', key: 'customer_id', width: 90, render: (v: string) => v || '-' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '严重程度', dataIndex: 'severity', key: 'severity', width: 90, render: (v: string) => <Tag color={{ low: 'green', medium: 'orange', high: 'red', critical: 'purple' }[v] || 'default'}>{v}</Tag> },
    { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at', width: 140, render: (v: string) => v?.slice(0, 16) },
    {
      title: '状态', dataIndex: 'action_taken', key: 'action_taken', width: 80,
      render: (v: string) => v
        ? <Tooltip title={v}><CheckCircleOutlined style={{ color: '#52c41a' }} /></Tooltip>
        : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
    },
    {
      title: '操作', key: 'op', width: 90,
      render: (_: any, record: any) => !record.action_taken && (
        <Popconfirm title="标记为已处理？" onConfirm={() => markSignalHandled(record.signal_id)} okText="确认" cancelText="取消">
          <Button size="small" type="link">标记处理</Button>
        </Popconfirm>
      ),
    },
  ];

  const journeyColumns: ColumnsType<any> = [
    { title: '旅程类型', dataIndex: 'journey_type', key: 'journey_type', width: 100, render: (v: string) => journeyLabel[v] || v },
    { title: '用户', dataIndex: 'customer_id', key: 'customer_id', width: 90 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={{ running: 'blue', completed: 'green', pending: 'orange', failed: 'red' }[v] || 'default'}>{v}</Tag> },
    { title: '进度', key: 'progress', width: 130, render: (_: any, r: any) => <Progress percent={Math.round((r.current_step / r.total_steps) * 100)} size="small" format={() => `${r.current_step}/${r.total_steps}`} /> },
    { title: '下次触达', dataIndex: 'next_action_at', key: 'next_action_at', width: 140, render: (v: string) => v?.slice(0, 16) || '-' },
    { title: '开始时间', dataIndex: 'started_at', key: 'started_at', width: 140, render: (v: string) => v?.slice(0, 16) },
  ];

  const quadrant = dashboard?.store_quadrant || 'potential';
  const pendingSignals = signals.filter(s => !s.action_taken).length;
  const badReviews = signals.filter(s => s.signal_type === 'bad_review');

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
            <Card
              title="门店象限"
              size="small"
              style={{ marginBottom: 16 }}
              extra={<Button size="small" icon={<SettingOutlined />} onClick={() => setQuadrantDrawer(true)}>调整参数</Button>}
            >
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
      key: 'trend', label: <span><LineChartOutlined /> 趋势分析</span>,
      children: (
        <Card size="small" title="近30天运营趋势">
          <ReactECharts option={trendOption} style={{ height: 360 }} />
        </Card>
      ),
    },
    {
      key: 'rfm', label: 'RFM分层',
      children: (
        <div>
          <Space style={{ marginBottom: 12 }}>
            {selectedRowKeys.length > 0 && (
              <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => setBatchModal(true)}>
                批量触发旅程（{selectedRowKeys.length}人）
              </Button>
            )}
          </Space>
          <Table
            columns={rfmColumns}
            dataSource={rfmData}
            rowKey="customer_id"
            loading={loading}
            scroll={{ x: 900 }}
            rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
          />
        </div>
      ),
    },
    {
      key: 'signals', label: (
        <span>信号感知 <Badge count={pendingSignals} size="small" /></span>
      ),
      children: <Table columns={signalColumns} dataSource={signals} rowKey="signal_id" loading={loading} scroll={{ x: 900 }} />,
    },
    {
      key: 'journeys', label: '旅程引擎',
      children: (
        <div>
          <Space style={{ marginBottom: 12 }}>
            <Button type="primary" icon={<RocketOutlined />} onClick={() => { setSelectedUser(null); setJourneyModal(true); }}>手动触发旅程</Button>
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
        <div>
          {churnRisks.length > 0 && (
            <Alert
              type="warning" showIcon style={{ marginBottom: 12 }}
              message={`共 ${churnRisks.length} 位用户存在流失风险，建议立即启动唤醒旅程`}
              action={<Button size="small" danger onClick={() => { setSelectedRowKeys(churnRisks.map(c => c.customer_id)); setBatchModal(true); }}>一键批量唤醒</Button>}
            />
          )}
          <Table
            columns={rfmColumns.filter(c => c.key !== 'actions').concat([{
              title: '操作', key: 'actions', width: 120,
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
        </div>
      ),
    },
    {
      key: 'reviews', label: (
        <span>差评管理 <Badge count={badReviews.length} size="small" status="error" /></span>
      ),
      children: (
        <div>
          <Space style={{ marginBottom: 12 }}>
            <Button icon={<WarningOutlined />} danger onClick={() => setReviewModal(true)}>处理新差评</Button>
          </Space>
          <Table
            columns={[
              { title: '信号ID', dataIndex: 'signal_id', key: 'signal_id', ellipsis: true },
              { title: '用户', dataIndex: 'customer_id', key: 'customer_id', width: 90, render: (v: string) => v || '-' },
              { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
              { title: '严重程度', dataIndex: 'severity', key: 'severity', width: 90, render: (v: string) => <Tag color={{ low: 'green', medium: 'orange', high: 'red', critical: 'purple' }[v] || 'default'}>{v}</Tag> },
              { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at', width: 140, render: (v: string) => v?.slice(0, 16) },
              {
                title: '操作', key: 'op', width: 120,
                render: (_: any, record: any) => (
                  <Button size="small" danger onClick={() => { setSelectedUser(record); setReviewModal(true); }}>启动修复旅程</Button>
                ),
              },
            ]}
            dataSource={badReviews}
            rowKey="signal_id"
            loading={loading}
          />
        </div>
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

      <Card><Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} /></Card>

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

      {/* 批量触发 Modal */}
      <Modal title={`批量触发旅程（${selectedRowKeys.length}人）`} open={batchModal} onCancel={() => setBatchModal(false)} footer={null}>
        <Form layout="vertical" onFinish={batchTrigger}>
          <Form.Item name="journey_type" label="旅程类型" rules={[{ required: true }]}>
            <Select placeholder="选择旅程">
              <Option value="reactivation">沉睡唤醒</Option>
              <Option value="new_customer">新客激活</Option>
              <Option value="vip_retention">VIP保鲜</Option>
            </Select>
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block icon={<ThunderboltOutlined />}>批量触发</Button></Form.Item>
        </Form>
      </Modal>

      {/* 处理差评 Modal */}
      <Modal title="处理差评" open={reviewModal} onCancel={() => setReviewModal(false)} footer={null}>
        <Form layout="vertical" onFinish={processReview} initialValues={{ customer_id: selectedUser?.customer_id }}>
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

      {/* 四象限参数 Drawer */}
      <Drawer title="调整门店四象限参数" open={quadrantDrawer} onClose={() => setQuadrantDrawer(false)} width={400}>
        <Form layout="vertical" onFinish={updateQuadrant}
          initialValues={{ competition_density: 4.0, member_count: dashboard?.total_members || 0, estimated_population: 1000 }}>
          <Form.Item name="competition_density" label="竞争密度（周边1km同品类数）" rules={[{ required: true }]}>
            <InputNumber min={0} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="member_count" label="当前会员数">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="estimated_population" label="估算消费人口">
            <InputNumber min={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>重新计算象限</Button>
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default PrivateDomainPage;
