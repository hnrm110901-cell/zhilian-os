import React from 'react';
import styles from './DecisionCard.module.css';

type Severity = 'high' | 'medium' | 'low';

interface DecisionCardProps {
  title: string;
  description?: string;
  severity?: Severity;
  savingYuan?: number;
  confidence?: number; // 0-100
  action?: React.ReactNode;
  style?: React.CSSProperties;
}

export default function DecisionCard({
  title, description, severity = 'medium', savingYuan, confidence, action, style,
}: DecisionCardProps) {
  return (
    <div className={`${styles.card} ${styles[severity]}`} style={style}>
      <div className={styles.header}>
        <div className={styles.title}>{title}</div>
        {savingYuan != null && (
          <div className={styles.saving}>{savingYuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}</div>
        )}
      </div>
      {description && <div className={styles.desc}>{description}</div>}
      <div className={styles.footer}>
        {confidence != null && (
          <span className={styles.confidence}>
            置信度 {confidence}%
            <span className={styles.confidenceBar}>
              <span className={styles.confidenceFill} style={{ width: `${confidence}%` }} />
            </span>
          </span>
        )}
        {action}
      </div>
    </div>
  );
}
