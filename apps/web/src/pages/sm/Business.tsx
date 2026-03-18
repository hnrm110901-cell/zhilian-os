/**
 * 店长经营分析屏
 * 路由：/sm/business
 *
 * 数据来源：
 *   - GET /api/v1/bff/chef/{store_id}        — 食材成本 + 损耗 + 库存
 *   - GET /api/v1/decisions/flow-history     — 今日四时段推送流水
 */
import React, { useEffect, useState, useCallback } from 'react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
  ChartTrend,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './Business.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface ChefData {
  store_id:           string;
  food_cost_variance: null | {
    actual_cost_pct:  number;
    theoretical_pct:  number;
    variance_pct:     number;
    actual_cost_yuan: number;
    revenue_yuan:     number;
    period_label:     string;
  };
  waste_top5: Array<{
    item_name:        string;
    waste_cost_yuan:  number;
    waste_qty:        number;
    unit:             string;
  }>;
  inventory_alerts: Array<{
    ingredient_name: string;
    current_stock:   number;
    reorder_point:   number;
    unit:            string;
  }>;
}

interface FlowWindow {
  window:  string;
  slug:    string;
  state:   null | {
    push_sent:        boolean;
    decision_count:   number;
    total_saving_yuan:number;
    push_message_id:  string | null;
    trigger_time:     string;
    completed_at:     string | null;
  };
}

const SLUG_LABEL: Record<string, string> = {
  morning:   '08:00 晨推',
  noon:      '12:00 午推',
  prebattle: '17:30 战前',
  evening:   '20:30 晚推',
};

export default function SmBusiness() {
  const [data,          setData]          = useState<ChefData | null>(null);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState<string | null>(null);
  const [flowWindows,   setFlowWindows]   = useState<FlowWindow[]>([]);
  const [flowLoading,   setFlowLoading]   = useState(true);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/chef/${STORE_ID}${refresh ? '?refresh=true' : ''}`
      );
      setData(resp);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFlow = useCallback(async () => {
    setFlowLoading(true);
    try {
      const resp = await apiClient.get('/api/v1/decisions/flow-history', {
        params: { store_id: STORE_ID, date: dayjs().format('YYYY-MM-DD') },
      });
      setFlowWindows(resp.windows ?? []);
    } catch (e) {
      handleApiError(e, '推送流水加载失败');
    } finally {
      setFlowLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    loadFlow();
  }, [load, loadFlow]);

  const fc = data?.food_cost_variance;
  const variance = fc?.variance_pct ?? 0;
  const varianceYuan = fc
    ? Math.abs(fc.actual_cost_yuan - fc.revenue_yuan * fc.theoretical_pct / 100)
    : 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>经营分析</div>
        <ZButton variant="ghost" size="sm" onClick={() => { load(true); loadFlow(); }}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}>
          <ZSkeleton block rows={3} style={{ gap: 16 }} />
        </div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          {/* 营收概览 */}
          {fc && (
            <ZCard title="本期营收">
              <div className={styles.fcRow}>
                <ZKpi
                  value={(fc.revenue_yuan / 10000).toFixed(1)}
                  label="本期营收"
                  unit="万元"
                  size="lg"
                />
                <ZKpi
                  value={fc.actual_cost_pct.toFixed(1)}
                  label="食材成本率"
                  unit="%"
                  change={-variance}
                  changeLabel={`目标${fc.theoretical_pct.toFixed(1)}%`}
                  size="lg"
                />
              </div>
            </ZCard>
          )}

          {/* 食材成本卡 */}
          <ZCard
            title="食材成本率"
            subtitle={fc?.period_label ?? '近7天'}
            extra={
              fc ? (
                <ZBadge
                  type={variance > 5 ? 'critical' : variance > 2 ? 'warning' : 'success'}
                  text={variance > 0 ? `超${variance.toFixed(1)}%` : '正常'}
                />
              ) : null
            }
          >
            {fc ? (
              <div className={styles.fcRow}>
                <ZKpi
                  value={fc.actual_cost_pct.toFixed(1)}
                  label="实际成本率"
                  unit="%"
                  change={-variance}
                  changeLabel={`目标${fc.theoretical_pct.toFixed(1)}%`}
                  size="lg"
                />
                <ZKpi
                  value={varianceYuan.toFixed(0)}
                  label={variance > 0 ? '超支金额' : '节省金额'}
                  unit="元"
                  size="lg"
                />
              </div>
            ) : (
              <ZEmpty title="暂无食材成本数据" />
            )}
          </ZCard>

          {/* 损耗 Top5 */}
          <ZCard title="损耗 Top 5" subtitle="近7天">
            {data?.waste_top5?.length ? (
              <div className={styles.wasteList}>
                {data.waste_top5.map((item, i) => (
                  <div key={i} className={styles.wasteItem}>
                    <span className={styles.wasteRank}>{i + 1}</span>
                    <span className={styles.wasteName}>{item.item_name}</span>
                    <span className={styles.wasteQty}>{item.waste_qty.toFixed(1)}{item.unit}</span>
                    <span className={styles.wasteCost}>¥{item.waste_cost_yuan.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <ZEmpty title="本周暂无损耗记录" icon="✅" />
            )}
          </ZCard>

          {/* 库存告警 */}
          <ZCard title="库存告警" extra={data?.inventory_alerts?.length ? <ZBadge type="warning" text={`${data.inventory_alerts.length}项`} /> : null}>
            {data?.inventory_alerts?.length ? (
              <div className={styles.invList}>
                {data.inventory_alerts.map((item, i) => (
                  <div key={i} className={styles.invItem}>
                    <span className={styles.invName}>{item.ingredient_name}</span>
                    <span className={styles.invStock}>
                      剩余 <strong>{item.current_stock}</strong>{item.unit}（补货点{item.reorder_point}）
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <ZEmpty title="库存充足，无告警" icon="✅" />
            )}
          </ZCard>

          {/* 今日推送流水 */}
          <ZCard title="今日推送流水" subtitle={dayjs().format('MM-DD')}>
            {flowLoading ? (
              <ZSkeleton rows={2} />
            ) : (
              <div className={styles.flowList}>
                {flowWindows.map((w) => (
                  <div key={w.slug} className={styles.flowItem}>
                    <span className={styles.flowWindow}>{SLUG_LABEL[w.slug] ?? w.window}</span>
                    {w.state ? (
                      <>
                        <ZBadge
                          type={w.state.push_sent ? 'success' : 'warning'}
                          text={w.state.push_sent ? '已推送' : '未发送'}
                        />
                        {w.state.push_sent && w.state.decision_count > 0 && (
                          <span className={styles.flowMeta}>
                            {w.state.decision_count}条 · ¥{w.state.total_saving_yuan.toFixed(0)}
                          </span>
                        )}
                      </>
                    ) : (
                      <ZBadge type="default" text="待推送" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
