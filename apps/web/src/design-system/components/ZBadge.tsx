import React from 'react';
import styles from './ZBadge.module.css';

type BadgeType =
  | 'critical'
  | 'warning'
  | 'success'
  | 'info'
  | 'default'
  | 'accent'
  | 'error'
  | 'neutral';

export interface ZBadgeProps {
  type?: BadgeType;
  text?: string;
  label?: string;
  icon?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

export default function ZBadge({ type = 'default', text, label, icon, className, children }: ZBadgeProps) {
  const shown = children ?? text ?? label ?? '';
  return (
    <span className={`${styles.badge} ${styles[type]}${className ? ` ${className}` : ''}`}>
      {icon && icon}
      {shown}
    </span>
  );
}
