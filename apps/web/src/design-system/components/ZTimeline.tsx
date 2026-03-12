import React from 'react';
import styles from './ZTimeline.module.css';

type TimelineStatus = 'done' | 'current' | 'pending';

export interface TimelineItem {
  key: string;
  label: string;
  time?: string;
  status: TimelineStatus;
}

interface ZTimelineProps {
  items: TimelineItem[];
  style?: React.CSSProperties;
}

export default function ZTimeline({ items, style }: ZTimelineProps) {
  return (
    <div className={styles.timeline} style={style}>
      {items.map((item) => (
        <div key={item.key} className={`${styles.item} ${styles[item.status]}`}>
          <div className={styles.indicator}>
            <div className={styles.dot} />
            <div className={styles.line} />
          </div>
          <div className={styles.body}>
            <div className={styles.label}>{item.label}</div>
            {item.time && <div className={styles.time}>{item.time}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
