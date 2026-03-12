/**
 * 总部桌面大屏总览 v2
 * 路由：/hq
 * 数据：GET /api/v1/bff/hq
 */
import React, { useEffect, useState, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import { useNavigate } from 'react-router-dom';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
  HealthRing,
} from '../../design-system/components';
import apiClient from '../../services/api';
import RecommendationCard from '../../components/RecommendationCard';
import styles from './HQHome.module.css';

interface StoreHealth {
  store_id:           string;
  store_name:         string;
  score:              number;
  level:              string;
  rank:               number;
  revenue_yuan:       number;
  weakest_dimension?: string;
}
interface FcRank {
  store_id:         string;
  store_name:       string;
  actual_cost_pct:  number;
  variance_pct:     number;
  variance_status?: string;
}
interface Decision {
  store_id:             string;
  title:                string;
  expected_saving_yuan: number;
  urgency_hours:        number;
}
interface EdgeHubSummary {
  total_hubs:         number;
  online_hubs:        number;
  offline_hubs:       number;
  open_alert_count:   number;
  p1_alert_count:     number;
}

interface HQData {
  as_of:                   string;
  stores_health_ranking:   StoreHealth[];
  food_cost_ranking:       FcRank[];
  cross_store_decisions:   Decision[];
  revenue_trend:           { dates: string[]; stores: { store_id: string; store_name: string; values: number[] }[] };
  pending_approvals_count: number;
  edge_hub_summary:        EdgeHubSummary | null;
  hq_summary: {
    store_count:          number;
    avg_health_score:     number;
    total_revenue_yuan:   number;
    critical_store_count: number;
    warning_store_count:  number;
  };
}

interface LaborRankingItem {
  store_id: string;
  rank_in_group?: number;
  labor_cost_rate?: number;
  labor_cost_rate_pct?: number;
}

interface LaborRankingResponse {
  ranking_date?: string;
  group_avg_rate?: number;
  rankings?: LaborRankingItem[];
}

const DIM_LABEL: Record<string, string> = {
  revenue_completion: '营收完成率',
  table_turnover:     '翻台率',
  cost_rate:          '成本率',
  complaint_rate:     '客诉率',
  staff_efficiency:   '人效',
};

const LEVEL_BADGE: Record<string, { type: 'success'|'info'|'warning'|'critical'; label: string }> = {
  excellent: { type: 'success',  label: '优秀'   },
  good:      { type: 'info',     label: '良好'   },
  warning:   { type: 'warning',  label: '需关注' },
  critical:  { type: 'critical', label: '危险'   },
};

const PALETTE = [
  '#0AAF9A','#3B82F6','#FFC244','#FF7A3D','#8B5CF6',
  '#EC4899','#1A7A52','#C8923A','#6366F1','#84CC16',
];

