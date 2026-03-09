/**
 * 总部人力成本排名页
 * 路由：/hq/workforce
 * 数据：GET /api/v1/workforce/multi-store/labor-ranking?month=YYYY-MM
 */
import React, { useEffect, useState, useCallback } from 'react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZSelect,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './Workforce.module.css';

interface RankingItem {
  store_id:           string;
  rank_in_group:      number;
  total_stores:       number;
  labor_cost_rate:    number;
  percentile_score:   number;
  group_avg_rate:     number;
  group_median_rate:  number;
  best_rate_in_group: number;
}

interface RankingResponse {
  brand_id:     string;
  ranking_date: string;
  total_stores: number;
  rankings:     RankingItem[];
}

// 生成近6个月的月份选项
function buildMonthOptions() {
  return Array.from({ length: 6 }, (_, i) => {
    const m = dayjs().subtract(i, 'month').format('YYYY-MM');
    return { value: m, label: m };
  });
}

function rateStatus(rate: number, avg: number): 'success' | 'info' | 'warning' | 'critical' {
  if (rate <= avg * 0.92) return 'success';
  if (rate <= avg * 1.05) return 'info';
  if (rate <= avg * 1.15) return 'warning';
  return 'critical';
}

export default function HQWorkforce() {
  const [month,   setMonth]   = useState(dayjs().format('YYYY-MM'));
  const [data,    setData]    = useState<RankingResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (m: string) => {
    setLoading(true);
    try {
      const resp = await apiClient.get('/api/v1/workforce/multi-store/labor-ranking', {
        params: { month: m },
      });
      setData(resp);
    } catch (e) {
      handleApiError(e, '人工成本排名加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(month); }, [load, month]);

  const avgRate  = data?.rankings?.[0]?.group_avg_rate  ?? 0;
  const bestRate = data?.rankings?.[0]?.best_rate_in_group ?? 0;
  const overAvg  = (data?.rankings ?? []).filter(r => r.labor_cost_rate > avgRate).length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>跨店人力成本排名</div>
        <ZSelect
          value={month}
          options={buildMonthOptions()}
          onChange={(v) => setMonth(v as string)}
          style={{ width: 120 }}
        />
      </div>

      {/* KPI 汇总行 */}
      <div className={styles.kpiRow}>
        <ZCard>
          <ZKpi value={data?.total_stores ?? '-'} label="参与门店" unit="家" />
        </ZCard>
        <ZCard>
          <ZKpi value={avgRate.toFixed(1)} label="品牌均值" unit="%" />
        </ZCard>
        <ZCard>
          <ZKpi value={bestRate.toFixed(1)} label="最优门店" unit="%" />
        </ZCard>
        <ZCard>
          <ZKpi value={overAvg} label="超均值门店" unit="家" />
        </ZCard>
      </div>

      {/* 排名列表 */}
      <ZCard title="人工成本率排名" subtitle={month}>
        {loading ? (
          <ZSkeleton rows={5} />
        ) : !data?.rankings?.length ? (
          <ZEmpty title="暂无排名数据" description="请确认已为该月配置人工成本快照" />
        ) : (
          <div className={styles.list}>
            {data.rankings.map((item) => {
              const status = rateStatus(item.labor_cost_rate, item.group_avg_rate);
              const diffPct = item.labor_cost_rate - item.group_avg_rate;
              return (
                <div key={item.store_id} className={styles.row}>
                  <span className={styles.rank}>{item.rank_in_group}</span>
                  <div className={styles.info}>
                    <div className={styles.storeId}>{item.store_id}</div>
                    <div className={styles.pct}>百分位 {item.percentile_score.toFixed(0)}%</div>
                  </div>
                  <div className={styles.right}>
                    <span className={styles.rate}>{item.labor_cost_rate.toFixed(1)}%</span>
                    <ZBadge
                      type={status}
                      text={diffPct >= 0 ? `+${diffPct.toFixed(1)}%` : `${diffPct.toFixed(1)}%`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ZCard>
    </div>
  );
}
