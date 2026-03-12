/**
 * 智能体中心总览 — /agent-hub
 *
 * 三栏结构：
 *   顶部  KPI 条（决策总量 / 采纳率 / 覆盖率 / 平均置信度 / 待处理）
 *   中部  8 个 Agent 卡片网格（每张：状态/指标/采纳率/进入工作台）
 *   底部  活动流（最近决策日志） + 周采纳趋势折线图
 *
 * 数据来源：GET /api/v1/governance/dashboard?days=7
 */
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ReloadOutlined, RobotOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ThunderboltOutlined, RiseOutlined,
  BarChartOutlined, SafetyOutlined, SyncOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZSelect, ZEmpty } from '../design-system/components';
import styles from './AgentHubPage.module.css';

// ── Agent metadata ─────────────────────────────────────────────────────────────

interface AgentMeta {
  label:       string;
  icon:        string;
  description: string;
  route:       string;
  color:       string;       // card accent / icon bg tint
  accentHex:   string;
  capabilities: string[];
}

const AGENT_META: Record<string, AgentMeta> = {
  decision: {
    label:       '经营决策',
    icon:        '🧠',
    description: '综合分析成本、损耗、排班数据，每日生成 Top3 决策建议并跟踪执行效果',
    route:       '/decision',
    color:       'rgba(200,146,58,0.08)',
    accentHex:   '#C8923A',
    capabilities: ['成本分析', '损耗归因', '决策排序'],
  },
  schedule: {
    label:       '排班优化',
    icon:        '📅',
    description: '预测客流趋势，自动推荐最优排班方案，降低人力成本',
    route:       '/schedule',
    color:       '#e6f7ff',
    accentHex:   '#0AAF9A',
    capabilities: ['客流预测', '班次推荐', '人力优化'],
  },
  inventory: {
    label:       '库存备货',
    icon:        '📦',
    description: '实时监控库存水位，预测缺货风险，自动生成采购补单建议',
    route:       '/inventory',
    color:       'rgba(26,122,82,0.08)',
    accentHex:   '#1A7A52',
    capabilities: ['库存预警', '备货建议', '采购优化'],
  },
  service: {
    label:       '服务质检',
    icon:        '⭐',
    description: '分析顾客评价与服务数据，识别服务风险点，推动质量持续改善',
    route:       '/service',
    color:       '#fff0f6',
    accentHex:   '#eb2f96',
    capabilities: ['评价分析', '风险识别', '改善建议'],
  },
  private_domain: {
    label:       '私域增长',
    icon:        '📱',
    description: '识别沉默会员与流失风险，生成个性化触达方案，提升复购率',
    route:       '/private-domain',
    color:       '#e6fffb',
    accentHex:   '#13c2c2',
    capabilities: ['人群分层', '触达策略', '文案生成'],
  },
  training: {
    label:       '培训管理',
    icon:        '🎓',
    description: '分析员工绩效与技能短板，自动生成个性化培训计划并追踪成长进度',
    route:       '/training',
    color:       '#f9f0ff',
    accentHex:   '#722ed1',
    capabilities: ['绩效分析', '培训推荐', '进度追踪'],
  },
  reservation: {
    label:       '预订管理',
    icon:        '🗓',
    description: '智能桌位分配，预测爽约率，优化预订接待策略提升翻台效率',
    route:       '/reservation',
    color:       '#e6f4ff',
    accentHex:   '#2f54eb',
    capabilities: ['智能排位', '爽约预测', '时段优化'],
  },
  order: {
    label:       '订单分析',
    icon:        '🛒',
    description: '分析订单模式与菜品组合规律，识别销售机会与菜品优化方向',
    route:       '/order',
    color:       '#fff2e8',
    accentHex:   '#d4380d',
    capabilities: ['订单趋势', '菜品推荐', '搭配分析'],
  },
};

// Canonical display order
const AGENT_ORDER = [
  'decision', 'schedule', 'inventory', 'service',
  'private_domain', 'training', 'reservation', 'order',
];

// ── Types ──────────────────────────────────────────────────────────────────────

interface AgentStat {
  agent_type:    string;
  total:         number;
  approved:      number;
  rejected:      number;
  modified:      number;
  pending:       number;
  adoption_rate: number;
}

interface RecentLog {
  id:                  string;
  created_at:          string;
  agent_type:          string | null;
  ai_suggestion:       string;
  decision_status:     string | null;
  ai_confidence:       number;
  cost_impact_yuan:    number;
  revenue_impact_yuan: number;
}