export default function HQHome() {
  const navigate = useNavigate();
  const [data,    setData]    = useState<HQData | null>(null);
  const [laborRanking, setLaborRanking] = useState<LaborRankingItem[]>([]);
  const [laborAvgRate, setLaborAvgRate] = useState<number>(0);
  const [prevRankMap, setPrevRankMap] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const month = new Date().toISOString().slice(0, 7);
      const d = new Date();
      d.setMonth(d.getMonth() - 1);
      const prevMonth = d.toISOString().slice(0, 7);

      const [hqResp, laborResp, prevResp] = await Promise.all([
        apiClient.get<HQData>(`/api/v1/bff/hq${refresh ? '?refresh=true' : ''}`),
        apiClient.get<LaborRankingResponse>(`/api/v1/workforce/multi-store/labor-ranking`, { params: { month } }),
        apiClient.get<LaborRankingResponse>(`/api/v1/workforce/multi-store/labor-ranking`, { params: { month: prevMonth } }),
      ]);

      setData(hqResp);
      setLaborRanking(laborResp.rankings ?? []);
      setLaborAvgRate(Number(laborResp.group_avg_rate ?? 0));
      setPrevRankMap(
        Object.fromEntries((prevResp.rankings ?? []).map((item) => [item.store_id, Number(item.rank_in_group ?? 0)]))
      );
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = data?.hq_summary;
  const criticalStores = (data?.stores_health_ranking ?? []).filter(s => s.level === 'critical');
  const storeNameMap = React.useMemo(() => (
    Object.fromEntries((data?.stores_health_ranking ?? []).map((x) => [x.store_id, x.store_name]))
  ), [data?.stores_health_ranking]);

  const trendOption = React.useMemo(() => {
    const trend = data?.revenue_trend;
    if (!trend?.dates?.length) return null;
    const labels = trend.dates.map(d => d.slice(5));
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any[]) =>
          `<b>${params[0]?.axisValue}</b><br/>` +
          params.map((p: any) =>
            `${p.marker}${p.seriesName}：¥${Number(p.value).toLocaleString()}`
          ).join('<br/>'),
      },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 11, color: '#888' } },
      grid: { top: 12, left: 52, right: 16, bottom: 64 },
      xAxis: {
        type: 'category', data: labels,
        axisLabel: { fontSize: 11, color: '#999' },
        axisLine:  { lineStyle: { color: '#e0e0e0' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          fontSize: 11, color: '#999',
          formatter: (v: number) => v >= 10000 ? `${(v / 10000).toFixed(1)}w` : String(v),
        },
        splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } },
      },
      series: trend.stores.map((store, i) => ({
        name: store.store_name, type: 'line', smooth: true, data: store.values,
        lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] },
        itemStyle: { color: PALETTE[i % PALETTE.length] },
        symbol: 'circle', symbolSize: 5,
      })),
    };
  }, [data?.revenue_trend]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>总部总览</div>
          <div className={styles.sub}>
            {data?.as_of
              ? new Date(data.as_of).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
              : '加载中…'}
          </div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}><ZSkeleton block rows={4} style={{ gap: 20 }} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error}
            action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>

          {/* KPI 行 */}
          <div className={styles.kpiRow}>
            <ZCard><ZKpi value={s?.total_revenue_yuan != null ? `¥${Math.round(s.total_revenue_yuan).toLocaleString()}` : '—'} label="今日全链总营收" size="lg" /></ZCard>
            <ZCard><ZKpi value={s?.avg_health_score?.toFixed(1) ?? '—'} label="平均门店健康分" size="lg" /></ZCard>
            <ZCard><ZKpi value={(s?.critical_store_count ?? 0) + (s?.warning_store_count ?? 0)} label="告警门店" unit="家" size="lg" /></ZCard>
            <ZCard><ZKpi value={data?.pending_approvals_count ?? 0} label="待审批决策" size="lg" /></ZCard>
            <ZCard>
              <div style={(data?.edge_hub_summary?.offline_hubs ?? 0) > 0 ? { color: '#f97316' } : undefined}>
                <ZKpi
                  value={data?.edge_hub_summary?.offline_hubs ?? '—'}
                  label="离线主机"
                  unit="台"
                  size="lg"
                />
              </div>
            </ZCard>
          </div>

          {/* 硬件告警横幅 */}
          {data?.edge_hub_summary && (data.edge_hub_summary.offline_hubs > 0 || data.edge_hub_summary.p1_alert_count > 0) && (
            <button className={styles.hwBanner} onClick={() => navigate('/edge-hub/dashboard')}>
              <span>📡</span>
              <span>
                <strong>硬件异常：</strong>
                {data.edge_hub_summary.offline_hubs > 0 && `${data.edge_hub_summary.offline_hubs} 台主机离线`}
                {data.edge_hub_summary.offline_hubs > 0 && data.edge_hub_summary.p1_alert_count > 0 && ' · '}
                {data.edge_hub_summary.p1_alert_count > 0 && `${data.edge_hub_summary.p1_alert_count} 条P1告警未解决`}
              </span>
              <span className={styles.hwBannerLink}>查看详情 ›</span>
            </button>
          )}

          {/* 危险门店横幅 */}
          {criticalStores.length > 0 && (
            <div className={styles.criticalBanner}>
              <span>🚨</span>
              <span><strong>危险门店需立即关注：</strong>{criticalStores.map(s => s.store_name).join('、')}</span>
            </div>
          )}

          {/* 主内容：趋势图 + 健康排名 */}
          <div className={styles.mainGrid}>
            <ZCard title="近7天各店营收趋势">
              {trendOption
                ? <ReactECharts option={trendOption} style={{ height: 300 }} notMerge />
                : <ZEmpty title="暂无趋势数据" />}
            </ZCard>

            <ZCard title="门店健康排名" subtitle={`共 ${data?.stores_health_ranking?.length ?? 0} 家`}>
              <div className={styles.healthList}>
                {(data?.stores_health_ranking ?? []).map(store => {
                  const badge = LEVEL_BADGE[store.level] ?? LEVEL_BADGE.good;
                  return (
                    <div key={store.store_id} className={styles.healthRow}>
                      <span className={styles.healthRank}>#{store.rank}</span>
                      <HealthRing score={store.score} size={36} strokeWidth={4} />
                      <div className={styles.healthMeta}>
                        <div className={styles.healthName}>{store.store_name}</div>
                        <div className={styles.healthDim}>
                          {store.weakest_dimension
                            ? `↓ ${DIM_LABEL[store.weakest_dimension] ?? store.weakest_dimension}`
                            : '各维度正常'}
                        </div>
                      </div>
                      <div className={styles.healthRight}>
                        <ZBadge type={badge.type} text={badge.label} />
                        {store.revenue_yuan > 0 && (
                          <span className={styles.healthRev}>¥{Math.round(store.revenue_yuan).toLocaleString()}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {!(data?.stores_health_ranking?.length) && <ZEmpty title="暂无门店数据" />}
              </div>
            </ZCard>
          </div>

          {/* 底部：人工成本排名 + 跨店决策 */}
          <div className={styles.bottomGrid}>
            <ZCard title="人工成本率排名" subtitle={`品牌均值 ${laborAvgRate.toFixed(2)}%`}>
              <div className={styles.fcList}>
                {(laborRanking ?? []).map((item, i) => {
                  const rank = Number(item.rank_in_group ?? i + 1);
                  const rate = Number(item.labor_cost_rate ?? item.labor_cost_rate_pct ?? 0);
                  const delta = Number((rate - laborAvgRate).toFixed(2));
                  const prevRank = prevRankMap[item.store_id];
                  const rankDelta = prevRank ? prevRank - rank : 0;
                  const barColor = delta > 2 ? '#ef4444' : delta > 0.5 ? '#f97316' : '#10b981';
                  return (
                    <div key={item.store_id} className={styles.fcRow}>
                      <span className={styles.fcRank}>{rank}</span>
                      <div className={styles.fcMeta}>
                        <div className={styles.fcName}>{storeNameMap[item.store_id] || item.store_id}</div>
                        <div className={styles.fcBarWrap}>
                          <div className={styles.fcFill} style={{ width: `${Math.min(100, rate)}%`, background: barColor }} />
                        </div>
                      </div>
                      <div className={styles.fcValues}>
                        <span className={styles.fcActual}>{rate.toFixed(2)}%</span>
                        <span className={styles.fcVariance} style={{ color: delta > 0 ? '#ef4444' : '#10b981' }}>
                          {delta > 0 ? '+' : ''}{delta.toFixed(2)}%
                        </span>
                        <span className={styles.fcRankTrend}>
                          {rankDelta > 0 ? '↑' : rankDelta < 0 ? '↓' : '→'} {Math.abs(rankDelta)}
                        </span>
                      </div>
                    </div>
                  );
                })}
                {!laborRanking.length && <ZEmpty title="暂无人工成本排名数据" />}
              </div>
            </ZCard>

            <ZCard title="跨店紧急决策" subtitle={`${data?.cross_store_decisions?.length ?? 0} 项待处理`}>
              <div className={styles.decList}>
                {(data?.cross_store_decisions ?? []).map((dec, i) => (
                  <div key={i} className={styles.decRow}>
                    <ZBadge
                      type={dec.urgency_hours <= 4 ? 'critical' : dec.urgency_hours <= 12 ? 'warning' : 'info'}
                      text={dec.urgency_hours <= 0 ? '立即' : `${Math.round(dec.urgency_hours)}h`}
                    />
                    <div className={styles.decMeta}>
                      <div className={styles.decTitle}>{dec.title}</div>
                      <div className={styles.decStore}>{dec.store_id}</div>
                    </div>
                    <span className={styles.decSaving}>¥{Math.round(dec.expected_saving_yuan).toLocaleString()}</span>
                  </div>
                ))}
                {!(data?.cross_store_decisions?.length) && (
                  <ZEmpty icon="✅" title="暂无紧急决策" description="各门店运营正常" />
                )}
              </div>
            </ZCard>
          </div>

          {/* AI 经营推荐（取排名最差门店，优先提供帮助） */}
          {data?.stores_health_ranking?.length ? (
            <div style={{ marginTop: 12 }}>
              <RecommendationCard
                storeId={data.stores_health_ranking[data.stores_health_ranking.length - 1].store_id}
                maxItems={4}
              />
            </div>
          ) : null}

        </div>
      )}
    </div>
  );
}
