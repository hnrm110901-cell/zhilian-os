import React from 'react';
import styles from './ZTag.module.css';

type TagVariant = 'mint' | 'warn' | 'danger' | 'ok' | 'neutral';

interface ZTagProps {
  variant?: TagVariant;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export default function ZTag({ variant = 'neutral', children, style }: ZTagProps) {
  return (
    <span className={`${styles.tag} ${styles[variant]}`} style={style}>
      {children}
    </span>
  );
}
