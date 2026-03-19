/**
 * 菜单优化建议引擎 — Phase 6 Month 2
 * 消费 BCG 数据，为每道菜生成¥量化优化建议（提价/降本/推广/下架/套餐）
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty, Badge, Popconfirm,
} from 'antd';
import {
  BulbOutlined, RiseOutlined, DollarOutlined, CheckCircleOutlined,
  SyncOutlined, CloseCircleOutlined, BarChartOutlined, FireOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './MenuOptimizationPage.module.css';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

// ── 建议类型配置 ──────────────────────────────────────────────────────────────
const REC_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  price_increase: { label: '提价空间', color: '#1A7A52',  icon: '📈' },
  cost_reduction: { label: '降本优化', color: '#0AAF9A',  icon: '🔧' },
  promote:        { label: '推广增量', color: '#C8923A',  icon: '📣' },
  discontinue:    { label: '建议下架', color: '#C53030',  icon: '🗑️' },
  bundle:         { label: '套餐捆绑', color: '#722ed1',  icon: '🎁' },
};

const BCG_CONFIG: Record<string, { label: string; color: string }> = {
  star:          { label: '明星菜', color: '#faad14' },
  cash_cow:      { label: '现金牛', color: '#1A7A52' },
  question_mark: { label: '问题菜', color: '#0AAF9A' },
  dog:           { label: '瘦狗菜', color: '#C53030' },
};

const URGENCY_CONFIG: Record<string, { label: string; color: string }> = {
  high:   { label: '紧急', color: 'red' },
  medium: { label: '一般', color: 'orange' },
  low:    { label: '低',   color: 'default' },
};

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface Rec {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  bcg_quadrant: string;
  rec_type: string;
  rec_label: string;
  title: string;
  description: string;
  action: string;
  expected_revenue_impact_yuan: number;
  expected_cost_impact_yuan: number;
  expected_profit_impact_yuan: number;
  confidence_pct: number;
  priority_score: number;
  urgency: string;
  current_fcr: number;
  current_gpm: number;
  current_order_count: number;
  current_avg_price: number;
  current_revenue_yuan: number;
  current_profit_yuan: number;
  status: string;
}

interface SummaryByType {
  rec_type: string;
  label: string;
  count: number;
  total_profit_impact_yuan: number;
  adopted: number;
  pending: number;
}

interface Summary {
  by_type: SummaryByType[];
  total_pending_profit_impact_yuan: number;
  pending_count: number;
  adopted_count: number;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────
const fmt = (n: number) =>
  `¥${Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPct = (n: number) => `${n.toFixed(1)}%`;

// ── 建议卡片 ──────────────────────────────────────────────────────────────────
const RecCard: React.FC<{
  rec: Rec;
  onAdopt: (id: number) => void;
  onDismiss: (id: number) => void;
  loading: boolean;
}> = ({ rec, onAdopt, onDismiss, loading }) => {
  const cfg    = REC_CONFIG[rec.rec_type] || { label: rec.rec_type, color: '#aaa', icon: '💡' };
  const bcgCfg = BCG_CONFIG[rec.bcg_quadrant] || { label: rec.bcg_quadrant, color: '#aaa' };
  const urgCfg = URGENCY_CONFIG[rec.urgency]  || { label: rec.urgency, color: 'default' };

  return (
    <div className={styles.recCard}
      style={{ borderLeftColor: cfg.color,
               opacity: rec.status !== 'pending' ? 0.6 : 1 }}>
      <div className={styles.recCardHeader}>
        <Space wrap>
          <span style={{ fontSize: 18 }}>{cfg.icon}</span>
          <Tag color={cfg.color}>{cfg.label}</Tag>
          <Tag color={bcgCfg.color}>{bcgCfg.label}</Tag>
          <Badge status={urgCfg.color as any} text={urgCfg.label} />
          {rec.status !== 'pending' && (
            <Tag color={rec.status === 'adopted' ? 'green' : 'default'}>
              {rec.status === 'adopted' ? '已采纳' : '已忽略'}
            </Tag>
          )}
        </Space>
        <Text strong style={{ fontSize: 15 }}>{rec.dish_name}</Text>
      </div>

      <Title level={5} style={{ margin: '8px 0 4px', color: cfg.color }}>
        {rec.title}
      </Title>
      <Paragraph style={{ margin: '0 0 8px', color: '#555', fontSize: 13 }}>
        {rec.description}
      </Paragraph>

      <div className={styles.recCardAction}>
        <Text type="secondary" style={{ fontSize: 12 }}>📋 建议操作：</Text>
        <Text style={{ fontSize: 13 }}>{rec.action}</Text>
      </div>

      <Row gutter={16} style={{ marginTop: 10 }}>
        <Col span={8}>
          <Statistic
            title="预期增利"
            value={rec.expected_profit_impact_yuan.toFixed(0)}
            prefix="¥"
            valueStyle={{
              color: rec.expected_profit_impact_yuan >= 0 ? '#1A7A52' : '#C53030',
              fontSize: 18,
            }}
          />
        </Col>
        <Col span={8}>
          <Statistic title="置信度" value={fmtPct(rec.confidence_pct)}
            valueStyle={{ fontSize: 16 }} />
        </Col>
        <Col span={8}>
          <Statistic title="优先分" value={rec.priority_score.toFixed(0)}
            suffix="/ 100" valueStyle={{ fontSize: 16 }} />
        </Col>
      </Row>

      <Row gutter={8} style={{ marginTop: 8, fontSize: 12, color: '#888' }}>
        <Col>食材成本率 {fmtPct(rec.current_fcr)}</Col>
        <Col>·</Col>
        <Col>毛利率 {fmtPct(rec.current_gpm)}</Col>
        <Col>·</Col>
        <Col>月销 {rec.current_order_count} 次</Col>
        <Col>·</Col>
        <Col>均价 {fmt(rec.current_avg_price)}</Col>
      </Row>

      {rec.status === 'pending' && (
        <div className={styles.recCardFooter}>
          <Popconfirm title="确认采纳此建议？" onConfirm={() => onAdopt(rec.id)}
            okText="采纳" cancelText="取消">
            <Button size="small" type="primary" icon={<CheckCircleOutlined />}
              loading={loading} style={{ background: cfg.color, borderColor: cfg.color }}>
              采纳
            </Button>
          </Popconfirm>
          <Popconfirm title="确认忽略此建议？" onConfirm={() => onDismiss(rec.id)}
            okText="忽略" cancelText="取消">
            <Button size="small" danger icon={<CloseCircleOutlined />} loading={loading}>
              忽略
            </Button>
          </Popconfirm>
        </div>
      )}
    </div>
  );
};

// ── 主页面 ────────────────────────────────────────────────────────────────────
const MenuOptimizationPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState(localStorage.getItem('store_id') || '');
  const [storeOptions, setStoreOptions] = useState<string[]>([]);
  const [period,    setPeriod]    = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);
  const [generating, setGenerating] = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [actionLoad, setActionLoad] = useState(false);
  const [recs,       setRecs]       = useState<Rec[]>([]);
  const [summary,    setSummary]    = useState<Summary | null>(null);
  const [recTypeFilter, setRecTypeFilter] = useState<string | undefined>(undefined);
  const [statusFilter,  setStatusFilter]  = useState<string>('pending');
  const [activeTab, setActiveTab] = useState('list');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, sumRes] = await Promise.all([
        apiClient.get(`/api/v1/menu-opt/${storeId}`, {
          params: { period, rec_type: recTypeFilter, status: statusFilter, limit: 100 },
        }),
        apiClient.get(`/api/v1/menu-opt/summary/${storeId}`, { params: { period } }),
      ]);
      setRecs(recRes.data.recommendations || []);
      setSummary(sumRes.data || null);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period, recTypeFilter, statusFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await apiClient.post(`/api/v1/menu-opt/generate/${storeId}`,
        null, { params: { period } });
      message.success(`生成完成：${res.data.dish_count} 道菜 / ${res.data.rec_count} 条建议`);
      fetchAll();
    } catch (e) {
      handleApiError(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleAdopt = async (recId: number) => {
    setActionLoad(true);
    try {
      await apiClient.post(`/api/v1/menu-opt/${recId}/adopt`);
      message.success('已采纳建议');
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setActionLoad(false); }
  };

  const handleDismiss = async (recId: number) => {
    setActionLoad(true);
    try {
      await apiClient.post(`/api/v1/menu-opt/${recId}/dismiss`);
      message.info('已忽略建议');
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setActionLoad(false); }
  };

  // ── KPI ───────────────────────────────────────────────────────────────────
  const pendingRecs    = summary?.pending_count ?? 0;
  const adoptedRecs    = summary?.adopted_count ?? 0;
  const totalImpact    = summary?.total_pending_profit_impact_yuan ?? 0;
  const highUrgency    = recs.filter(r => r.urgency === 'high' && r.status === 'pending').length;

  // ── 汇总柱状图 ─────────────────────────────────────────────────────────────
  const barOption = () => {
    if (!summary) return {};
    const types = summary.by_type.filter(t => t.count > 0);
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['预期增利¥', '已采纳数'], bottom: 0 },
      grid: { left: 60, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: types.map(t => t.label), axisLabel: { fontSize: 11 } },
      yAxis: [
        { type: 'value', name: '¥', axisLabel: { formatter: (v: number) => `${(v/1000).toFixed(0)}k` } },
        { type: 'value', name: '数量', splitLine: { show: false } },
      ],
      series: [
        {
          name: '预期增利¥', type: 'bar',
          data: types.map(t => ({
            value: t.total_profit_impact_yuan,
            itemStyle: { color: REC_CONFIG[t.rec_type]?.color || '#aaa' },
          })),
          label: { show: true, position: 'top', formatter: (p: any) => fmt(p.value) },
        },
        {
          name: '已采纳数', type: 'line', yAxisIndex: 1,
          data: types.map(t => t.adopted),
          itemStyle: { color: '#1A7A52' },
          symbol: 'circle', symbolSize: 8,
        },
      ],
    };
  };

  // ── 紧急度饼图 ─────────────────────────────────────────────────────────────
  const urgencyPieOption = () => {
    const counts = { high: 0, medium: 0, low: 0 };
    recs.filter(r => r.status === 'pending').forEach(r => {
      if (r.urgency in counts) counts[r.urgency as keyof typeof counts]++;
    });
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c}条 ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        data: [
          { name: '紧急', value: counts.high,   itemStyle: { color: '#C53030' } },
          { name: '一般', value: counts.medium, itemStyle: { color: '#C8923A' } },
          { name: '低',   value: counts.low,    itemStyle: { color: '#bbb' } },
        ],
        label: { formatter: '{b}\n{c}' },
      }],
    };
  };

  // ── 菜单健康评分 ──────────────────────────────────────────────────────────
  const computeHealthScore = () => {
    if (!summary) return 0;
    // 评分公式：已采纳率×40 + 无下架建议×30 + 无紧急建议×30
    const total        = (summary.pending_count || 0) + (summary.adopted_count || 0);
    const adoptionRate = total > 0 ? summary.adopted_count / total : 0;
    const discCount    = summary.by_type.find(t => t.rec_type === 'discontinue')?.count || 0;
    const noDisc       = discCount === 0 ? 1.0 : Math.max(0, 1 - discCount / 5);
    const noUrgency    = highUrgency === 0 ? 1.0 : Math.max(0, 1 - highUrgency / 5);
    return Math.round(adoptionRate * 40 + noDisc * 30 + noUrgency * 30);
  };

  const healthScore = computeHealthScore();
  const healthColor = healthScore >= 70 ? '#1A7A52' : healthScore >= 40 ? '#C8923A' : '#C53030';

  const gaugeOption = () => ({
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      startAngle: 200, endAngle: -20, min: 0, max: 100,
      pointer: { itemStyle: { color: healthColor } },
      progress: { show: true, itemStyle: { color: healthColor } },
      axisLine: { lineStyle: { width: 12, color: [[1, '#eee']] } },
      axisTick: { show: false },
      splitLine: { length: 10, lineStyle: { width: 2 } },
      axisLabel: { distance: 15, fontSize: 10 },
      detail: {
        valueAnimation: true,
        formatter: '{value}',
        fontSize: 32, fontWeight: 700,
        color: healthColor, offsetCenter: [0, '60%'],
      },
      data: [{ value: healthScore, name: '菜单健康分' }],
    }],
  });

  // ── 月份选项 ──────────────────────────────────────────────────────────────
  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ─────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <BulbOutlined /> 菜单优化建议
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="读取BCG数据，为每道菜生成优化建议">
            <Button type="primary" icon={<SyncOutlined spin={generating} />}
              onClick={handleGenerate} loading={generating}>
              生成建议
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── KPI 卡片 ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="待处理建议" value={pendingRecs} suffix="条"
              prefix={<BulbOutlined />} valueStyle={{ color: '#0AAF9A' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="紧急建议" value={highUrgency} suffix="条"
              prefix={<FireOutlined />} valueStyle={{ color: '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="预期总增利" value={totalImpact.toFixed(0)}
              prefix="¥" valueStyle={{ color: '#1A7A52' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="已采纳建议" value={adoptedRecs} suffix="条"
              prefix={<CheckCircleOutlined />} valueStyle={{ color: '#1A7A52' }} />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 ───────────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'list',
            label: <span><BulbOutlined /> 建议列表</span>,
            children: (
              <Spin spinning={loading}>
                {/* 过滤器 */}
                <Space style={{ marginBottom: 12 }}>
                  <Select value={recTypeFilter} onChange={setRecTypeFilter}
                    style={{ width: 130 }} allowClear placeholder="建议类型">
                    {Object.entries(REC_CONFIG).map(([k, v]) => (
                      <Option key={k} value={k}>{v.icon} {v.label}</Option>
                    ))}
                  </Select>
                  <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 110 }}>
                    <Option value="pending">待处理</Option>
                    <Option value="adopted">已采纳</Option>
                    <Option value="dismissed">已忽略</Option>
                  </Select>
                </Space>

                {recs.length === 0 ? (
                  <Empty description="暂无建议，请先点击「生成建议」" />
                ) : (
                  <div className={styles.recGrid}>
                    {recs.map(rec => (
                      <RecCard key={rec.id} rec={rec}
                        onAdopt={handleAdopt} onDismiss={handleDismiss}
                        loading={actionLoad} />
                    ))}
                  </div>
                )}
              </Spin>
            ),
          },
          {
            key: 'analysis',
            label: <span><BarChartOutlined /> 汇总分析</span>,
            children: (
              <Spin spinning={loading}>
                {!summary ? <Empty /> : (
                  <Row gutter={16}>
                    <Col xs={24} lg={14}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        各建议类型预期¥增利
                      </Text>
                      <ReactECharts option={barOption()} style={{ height: 320 }} notMerge />
                    </Col>
                    <Col xs={24} lg={10}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        待处理建议紧急度分布
                      </Text>
                      <ReactECharts option={urgencyPieOption()} style={{ height: 240 }} notMerge />
                      <Table
                        dataSource={summary.by_type}
                        rowKey="rec_type"
                        size="small"
                        pagination={false}
                        style={{ marginTop: 12 }}
                        columns={[
                          { title: '类型', dataIndex: 'label',
                            render: (l: string, r: SummaryByType) => (
                              <Space>
                                <span>{REC_CONFIG[r.rec_type]?.icon}</span>
                                <Tag color={REC_CONFIG[r.rec_type]?.color}>{l}</Tag>
                              </Space>
                            )},
                          { title: '数量', dataIndex: 'count', width: 60 },
                          { title: '预期增利', dataIndex: 'total_profit_impact_yuan',
                            render: (v: number) => <Text style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>{fmt(v)}</Text> },
                          { title: '已采纳', dataIndex: 'adopted', width: 60 },
                        ]}
                      />
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
          {
            key: 'health',
            label: <span><RiseOutlined /> 菜单健康</span>,
            children: (
              <Spin spinning={loading}>
                <Row gutter={16} align="middle">
                  <Col xs={24} md={10}>
                    <ReactECharts option={gaugeOption()} style={{ height: 280 }} notMerge />
                    <div style={{ textAlign: 'center', marginTop: -20 }}>
                      <Text type="secondary">菜单健康综合评分（满分100）</Text>
                    </div>
                  </Col>
                  <Col xs={24} md={14}>
                    <div className={styles.healthBreakdown}>
                      <div className={styles.healthItem}>
                        <Text strong>建议采纳率</Text>
                        <Text style={{ color: '#1A7A52' }}>
                          {summary && (summary.pending_count + summary.adopted_count) > 0
                            ? fmtPct(summary.adopted_count / (summary.pending_count + summary.adopted_count) * 100)
                            : '—'}
                        </Text>
                        <Text type="secondary">占总分 40%</Text>
                      </div>
                      <div className={styles.healthItem}>
                        <Text strong>下架建议数</Text>
                        <Text style={{ color: (summary?.by_type.find(t => t.rec_type === 'discontinue')?.count ?? 0) > 0 ? '#C53030' : '#1A7A52' }}>
                          {summary?.by_type.find(t => t.rec_type === 'discontinue')?.count ?? 0} 条
                        </Text>
                        <Text type="secondary">占总分 30%（越少越好）</Text>
                      </div>
                      <div className={styles.healthItem}>
                        <Text strong>紧急建议数</Text>
                        <Text style={{ color: highUrgency > 0 ? '#C53030' : '#1A7A52' }}>
                          {highUrgency} 条
                        </Text>
                        <Text type="secondary">占总分 30%（越少越好）</Text>
                      </div>
                    </div>
                    <div className={styles.healthTip}
                      style={{ borderColor: healthColor, background: `${healthColor}15` }}>
                      <Text strong style={{ color: healthColor }}>
                        {healthScore >= 70 ? '✅ 菜单状态良好，继续保持！'
                          : healthScore >= 40 ? '⚠️ 有待优化，请关注紧急建议'
                          : '🚨 菜单需要重点优化，立即行动！'}
                      </Text>
                    </div>
                  </Col>
                </Row>
              </Spin>
            ),
          },
        ]} />
      </Card>
    </div>
  );
};

export default MenuOptimizationPage;
