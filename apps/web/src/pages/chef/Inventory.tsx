/**
 * 厨师长库存状态页
 * 路由：/chef/inventory
 * 数据：GET /api/v1/bff/chef/{store_id}（复用缓存）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZKpi,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Inventory.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

interface InventoryAlert {
  ingredient_name:  string;
  current_stock:    number;
  unit:             string;
  alert_type:       string;
  severity:         'warning' | 'critical';
  suggested_action?: string;
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  low:    '库存不足',
  expiry: '临期预警',
  excess: '库存过剩',
};

export default function ChefInventory() {
  const [alerts,  setAlerts]  = useState<InventoryAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(
        `/api/v1/bff/chef/${STORE_ID}${refresh ? '?refresh=true' : ''}`,
      );
      setAlerts(resp.inventory_alerts ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const criticalCount = alerts.filter(a => a.severity === 'critical').length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>库存状态</div>
        <ZButton variant="ghost" size="sm" onClick={() => load(true)}>刷新</ZButton>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={5} /></div>
      ) : error ? (
        <div className={styles.body}>
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={() => load()}>重试</ZButton>} />
        </div>
      ) : (
        <div className={styles.body}>
          <div className={styles.kpiRow}>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={String(alerts.length)} label="告警项" size="lg" />
            </ZCard>
            <ZCard style={{ flex: 1 }}>
              <ZKpi value={String(criticalCount)} label="紧急项" size="lg" />
            </ZCard>
          </div>

          {alerts.length === 0 ? (
            <ZEmpty icon="✅" title="库存状态正常" description="所有食材均在安全库存范围内" />
          ) : (
            <ZCard subtitle={`共 ${alerts.length} 项需处理`}>
              {alerts.map((alert, i) => (
                <div key={i} className={styles.row}>
                  <div className={styles.info}>
                    <div className={styles.name}>{alert.ingredient_name}</div>
                    <div className={styles.sub}>
                      当前库存：{alert.current_stock.toFixed(1)} {alert.unit}
                    </div>
                    {alert.suggested_action && (
                      <div className={styles.action}>{alert.suggested_action}</div>
                    )}
                  </div>
                  <div className={styles.right}>
                    <ZBadge
                      type={alert.severity === 'critical' ? 'critical' : 'warning'}
                      text={ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
                    />
                  </div>
                </div>
              ))}
            </ZCard>
          )}
        </div>
      )}
    </div>
  );
}
