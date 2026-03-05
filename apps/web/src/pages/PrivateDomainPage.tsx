/**
 * 私域增长驾驶舱
 * Private Domain Growth Dashboard
 *
 * 三角 KPI：
 *   ① 自有流量  — 私域规模
 *   ② 客户价值  — 盈利能力
 *   ③ 旅程健康  — 运营效率
 *
 * + 生命周期漏斗（9段）
 * + 30天趋势折线图
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Progress, Typography, Space,
  Tag, Spin, Alert, Select, Tooltip, Divider,
} from 'antd';
import {
  TeamOutlined, RiseOutlined, ThunderboltOutlined,
  ReloadOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import apiClient from '../services/api';

const { Title, Text } = Typography;
const { Option } = Select;

// ── Types ─────────────────────────────────────────────────────────────────────

interface OwnedAudience {
  total_members: number;
  active_members: number;
  active_rate: number;
  wxwork_connected: number;
  connect_rate: number;
  new_this_month: number;
}

interface CustomerValue {
  repeat_rate_30d: number;
  avg_ltv_yuan: number;
  avg_order_value_yuan: number;
  avg_orders_per_member: number;
}

interface JourneyHealth {
  running_journeys: number;
  completed_journeys: number;
  total_journeys_90d: number;
  completion_rate: number;
  bad_review_signals: number;
  churn_risk_count: number;
}

interface LifecycleFunnel {
  lead: number;
  registered: number;
  first_order_pending: number;
  repeat: number;
  high_frequency: number;
  vip: number;
  at_risk: number;
  dormant: number;
  lost: number;
}

interface Metrics {
  store_id: string;
  as_of: string;
  owned_audience: OwnedAudience;
  customer_value: CustomerValue;
  journey_health: JourneyHealth;
  lifecycle_funnel: LifecycleFunnel;
}

interface TrendPoint {
  date: string;
  new_members: number;
  repurchase_rate: number;
  journey_completion: number;
  revenue: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const LIFECYCLE_LABELS: Record<string, string> = {
  lead:                '潜客',
  registered:          '已注册',
  first_order_pending: '待首单',
  repeat:              '复购',
  high_frequency:      '高频',
  vip:                 'VIP',
  at_risk:             '风险',
  dormant:             '沉睡',
  lost:                '流失',
};

const LIFECYCLE_COLORS: Record<string, string> = {
  lead:                '#bfbfbf',
  registered:          '#91d5ff',
  first_order_pending: '#ffd591',
  repeat:              '#52c41a',
  high_frequency:      '#1890ff',
  vip:                 '#722ed1',
  at_risk:             '#fa8c16',
  dormant:             '#ff7875',
  lost:                '#434343',
};

const STORE_OPTIONS = ['S001', 'S002', 'S003'];

// ── Sub-components ────────────────────────────────────────────────────────────

const PillarCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  color: string;
  children: React.ReactNode;
  loading?: boolean;
}> = ({ icon, title, color, children, loading }) => (
  <Card
    bordered={false}
    style={{ borderTop: `3px solid ${color}`, height: '100%' }}
    loading={loading}
  >
    <Space style={{ marginBottom: 16 }}>
      <span style={{ fontSize: 20, color }}>{icon}</span>
      <Title level={5} style={{ margin: 0 }}>{title}</Title>
    </Space>
    {children}
  </Card>
);

// ── Main Component ────────────────────────────────────────────────────────────

const PrivateDomainPage: React.FC = () => {
  const [storeId, setStoreId] = useState('S001');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [trendLoading, setTrendLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async (sid: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<Metrics>(
        `/api/v1/private-domain/metrics/${sid}`
      );
      setMetrics(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? '加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTrend = useCallback(async (sid: string) => {
    setTrendLoading(true);
    try {
      const data = await apiClient.get<{ trend: TrendPoint[] }>(
        `/api/v1/private-domain/stats/trend/${sid}?days=30`
      );
      setTrend(data.trend ?? []);
    } catch {
      setTrend([]);
    } finally {
      setTrendLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics(storeId);
    fetchTrend(storeId);
  }, [storeId, fetchMetrics, fetchTrend]);

  // ── ECharts Options ──────────────────────────────────────────────────────

  const funnelOption = React.useMemo(() => {
    if (!metrics) return {};
    const funnel = metrics.lifecycle_funnel;
    const data = Object.entries(LIFECYCLE_LABELS).map(([key, label]) => ({
      name: label,
      value: funnel[key as keyof LifecycleFunnel] ?? 0,
      itemStyle: { color: LIFECYCLE_COLORS[key] },
    }));
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} 人' },
      legend: { show: false },
      series: [{
        type: 'funnel',
        left: '5%',
        width: '90%',
        min: 0,
        minSize: '2%',
        maxSize: '100%',
        sort: 'none',
        gap: 3,
        label: {
          show: true,
          position: 'inside',
          formatter: (p: any) => `${p.name}\n${p.value}`,
          color: '#fff',
          fontWeight: 'bold',
          fontSize: 12,
        },
        data,
      }],
    };
  }, [metrics]);

  const trendOption = React.useMemo(() => {
    if (!trend.length) return {};
    const dates = trend.map(t => t.date);
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['新会员', '复购率', '旅程完成率'] },
      grid: { left: 40, right: 20, bottom: 30, containLabel: true },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 30, fontSize: 11 } },
      yAxis: [
        { type: 'value', name: '人数', min: 0 },
        { type: 'value', name: '比率', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      ],
      series: [
        {
          name: '新会员',
          type: 'bar',
          data: trend.map(t => t.new_members),
          itemStyle: { color: '#1890ff' },
          yAxisIndex: 0,
        },
        {
          name: '复购率',
          type: 'line',
          data: trend.map(t => t.repurchase_rate),
          smooth: true,
          itemStyle: { color: '#52c41a' },
          yAxisIndex: 1,
        },
        {
          name: '旅程完成率',
          type: 'line',
          data: trend.map(t => t.journey_completion),
          smooth: true,
          itemStyle: { color: '#722ed1' },
          yAxisIndex: 1,
        },
      ],
    };
  }, [trend]);

  // ── Render ───────────────────────────────────────────────────────────────

  const m = metrics;

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>私域增长驾驶舱</Title>
          {m && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              更新于 {dayjs(m.as_of).format('MM-DD HH:mm')}
            </Text>
          )}
        </Col>
        <Col>
          <Space>
            <Select
              value={storeId}
              onChange={(v) => setStoreId(v)}
              style={{ width: 120 }}
            >
              {STORE_OPTIONS.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
            <Tooltip title="刷新">
              <ReloadOutlined
                style={{ cursor: 'pointer', fontSize: 16 }}
                onClick={() => { fetchMetrics(storeId); fetchTrend(storeId); }}
              />
            </Tooltip>
          </Space>
        </Col>
      </Row>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {/* ── 三角 KPI 主卡 ── */}
      <Row gutter={[16, 16]}>
        {/* ① 自有流量 */}
        <Col xs={24} lg={8}>
          <PillarCard
            icon={<TeamOutlined />}
            title="① 自有流量"
            color="#1890ff"
            loading={loading}
          >
            {m && (
              <>
                <Statistic
                  title="私域会员总数"
                  value={m.owned_audience.total_members}
                  suffix="人"
                  valueStyle={{ fontSize: 28, fontWeight: 'bold', color: '#1890ff' }}
                />
                <Divider style={{ margin: '12px 0' }} />
                <Row gutter={16}>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>近30天活跃</Text>
                    <div>
                      <Text strong>{m.owned_audience.active_members}</Text>
                      <Text type="secondary"> 人</Text>
                    </div>
                    <Progress
                      percent={Math.round(m.owned_audience.active_rate * 100)}
                      size="small"
                      strokeColor="#1890ff"
                    />
                  </Col>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>企微连接</Text>
                    <div>
                      <Text strong>{m.owned_audience.wxwork_connected}</Text>
                      <Text type="secondary"> 人</Text>
                    </div>
                    <Progress
                      percent={Math.round(m.owned_audience.connect_rate * 100)}
                      size="small"
                      strokeColor="#52c41a"
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 8 }}>
                  <Tag color="blue">本月新增 +{m.owned_audience.new_this_month}</Tag>
                </div>
              </>
            )}
          </PillarCard>
        </Col>

        {/* ② 客户价值 */}
        <Col xs={24} lg={8}>
          <PillarCard
            icon={<RiseOutlined />}
            title="② 客户价值"
            color="#52c41a"
            loading={loading}
          >
            {m && (
              <>
                <Statistic
                  title="30天复购率"
                  value={(m.customer_value.repeat_rate_30d * 100).toFixed(1)}
                  suffix="%"
                  valueStyle={{ fontSize: 28, fontWeight: 'bold', color: '#52c41a' }}
                />
                <Divider style={{ margin: '12px 0' }} />
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic
                      title={<><Text type="secondary" style={{ fontSize: 12 }}>平均 LTV</Text></>}
                      value={m.customer_value.avg_ltv_yuan}
                      prefix="¥"
                      precision={0}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title={<><Text type="secondary" style={{ fontSize: 12 }}>近30天客单</Text></>}
                      value={m.customer_value.avg_order_value_yuan}
                      prefix="¥"
                      precision={0}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">人均 {m.customer_value.avg_orders_per_member} 单</Tag>
                </div>
              </>
            )}
          </PillarCard>
        </Col>

        {/* ③ 旅程健康 */}
        <Col xs={24} lg={8}>
          <PillarCard
            icon={<ThunderboltOutlined />}
            title="③ 旅程健康"
            color="#722ed1"
            loading={loading}
          >
            {m && (
              <>
                <Statistic
                  title="90天旅程完成率"
                  value={(m.journey_health.completion_rate * 100).toFixed(1)}
                  suffix="%"
                  valueStyle={{ fontSize: 28, fontWeight: 'bold', color: '#722ed1' }}
                />
                <Divider style={{ margin: '12px 0' }} />
                <Row gutter={16}>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>进行中旅程</Text>
                    <div><Text strong style={{ fontSize: 20 }}>{m.journey_health.running_journeys}</Text></div>
                  </Col>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>已完成</Text>
                    <div><Text strong style={{ fontSize: 20 }}>{m.journey_health.completed_journeys}</Text></div>
                  </Col>
                </Row>
                <div style={{ marginTop: 8 }}>
                  {m.journey_health.bad_review_signals > 0 && (
                    <Tag color="red">差评信号 {m.journey_health.bad_review_signals}</Tag>
                  )}
                  {m.journey_health.churn_risk_count > 0 && (
                    <Tag color="orange">流失风险 {m.journey_health.churn_risk_count} 人</Tag>
                  )}
                  {m.journey_health.bad_review_signals === 0 && m.journey_health.churn_risk_count === 0 && (
                    <Tag color="green">运营健康</Tag>
                  )}
                </div>
              </>
            )}
          </PillarCard>
        </Col>
      </Row>

      {/* ── 生命周期漏斗 + 趋势图 ── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                生命周期漏斗
                <Tooltip title="按 lifecycle_state 字段统计会员分布，未分类成员按 frequency 估算">
                  <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                </Tooltip>
              </Space>
            }
            bordered={false}
            loading={loading}
          >
            {m ? (
              <>
                <ReactECharts option={funnelOption} style={{ height: 360 }} />
                {/* 图例 */}
                <Row gutter={[8, 4]} style={{ marginTop: 8 }}>
                  {Object.entries(LIFECYCLE_LABELS).map(([key, label]) => (
                    <Col key={key} span={8}>
                      <Space size={4}>
                        <span style={{
                          display: 'inline-block',
                          width: 10, height: 10,
                          borderRadius: 2,
                          background: LIFECYCLE_COLORS[key],
                        }} />
                        <Text style={{ fontSize: 11 }}>
                          {label}: {m.lifecycle_funnel[key as keyof LifecycleFunnel] ?? 0}
                        </Text>
                      </Space>
                    </Col>
                  ))}
                </Row>
              </>
            ) : (
              <div style={{ height: 360, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title="30天趋势（新会员 / 复购率 / 旅程完成率）"
            bordered={false}
            loading={trendLoading}
          >
            {trend.length > 0 ? (
              <ReactECharts option={trendOption} style={{ height: 420 }} />
            ) : (
              <div style={{ height: 420, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {trendLoading ? <Spin /> : <Text type="secondary">暂无趋势数据</Text>}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default PrivateDomainPage;
