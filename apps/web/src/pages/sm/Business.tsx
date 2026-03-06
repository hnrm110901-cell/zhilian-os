/**
 * 店长经营分析屏
 * 路由：/sm/business
 *
 * 数据来源：GET /api/v1/bff/chef/{store_id}（食材成本 + 损耗 + 库存）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
  ChartTrend,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Business.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

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

export default function SmBusiness() {
  const [data,    setData]    = useState<ChefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/chef/${STORE_ID}${refresh ? '?refresh=true' : ''}`
      );
      setData(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fc = data?.food_cost_variance;
  const variance = fc?.variance_pct ?? 0;
  const varianceYuan = fc
    ? Math.abs(fc.actual_cost_yuan - fc.revenue_yuan * fc.theoretical_pct / 100)
    : 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>经营分析</div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
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
        </div>
      )}
    </div>
  );
}
