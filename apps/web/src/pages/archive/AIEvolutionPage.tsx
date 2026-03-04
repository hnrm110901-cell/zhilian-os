import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Tabs, Table, Progress, Tag, Space,
  Select, Spin, Alert, Typography
} from 'antd';
import {
  RobotOutlined, RiseOutlined, CheckCircleOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Title, Text } = Typography;
const { Option } = Select;

interface EvolutionSummary {
  total_agents: number;
  avg_adoption_rate: number;
  total_decisions: number;
  avg_success_rate: number;
  autonomous_rate: number;
  trust_phase: string;
}

interface AdoptionMetric {
  agent_name: string;
  adoption_rate: number;
  decisions_made: number;
  success_rate: number;
  trust_phase: string;
}

interface WeeklyTrend {
  week: string;
  adoption_rate: number;
  success_rate: number;
  autonomous_decisions: number;
}

interface AgentPerformance {
  agent_id: string;
  agent_name: string;
  total_actions: number;
  success_rate: number;
  avg_confidence: number;
  escalation_rate: number;
  last_active: string;
}

interface HitlEscalation {
  date: string;
  total: number;
  approved: number;
  rejected: number;
}

const AIEvolutionPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<EvolutionSummary | null>(null);
  const [adoptionMetrics, setAdoptionMetrics] = useState<AdoptionMetric[]>([]);
  const [weeklyTrend, setWeeklyTrend] = useState<WeeklyTrend[]>([]);
  const [agentPerformance, setAgentPerformance] = useState<AgentPerformance[]>([]);
  const [hitlEscalations, setHitlEscalations] = useState<HitlEscalation[]>([]);
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, adoptionRes, trendRes, perfRes, hitlRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/ai-evolution/summary?store_id=${storeId}`),
        apiClient.get(`/api/v1/ai-evolution/adoption-rate?store_id=${storeId}`),
        apiClient.get(`/api/v1/ai-evolution/weekly-trend?store_id=${storeId}`),
        apiClient.get(`/api/v1/ai-evolution/agent-performance?store_id=${storeId}`),
        apiClient.get(`/api/v1/ai-evolution/hitl-escalations?store_id=${storeId}`),
      ]);
      if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value.data);
      if (adoptionRes.status === 'fulfilled') setAdoptionMetrics(adoptionRes.value.data || []);
      if (trendRes.status === 'fulfilled') setWeeklyTrend(trendRes.value.data || []);
      if (perfRes.status === 'fulfilled') setAgentPerformance(perfRes.value.data || []);
      if (hitlRes.status === 'fulfilled') setHitlEscalations(hitlRes.value.data || []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadStores(); loadData(); }, [loadStores, loadData]);

  const trendChartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['采纳率', '成功率'] },
    xAxis: { type: 'category', data: weeklyTrend.map(d => d.week) },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '采纳率', type: 'line', smooth: true,
        data: weeklyTrend.map(d => +(d.adoption_rate * 100).toFixed(1)),
        itemStyle: { color: '#1890ff' },
      },
      {
        name: '成功率', type: 'line', smooth: true,
        data: weeklyTrend.map(d => +(d.success_rate * 100).toFixed(1)),
        itemStyle: { color: '#52c41a' },
      },
    ],
  };

  const hitlChartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['总计', '批准', '拒绝'] },
    xAxis: { type: 'category', data: hitlEscalations.map(d => d.date) },
    yAxis: { type: 'value' },
    series: [
      { name: '总计', type: 'bar', data: hitlEscalations.map(d => d.total), itemStyle: { color: '#1890ff' } },
      { name: '批准', type: 'bar', data: hitlEscalations.map(d => d.approved), itemStyle: { color: '#52c41a' } },
      { name: '拒绝', type: 'bar', data: hitlEscalations.map(d => d.rejected), itemStyle: { color: '#ff4d4f' } },
    ],
  };

  const phaseColor: Record<string, string> = {
    learning: 'blue', supervised: 'orange', semi_autonomous: 'purple', autonomous: 'green',
  };
  const phaseLabel: Record<string, string> = {
    learning: '学习阶段', supervised: '监督阶段', semi_autonomous: '半自主', autonomous: '自主',
  };

  const agentColumns = [
    { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name' },
    { title: '总操作数', dataIndex: 'total_actions', key: 'total_actions' },
    {
      title: '成功率', dataIndex: 'success_rate', key: 'success_rate',
      render: (v: number) => <Progress percent={+(v * 100).toFixed(1)} size="small" />,
    },
    {
      title: '平均置信度', dataIndex: 'avg_confidence', key: 'avg_confidence',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '升级率', dataIndex: 'escalation_rate', key: 'escalation_rate',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    { title: '最后活跃', dataIndex: 'last_active', key: 'last_active' },
  ];

  const adoptionColumns = [
    { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name' },
    {
      title: '采纳率', dataIndex: 'adoption_rate', key: 'adoption_rate',
      render: (v: number) => <Progress percent={+(v * 100).toFixed(1)} size="small" strokeColor="#1890ff" />,
    },
    { title: '决策数', dataIndex: 'decisions_made', key: 'decisions_made' },
    {
      title: '成功率', dataIndex: 'success_rate', key: 'success_rate',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '信任阶段', dataIndex: 'trust_phase', key: 'trust_phase',
      render: (v: string) => <Tag color={phaseColor[v] || 'default'}>{phaseLabel[v] || v}</Tag>,
    },
  ];

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>AI进化看板</Title>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0 ? stores.map((s: any) => (
              <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
            )) : <Option value="STORE001">门店 001</Option>}
          </Select>
        </div>

        {summary && (
          <Row gutter={16}>
            <Col span={4}>
              <Card><Statistic title="Agent总数" value={summary.total_agents} prefix={<RobotOutlined />} /></Card>
            </Col>
            <Col span={5}>
              <Card>
                <Statistic
                  title="平均采纳率"
                  value={+(summary.avg_adoption_rate * 100).toFixed(1)}
                  suffix="%"
                  prefix={<RiseOutlined />}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={5}>
              <Card><Statistic title="总决策数" value={summary.total_decisions} prefix={<ThunderboltOutlined />} /></Card>
            </Col>
            <Col span={5}>
              <Card>
                <Statistic
                  title="平均成功率"
                  value={+(summary.avg_success_rate * 100).toFixed(1)}
                  suffix="%"
                  prefix={<CheckCircleOutlined />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={5}>
              <Card>
                <Statistic title="自主率" value={+(summary.autonomous_rate * 100).toFixed(1)} suffix="%" />
                <Text type="secondary">
                  信任阶段：<Tag color={phaseColor[summary.trust_phase] || 'default'}>{phaseLabel[summary.trust_phase] || summary.trust_phase}</Tag>
                </Text>
              </Card>
            </Col>
          </Row>
        )}

        <Card>
          <Tabs
            items={[
              {
                key: 'trend',
                label: '周趋势',
                children: weeklyTrend.length > 0
                  ? <ReactECharts option={trendChartOption} style={{ height: 320 }} />
                  : <Alert message="暂无趋势数据" type="info" showIcon />,
              },
              {
                key: 'adoption',
                label: '采纳率明细',
                children: (
                  <Table
                    dataSource={adoptionMetrics}
                    columns={adoptionColumns}
                    rowKey="agent_name"
                    size="small"
                    pagination={false}
                  />
                ),
              },
              {
                key: 'performance',
                label: 'Agent性能',
                children: (
                  <Table
                    dataSource={agentPerformance}
                    columns={agentColumns}
                    rowKey="agent_id"
                    size="small"
                    pagination={{ pageSize: 10 }}
                  />
                ),
              },
              {
                key: 'hitl',
                label: 'HITL升级',
                children: hitlEscalations.length > 0
                  ? <ReactECharts option={hitlChartOption} style={{ height: 320 }} />
                  : <Alert message="暂无升级数据" type="info" showIcon />,
              },
            ]}
          />
        </Card>
      </Space>
    </Spin>
  );
};

export default AIEvolutionPage;
