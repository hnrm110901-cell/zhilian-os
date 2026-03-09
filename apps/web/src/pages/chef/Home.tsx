/**
 * 厨师长手机主屏
 * 路由：/chef
 * 数据：GET /api/v1/bff/chef/{store_id}
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTabs,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './ChefHome.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

interface WasteItem {
  item_name:       string;
  waste_cost_yuan: number;
  waste_qty:       number;
  unit:            string;
}
interface InvAlert {
  ingredient_name: string;
  current_stock:   number;
  reorder_point:   number;
  unit:            string;
}
interface ChefData {
  store_id:           string;
  food_cost_variance: null | {
    actual_cost_pct:  number;
    theoretical_pct:  number;
    variance_pct:     number;
    actual_cost_yuan: number;
    revenue_yuan:     number;
    period_label?:    string;
  };
  waste_top5:       WasteItem[];
  inventory_alerts: InvAlert[];
}

export default function ChefHome() {
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
      setData(resp);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fc       = data?.food_cost_variance;
  const variance = fc?.variance_pct ?? 0;
  const invCount = data?.inventory_alerts?.length ?? 0;
  const varianceYuan = fc
    ? Math.abs(fc.actual_cost_yuan - fc.revenue_yuan * fc.theoretical_pct / 100)
    : 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>厨房看板</div>
          <div className={styles.sub}>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}</div>
        </div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading && !data ? (
        <div className={styles.body}><ZSkeleton block rows={3} style={{ gap: 16 }} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          {/* 食材成本率 */}
          <ZCard
            title="食材成本率"
            subtitle={fc?.period_label ?? '近7天'}
            extra={fc ? <ZBadge type={variance > 5 ? 'critical' : variance > 2 ? 'warning' : 'success'} text={variance > 0 ? `超${variance.toFixed(1)}%` : '达标'} /> : undefined}
          >
            {fc ? (
              <div className={styles.fcGrid}>
                <ZKpi value={fc.actual_cost_pct.toFixed(1)} label="实际" unit="%" size="lg" />
                <ZKpi value={fc.theoretical_pct.toFixed(1)} label="目标" unit="%" size="lg" />
                <ZKpi
                  value={varianceYuan.toFixed(0)}
                  label={variance > 0 ? '超支' : '节省'}
                  unit="元"
                  size="lg"
                />
              </div>
            ) : (
              <ZEmpty title="暂无成本数据" />
            )}
          </ZCard>

          {/* 损耗 + 库存 标签页 */}
          <ZCard noPadding>
            <ZTabs
              items={[
                {
                  key: 'waste',
                  label: '损耗 Top5',
                  children: (
                    <div className={styles.listWrap}>
                      {data?.waste_top5?.length ? (
                        data.waste_top5.map((item, i) => (
                          <div key={i} className={styles.listRow}>
                            <span className={`${styles.rank} ${i === 0 ? styles.rankTop : ''}`}>{i + 1}</span>
                            <span className={styles.itemName}>{item.item_name}</span>
                            <span className={styles.qty}>{item.waste_qty.toFixed(1)}{item.unit}</span>
                            <span className={styles.cost}>¥{item.waste_cost_yuan.toFixed(0)}</span>
                          </div>
                        ))
                      ) : (
                        <ZEmpty icon="✅" title="本周暂无损耗" />
                      )}
                    </div>
                  ),
                },
                {
                  key: 'inventory',
                  label: '库存告警',
                  badge: invCount,
                  children: (
                    <div className={styles.listWrap}>
                      {data?.inventory_alerts?.length ? (
                        data.inventory_alerts.map((item, i) => (
                          <div key={i} className={styles.listRow}>
                            <ZBadge type="warning" text="低库存" />
                            <span className={styles.itemName}>{item.ingredient_name}</span>
                            <span className={styles.qty}>
                              {item.current_stock}{item.unit} / {item.reorder_point}{item.unit}
                            </span>
                          </div>
                        ))
                      ) : (
                        <ZEmpty icon="✅" title="库存充足" />
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </ZCard>
        </div>
      )}
    </div>
  );
}
