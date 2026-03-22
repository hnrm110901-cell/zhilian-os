/**
 * 菜品经营综合月报页面 — Phase 6 Month 12
 * 3 Tabs: 月报总览 / 趋势对比 / 行动清单
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Tabs, Card, Button, Select, Spin, Alert, Row, Col,
  Typography, Tag, Table, Badge, Statistic, Divider,
  Space, Tooltip,
} from 'antd';
import {
  SyncOutlined, FileTextOutlined, RiseOutlined, FallOutlined,
  HeartOutlined, PieChartOutlined, DollarOutlined, DatabaseOutlined,
  BulbOutlined, WarningOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';

import { apiClient } from '../services/api';
import styles from './DishMonthlySummaryPage.module.css';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const DEFAULT_STORE = localStorage.getItem('store_id') || '';
const DEFAULT_PERIOD = dayjs().subtract(1, 'month').format('YYYY-MM');

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function fmtYuan(v: number | null | undefined) {
  if (v == null) return '-';
  return `¥${Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtPct(v: number | null | undefined, digits = 1) {
  if (v == null) return '-';
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
}

function DeltaTag({ v }: { v: number | null | undefined }) {
  if (v == null) return <Tag>-</Tag>;
  if (v >= 10)  return <Tag color="green">{fmtPct(v)}</Tag>;
  if (v >= 0)   return <Tag color="cyan">{fmtPct(v)}</Tag>;
  if (v >= -10) return <Tag color="mint">{fmtPct(v)}</Tag>;
  return <Tag color="red">{fmtPct(v)}</Tag>;
}

// ── 数据源指示器 ──────────────────────────────────────────────────────────────

const SOURCE_LABELS = ['盈利基线', '健康评分', '矩阵分析', 'PVM归因', '成本压缩'];

function DataSourceBadges({ count }: { count: number | undefined }) {
  return (
    <Space wrap>
      {SOURCE_LABELS.map((label, i) => (
        <Badge
          key={label}
          status={i < (count ?? 0) ? 'success' : 'default'}
          text={<Text type={i < (count ?? 0) ? undefined : 'secondary'} style={{ fontSize: 12 }}>{label}</Text>}
        />
      ))}
    </Space>
  );
}

// ── Tab 1: 月报总览 ───────────────────────────────────────────────────────────

function OverviewTab({ data }: { data: Record<string, any> | null }) {
  if (!data) return <Alert message="暂无数据，请先构建月报" type="info" showIcon />;

  const deltaColor = (data.revenue_delta_pct ?? 0) >= 0 ? '#1A7A52' : '#C53030';

  return (
    <div className={styles.overviewWrap}>
      {/* 洞察文本 banner */}
      {data.insight_text && (
        <Alert
          className={styles.insightBanner}
          icon={<BulbOutlined />}
          message={<Text strong>AI 经营洞察</Text>}
          description={data.insight_text}
          type="success"
          showIcon
        />
      )}

      {/* 数据源完整度 */}
      <Card size="small" className={styles.sourceCard}
        title={<><DatabaseOutlined /> 数据源完整度 ({data.data_sources_available ?? 0}/5)</>}>
        <DataSourceBadges count={data.data_sources_available} />
      </Card>

      {/* 营收基线 */}
      <Card title={<><RiseOutlined /> 营收概览</>} className={styles.sectionCard}>
        <Row gutter={16}>
          <Col span={8}>
            <Statistic title="本期菜品数" value={data.total_dishes ?? '-'} suffix="道" />
          </Col>
          <Col span={8}>
            <Statistic title="本期总营收" value={fmtYuan(data.total_revenue)} />
          </Col>
          <Col span={8}>
            <Statistic
              title="环比变化"
              value={data.revenue_delta_pct != null ? `${Number(data.revenue_delta_pct) >= 0 ? '+' : ''}${Number(data.revenue_delta_pct).toFixed(1)}%` : '-'}
              valueStyle={{ color: deltaColor }}
              prefix={data.revenue_delta_pct != null ? (data.revenue_delta_pct >= 0 ? <RiseOutlined /> : <FallOutlined />) : null}
            />
          </Col>
        </Row>
      </Card>

      {/* 健康评分 */}
      {data.avg_health_score != null && (
        <Card title={<><HeartOutlined /> 菜品健康评分</>} className={styles.sectionCard}>
          <Row gutter={16}>
            <Col span={6}><Statistic title="平均健康分" value={Number(data.avg_health_score).toFixed(1)} suffix="/ 100" /></Col>
            <Col span={6}><Statistic title="优秀" value={data.excellent_count ?? 0} valueStyle={{ color: '#1A7A52' }} /></Col>
            <Col span={6}><Statistic title="良好" value={data.good_count ?? 0} valueStyle={{ color: '#FF6B2C' }} /></Col>
            <Col span={6}><Statistic title="待改善" value={(data.poor_count ?? 0) + (data.immediate_action_count ?? 0)} valueStyle={{ color: '#C53030' }} /></Col>
          </Row>
        </Card>
      )}

      {/* BCG 矩阵 */}
      {data.star_count != null && (
        <Card title={<><PieChartOutlined /> BCG 矩阵分布</>} className={styles.sectionCard}>
          <Row gutter={16}>
            <Col span={6}><Statistic title="⭐ 明星菜" value={data.star_count ?? 0} valueStyle={{ color: '#faad14' }} /></Col>
            <Col span={6}><Statistic title="🐄 现金牛" value={data.cash_cow_count ?? 0} valueStyle={{ color: '#1A7A52' }} /></Col>
            <Col span={6}><Statistic title="❓ 问题菜" value={data.question_mark_count ?? 0} valueStyle={{ color: '#FF6B2C' }} /></Col>
            <Col span={6}><Statistic title="🐕 瘦狗菜" value={data.dog_count ?? 0} valueStyle={{ color: '#8c8c8c' }} /></Col>
          </Row>
          {data.matrix_total_impact_yuan != null && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">矩阵优化潜在影响: </Text>
              <Text strong>{fmtYuan(data.matrix_total_impact_yuan)}</Text>
            </div>
          )}
        </Card>
      )}

      {/* PVM 归因 */}
      {data.dominant_driver != null && (
        <Card title={<><FallOutlined /> PVM 营收归因</>} className={styles.sectionCard}>
          <Row gutter={16}>
            <Col span={6}><Statistic title="分析菜品数" value={data.pvm_dish_count ?? '-'} /></Col>
            <Col span={6}><Statistic title="总营收变动" value={fmtYuan(data.total_pvm_delta)} /></Col>
            <Col span={6}>
              <div>
                <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>主导驱动</Text>
                <Tag color={data.dominant_driver === 'price' ? 'purple' : data.dominant_driver === 'volume' ? 'blue' : 'default'} style={{ fontSize: 14 }}>
                  {data.dominant_driver === 'price' ? '价格驱动' :
                   data.dominant_driver === 'volume' ? '销量驱动' :
                   data.dominant_driver === 'interaction' ? '交互效应' : data.dominant_driver}
                </Tag>
              </div>
            </Col>
            <Col span={6}><Statistic title="价格效应" value={fmtYuan(data.total_price_effect)} /></Col>
          </Row>
        </Card>
      )}

      {/* 成本压缩 */}
      {data.total_expected_saving != null && (
        <Card title={<><DollarOutlined /> 成本压缩机会</>} className={styles.sectionCard}>
          <Row gutter={16}>
            <Col span={6}><Statistic title="涉及菜品数" value={data.compression_dish_count ?? '-'} /></Col>
            <Col span={6}><Statistic title="年化节省空间" value={fmtYuan(data.total_expected_saving)} valueStyle={{ color: '#1A7A52' }} /></Col>
            <Col span={6}><Statistic title="需重新谈判" value={data.renegotiate_count ?? 0} valueStyle={{ color: '#C53030' }} /></Col>
            <Col span={6}><Statistic title="FCR恶化菜品" value={data.worsening_fcr_count ?? 0} valueStyle={{ color: '#C8923A' }} /></Col>
          </Row>
        </Card>
      )}

      <div className={styles.genAt}>
        <Text type="secondary">报告生成时间：{data.generated_at ? dayjs(data.generated_at).format('YYYY-MM-DD HH:mm') : '-'}</Text>
      </div>
    </div>
  );
}

