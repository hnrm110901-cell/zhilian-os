import React from 'react';
import styles from './AIMessageCard.module.css';

type ConfidenceLevel = 'high' | 'medium' | 'low';

interface AIMessageCardProps {
  children: React.ReactNode;
  confidence?: ConfidenceLevel;
  actions?: React.ReactNode;
  style?: React.CSSProperties;
}

export default function AIMessageCard({ children, confidence = 'medium', actions, style }: AIMessageCardProps) {
  return (
    <div className={`${styles.card} ${styles[confidence]}`} style={style}>
      <div className={styles.header}>
        <span className={styles.avatar}>🤖</span>
        <span className={styles.label}>屯象智脑</span>
        {confidence && <span className={styles.confidenceDot} title={`置信度: ${confidence}`} />}
      </div>
      <div className={styles.body}>{children}</div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
