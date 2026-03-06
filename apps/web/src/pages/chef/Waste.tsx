/**
 * 厨师长损耗分析页
 * 路由：/chef/waste
 * 数据：GET /api/v1/waste/report
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZKpi,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Waste.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

function getDateRange() {
  const end   = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  return {
    end:   end.toISOString().slice(0, 10),
    start: start.toISOString().slice(0, 10),
  };
}

interface WasteItem {
  rank:             number;
  item_name:        string;
  waste_cost_yuan:  number;
  waste_qty:        number;
  unit:             string;
  cost_share_pct:   number;
  root_causes:      string[];
  action?:          string;
}

interface WasteReport {
  total_waste_yuan: number;
  waste_rate_pct:   number;
  top5:             WasteItem[];
}

const REASON_LABELS: Record<string, { label: string; type: 'warning' | 'critical' | 'info' }> = {
  over_purchase: { label: '超量采购', type: 'warning'  },
  expired:       { label: '过期',     type: 'critical' },
  prep_error:    { label: '制作损耗', type: 'warning'  },
  storage_issue: { label: '存储不当', type: 'critical' },
  bom_deviation: { label: 'BOM偏差', type: 'info'     },
};

export default function ChefWaste() {
  const [report,  setReport]  = useState<WasteReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const { start, end } = getDateRange();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get('/api/v1/waste/report', {
        params: { store_id: STORE_ID, start_date: start, end_date: end },
      });
      setReport(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>损耗分析</div>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={6} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={load}>重试</ZButton>} />
        </div>
      ) : !report ? (
        <div className={styles.body}><ZEmpty icon="✅" title="暂无损耗数据" /></div>
      ) : (
        <div className={styles.body}>
          <div className={styles.kpiRow}>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={`¥${report.total_waste_yuan.toFixed(0)}`} label="近7日损耗" size="lg" />
            </ZCard>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={`${report.waste_rate_pct.toFixed(1)}%`} label="损耗率" size="lg" />
            </ZCard>
          </div>

          <ZCard subtitle="Top5 损耗食材">
            {report.top5.length === 0 ? (
              <ZEmpty title="暂无损耗记录" />
            ) : (
              report.top5.map(item => {
                const reason = REASON_LABELS[item.root_causes?.[0]] ?? { label: item.root_causes?.[0] ?? '未知', type: 'info' as const };
                return (
                  <div key={item.rank} className={styles.row}>
                    <div className={styles.rank}>#{item.rank}</div>
                    <div className={styles.info}>
                      <div className={styles.name}>{item.item_name}</div>
                      <div className={styles.sub}>
                        {item.waste_qty.toFixed(1)}{item.unit} · 占比 {item.cost_share_pct.toFixed(1)}%
                      </div>
                      {item.action && (
                        <div className={styles.action}>{item.action}</div>
                      )}
                    </div>
                    <div className={styles.right}>
                      <ZBadge type={reason.type} text={reason.label} />
                      <span className={styles.yuan}>¥{item.waste_cost_yuan.toFixed(0)}</span>
                    </div>
                  </div>
                );
              })
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