// ── Tab 2: 趋势对比 ───────────────────────────────────────────────────────────

function TrendTab({ history }: { history: Record<string, any>[] }) {
  if (history.length === 0) return <Alert message="暂无历史数据" type="info" showIcon />;

  const periods = [...history].reverse().map(r => r.period);

  const revenueOpt = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['总营收', '环比%'] },
    xAxis: { type: 'category', data: periods },
    yAxis: [
      { type: 'value', name: '营收(元)', axisLabel: { formatter: (v: number) => `¥${(v / 10000).toFixed(0)}万` } },
      { type: 'value', name: '环比%', axisLabel: { formatter: (v: number) => `${v}%` } },
    ],
    series: [
      { name: '总营收', type: 'bar', data: [...history].reverse().map(r => Number(r.total_revenue ?? 0)), itemStyle: { color: '#FF6B2C' } },
      { name: '环比%', type: 'line', yAxisIndex: 1, data: [...history].reverse().map(r => r.revenue_delta_pct != null ? Number(r.revenue_delta_pct) : null), itemStyle: { color: '#1A7A52' }, connectNulls: true },
    ],
  };

  const healthOpt = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['平均健康分', '年化节省'] },
    xAxis: { type: 'category', data: periods },
    yAxis: [
      { type: 'value', name: '健康分', min: 0, max: 100 },
      { type: 'value', name: '年化节省(元)', axisLabel: { formatter: (v: number) => `¥${(v / 10000).toFixed(0)}万` } },
    ],
    series: [
      { name: '平均健康分', type: 'line', data: [...history].reverse().map(r => r.avg_health_score != null ? Number(r.avg_health_score) : null), itemStyle: { color: '#C8923A' }, connectNulls: true },
      { name: '年化节省', type: 'bar', yAxisIndex: 1, data: [...history].reverse().map(r => r.total_expected_saving != null ? Number(r.total_expected_saving) : null), itemStyle: { color: '#1A7A52' } },
    ],
  };

  const matrixOpt = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['明星', '现金牛', '问题', '瘦狗'] },
    xAxis: { type: 'category', data: periods },
    yAxis: { type: 'value', name: '菜品数' },
    series: [
      { name: '明星',  type: 'bar', stack: 'total', data: [...history].reverse().map(r => r.star_count ?? 0),          itemStyle: { color: '#faad14' } },
      { name: '现金牛', type: 'bar', stack: 'total', data: [...history].reverse().map(r => r.cash_cow_count ?? 0),      itemStyle: { color: '#1A7A52' } },
      { name: '问题',  type: 'bar', stack: 'total', data: [...history].reverse().map(r => r.question_mark_count ?? 0), itemStyle: { color: '#FF6B2C' } },
      { name: '瘦狗',  type: 'bar', stack: 'total', data: [...history].reverse().map(r => r.dog_count ?? 0),           itemStyle: { color: '#8c8c8c' } },
    ],
  };

  return (
    <div className={styles.trendWrap}>
      <Card title="营收趋势" className={styles.chartCard}>
        <ReactECharts option={revenueOpt} style={{ height: 280 }} />
      </Card>
      <Card title="健康评分 & 成本节省趋势" className={styles.chartCard}>
        <ReactECharts option={healthOpt} style={{ height: 280 }} />
      </Card>
      <Card title="BCG 矩阵历史分布" className={styles.chartCard}>
        <ReactECharts option={matrixOpt} style={{ height: 280 }} />
      </Card>
    </div>
  );
}

