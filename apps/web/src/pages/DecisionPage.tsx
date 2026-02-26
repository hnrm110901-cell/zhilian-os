import React, { useState, useEffect, useCallback } from 'react';
import { Card, Table, Tabs, Statistic, Row, Col, Progress, Tag, Space, Select, DatePicker, Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ArrowUpOutlined, ArrowDownOutlined, TrophyOutlined, WarningOutlined, ReloadOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import apiClient from '../services/api';
import { handleApiError } from '../utils/message';

const { TabPane } = Tabs;
const { Option } = Select;
const { RangePicker } = DatePicker;

interface BusinessMetric {
  id: string;
  name: string;
  value: number;
  target: number;
  trend: 'up' | 'down' | 'stable';
  changeRate: number;
  status: 'excellent' | 'good' | 'warning' | 'danger';
}

interface DecisionRecommendation {
  id: string;
  category: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  actionItems: string[];
  createdAt: string;
}

interface PerformanceData {
  department: string;
  revenue: number;
  growth: number;
  efficiency: number;
  satisfaction: number;
}

const DecisionPage: React.FC = () => {
  const [metrics, setMetrics] = useState<BusinessMetric[]>([]);
  const [recommendations, setRecommendations] = useState<DecisionRecommendation[]>([]);
  const [performanceData, setPerformanceData] = useState<PerformanceData[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('month');
  const [loading, setLoading] = useState(false);
  const [storeId] = useState('STORE001');

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [metricsRes, recommendationsRes, performanceRes] = await Promise.allSettled([
        apiClient.callAgent('decision', { action: 'analyze_kpi', period: selectedPeriod, store_id: storeId }),
        apiClient.callAgent('decision', { action: 'get_recommendations', store_id: storeId }),
        apiClient.callAgent('decision', { action: 'get_insights', store_id: storeId }),
      ]);
      if (metricsRes.status === 'fulfilled') {
        setMetrics(metricsRes.value.output_data?.metrics || []);
      }
      if (recommendationsRes.status === 'fulfilled') {
        setRecommendations(recommendationsRes.value.output_data?.recommendations || []);
      }
      if (performanceRes.status === 'fulfilled') {
        setPerformanceData(performanceRes.value.output_data?.performance || []);
      }
    } catch (error: any) {
      handleApiError(error, '加载决策数据失败');
    } finally {
      setLoading(false);
    }
  }, [selectedPeriod, storeId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (metrics.length > 0 || performanceData.length > 0) {
      initCharts();
    }
  }, [metrics, performanceData]);

  const initCharts = () => {
    setTimeout(() => {
      const trendEl = document.getElementById('trendChart');
      const radarEl = document.getElementById('radarChart');
      if (!trendEl || !radarEl) return;

      const trendChart = echarts.init(trendEl);
      const radarChart = echarts.init(radarEl);

      trendChart.setOption({
        title: { text: '关键指标趋势分析', left: 'center' },
        tooltip: { trigger: 'axis' },
        legend: { data: metrics.map(m => m.name).slice(0, 3), bottom: 0 },
        xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月'] },
        yAxis: { type: 'value' },
        series: metrics.slice(0, 3).map(m => ({
          name: m.name,
          type: 'line',
          data: [m.value * 0.8, m.value * 0.85, m.value * 0.9, m.value * 0.95, m.value * 0.98, m.value],
          smooth: true,
        })),
      });

      const depts = performanceData.map(p => p.department);
      radarChart.setOption({
        title: { text: '部门综合能力评估', left: 'center' },
        tooltip: {},
        legend: { data: depts, bottom: 0 },
        radar: {
          indicator: [
            { name: '营收贡献', max: 100 },
            { name: '增长率', max: 100 },
            { name: '工作效率', max: 100 },
            { name: '客户满意度', max: 100 },
          ],
        },
        series: [{
          type: 'radar',
          data: performanceData.map(p => ({
            value: [
              Math.min(100, p.revenue / 10000),
              Math.min(100, p.growth * 3),
              p.efficiency,
              p.satisfaction,
            ],
            name: p.department,
          })),
        }],
      });
    }, 100);
  };

  const metricColumns: ColumnsType<BusinessMetric> = [
    { title: '指标名称', dataIndex: 'name', key: 'name' },
    {
      title: '当前值',
      dataIndex: 'value',
      key: 'value',
      render: (value: number, record) => record.name.includes('营收') ? `¥${(value / 10000).toFixed(1)}万` : `${value}%`,
    },
    {
      title: '目标值',
      dataIndex: 'target',
      key: 'target',
      render: (value: number, record) => record.name.includes('营收') ? `¥${(value / 10000).toFixed(1)}万` : `${value}%`,
    },
    {
      title: '完成度',
      key: 'completion',
      render: (_, record) => {
        const completion = Math.round((record.value / record.target) * 100);
        return <Progress percent={completion} size="small" status={completion >= 100 ? 'success' : completion >= 80 ? 'active' : 'exception'} />;
      },
    },
    {
      title: '趋势',
      dataIndex: 'trend',
      key: 'trend',
      render: (trend: string, record) => {
        const trendMap = {
          up: { icon: <ArrowUpOutlined />, color: 'green', text: `+${record.changeRate}%` },
          down: { icon: <ArrowDownOutlined />, color: 'red', text: `${record.changeRate}%` },
          stable: { icon: null, color: 'blue', text: `${record.changeRate}%` },
        };
        const config = trendMap[trend as keyof typeof trendMap];
        return <Tag color={config.color} icon={config.icon}>{config.text}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap = {
          excellent: { text: '优秀', color: 'green', icon: <TrophyOutlined /> },
          good: { text: '良好', color: 'blue', icon: null },
          warning: { text: '预警', color: 'orange', icon: <WarningOutlined /> },
          danger: { text: '危险', color: 'red', icon: <WarningOutlined /> },
        };
        const config = statusMap[status as keyof typeof statusMap];
        return <Tag color={config?.color} icon={config?.icon}>{config?.text || status}</Tag>;
      },
    },
  ];

  const recommendationColumns: ColumnsType<DecisionRecommendation> = [
    { title: '类别', dataIndex: 'category', key: 'category', render: (c: string) => <Tag color="blue">{c}</Tag> },
    { title: '建议标题', dataIndex: 'title', key: 'title' },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (priority: string) => {
        const priorityMap = { high: { text: '高', color: 'red' }, medium: { text: '中', color: 'orange' }, low: { text: '低', color: 'green' } };
        return <Tag color={priorityMap[priority as keyof typeof priorityMap]?.color}>{priorityMap[priority as keyof typeof priorityMap]?.text || priority}</Tag>;
      },
    },
    { title: '预期影响', dataIndex: 'impact', key: 'impact' },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt' },
  ];

  const performanceColumns: ColumnsType<PerformanceData> = [
    { title: '部门', dataIndex: 'department', key: 'department' },
    { title: '营收贡献', dataIndex: 'revenue', key: 'revenue', render: (r: number) => r > 0 ? `¥${(r / 10000).toFixed(1)}万` : '-' },
    {
      title: '增长率',
      dataIndex: 'growth',
      key: 'growth',
      render: (growth: number) => growth > 0 ? <Tag color="green" icon={<ArrowUpOutlined />}>+{growth}%</Tag> : '-',
    },
    {
      title: '工作效率',
      dataIndex: 'efficiency',
      key: 'efficiency',
      render: (e: number) => <Progress percent={e} size="small" status={e >= 90 ? 'success' : 'active'} />,
    },
    {
      title: '客户满意度',
      dataIndex: 'satisfaction',
      key: 'satisfaction',
      render: (s: number) => <Progress percent={s} size="small" status={s >= 90 ? 'success' : 'active'} />,
    },
  ];

  const excellentMetrics = metrics.filter(m => m.status === 'excellent').length;
  const warningMetrics = metrics.filter(m => m.status === 'warning' || m.status === 'danger').length;
  const highPriorityRecommendations = recommendations.filter(r => r.priority === 'high').length;
  const growingDepts = performanceData.filter(p => p.growth > 0);
  const avgGrowth = growingDepts.length > 0
    ? Math.round(growingDepts.reduce((sum, p) => sum + p.growth, 0) / growingDepts.length * 10) / 10
    : 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>决策支持Agent</h1>
        <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>刷新</Button>
      </div>

      <Space style={{ marginBottom: 16 }}>
        <Select value={selectedPeriod} onChange={setSelectedPeriod} style={{ width: 120 }}>
          <Option value="week">本周</Option>
          <Option value="month">本月</Option>
          <Option value="quarter">本季度</Option>
          <Option value="year">本年</Option>
        </Select>
        <RangePicker />
      </Space>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="优秀指标数" value={excellentMetrics} suffix={`/ ${metrics.length}`} valueStyle={{ color: '#3f8600' }} prefix={<TrophyOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="预警指标数" value={warningMetrics} suffix={`/ ${metrics.length}`} valueStyle={{ color: '#cf1322' }} prefix={<WarningOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="高优先级建议" value={highPriorityRecommendations} suffix="条" valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="平均增长率" value={avgGrowth} suffix="%" valueStyle={{ color: '#3f8600' }} prefix={<ArrowUpOutlined />} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card><div id="trendChart" style={{ width: '100%', height: 300 }}></div></Card>
        </Col>
        <Col span={12}>
          <Card><div id="radarChart" style={{ width: '100%', height: 300 }}></div></Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="1">
          <TabPane tab="关键指标" key="1">
            <Table columns={metricColumns} dataSource={metrics} rowKey="id" pagination={false} loading={loading} />
          </TabPane>

          <TabPane tab="决策建议" key="2">
            <Table
              columns={recommendationColumns}
              dataSource={recommendations}
              rowKey="id"
              pagination={false}
              loading={loading}
              expandable={{
                expandedRowRender: (record) => (
                  <div style={{ padding: '16px', background: '#fafafa' }}>
                    <p><strong>详细描述：</strong>{record.description}</p>
                    <p><strong>行动建议：</strong></p>
                    <ul>{record.actionItems?.map((item, index) => <li key={index}>{item}</li>)}</ul>
                  </div>
                ),
              }}
            />
          </TabPane>

          <TabPane tab="部门绩效" key="3">
            <Table columns={performanceColumns} dataSource={performanceData} rowKey="department" pagination={false} loading={loading} />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default DecisionPage;