interface GovData {
  summary: {
    total_decisions: number;
    decided_count:   number;
    adoption_rate:   number;
    override_rate:   number;
    avg_confidence:  number;
    avg_trust_score: number;
    pending_count:   number;
  };
  agent_stats:  AgentStat[];
  recent_logs:  RecentLog[];
  weekly_trend: Array<{
    week_start:    string;
    week_end:      string;
    total:         number;
    decided:       number;
    adoption_rate: number;
  }>;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function statusForAgent(stat: AgentStat | undefined): {
  label: string; color: string; badgeType: 'success' | 'warning' | 'default';
} {
  if (!stat || stat.total === 0) {
    return { label: '待机', color: '#8c8c8c', badgeType: 'default' };
  }
  if (stat.adoption_rate < 30) {
    return { label: '需关注', color: '#C8923A', badgeType: 'warning' };
  }
  return { label: '运行中', color: '#1A7A52', badgeType: 'success' };
}

function adoptionColor(rate: number): string {
  if (rate >= 70) return '#1A7A52';
  if (rate >= 40) return '#faad14';
  return '#C53030';
}

function statusColor(status: string | null): string {
  switch (status) {
    case 'approved':  case 'executed':  return '#1A7A52';
    case 'rejected':                    return '#C53030';
    case 'modified':                    return '#C8923A';
    case 'pending':                     return '#0AAF9A';
    default:                            return '#8c8c8c';
  }
}

function statusBadgeType(status: string | null): 'success' | 'critical' | 'warning' | 'info' | 'default' {
  switch (status) {
    case 'approved': case 'executed': return 'success';
    case 'rejected':                  return 'critical';
    case 'modified':                  return 'warning';
    case 'pending':                   return 'info';
    default:                          return 'default';
  }
}

function statusLabel(status: string | null): string {
  const map: Record<string, string> = {
    approved: '已采纳', executed: '已执行', rejected: '已否决',
    modified: '已修改', pending: '待处理', cancelled: '已取消',
  };
  return map[status ?? ''] ?? (status ?? '—');
}

// ── Component ──────────────────────────────────────────────────────────────────

const AgentHubPage: React.FC = () => {
  const navigate = useNavigate();

  const [stores,        setStores]        = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState('');
  const [days,          setDays]          = useState(7);

  const [loading,  setLoading]  = useState(true);
  const [govData,  setGovData]  = useState<GovData | null>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* silent */ }
  }, []);

  const loadGov = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { days };
      if (selectedStore) params.store_id = selectedStore;
      const res = await apiClient.get('/api/v1/governance/dashboard', { params });
      setGovData(res.data);
    } catch {
      setGovData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedStore, days]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadGov(); }, [loadGov]);

  // ── Derived ───────────────────────────────────────────────────────────────────

  const statsByType = Object.fromEntries(
    (govData?.agent_stats ?? []).map(s => [s.agent_type, s])
  );

  const summary = govData?.summary;

  // ── KPI strip items ───────────────────────────────────────────────────────────

  const statsItems = [
    {
      label: '决策总量',
      value: summary?.total_decisions ?? '—',
      unit: '次',
      iconBg: '#e6f7ff',
      iconColor: '#0AAF9A',
      icon: <ThunderboltOutlined />,
    },
    {
      label: '决策采纳率',
      value: summary?.adoption_rate != null ? `${summary.adoption_rate.toFixed(1)}` : '—',
      unit: '%',
      iconBg: 'rgba(26,122,82,0.08)',
      iconColor: '#1A7A52',
      icon: <CheckCircleOutlined />,
    },
    {
      label: '人工覆盖率',
      value: summary?.override_rate != null ? `${summary.override_rate.toFixed(1)}` : '—',
      unit: '%',
      iconBg: 'rgba(200,146,58,0.08)',
      iconColor: '#C8923A',
      icon: <SyncOutlined />,
    },
    {
      label: '平均置信度',
      value: summary?.avg_confidence != null ? `${summary.avg_confidence.toFixed(1)}` : '—',
      unit: '%',
      iconBg: '#f9f0ff',
      iconColor: '#722ed1',
      icon: <BarChartOutlined />,
    },
    {
      label: '待处理决策',
      value: summary?.pending_count ?? '—',
      unit: '项',
      iconBg: summary?.pending_count ? 'rgba(197,48,48,0.08)' : 'rgba(26,122,82,0.08)',
      iconColor: summary?.pending_count ? '#C53030' : '#1A7A52',
      icon: <ClockCircleOutlined />,
    },
  ];

  // ── Trend chart ───────────────────────────────────────────────────────────────

  const trend = govData?.weekly_trend ?? [];
  const trendChartOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const p = params[0];
        return `${p.name}<br/>采纳率 <b>${p.value}%</b>`;
      },
    },
    grid: { top: 16, right: 8, bottom: 24, left: 36 },
    xAxis: {
      type: 'category',
      data: trend.map(t => t.week_start),
      axisLabel: { fontSize: 11 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#f0f0f0' } },
    },
    yAxis: {
      type: 'value',
      min: 0, max: 100,
      axisLabel: { formatter: '{value}%', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f5f5f5' } },
    },
    series: [{
      type: 'line',
      smooth: true,
      data: trend.map(t => t.adoption_rate),
      lineStyle: { color: '#0AAF9A', width: 2 },
      itemStyle: { color: '#0AAF9A' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(24,144,255,0.15)' },
        { offset: 1, color: 'rgba(24,144,255,0)' },
      ]}},
      symbol: 'circle',
      symbolSize: 6,
    }],
  };

  const storeOptions = [
    { value: '', label: '全部门店' },
    ...stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id })),
  ];

  const daysOptions = [
    { value: 7,  label: '近 7 天' },
    { value: 30, label: '近 30 天' },
    { value: 90, label: '近 90 天' },
  ];

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h4 className={styles.pageTitle}>智能体中心</h4>
          <span className={styles.pageSub}>{AGENT_ORDER.length} 个 Agent 运行中</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <ZSelect
            value={selectedStore}
            onChange={(v) => setSelectedStore(v as string)}
            style={{ width: 160 }}
            options={storeOptions}
          />
          <ZSelect
            value={days}
            onChange={(v) => setDays(Number(v))}
            style={{ width: 100 }}
            options={daysOptions}
          />
          <ZButton icon={<ReloadOutlined />} onClick={loadGov} loading={loading}>刷新</ZButton>
        </div>
      </div>

      {loading ? (
        <ZSkeleton rows={10} block />
      ) : (
        <>
          {/* ── Stats bar ──────────────────────────────────────────────────────── */}
          <div className={styles.statsBar}>
            {statsItems.map((item, idx) => (
              <div key={idx} className={styles.statsBarItem}>
                <div
                  className={styles.statsBarIconWrap}
                  style={{ background: item.iconBg, color: item.iconColor }}
                >
                  {item.icon}
                </div>
                <div className={styles.statsBarBody}>
                  <div className={styles.statsBarLabel}>{item.label}</div>
                  <div className={styles.statsBarValue} style={{ color: item.iconColor }}>
                    {item.value}
                    <span className={styles.statsBarUnit}>{item.unit}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* ── Agent cards ────────────────────────────────────────────────────── */}
          <div className={styles.agentGrid}>
            {AGENT_ORDER.map(agentType => {
              const meta  = AGENT_META[agentType];
              const stat  = statsByType[agentType];
              const st    = statusForAgent(stat);
              const rate  = stat?.adoption_rate ?? 0;

              return (
                <div key={agentType} className={styles.agentCard}>

                  {/* Header */}
                  <div className={styles.agentCardTop}>
                    <div
                      className={styles.agentIconWrap}
                      style={{ background: meta.color, fontSize: 22 }}
                    >
                      {meta.icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                        <span className={styles.agentCardName}>{meta.label} Agent</span>
                        <ZBadge type={st.badgeType} text={st.label} />
                      </div>
                      <div className={styles.agentCardDesc}>{meta.description}</div>
                    </div>
                  </div>

                  {/* Capability tags */}
                  <div className={styles.agentCardCapabilities}>
                    {meta.capabilities.map(cap => (
                      <ZBadge key={cap} type="default" text={cap} />
                    ))}
                  </div>

                  {/* Metrics strip */}
                  <div className={styles.agentMetrics}>
                    <div className={styles.agentMetricItem}>
                      <span className={styles.agentMetricValue}>{stat?.total ?? 0}</span>
                      <span className={styles.agentMetricLabel}>决策总量</span>
                    </div>
                    <div className={styles.agentMetricItem}>
                      <span
                        className={styles.agentMetricValue}
                        style={{ color: adoptionColor(rate) }}
                      >
                        {stat ? `${rate.toFixed(0)}%` : '—'}
                      </span>
                      <span className={styles.agentMetricLabel}>采纳率</span>
                    </div>
                    <div className={styles.agentMetricItem}>
                      <span
                        className={styles.agentMetricValue}
                        style={{ color: (stat?.pending ?? 0) > 0 ? '#C53030' : '#8c8c8c' }}
                      >
                        {stat?.pending ?? 0}
                      </span>
                      <span className={styles.agentMetricLabel}>待处理</span>
                    </div>
                  </div>

                  {/* Adoption bar */}
                  <div className={styles.agentAdoptionRow}>
                    <div className={styles.agentAdoptionHeader}>
                      <span className={styles.agentAdoptionLabel}>采纳率</span>
                      <span
                        className={styles.agentAdoptionPct}
                        style={{ color: adoptionColor(rate) }}
                      >
                        {stat ? `${rate.toFixed(1)}%` : '暂无数据'}
                      </span>
                    </div>
                    <div className={styles.agentAdoptionBar}>
                      <div
                        className={styles.agentAdoptionFill}
                        style={{
                          width: `${stat ? Math.min(rate, 100) : 0}%`,
                          background: adoptionColor(rate),
                        }}
                      />
                    </div>
                  </div>

                  {/* Footer: enter workspace */}
                  <div className={styles.agentCardFooter}>
                    <button
                      className={styles.agentEnterBtn}
                      style={{ borderColor: meta.accentHex, color: meta.accentHex }}
                      onClick={() => navigate(meta.route)}
                    >
                      <ArrowRightOutlined style={{ fontSize: 12 }} />
                      进入工作台
                    </button>
                  </div>

                </div>
              );
            })}
          </div>

          {/* ── Bottom: activity + trend ────────────────────────────────────────── */}
          <div className={styles.bottomSection}>

            {/* Activity feed */}
            <ZCard
              title={
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <RobotOutlined style={{ color: '#0AAF9A' }} />
                  <span>最近决策活动</span>
                </div>
              }
              extra={
                <ZButton variant="ghost" size="sm" icon={<SafetyOutlined />} onClick={() => navigate('/governance')}>
                  查看治理看板 →
                </ZButton>
              }
              noPadding
            >
              {(govData?.recent_logs ?? []).length === 0 ? (
                <ZEmpty description="暂无决策记录" />
              ) : (
                (govData?.recent_logs ?? []).slice(0, 10).map(log => {
                  const meta = AGENT_META[log.agent_type ?? ''];
                  const netImpact = (log.revenue_impact_yuan || 0) - (log.cost_impact_yuan || 0);
                  return (
                    <div key={log.id} className={styles.activityItem}>
                      <div
                        className={styles.activityDot}
                        style={{ background: statusColor(log.decision_status) }}
                      />
                      <div className={styles.activityBody}>
                        <div className={styles.activityTitle}>
                          {log.ai_suggestion || '（无建议摘要）'}
                        </div>
                        <div className={styles.activityMeta}>
                          <span>{log.created_at}</span>
                          {meta && (
                            <ZBadge type="default" text={`${meta.icon} ${meta.label}`} />
                          )}
                          <ZBadge
                            type={statusBadgeType(log.decision_status)}
                            text={statusLabel(log.decision_status)}
                          />
                          <span title="置信度">{log.ai_confidence.toFixed(0)}%</span>
                        </div>
                      </div>
                      {netImpact !== 0 && (
                        <span
                          className={styles.activityAmount}
                          style={{ color: netImpact >= 0 ? '#1A7A52' : '#C53030' }}
                        >
                          {netImpact >= 0 ? '+' : ''}¥{Math.abs(netImpact).toLocaleString()}
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </ZCard>

            {/* Weekly trend chart */}
            <ZCard
              title={
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <RiseOutlined style={{ color: '#1A7A52' }} />
                  <span>采纳率趋势</span>
                </div>
              }
            >
              {trend.length === 0 ? (
                <ZEmpty description="暂无趋势数据" />
              ) : (
                <ReactECharts option={trendChartOption} style={{ height: 180 }} />
              )}

              <div style={{ borderTop: '1px solid var(--border)', margin: '12px 0' }} />

              {/* Per-agent adoption quick list */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {AGENT_ORDER.filter(k => statsByType[k]).slice(0, 6).map(agentType => {
                  const meta = AGENT_META[agentType];
                  const stat = statsByType[agentType];
                  return (
                    <div key={agentType} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 14 }}>{meta.icon}</span>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)', flex: 1, whiteSpace: 'nowrap' }}>
                        {meta.label}
                      </span>
                      <div style={{ width: 80, height: 4, background: '#f0f0f0', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${Math.min(stat.adoption_rate, 100)}%`,
                          background: adoptionColor(stat.adoption_rate),
                          borderRadius: 2,
                          transition: 'width 0.5s ease',
                        }} />
                      </div>
                      <span style={{
                        fontSize: 12, fontWeight: 600, width: 38, textAlign: 'right',
                        color: adoptionColor(stat.adoption_rate),
                      }}>
                        {stat.adoption_rate.toFixed(0)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </ZCard>

          </div>
        </>
      )}
    </div>
  );
};

export default AgentHubPage;
