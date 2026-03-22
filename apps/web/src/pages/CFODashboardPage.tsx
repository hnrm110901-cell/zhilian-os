import React, { useState, useEffect, useCallback } from 'react';
import { Card, Select, Button, Tag, Progress, Empty, Spin, Alert, Tooltip } from 'antd';
import {
  ReloadOutlined,
  BankOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  DollarOutlined,
  RiseOutlined,
  FallOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient, handleApiError } from '../services/api';
import styles from './CFODashboardPage.module.css';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface StoreScore {
  store_id: string;
  total_score: number;
  grade: string;
  profit_score: number;
  cash_score: number;
  tax_score: number;
  settlement_score: number;
  budget_score: number;
}

interface HealthOverview {
  store_scores: StoreScore[];
  avg_score: number;
  grade_distribution: { A: number; B: number; C: number; D: number };
  best_store: { store_id: string; total_score: number; grade: string } | null;
  worst_store: { store_id: string; total_score: number; grade: string } | null;
  store_count: number;
}

interface AlertEvent {
  event_id: number;
  store_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'open' | 'acknowledged';
  metric: string;
  message: string;
}

interface AlertSummary {
  open_count: number;
  critical_count: number;
  acknowledged_count: number;
  total_count: number;
  by_store: { store_id: string; events: AlertEvent[] }[];
  all_events: AlertEvent[];
}

interface StoreBudget {
  store_id: string;
  budget_revenue: number;
  actual_revenue: number;
  achievement_pct: number | null;
}

interface BudgetSummary {
  store_count_with_budget: number;
  avg_achievement_pct: number | null;
  over_budget_count: number;
  under_budget_count: number;
  store_budgets: StoreBudget[];
}

interface ActionItem {
  source: 'insight' | 'alert';
  store_id: string;
  type: string;
  priority: 'high' | 'medium' | 'low';
  content: string;
  action_id: string;
}

