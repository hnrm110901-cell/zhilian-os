import React from 'react';
import styles from './ZAlert.module.css';

type AlertVariant = 'info' | 'success' | 'warning' | 'error';

interface ZAlertProps {
  variant?: AlertVariant;
  icon?: React.ReactNode;
  title?: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  style?: React.CSSProperties;
}

const defaultIcons: Record<AlertVariant, string> = {
  info: 'ℹ️',
  success: '✅',
  warning: '⚠️',
  error: '🚫',
};

export default function ZAlert({ variant = 'info', icon, title, children, action, style }: ZAlertProps) {
  return (
    <div className={`${styles.alert} ${styles[variant]}`} style={style}>
      <span className={styles.icon}>{icon ?? defaultIcons[variant]}</span>
      <div className={styles.content}>
        {title && <div className={styles.title}>{title}</div>}
        {children && <div className={styles.desc}>{children}</div>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
