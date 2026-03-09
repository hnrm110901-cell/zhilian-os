/**
 * OpsTimeline — 运营节奏时间轴（设计系统组件）
 *
 * 纯 CSS 实现的垂直时间轴，展示餐厅一天的运营阶段。
 * 当前阶段高亮 + 脉冲圆点，已过阶段灰显。
 *
 * 用法：
 * <OpsTimeline phases={OPS_PHASES} currentIndex={phaseIdx} />
 */
import React from 'react';
import styles from './OpsTimeline.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface OpsPhase {
  label: string;
  /** 开始时刻（小时，支持小数，如 10.5 = 10:30） */
  start: number;
  /** 结束时刻 */
  end: number;
  icon?: React.ReactNode;
  color: string;
}

export interface OpsTimelineProps {
  phases: OpsPhase[];
  /** 当前所在阶段索引（-1 表示不在任何阶段） */
  currentIndex: number;
  className?: string;
  style?: React.CSSProperties;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(h: number): string {
  const hour = Math.floor(h);
  const min  = h % 1 === 0.5 ? '30' : '00';
  return `${hour}:${min}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

const OpsTimeline: React.FC<OpsTimelineProps> = ({
  phases,
  currentIndex,
  className,
  style,
}) => {
  return (
    <div className={`${styles.root} ${className ?? ''}`} style={style}>
      {phases.map((phase, i) => {
        const isPast    = i < currentIndex;
        const isCurrent = i === currentIndex;
        const isFuture  = i > currentIndex;

        const dotColor  = isCurrent ? phase.color : isPast ? '#d9d9d9' : '#d9d9d9';
        const lineColor = i < phases.length - 1
          ? (isPast || isCurrent ? phase.color : '#e8e8e8')
          : 'transparent';

        return (
          <div key={i} className={styles.item}>
            {/* ── Left: dot + line ── */}
            <div className={styles.track}>
              <div
                className={`${styles.dot} ${isCurrent ? styles.dotCurrent : ''}`}
                style={{ background: dotColor, boxShadow: isCurrent ? `0 0 0 3px ${phase.color}33` : 'none' }}
              >
                {isCurrent && phase.icon ? (
                  <span className={styles.dotIcon} style={{ color: '#fff' }}>{phase.icon}</span>
                ) : null}
              </div>
              {i < phases.length - 1 && (
                <div className={styles.line} style={{ background: lineColor }} />
              )}
            </div>

            {/* ── Right: content ── */}
            <div className={`${styles.content} ${isPast ? styles.contentPast : ''}`}>
              <div className={styles.labelRow}>
                <span
                  className={styles.label}
                  style={{
                    color:      isCurrent ? phase.color : isPast ? '#bfbfbf' : '#555',
                    fontWeight: isCurrent ? 700 : 400,
                  }}
                >
                  {phase.label}
                </span>
                {isCurrent && (
                  <span className={styles.currentTag} style={{ background: phase.color }}>
                    当前
                  </span>
                )}
              </div>
              <div className={styles.timeRange}>
                {formatTime(phase.start)}—{formatTime(phase.end)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default OpsTimeline;