interface CfoDashboard {
  brand_id: string;
  period: string;
  brand_grade: string;
  narrative: string;
  health_overview: HealthOverview | null;
  alert_summary: AlertSummary | null;
  budget_summary: BudgetSummary | null;
  actions: ActionItem[];
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const GRADE_COLORS: Record<string, string> = {
  A: '#1A7A52', B: '#FF6B2C', C: '#C8923A', D: '#C53030',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#C53030', high: '#fa541c', medium: '#C8923A', low: '#1A7A52',
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重', high: '高', medium: '中', low: '低',
};

const INSIGHT_TYPE_LABELS: Record<string, string> = {
  profit:     '利润率',
  cash:       '现金流',
  tax:        '税务',
  settlement: '结算',
  budget:     '预算',
};

// ── 工具 ──────────────────────────────────────────────────────────────────────

const gradeColor = (g: string) => GRADE_COLORS[g] ?? '#8c8c8c';

const fmt = (n: number | null | undefined, suffix = '') =>
  n == null ? '—' : `${n.toFixed(1)}${suffix}`;

// ── 组件 ──────────────────────────────────────────────────────────────────────

const CFODashboardPage: React.FC = () => {
  const [brandId, setBrandId]   = useState<string>('BRAND001');
  const [period, setPeriod]     = useState<string>(dayjs().format('YYYY-MM'));
  const [tab, setTab]           = useState<'overview' | 'alerts' | 'actions'>('overview');
  const [data, setData]         = useState<CfoDashboard | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [saving, setSaving]     = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get('/api/v1/cfo/dashboard', {
        params: { brand_id: brandId, period },
      });
      setData(resp.data);
    } catch (e) {
      setError(handleApiError(e));
    } finally {
      setLoading(false);
    }
  }, [brandId, period]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiClient.post('/api/v1/cfo/report/save', null, {
        params: { brand_id: brandId, period },
      });
    } finally {
      setSaving(false);
    }
  };

  const ho = data?.health_overview;
  const as_ = data?.alert_summary;
  const bs = data?.budget_summary;

  // ── KPI 卡片数据 ──────────────────────────────────────────────────────────

  const kpis = [
    {
      label:    '品牌综合等级',
      value:    data?.brand_grade ?? '—',
      sub:      ho ? `均分 ${fmt(ho.avg_score)} 分` : '—',
      color:    gradeColor(data?.brand_grade ?? ''),
      icon:     <BankOutlined />,
    },
    {
      label:    '门店数量',
      value:    ho ? `${ho.store_count}` : '—',
      sub:      ho
        ? `优秀 ${ho.grade_distribution.A} / 良好 ${ho.grade_distribution.B}`
        : '—',
      color:    '#FF6B2C',
      icon:     <CheckCircleOutlined />,
    },
    {
      label:    '开放告警',
      value:    as_ != null ? `${as_.open_count}` : '—',
      sub:      as_ ? `严重 ${as_.critical_count} 条` : '—',
      color:    as_ && as_.critical_count > 0 ? '#C53030' : '#C8923A',
      icon:     <WarningOutlined />,
    },
    {
      label:    '预算达成率',
      value:    bs?.avg_achievement_pct != null ? `${fmt(bs.avg_achievement_pct)}%` : '—',
      sub:      bs ? `${bs.store_count_with_budget} 家已设预算` : '—',
      color:    bs?.avg_achievement_pct != null
        ? (bs.avg_achievement_pct >= 100 ? '#1A7A52' : bs.avg_achievement_pct >= 80 ? '#C8923A' : '#C53030')
        : '#8c8c8c',
      icon:     <DollarOutlined />,
    },
    {
      label:    '最优门店',
      value:    ho?.best_store?.store_id ?? '—',
      sub:      ho?.best_store ? `${fmt(ho.best_store.total_score)} 分 (${ho.best_store.grade})` : '—',
      color:    '#1A7A52',
      icon:     <RiseOutlined />,
    },
    {
      label:    '最弱门店',
      value:    ho?.worst_store?.store_id ?? '—',
      sub:      ho?.worst_store ? `${fmt(ho.worst_store.total_score)} 分 (${ho.worst_store.grade})` : '—',
      color:    gradeColor(ho?.worst_store?.grade ?? ''),
      icon:     <FallOutlined />,
    },
  ];

  // ── ECharts: 门店健康评分横向柱图 ─────────────────────────────────────────

  const storeBarOption = () => {
    if (!ho || !ho.store_scores.length) return {};
    const sorted = [...ho.store_scores].sort((a, b) => b.total_score - a.total_score);
    return {
      tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}: ${p[0].value.toFixed(1)}分` },
      grid: { left: 80, right: 20, top: 10, bottom: 30 },
      xAxis: { type: 'value', max: 100, axisLabel: { fontSize: 11 } },
      yAxis: {
        type: 'category',
        data: sorted.map(s => s.store_id),
        axisLabel: { fontSize: 11 },
      },
      series: [{
        type: 'bar',
        data: sorted.map(s => ({
          value: s.total_score,
          itemStyle: { color: gradeColor(s.grade) },
        })),
        label: { show: true, position: 'right', formatter: (p: any) => `${p.value.toFixed(1)}`, fontSize: 11 },
      }],
    };
  };

  // ── ECharts: 等级分布饼图 ────────────────────────────────────────────────

  const gradePieOption = () => {
    if (!ho) return {};
    const dist = ho.grade_distribution;
    const pieData = (['A', 'B', 'C', 'D'] as const)
      .filter(g => dist[g] > 0)
      .map(g => ({ value: dist[g], name: `${g}级 (${dist[g]})`, itemStyle: { color: GRADE_COLORS[g] } }));
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, fontSize: 11 },
      series: [{
        type: 'pie', radius: ['45%', '70%'],
        data: pieData,
        label: { formatter: '{b}: {d}%', fontSize: 11 },
      }],
    };
  };

  // ── ECharts: 5维雷达（最差门店 vs 品牌均值）──────────────────────────────

  const radarOption = () => {
    if (!ho || !ho.store_scores.length) return {};
    const dims = ['profit', 'cash', 'tax', 'settlement', 'budget'];
    const labels = ['利润(30)', '现金(20)', '税务(20)', '结算(15)', '预算(15)'];
    const maxes  = [30, 20, 20, 15, 15];
    const scores = ho.store_scores;
    const avg = (key: keyof StoreScore) =>
      scores.reduce((s, r) => s + (r[key] as number), 0) / scores.length;

    const worst = ho.worst_store
      ? scores.find(s => s.store_id === ho.worst_store?.store_id) ?? scores[scores.length - 1]
      : scores[scores.length - 1];

    return {
      tooltip: {},
      legend: { data: ['品牌均值', worst.store_id], bottom: 0, fontSize: 11 },
      radar: {
        indicator: dims.map((_, i) => ({ name: labels[i], max: maxes[i] })),
        radius: '65%',
      },
      series: [{
        type: 'radar',
        data: [
          {
            name: '品牌均值',
            value: dims.map(d => avg(`${d}_score` as keyof StoreScore)),
            areaStyle: { opacity: 0.2 },
            lineStyle: { color: '#FF6B2C' },
            itemStyle: { color: '#FF6B2C' },
          },
          {
            name: worst.store_id,
            value: dims.map(d => worst[`${d}_score` as keyof StoreScore] as number),
            areaStyle: { opacity: 0.2 },
            lineStyle: { color: '#C53030' },
            itemStyle: { color: '#C53030' },
          },
        ],
      }],
    };
  };

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.pageTitle}>CFO 工作台</h2>
          <p className={styles.pageSub}>品牌财务健康综合驾驶舱 — 聚合健康评分 / 预警 / 预算 / 行动清单</p>
        </div>
        <div className={styles.headerActions}>
          <Select
            value={brandId}
            onChange={setBrandId}
            style={{ width: 140 }}
            options={[
              { value: 'BRAND001', label: '品牌001' },
              { value: 'BRAND002', label: '品牌002' },
            ]}
          />
          <Select
            value={period}
            onChange={setPeriod}
            style={{ width: 120 }}
            options={Array.from({ length: 6 }, (_, i) => {
              const m = dayjs().subtract(i, 'month').format('YYYY-MM');
              return { value: m, label: m };
            })}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          <Button icon={<SaveOutlined />}   onClick={handleSave} loading={saving}>保存快照</Button>
        </div>
      </div>

      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}

      <Spin spinning={loading}>
        {/* KPI 卡片行 */}
        <div className={styles.kpiGrid}>
          {kpis.map((k, i) => (
            <Card key={i} size="small" className={styles.kpiCard}>
              <div className={styles.kpiIcon} style={{ color: k.color }}>{k.icon}</div>
              <div className={styles.kpiLabel}>{k.label}</div>
              <div className={styles.kpiValue} style={{ color: k.color }}>{k.value}</div>
              <div className={styles.kpiSub}>{k.sub}</div>
            </Card>
          ))}
        </div>

        {/* 叙事简报 */}
        {data?.narrative && (
          <Card size="small" className={styles.narrativeCard}>
            <span className={styles.narrativeIcon}>📊</span>
            <span className={styles.narrativeText}>{data.narrative}</span>
          </Card>
        )}

        {/* Tabs */}
        <div className={styles.tabBar}>
          {(['overview', 'alerts', 'actions'] as const).map(t => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`}
              onClick={() => setTab(t)}
            >
              {{ overview: '门店健康总览', alerts: `预警中心${as_ ? ` (${as_.open_count})` : ''}`, actions: `行动清单${data ? ` (${data.actions.length})` : ''}` }[t]}
            </button>
          ))}
        </div>

        {/* 总览 Tab */}
        {tab === 'overview' && (
          <div>
            {!ho || ho.store_count === 0 ? (
              <Empty description="暂无健康评分数据，请先对各门店执行 /finance-health 计算" />
            ) : (
              <div className={styles.overviewLayout}>
                {/* 左：柱图 */}
                <Card size="small" title="门店评分排名">
                  <ReactECharts
                    option={storeBarOption()}
                    style={{ height: Math.max(200, ho.store_scores.length * 36) }}
                  />
                </Card>

                {/* 右：饼图 + 雷达图 */}
                <div className={styles.overviewRight}>
                  <Card size="small" title="等级分布">
                    <ReactECharts option={gradePieOption()} style={{ height: 200 }} />
                  </Card>
                  <Card size="small" title="品牌均值 vs 最弱门店（5维）">
                    <ReactECharts option={radarOption()} style={{ height: 200 }} />
                  </Card>
                </div>
              </div>
            )}

            {/* 评分明细表 */}
            {ho && ho.store_scores.length > 0 && (
              <Card size="small" title="评分明细" style={{ marginTop: 12 }}>
                <table className={styles.scoreTable}>
                  <thead>
                    <tr>
                      <th>门店</th>
                      <th>综合</th>
                      <th>等级</th>
                      <th>利润 /30</th>
                      <th>现金 /20</th>
                      <th>税务 /20</th>
                      <th>结算 /15</th>
                      <th>预算 /15</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ho.store_scores.map(s => (
                      <tr key={s.store_id}>
                        <td>{s.store_id}</td>
                        <td>
                          <Progress
                            percent={Math.round(s.total_score)}
                            size="small"
                            strokeColor={gradeColor(s.grade)}
                            format={p => `${s.total_score.toFixed(1)}`}
                          />
                        </td>
                        <td><Tag color={gradeColor(s.grade)}>{s.grade}</Tag></td>
                        <td className={styles.scoreCell}>{fmt(s.profit_score)}</td>
                        <td className={styles.scoreCell}>{fmt(s.cash_score)}</td>
                        <td className={styles.scoreCell}>{fmt(s.tax_score)}</td>
                        <td className={styles.scoreCell}>{fmt(s.settlement_score)}</td>
                        <td className={styles.scoreCell}>{fmt(s.budget_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        )}

        {/* 预警 Tab */}
        {tab === 'alerts' && (
          <div>
            {!as_ || as_.total_count === 0 ? (
              <Empty description="当前无开放告警，财务状态良好" />
            ) : (
              <div className={styles.alertList}>
                {as_.all_events.map(evt => (
                  <div
                    key={evt.event_id}
                    className={`${styles.alertCard} ${evt.severity === 'critical' ? styles.alertCritical : evt.severity === 'high' ? styles.alertHigh : ''}`}
                  >
                    <div className={styles.alertHeader}>
                      <Tag color={SEVERITY_COLORS[evt.severity]}>{SEVERITY_LABELS[evt.severity]}</Tag>
                      <span className={styles.alertStore}>{evt.store_id}</span>
                      <Tag>{evt.metric}</Tag>
                      <Tag color={evt.status === 'open' ? 'red' : 'orange'}>
                        {evt.status === 'open' ? '开放' : '已确认'}
                      </Tag>
                    </div>
                    <p className={styles.alertMsg}>{evt.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 行动清单 Tab */}
        {tab === 'actions' && (
          <div>
            {data?.actions.length === 0 ? (
              <Empty description="暂无行动项" />
            ) : (
              <div className={styles.actionList}>
                {data?.actions.map((a, i) => (
                  <div
                    key={a.action_id}
                    className={`${styles.actionCard} ${a.priority === 'high' ? styles.actionHigh : a.priority === 'medium' ? styles.actionMedium : ''}`}
                  >
                    <div className={styles.actionHeader}>
                      <span className={styles.actionRank}>#{i + 1}</span>
                      <Tag color={a.priority === 'high' ? 'red' : a.priority === 'medium' ? 'orange' : 'default'}>
                        {a.priority === 'high' ? '紧急' : a.priority === 'medium' ? '关注' : '一般'}
                      </Tag>
                      <Tag>{a.store_id}</Tag>
                      <Tag color="blue">
                        {a.source === 'insight'
                          ? (INSIGHT_TYPE_LABELS[a.type] ?? a.type)
                          : `预警·${a.type}`}
                      </Tag>
                    </div>
                    <p className={styles.actionContent}>{a.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Spin>
    </div>
  );
};

export default CFODashboardPage;