// ── Tab 3: 行动清单 ───────────────────────────────────────────────────────────

interface ActionItem {
  key: string;
  source: string;
  priority: 'high' | 'medium' | 'low';
  action: string;
  impact: string;
}

function buildActionItems(data: Record<string, any> | null): ActionItem[] {
  if (!data) return [];
  const items: ActionItem[] = [];

  if ((data.immediate_action_count ?? 0) > 0) {
    items.push({ key: 'health-1', source: '健康评分', priority: 'high', action: `立即处理 ${data.immediate_action_count} 道评分极低菜品`, impact: '降低经营风险' });
  }
  if ((data.poor_count ?? 0) > 0) {
    items.push({ key: 'health-2', source: '健康评分', priority: 'medium', action: `改善 ${data.poor_count} 道低健康评分菜品`, impact: '提升整体健康分' });
  }
  if ((data.dog_count ?? 0) > 0 && data.total_dishes > 0 && data.dog_count / data.total_dishes >= 0.3) {
    items.push({ key: 'matrix-1', source: 'BCG矩阵', priority: 'high', action: `精简 ${data.dog_count} 道瘦狗菜品`, impact: '优化菜单结构' });
  }
  if ((data.star_count ?? 0) > 0) {
    items.push({ key: 'matrix-2', source: 'BCG矩阵', priority: 'medium', action: `重点推广 ${data.star_count} 道明星菜品`, impact: `营收提升潜力 ${fmtYuan(data.matrix_total_impact_yuan)}` });
  }
  if ((data.renegotiate_count ?? 0) > 0) {
    items.push({ key: 'compress-1', source: '成本压缩', priority: 'high', action: `对 ${data.renegotiate_count} 道菜品与供应商重新谈判`, impact: `年化节省 ${fmtYuan(data.total_expected_saving)}` });
  }
  if ((data.worsening_fcr_count ?? 0) > 0) {
    items.push({ key: 'compress-2', source: '成本压缩', priority: 'medium', action: `监控 ${data.worsening_fcr_count} 道FCR持续恶化菜品`, impact: '防止成本率上升' });
  }
  if (data.dominant_driver === 'price') {
    items.push({ key: 'pvm-1', source: 'PVM归因', priority: 'medium', action: '审查价格策略，分析提价/降价影响', impact: `总营收变动 ${fmtYuan(data.total_pvm_delta)}` });
  } else if (data.dominant_driver === 'volume') {
    items.push({ key: 'pvm-1', source: 'PVM归因', priority: 'medium', action: '分析销量下滑/增长根因，优化推广策略', impact: `总营收变动 ${fmtYuan(data.total_pvm_delta)}` });
  }

  if (items.length === 0) {
    items.push({ key: 'ok-1', source: '综合评估', priority: 'low', action: '本期各项指标平稳，维持现有运营策略', impact: '持续监控' });
  }

  return items;
}

