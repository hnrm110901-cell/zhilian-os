import React from 'react';
import styles from './ZKpi.module.css';

interface ZKpiProps {
  value: string | number;
  label: string;
  unit?: string;
  prefix?: string;
  change?: number;       // 正数=上升，负数=下降，0=持平
  changeLabel?: string;  // 如 "较昨日"
  size?: 'sm' | 'md' | 'lg';
  status?: 'good' | 'warning' | 'critical' | string;
  color?: string;
}

export default function ZKpi({
  value, label, unit, prefix, change, changeLabel, size = 'md', color,
}: ZKpiProps) {
  const changeDir = change == null ? null : change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  const changeSymbol = change == null ? '' : change > 0 ? '↑' : change < 0 ? '↓' : '—';

  return (
    <div className={styles.kpi}>
      <div className={styles.label}>{label}</div>
      <div className={styles.valueRow}>
        <span className={`${styles.value} ${styles[size]}`} style={color ? { color } : undefined}>{prefix ?? ''}{value}</span>
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
      {change != null && (
        <span className={`${styles.change} ${changeDir ? styles[changeDir] : ''}`}>
          {changeSymbol} {Math.abs(change).toFixed(1)}%
          {changeLabel && <span style={{ color: 'var(--text-tertiary)' }}>&nbsp;{changeLabel}</span>}
        </span>
      )}
    </div>
  );
}
