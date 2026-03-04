import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, Statistic, Table, Tag, Button,
  Typography, Space, Spin, Segmented,
} from 'antd';
import { RobotOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

const DECISION_TYPE_LABELS: Record<string, string> = {
  revenue_anomaly: '营收异常',
  inventory_alert: '库存预警',
  purchase_suggestion: '采购建议',
  schedule_optimization: '排班优化',
  menu_pricing: '菜品定价',
  order_anomaly: '订单异常',
  kpi_improvement: 'KPI改进',
  cost_optimization: '成本优化',
};

const AIAccuracyPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState<string | undefined>(undefined);
  const [data, setData] = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/ai-evolution/accuracy-retrospective', {
        params: { days, ...(storeId ? { store_id: storeId } : {}) },
      });
      setData(res.data);
    } catch (err: any) {
      handleApiError(err, '加载准确率数据失败');
    } finally {
      setLoading(false);
    }
  }, [days, storeId]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { load(); }, [load]);

  const byType: any[] = data?.by_type || [];
  const weeklyTrend: any[] = data?.weekly_trend || [];
  const confidenceBuckets: any[] = data?.confidence_buckets || [];

  // 趋势折线图
  const trendOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: weeklyTrend.map((w: any) => w.week_start) },
    yAxis: { type: 'value', name: '准确率 (%)', min: 0, max: 100 },
    series: [{
      name: '准确率',
      type: 'line',
      smooth: true,
      data: weeklyTrend.map((w: any) => w.accuracy),
      markLine: { data: [{ type: 'average', name: '均值' }] },
      areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#1890ff' },
    }],
  };

  // 置信度 vs 准确率柱状图
  const confOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: confidenceBuckets.map((b: any) => b.confidence_range) },
    yAxis: [
      { type: 'value', name: '准确率 (%)', min: 0, max: 100 },
      { type: 'value', name: '决策数' },
    ],
    series: [
      {
        name: '准确率',
        type: 'bar',
        data: confidenceBuckets.map((b: any) => b.accuracy),
        itemStyle: { color: '#52c41a' },
      },
      {
        name: '决策数',
        type: 'line',
        yAxisIndex: 1,
        data: confidenceBuckets.map((b: any) => b.total),
        itemStyle: { color: '#faad14' },
      },
    ],
  };

  const typeColumns = [
    {
      title: '决策类型',
      dataIndex: 'decision_type',
      render: (v: string) => DECISION_TYPE_LABELS[v] || v,
    },
    { title: '总数', dataIndex: 'total' },
    { title: '成功', dataIndex: 'success', render: (v: number) => <Text type="success">{v}</Text> },
    { title: '部分', dataIndex: 'partial', render: (v: number) => <Text type="warning">{v}</Text> },
    { title: '失败', dataIndex: 'failure', render: (v: number) => <Text type="danger">{v}</Text> },
    {
      title: '准确率',
      dataIndex: 'accuracy',
      render: (v: number) => (
        <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}%</Tag>
      ),
      sorter: (a: any, b: any) => a.accuracy - b.accuracy,
    },
    {
      title: '平均置信度',
      dataIndex: 'avg_confidence',
      render: (v: number) => `${v}%`,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><RobotOutlined /> AI建议准确率回溯</Title>
        <Space>
          <Select
            placeholder="全部门店"
            allowClear
            style={{ width: 160 }}
            value={storeId}
            onChange={setStoreId}
          >
            {stores.map((s: any) => <Option key={s.id} value={s.id}>{s.name}</Option>)}
          </Select>
          <Segmented
            options={[
              { label: '近7天', value: 7 },
              { label: '近30天', value: 30 },
              { label: '近90天', value: 90 },
            ]}
            value={days}
            onChange={(v) => setDays(v as number)}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="总决策数" value={data?.total_decisions || 0} suffix="条" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="整体准确率"
                value={data?.overall_accuracy || 0}
                suffix="%"
                valueStyle={{ color: (data?.overall_accuracy || 0) >= 75 ? '#52c41a' : '#faad14' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="回溯周期" value={days} suffix="天" />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="决策类型" value={byType.length} suffix="种" />
            </Card>
          </Col>
        </Row>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={14}>
            <Card title="准确率周趋势">
              {weeklyTrend.length > 0
                ? <ReactECharts option={trendOption} style={{ height: 260 }} />
                : <Text type="secondary">暂无趋势数据</Text>}
            </Card>
          </Col>
          <Col span={10}>
            <Card title="置信度 vs 准确率">
              {confidenceBuckets.length > 0
                ? <ReactECharts option={confOption} style={{ height: 260 }} />
                : <Text type="secondary">暂无数据</Text>}
            </Card>
          </Col>
        </Row>

        <Card title="按决策类型分析">
          <Table
            dataSource={byType}
            columns={typeColumns}
            rowKey="decision_type"
            pagination={false}
            size="middle"
          />
        </Card>
      </Spin>
    </div>
  );
};

export default AIAccuracyPage;
