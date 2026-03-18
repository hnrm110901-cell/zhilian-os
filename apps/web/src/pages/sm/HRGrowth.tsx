import React from 'react';
import { ZCard, ZKpi, ZBadge, ZEmpty } from '../../design-system/components';
import styles from './HRGrowth.module.css';

const MOCK_SKILLS = [
  { name: '基础服务', level: 'certified' },
  { name: '收银操作', level: 'certified' },
  { name: '食品安全', level: 'learning' },
];

const MOCK_TIMELINE = [
  { date: '2025-12-01', event: '入职', badge: 'success' as const },
  { date: '2026-03-01', event: '转正', badge: 'success' as const },
  { date: '2026-06-01', event: '晋升目标', badge: 'info' as const },
];

export default function HRGrowth() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>我的成长</span>
      </div>

      {/* 技能图谱 */}
      <ZCard title="已认证技能">
        <div className={styles.skillList}>
          {MOCK_SKILLS.map((s, i) => (
            <div key={i} className={styles.skillItem}>
              <ZBadge type={s.level === 'certified' ? 'success' : 'warning'} text={s.name} />
              <span className={styles.skillLevel}>
                {s.level === 'certified' ? '已认证' : '学习中'}
              </span>
            </div>
          ))}
        </div>
      </ZCard>

      {/* 成长时间线 */}
      <ZCard title="成长时间线">
        <div className={styles.timeline}>
          {MOCK_TIMELINE.map((t, i) => (
            <div key={i} className={styles.timelineItem}>
              <div className={`${styles.timelineDot} ${t.badge === 'success' ? styles.dotDone : styles.dotFuture}`} />
              <div className={styles.timelineContent}>
                <span className={styles.timelineDate}>{t.date}</span>
                <ZBadge type={t.badge} text={t.event} />
              </div>
            </div>
          ))}
        </div>
      </ZCard>

      {/* AI推荐 */}
      <ZCard title="AI成长建议" extra={<ZBadge type="info" text="AI" />}>
        <div className={styles.aiCard}>
          <p className={styles.aiText}>
            建议下一步掌握「<strong>拉面技术</strong>」，预期增收
          </p>
          <ZKpi value="¥300" label="预期月增收" unit="/月" />
        </div>
      </ZCard>

      {/* ¥贡献值 */}
      <ZCard title="技能贡献值">
        <div className={styles.contribution}>
          <ZKpi value="¥1,200" label="当前技能月贡献" unit="/月" />
        </div>
      </ZCard>
    </div>
  );
}
