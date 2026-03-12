/**
 * 菜品智能定价引擎 — Phase 6 Month 5
 * 基于BCG象限+需求弹性推荐具体售价，量化¥收入/利润变化，支持采纳跟踪
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Select, Button, Table, Tag, Tabs, Spin,
  Typography, Space, Tooltip, message, Empty, Popconfirm, InputNumber,
  Modal,
} from 'antd';
import {
  RiseOutlined, FallOutlined, DollarOutlined, SyncOutlined,
  CheckCircleOutlined, StopOutlined, BarChartOutlined, LineChartOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './DishPricingPage.module.css';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 配置 ──────────────────────────────────────────────────────────────────────
const ACTION_CONFIG: Record<string, { label: string; color: string; antColor: string; icon: React.ReactNode }> = {
  increase: { label: '建议提价', color: '#1A7A52', antColor: 'success', icon: <RiseOutlined /> },
  decrease: { label: '建议降价', color: '#0AAF9A', antColor: 'processing', icon: <FallOutlined /> },
  maintain: { label: '维持定价', color: '#8c8c8c', antColor: 'default', icon: <DollarOutlined /> },
};

const ELASTICITY_CONFIG: Record<string, { label: string; color: string }> = {
  inelastic: { label: '低弹性', color: '#1A7A52' },
  moderate:  { label: '中弹性', color: '#C8923A' },
  elastic:   { label: '高弹性', color: '#C53030' },
};

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface PricingRec {
  id: number;
  dish_id: string;
  dish_name: string;
  category: string;
  bcg_quadrant: string;
  current_price: number;
  order_count: number;
  revenue_yuan: number;
  gross_profit_margin: number;
  food_cost_rate: number;
  rec_action: string;
  suggested_price: number;
  price_change_pct: number;
  elasticity_class: string;
  expected_order_count: number;
  expected_revenue_delta_yuan: number;
  expected_profit_delta_yuan: number;
  confidence_pct: number;
  reasoning: string;
  status: string;
  adopted_price: number | null;
  adopted_at: string | null;
  dismissed_at: string | null;
}

interface ActionStat {
  rec_action: string;
  total: number;
  pending: number;
  adopted: number;
  dismissed: number;
  total_rev_delta: number;
  total_profit_delta: number;
  avg_confidence: number;
}

interface Summary {
  store_id: string;
  period: string;
  total_dishes: number;
  total_adopted: number;
  adoption_rate: number;
  by_action: ActionStat[];
  total_rev_delta_yuan: number;
  total_profit_delta_yuan: number;
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────
const fmt  = (n: number) =>
  `¥${Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const fmtPrice = (n: number) => `¥${Number(n).toFixed(1)}`;
const fmtPct   = (n: number) => `${Number(n).toFixed(1)}%`;

// ── 主页面 ────────────────────────────────────────────────────────────────────
const DishPricingPage: React.FC = () => {
  const [storeId,     setStoreId]     = useState('S001');
  const [storeOptions, setStoreOptions] = useState<string[]>(['S001']);
  const [period,      setPeriod]      = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));
  const [generating,  setGenerating]  = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [actioning,   setActioning]   = useState(false);
  const [recs,        setRecs]        = useState<PricingRec[]>([]);
  const [summary,     setSummary]     = useState<Summary | null>(null);
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [activeTab,   setActiveTab]   = useState('list');
  // 采纳弹窗
  const [adoptModal,  setAdoptModal]  = useState<{ open: boolean; rec: PricingRec | null }>({
    open: false, rec: null,
  });
  const [adoptedPrice, setAdoptedPrice] = useState<number | null>(null);

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认门店列表 */ });
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, sumRes] = await Promise.all([
        apiClient.get(`/api/v1/dish-pricing/${storeId}`, {
          params: { period, rec_action: actionFilter, status: statusFilter, limit: 200 },
        }),
        apiClient.get(`/api/v1/dish-pricing/summary/${storeId}`,
          { params: { period } }),
      ]);
      setRecs(recRes.data.recommendations || []);
      setSummary(sumRes.data              || null);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [storeId, period, actionFilter, statusFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await apiClient.post(
        `/api/v1/dish-pricing/generate/${storeId}`, null, { params: { period } }
      );
      message.success(
        `定价建议生成完成：${res.data.dish_count} 道菜，` +
        `提价 ${res.data.increase_count} / 降价 ${res.data.decrease_count} / ` +
        `维持 ${res.data.maintain_count}，` +
        `预期利润 ¥${Number(res.data.total_profit_delta_yuan).toFixed(0)}`
      );
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setGenerating(false); }
  };

  const handleAdopt = async () => {
    if (!adoptModal.rec) return;
    setActioning(true);
    try {
      await apiClient.post(
        `/api/v1/dish-pricing/${adoptModal.rec.id}/adopt`,
        null, { params: adoptedPrice ? { adopted_price: adoptedPrice } : {} }
      );
      message.success('已标记为采纳');
      setAdoptModal({ open: false, rec: null });
      setAdoptedPrice(null);
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setActioning(false); }
  };

  const handleDismiss = async (recId: number) => {
    setActioning(true);
    try {
      await apiClient.post(`/api/v1/dish-pricing/${recId}/dismiss`);
      message.success('已忽略');
      fetchAll();
    } catch (e) { handleApiError(e); }
    finally { setActioning(false); }
  };

  // ── KPI ───────────────────────────────────────────────────────────────────
  const increaseCount   = summary?.by_action.find(a => a.rec_action === 'increase')?.total ?? 0;
  const decreaseCount   = summary?.by_action.find(a => a.rec_action === 'decrease')?.total ?? 0;
  const totalRevDelta   = summary?.total_rev_delta_yuan    ?? 0;
  const totalProfDelta  = summary?.total_profit_delta_yuan ?? 0;
  const adoptionRate    = summary?.adoption_rate ?? 0;

  // ── 采纳率仪表盘 ──────────────────────────────────────────────────────────
  const gaugeOption = () => ({
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      radius: '80%',
      min: 0, max: 100,
      progress: { show: true, width: 14 },
      axisLine: { lineStyle: { width: 14 } },
      axisTick: { show: false },
      splitLine: { length: 10, lineStyle: { width: 2, color: '#999' } },
      axisLabel: { distance: 20, color: '#999', fontSize: 10 },
      anchor: { show: true, showAbove: true, size: 20, itemStyle: { borderColor: '#999', borderWidth: 2 } },
      detail: { valueAnimation: true, formatter: '{value}%', color: '#0AAF9A', fontSize: 22, offsetCenter: [0, '70%'] },
      title: { offsetCenter: [0, '95%'], fontSize: 12, color: '#8c8c8c' },
      data: [{ value: adoptionRate.toFixed(1), name: '建议采纳率' }],
      itemStyle: { color: adoptionRate >= 60 ? '#1A7A52' : adoptionRate >= 30 ? '#C8923A' : '#C53030' },
    }],
  });

  // ── ¥影响柱图 ─────────────────────────────────────────────────────────────
  const impactBarOption = () => {
    if (!summary) return {};
    const actions = summary.by_action.filter(a => a.total > 0 && a.rec_action !== 'maintain');
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['¥营收变化', '¥利润变化'], bottom: 0 },
      grid: { left: 60, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: actions.map(a => ACTION_CONFIG[a.rec_action]?.label || a.rec_action) },
      yAxis: { type: 'value', name: '¥' },
      series: [
        {
          name: '¥营收变化', type: 'bar',
          data: actions.map(a => ({
            value: a.total_rev_delta.toFixed(0),
            itemStyle: { color: ACTION_CONFIG[a.rec_action]?.color || '#aaa' },
          })),
        },
        {
          name: '¥利润变化', type: 'bar',
          data: actions.map(a => a.total_profit_delta.toFixed(0)),
          itemStyle: { color: '#aaa' },
        },
      ],
    };
  };

  // ── 弹性分布饼图 ──────────────────────────────────────────────────────────
  const elasticityPieOption = () => {
    const counts: Record<string, number> = { inelastic: 0, moderate: 0, elastic: 0 };
    recs.forEach(r => { if (counts[r.elasticity_class] !== undefined) counts[r.elasticity_class]++; });
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c}道 ({d}%)' },
      series: [{
        type: 'pie', radius: ['35%', '65%'],
        data: Object.entries(counts)
          .filter(([, v]) => v > 0)
          .map(([k, v]) => ({
            name: ELASTICITY_CONFIG[k]?.label || k,
            value: v,
            itemStyle: { color: ELASTICITY_CONFIG[k]?.color || '#aaa' },
          })),
        label: { formatter: '{b}\n{c}道' },
      }],
    };
  };

  // ── 建议列表列 ────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '菜品', dataIndex: 'dish_name', width: 120,
      render: (n: string, r: PricingRec) => (
        <Space direction="vertical" size={0}>
          <Text strong>{n}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.category}</Text>
        </Space>
      ),
    },
    {
      title: 'BCG', dataIndex: 'bcg_quadrant', width: 85,
      render: (q: string) => {
        const colorMap: Record<string, string> = {
          star: 'gold', cash_cow: 'green', question_mark: 'blue', dog: 'default',
        };
        const labelMap: Record<string, string> = {
          star: '⭐明星', cash_cow: '🐄金牛', question_mark: '❓问号', dog: '🐕犬只',
        };
        return <Tag color={colorMap[q] || 'default'}>{labelMap[q] || q}</Tag>;
      },
    },
    {
      title: '当前价', dataIndex: 'current_price', width: 80,
      render: (v: number) => fmtPrice(v),
    },
    {
      title: '建议', dataIndex: 'rec_action', width: 100,
      render: (a: string, r: PricingRec) => {
        const cfg = ACTION_CONFIG[a] || { label: a, antColor: 'default', icon: null };
        return (
          <Space direction="vertical" size={0}>
            <Tag color={cfg.antColor}>{cfg.icon} {cfg.label}</Tag>
            <Text style={{ fontSize: 12, fontWeight: 600,
              color: a === 'increase' ? '#1A7A52' : a === 'decrease' ? '#0AAF9A' : '#8c8c8c' }}>
              → {fmtPrice(r.suggested_price)}
              {r.price_change_pct !== 0 &&
                <span style={{ fontSize: 11, marginLeft: 4 }}>
                  ({r.price_change_pct > 0 ? '+' : ''}{r.price_change_pct.toFixed(0)}%)
                </span>
              }
            </Text>
          </Space>
        );
      },
    },
    {
      title: '弹性', dataIndex: 'elasticity_class', width: 75,
      render: (e: string) => {
        const cfg = ELASTICITY_CONFIG[e] || { label: e, color: '#aaa' };
        return <Text style={{ color: cfg.color, fontSize: 12 }}>{cfg.label}</Text>;
      },
    },
    {
      title: '¥营收变化', dataIndex: 'expected_revenue_delta_yuan', width: 95,
      sorter: (a: PricingRec, b: PricingRec) =>
        b.expected_revenue_delta_yuan - a.expected_revenue_delta_yuan,
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>
          {v >= 0 ? '+' : ''}{fmt(v)}
        </Text>
      ),
    },
    {
      title: '¥利润变化', dataIndex: 'expected_profit_delta_yuan', width: 95,
      sorter: (a: PricingRec, b: PricingRec) =>
        b.expected_profit_delta_yuan - a.expected_profit_delta_yuan,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>
          {v >= 0 ? '+' : ''}{fmt(v)}
        </Text>
      ),
    },
    {
      title: '置信度', dataIndex: 'confidence_pct', width: 75,
      render: (v: number) => fmtPct(v),
    },
    {
      title: '说明', dataIndex: 'reasoning', ellipsis: true,
    },
    {
      title: '操作', width: 120,
      render: (_: any, r: PricingRec) =>
        r.status === 'pending' ? (
          <Space>
            <Button size="small" type="link" icon={<CheckCircleOutlined />}
              onClick={() => { setAdoptModal({ open: true, rec: r }); setAdoptedPrice(null); }}>
              采纳
            </Button>
            <Popconfirm title="确认忽略此建议？" onConfirm={() => handleDismiss(r.id)}
              okText="确认" cancelText="取消">
              <Button size="small" type="link" danger icon={<StopOutlined />}
                loading={actioning}>
                忽略
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Tag color={r.status === 'adopted' ? 'success' : 'default'} style={{ margin: 0 }}>
            {r.status === 'adopted' ? `已采纳 ${r.adopted_price ? fmtPrice(r.adopted_price) : ''}` : '已忽略'}
          </Tag>
        ),
    },
  ];

  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  const rowClass = (r: PricingRec) => {
    if (r.rec_action === 'increase') return styles.rowIncrease;
    if (r.rec_action === 'decrease') return styles.rowDecrease;
    return '';
  };

  return (
    <div className={styles.page}>
      {/* ── 顶部控制 ─────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <Title level={4} style={{ margin: 0 }}>
          <DollarOutlined /> 菜品智能定价
        </Title>
        <Space>
          <Select value={storeId} onChange={setStoreId} style={{ width: 120 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map(p => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Tooltip title="基于BCG象限+弹性分析生成定价建议（幂等，已采纳的不覆盖）">
            <Button type="primary" icon={<SyncOutlined spin={generating} />}
              onClick={handleGenerate} loading={generating}>
              生成定价建议
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ── KPI 卡片 ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="建议提价" value={increaseCount} suffix="道"
              prefix={<RiseOutlined />} valueStyle={{ color: '#1A7A52' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="建议降价" value={decreaseCount} suffix="道"
              prefix={<FallOutlined />} valueStyle={{ color: '#0AAF9A' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="预期¥利润变化" value={totalProfDelta.toFixed(0)}
              prefix={totalProfDelta >= 0 ? '+¥' : '-¥'}
              valueStyle={{ color: totalProfDelta >= 0 ? '#1A7A52' : '#C53030' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="建议采纳率" value={adoptionRate.toFixed(1)} suffix="%"
              prefix={<TrophyOutlined />}
              valueStyle={{ color: adoptionRate >= 60 ? '#1A7A52' : '#C8923A' }} />
          </Card>
        </Col>
      </Row>

      {/* ── 主内容 ───────────────────────────────────────────────────────── */}
      <Card bodyStyle={{ padding: '0 16px 16px' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'list',
            label: <span><DollarOutlined /> 定价建议</span>,
            children: (
              <Spin spinning={loading}>
                <Space style={{ marginBottom: 12 }}>
                  <Select value={actionFilter} onChange={setActionFilter}
                    style={{ width: 120 }} allowClear placeholder="建议类型">
                    <Option value="increase">↑ 建议提价</Option>
                    <Option value="decrease">↓ 建议降价</Option>
                    <Option value="maintain">— 维持定价</Option>
                  </Select>
                  <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 110 }}>
                    <Option value="pending">待处理</Option>
                    <Option value="adopted">已采纳</Option>
                    <Option value="dismissed">已忽略</Option>
                  </Select>
                </Space>
                {recs.length === 0 ? (
                  <Empty description="暂无定价建议，请先点击「生成定价建议」" />
                ) : (
                  <Table
                    dataSource={recs}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 1100 }}
                    rowClassName={rowClass}
                  />
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
                    <Col xs={24} lg={12}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        各类建议¥影响（营收 vs 利润）
                      </Text>
                      <ReactECharts option={impactBarOption()} style={{ height: 280 }} notMerge />
                    </Col>
                    <Col xs={24} lg={6}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        需求弹性分布
                      </Text>
                      <ReactECharts option={elasticityPieOption()} style={{ height: 200 }} notMerge />
                    </Col>
                    <Col xs={24} lg={6}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        建议采纳率
                      </Text>
                      <div className={styles.gaugeWrap}>
                        <ReactECharts option={gaugeOption()} style={{ height: 200, width: '100%' }} notMerge />
                      </div>
                    </Col>
                  </Row>
                )}
              </Spin>
            ),
          },
          {
            key: 'detail',
            label: <span><LineChartOutlined /> 明细统计</span>,
            children: (
              <Spin spinning={loading}>
                {!summary ? <Empty /> : (
                  <Table
                    dataSource={summary.by_action}
                    rowKey="rec_action"
                    size="small"
                    pagination={false}
                    columns={[
                      {
                        title: '建议类型', dataIndex: 'rec_action',
                        render: (a: string) => {
                          const cfg = ACTION_CONFIG[a] || { label: a, antColor: 'default', icon: null };
                          return <Tag color={cfg.antColor}>{cfg.icon} {cfg.label}</Tag>;
                        },
                      },
                      { title: '总计', dataIndex: 'total', width: 65 },
                      { title: '待处理', dataIndex: 'pending', width: 70 },
                      {
                        title: '已采纳', dataIndex: 'adopted', width: 70,
                        render: (v: number) => <Text style={{ color: '#1A7A52' }}>{v}</Text>,
                      },
                      { title: '已忽略', dataIndex: 'dismissed', width: 70 },
                      {
                        title: '¥营收变化', dataIndex: 'total_rev_delta',
                        render: (v: number) => (
                          <Text style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>
                            {v >= 0 ? '+' : ''}{fmt(v)}
                          </Text>
                        ),
                      },
                      {
                        title: '¥利润变化', dataIndex: 'total_profit_delta',
                        render: (v: number) => (
                          <Text style={{ color: v >= 0 ? '#1A7A52' : '#C53030' }}>
                            {v >= 0 ? '+' : ''}{fmt(v)}
                          </Text>
                        ),
                      },
                      {
                        title: '平均置信度', dataIndex: 'avg_confidence',
                        render: (v: number) => `${Number(v).toFixed(1)}%`,
                      },
                    ]}
                    summary={() => (
                      <Table.Summary.Row>
                        <Table.Summary.Cell index={0}><Text strong>合计</Text></Table.Summary.Cell>
                        <Table.Summary.Cell index={1}>
                          <Text strong>{summary.total_dishes}</Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={2} />
                        <Table.Summary.Cell index={3}>
                          <Text strong style={{ color: '#1A7A52' }}>{summary.total_adopted}</Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={4} />
                        <Table.Summary.Cell index={5}>
                          <Text strong style={{ color: totalRevDelta >= 0 ? '#1A7A52' : '#C53030' }}>
                            {totalRevDelta >= 0 ? '+' : ''}{fmt(totalRevDelta)}
                          </Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={6}>
                          <Text strong style={{ color: totalProfDelta >= 0 ? '#1A7A52' : '#C53030' }}>
                            {totalProfDelta >= 0 ? '+' : ''}{fmt(totalProfDelta)}
                          </Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={7} />
                      </Table.Summary.Row>
                    )}
                  />
                )}
              </Spin>
            ),
          },
        ]} />
      </Card>

      {/* ── 采纳弹窗 ─────────────────────────────────────────────────────── */}
      <Modal
        title={`采纳定价建议：${adoptModal.rec?.dish_name}`}
        open={adoptModal.open}
        onOk={handleAdopt}
        onCancel={() => { setAdoptModal({ open: false, rec: null }); setAdoptedPrice(null); }}
        confirmLoading={actioning}
        okText="确认采纳"
        cancelText="取消"
      >
        {adoptModal.rec && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>
              建议售价：<Text strong style={{ color: '#1A7A52' }}>
                {fmtPrice(adoptModal.rec.suggested_price)}
              </Text>
              <Text type="secondary" style={{ marginLeft: 8 }}>
                （当前 {fmtPrice(adoptModal.rec.current_price)}，
                {adoptModal.rec.price_change_pct > 0 ? '+' : ''}
                {adoptModal.rec.price_change_pct.toFixed(0)}%）
              </Text>
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {adoptModal.rec.reasoning}
            </Text>
            <Space>
              <Text>实际定价（选填）：</Text>
              <InputNumber
                placeholder={`建议价 ${fmtPrice(adoptModal.rec.suggested_price)}`}
                value={adoptedPrice}
                onChange={v => setAdoptedPrice(v)}
                prefix="¥"
                min={0}
                precision={1}
                style={{ width: 150 }}
              />
            </Space>
          </Space>
        )}
      </Modal>
    </div>
  );
};

export default DishPricingPage;
