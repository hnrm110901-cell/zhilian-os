import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Tabs, Table, Tag, Select, Statistic,
  Progress, Empty, Spin, message, Tooltip,
} from 'antd';
import {
  RiseOutlined, FallOutlined, MinusOutlined,
  TrophyOutlined, WarningOutlined, StarOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './PerformanceRankingPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────

interface MetricRanking {
  metric: string;
  label: string;
  value: number | null;
  rank: number;
  total_stores: number;
  percentile: number | null;
  tier: string;
  prev_rank: number | null;
  rank_change: string | null;
}

interface StoreRanking {
  store_id: string;
  period: string;
  metrics: Record<string, MetricRanking>;
}

interface GapRow {
  metric: string;
  label: string;
  benchmark_type: string;
  store_value: number | null;
  benchmark_value: number | null;
  gap_pct: number | null;
  gap_direction: string;
  yuan_potential: number | null;
}

interface LeaderboardEntry {
  store_id: string;
  value: number | null;
  rank: number;
  total_stores: number;
  percentile: number | null;
  tier: string;
  rank_change: string | null;
  label: string;
}

interface TrendItem {
  period: string;
  rank: number;
  total_stores: number;
  percentile: number | null;
  tier: string;
  rank_change: string | null;
}

// ── 常量 ──────────────────────────────────────────────────────────────────

const TIER_COLOR: Record<string, string> = {
  top:       '#1A7A52',
  above_avg: '#0AAF9A',
  below_avg: '#C8923A',
  laggard:   '#C53030',
};

const TIER_LABEL: Record<string, string> = {
  top:       '头部',
  above_avg: '中上',
  below_avg: '中下',
  laggard:   '落后',
};

const CHANGE_ICON: Record<string, React.ReactNode> = {
  improved: <RiseOutlined style={{ color: '#1A7A52' }} />,
  declined: <FallOutlined  style={{ color: '#C53030' }} />,
  stable:   <MinusOutlined style={{ color: '#8c8c8c' }} />,
  new:      <StarOutlined  style={{ color: '#faad14' }} />,
};

const BENCHMARK_LABEL: Record<string, string> = {
  median:       '中位数',
  top_quartile: '头部四分位',
  best:         '最优门店',
};

const METRICS = ['revenue', 'food_cost_rate', 'profit_margin', 'health_score'];
const METRIC_LABEL: Record<string, string> = {
  revenue: '月净收入', food_cost_rate: '食材成本率',
  profit_margin: '利润率', health_score: '财务健康评分',
};
const METRIC_UNIT: Record<string, string> = {
  revenue: '¥', food_cost_rate: '%', profit_margin: '%', health_score: '分',
};

function fmtVal(metric: string, val: number | null): string {
  if (val === null) return '—';
  if (metric === 'revenue') return `¥${val.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`;
  if (metric === 'health_score') return val.toFixed(1) + ' 分';
  return val.toFixed(1) + '%';
}

// ── 主组件 ────────────────────────────────────────────────────────────────

const PerformanceRankingPage: React.FC = () => {
  const [storeId,      setStoreId]      = useState('S001');
  const [storeOptions, setStoreOptions] = useState<string[]>(['S001']);
  const [period, setPeriod] = useState(dayjs().subtract(1, 'month').format('YYYY-MM'));
  const [selectedMetric, setSelectedMetric] = useState('health_score');

  useEffect(() => {
    apiClient.get<{ items: Array<{ id: string }> }>('/api/v1/stores?limit=50')
      .then(data => {
        const ids = (data.items ?? []).map((s: { id: string }) => s.id).filter(Boolean);
        if (ids.length > 0) setStoreOptions(ids);
      })
      .catch(() => { /* 保持默认 */ });
  }, []);

  const [storeRanking, setStoreRanking] = useState<StoreRanking | null>(null);
  const [gaps, setGaps] = useState<GapRow[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [computing, setComputing] = useState(false);

  const periodOptions = Array.from({ length: 12 }, (_, i) =>
    dayjs().subtract(i + 1, 'month').format('YYYY-MM')
  );

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [rankResp, gapsResp, boardResp, trendResp] = await Promise.allSettled([
        apiClient.get(`/api/v1/fin-ranking/store/${storeId}?period=${period}`),
        apiClient.get(`/api/v1/fin-ranking/store/${storeId}/gaps?period=${period}`),
        apiClient.get(`/api/v1/fin-ranking/leaderboard?period=${period}&metric=${selectedMetric}&limit=20`),
        apiClient.get(`/api/v1/fin-ranking/store/${storeId}/trend?metric=${selectedMetric}&periods=6`),
      ]);
      if (rankResp.status === 'fulfilled') setStoreRanking(rankResp.value.data);
      if (gapsResp.status === 'fulfilled') setGaps(gapsResp.value.data.gaps ?? []);
      if (boardResp.status === 'fulfilled') setLeaderboard(boardResp.value.data.board ?? []);
      if (trendResp.status === 'fulfilled') setTrend(trendResp.value.data.trend ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCompute = async () => {
    setComputing(true);
    try {
      const resp = await apiClient.post(`/api/v1/fin-ranking/compute?period=${period}`);
      message.success(`排名计算完成：${resp.data.ranking_rows} 条排名 / ${resp.data.gap_rows} 条对标差距`);
      await fetchAll();
    } catch (err) {
      handleApiError(err);
    } finally {
      setComputing(false);
    }
  };

  useEffect(() => { fetchAll(); }, [period, selectedMetric]);

  // ── 趋势折线图 ──────────────────────────────────────────────────────────

  const trendOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: trend.map((t) => t.period) },
    yAxis: {
      type: 'value',
      name: '排名（1=最优）',
      inverse: true,        // 排名1在顶部
      minInterval: 1,
    },
    series: [
      {
        name: '排名',
        type: 'line',
        data: trend.map((t) => t.rank),
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#0AAF9A' },
        lineStyle: { width: 2 },
      },
    ],
  };

  // ── 差距雷达图 ──────────────────────────────────────────────────────────

  const medianGaps = gaps.filter((g) => g.benchmark_type === 'median');
  const radarOption = medianGaps.length > 0
    ? {
        tooltip: {},
        radar: {
          indicator: medianGaps.map((g) => ({ name: g.label, max: 100 })),
          shape: 'polygon',
        },
        series: [
          {
            type: 'radar',
            data: [
              {
                name: '百分位',
                value: METRICS.map((m) => {
                  const entry = storeRanking?.metrics[m];
                  return entry?.percentile ?? 0;
                }),
                itemStyle: { color: '#0AAF9A' },
                areaStyle: { opacity: 0.3 },
              },
            ],
          },
        ],
      }
    : null;

  // ── KPI 卡 ───────────────────────────────────────────────────────────────

  const overallPercentile = storeRanking
    ? Object.values(storeRanking.metrics).reduce((s, m) => s + (m.percentile ?? 0), 0) /
      Math.max(1, Object.values(storeRanking.metrics).length)
    : null;

  const overallTier = overallPercentile !== null ? (
    overallPercentile >= 75 ? 'top' :
    overallPercentile >= 50 ? 'above_avg' :
    overallPercentile >= 25 ? 'below_avg' : 'laggard'
  ) : null;

  // ── 对标差距表 ──────────────────────────────────────────────────────────

  const gapColumns = [
    {
      title: '指标', dataIndex: 'label', width: 100,
      render: (v: string) => <strong>{v}</strong>,
    },
    {
      title: '基准类型', dataIndex: 'benchmark_type', width: 100,
      render: (v: string) => BENCHMARK_LABEL[v] ?? v,
    },
    {
      title: '本店', key: 'sv', width: 110,
      render: (_: unknown, r: GapRow) => fmtVal(r.metric, r.store_value),
    },
    {
      title: '基准值', key: 'bv', width: 110,
      render: (_: unknown, r: GapRow) => fmtVal(r.metric, r.benchmark_value),
    },
    {
      title: '差距', dataIndex: 'gap_pct', width: 90,
      render: (v: number | null, r: GapRow) => {
        if (v === null) return '—';
        const isGood = r.gap_direction === 'above';
        return (
          <span style={{ color: isGood ? '#1A7A52' : '#C53030' }}>
            {v > 0 ? '+' : ''}{v.toFixed(1)}%
          </span>
        );
      },
    },
    {
      title: '方向', dataIndex: 'gap_direction', width: 80,
      render: (v: string) => (
        <Tag color={v === 'above' ? 'green' : v === 'below' ? 'red' : 'default'}>
          {v === 'above' ? '优于' : v === 'below' ? '低于' : '持平'}
        </Tag>
      ),
    },
    {
      title: '¥提升潜力', dataIndex: 'yuan_potential', width: 120,
      render: (v: number | null) =>
        v === null ? '—' : (
          <span style={{ color: '#0AAF9A', fontWeight: 600 }}>
            ¥{Math.abs(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
          </span>
        ),
    },
  ];

  // ── 排行榜列 ───────────────────────────────────────────────────────────

  const boardColumns = [
    {
      title: '排名', dataIndex: 'rank', width: 60,
      render: (v: number) => (
        <span style={{ fontWeight: 700, color: v === 1 ? '#faad14' : v <= 3 ? '#0AAF9A' : undefined }}>
          {v === 1 ? <TrophyOutlined /> : null} {v}
        </span>
      ),
    },
    { title: '门店', dataIndex: 'store_id', width: 100 },
    {
      title: '数值', key: 'value', width: 120,
      render: (_: unknown, r: LeaderboardEntry) => fmtVal(selectedMetric, r.value),
    },
    {
      title: '百分位', dataIndex: 'percentile', width: 80,
      render: (v: number | null) => v !== null ? `${v.toFixed(0)}%` : '—',
    },
    {
      title: '层级', dataIndex: 'tier', width: 80,
      render: (v: string) => <Tag color={TIER_COLOR[v]}>{TIER_LABEL[v]}</Tag>,
    },
    {
      title: '环比', dataIndex: 'rank_change', width: 60,
      render: (v: string | null) => v ? <Tooltip title={v}>{CHANGE_ICON[v]}</Tooltip> : null,
    },
    {
      title: '分位进度', key: 'progress', width: 160,
      render: (_: unknown, r: LeaderboardEntry) => (
        <Progress
          percent={r.percentile ?? 0}
          size="small"
          strokeColor={TIER_COLOR[r.tier] ?? '#0AAF9A'}
          showInfo={false}
        />
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>多店财务对标排名</h2>
        <div className={styles.controls}>
          <Select value={storeId} onChange={setStoreId} style={{ width: 110 }}>
            {storeOptions.map(s => <Option key={s} value={s}>{s}</Option>)}
          </Select>
          <Select value={period} onChange={setPeriod} style={{ width: 120 }}>
            {periodOptions.map((p) => <Option key={p} value={p}>{p}</Option>)}
          </Select>
          <Select value={selectedMetric} onChange={setSelectedMetric} style={{ width: 140 }}>
            {METRICS.map((m) => <Option key={m} value={m}>{METRIC_LABEL[m]}</Option>)}
          </Select>
          <button
            className={styles.computeBtn}
            onClick={handleCompute}
            disabled={computing}
          >
            {computing ? '计算中…' : '触发排名计算'}
          </button>
        </div>
      </div>

      {/* KPI 卡 */}
      <Row gutter={[16, 16]} className={styles.kpiRow}>
        {METRICS.map((m) => {
          const entry = storeRanking?.metrics[m];
          return (
            <Col xs={12} sm={6} key={m}>
              <Card
                className={styles.kpiCard}
                style={{ borderTop: `3px solid ${entry ? TIER_COLOR[entry.tier] : '#d9d9d9'}` }}
              >
                <div className={styles.kpiLabel}>{METRIC_LABEL[m]}</div>
                {entry ? (
                  <>
                    <div className={styles.kpiRank}>
                      # {entry.rank}
                      <span className={styles.kpiTotal}>/{entry.total_stores}</span>
                    </div>
                    <div className={styles.kpiMeta}>
                      <Tag color={TIER_COLOR[entry.tier]}>{TIER_LABEL[entry.tier]}</Tag>
                      <span className={styles.kpiPct}>{entry.percentile?.toFixed(0)}th</span>
                      {entry.rank_change && CHANGE_ICON[entry.rank_change]}
                    </div>
                    <Progress
                      percent={entry.percentile ?? 0}
                      size="small"
                      strokeColor={TIER_COLOR[entry.tier]}
                      showInfo={false}
                      style={{ marginTop: 4 }}
                    />
                  </>
                ) : (
                  <div className={styles.kpiEmpty}>暂无数据</div>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* 综合层级 */}
      {overallTier && (
        <Card className={styles.overallCard} size="small">
          <Row gutter={16} align="middle">
            <Col>
              <Statistic
                title="综合层级"
                value={TIER_LABEL[overallTier]}
                valueStyle={{ color: TIER_COLOR[overallTier], fontSize: 24, fontWeight: 700 }}
              />
            </Col>
            <Col>
              <Statistic
                title="综合百分位"
                value={overallPercentile?.toFixed(1) ?? '—'}
                suffix="th"
              />
            </Col>
          </Row>
        </Card>
      )}

      <Spin spinning={loading}>
        <Tabs
          defaultActiveKey="leaderboard"
          items={[
            {
              key: 'leaderboard',
              label: '排行榜',
              children: (
                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={15}>
                    <Card title={`${METRIC_LABEL[selectedMetric]} 排行榜（${period}）`} size="small">
                      {leaderboard.length === 0 ? (
                        <Empty description="暂无数据，请先触发排名计算" />
                      ) : (
                        <Table
                          dataSource={leaderboard}
                          columns={boardColumns}
                          rowKey="store_id"
                          size="small"
                          pagination={false}
                          rowClassName={(r) => r.store_id === storeId ? styles.highlightRow : ''}
                        />
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} lg={9}>
                    <Card title="本店能力雷达（vs 中位数）" size="small">
                      {radarOption ? (
                        <ReactECharts option={radarOption} style={{ height: 280 }} />
                      ) : (
                        <Empty description="暂无数据" />
                      )}
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'trend',
              label: '排名趋势',
              children: (
                <Card title={`${METRIC_LABEL[selectedMetric]} — 近6期排名变化`} size="small">
                  {trend.length === 0 ? (
                    <Empty description="暂无趋势数据" />
                  ) : (
                    <ReactECharts option={trendOption} style={{ height: 300 }} />
                  )}
                </Card>
              ),
            },
            {
              key: 'gaps',
              label: '对标差距',
              children: (
                <Card title="对标差距分析（vs 中位数 / 头部四分位 / 最优）" size="small">
                  {gaps.length === 0 ? (
                    <Empty description="暂无对标数据，请先触发排名计算" />
                  ) : (
                    <Table
                      dataSource={gaps}
                      columns={gapColumns}
                      rowKey={(r) => `${r.metric}-${r.benchmark_type}`}
                      size="small"
                      pagination={false}
                      rowClassName={(r) =>
                        r.gap_direction === 'below' && (r.yuan_potential ?? 0) > 5000
                          ? styles.highlightGap : ''
                      }
                    />
                  )}
                </Card>
              ),
            },
          ]}
        />
      </Spin>
    </div>
  );
};

export default PerformanceRankingPage;