const PRIORITY_TAG: Record<string, { color: string; label: string }> = {
  high:   { color: 'red',    label: '紧急' },
  medium: { color: 'orange', label: '重要' },
  low:    { color: 'default', label: '常规' },
};

function ActionTab({ data }: { data: Record<string, any> | null }) {
  const items = buildActionItems(data);
  const columns: ColumnsType<ActionItem> = [
    {
      title: '优先级', dataIndex: 'priority', width: 80,
      render: (v) => <Tag color={PRIORITY_TAG[v]?.color}>{PRIORITY_TAG[v]?.label}</Tag>,
      sorter: (a, b) => { const o = { high: 0, medium: 1, low: 2 }; return o[a.priority] - o[b.priority]; },
    },
    { title: '数据来源', dataIndex: 'source', width: 110, render: (v) => <Tag>{v}</Tag> },
    { title: '建议行动', dataIndex: 'action', ellipsis: true },
    { title: '预期影响', dataIndex: 'impact', width: 200, render: (v) => <Text type="success">{v}</Text> },
  ];

  return (
    <Table
      columns={columns}
      dataSource={items}
      rowKey="key"
      size="middle"
      pagination={false}
      rowClassName={(r) => r.priority === 'high' ? styles.rowHigh : r.priority === 'medium' ? styles.rowMedium : ''}
    />
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const DishMonthlySummaryPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(DEFAULT_STORE);
  const [storeOptions, setStoreOptions] = useState<string[]>([DEFAULT_STORE]);
  const [period,  setPeriod]    = useState(DEFAULT_PERIOD);

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [data,    setData]      = useState<Record<string, any> | null>(null);
  const [history, setHistory]   = useState<Record<string, any>[]>([]);
  const [loading, setLoading]   = useState(false);
  const [building, setBuilding] = useState(false);
  const [error,   setError]     = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, historyRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-monthly-summary/${storeId}?period=${period}`),
        apiClient.get(`/api/v1/dish-monthly-summary/history/${storeId}?periods=6`),
      ]);
      if (summaryRes.data.ok) {
        setData(summaryRes.data.data);
      } else {
        setData(null);
        setError(summaryRes.data.error ?? '查询失败');
      }
      if (historyRes.data.ok) setHistory(historyRes.data.data ?? []);
    } catch (e: any) {
      setError(e.message ?? '请求失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, period]);

  const handleBuild = useCallback(async () => {
    setBuilding(true);
    setError(null);
    try {
      const res = await apiClient.post(`/api/v1/dish-monthly-summary/build/${storeId}?period=${period}`);
      if (res.data.ok) {
        await fetchData();
      } else {
        setError(res.data.error ?? '构建失败');
      }
    } catch (e: any) {
      setError(e.message ?? '请求失败');
    } finally {
      setBuilding(false);
    }
  }, [storeId, period, fetchData]);

  const periods = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <FileTextOutlined /> 菜品经营综合月报
        </Title>
        <Space wrap>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periods.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Button icon={<SyncOutlined />} onClick={fetchData} loading={loading}>查询</Button>
          <Tooltip title="聚合本期所有分析数据源，生成月度汇总（幂等操作）">
            <Button type="primary" icon={<FileTextOutlined />} onClick={handleBuild} loading={building}>
              构建月报
            </Button>
          </Tooltip>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon closable onClose={() => setError(null)} style={{ marginBottom: 16 }} />}

      <Spin spinning={loading || building}>
        <Tabs
          items={[
            {
              key: 'overview',
              label: <><FileTextOutlined />月报总览</>,
              children: <OverviewTab data={data} />,
            },
            {
              key: 'trend',
              label: <><RiseOutlined />趋势对比</>,
              children: <TrendTab history={history} />,
            },
            {
              key: 'actions',
              label: <><BulbOutlined />行动清单 {data && <Badge count={buildActionItems(data).filter(i => i.priority === 'high').length} offset={[4, -2]} />}</>,
              children: <ActionTab data={data} />,
            },
          ]}
        />
      </Spin>
    </div>
  );
};

export default DishMonthlySummaryPage;
