import React from 'react';
import { ZTag, ZButton, ZEmpty, ZSkeleton } from '../design-system/components';
import styles from './MemberProfileCard.module.css';

/** BFF /api/v1/bff/member-profile/{store_id}/{phone} 响应类型 */
export interface MemberProfile {
  consumer_id: string;
  identity: {
    name: string;
    phone: string;
    tags: string[];
    lifecycle_stage: string;
  } | null;
  preferences: {
    favorite_dishes: { name: string; count: number }[];
    dietary_restrictions: string[];
    preferred_seating: string | null;
  } | null;
  assets: {
    level: string;
    balance_fen: number;
    balance_display: string;
    points: number;
    available_coupons: { id: string; name: string; expires: string }[];
  } | null;
  milestones: {
    birthday: string | null;
    birthday_upcoming: boolean;
    last_visit: string | null;
    total_visits: number;
    member_since: string | null;
  } | null;
  ai_script: string | null;
}

interface MemberProfileCardProps {
  profile: MemberProfile | null;
  loading?: boolean;
  compact?: boolean;
  onIssueCoupon?: (consumerId: string) => void;
}

export default function MemberProfileCard({
  profile,
  loading = false,
  compact = false,
  onIssueCoupon,
}: MemberProfileCardProps) {
  if (loading) {
    return <ZSkeleton rows={compact ? 3 : 6} />;
  }
  if (!profile || !profile.identity) {
    return <ZEmpty title="未找到会员信息" description="请确认手机号是否正确" />;
  }

  const { identity, preferences, assets, milestones, ai_script } = profile;

  return (
    <div className={compact ? styles.cardCompact : styles.card}>
      {/* 身份区 */}
      <div className={styles.header}>
        <div className={styles.avatar}>{identity.name.charAt(0)}</div>
        <div className={styles.info}>
          <div className={styles.name}>{identity.name}</div>
          <div className={styles.tags}>
            {assets?.level && <ZTag variant="mint">{assets.level}</ZTag>}
            <ZTag>{identity.lifecycle_stage}</ZTag>
            {identity.tags.map((t) => <ZTag key={t}>{t}</ZTag>)}
          </div>
        </div>
      </div>

      {/* 资产区 */}
      {assets && (
        <div className={styles.kpiRow}>
          <div className={styles.kpi}>
            <span className={styles.kpiValue}>{assets.balance_display}</span>
            <span className={styles.kpiLabel}>余额</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiValue}>{assets.points?.toLocaleString()}</span>
            <span className={styles.kpiLabel}>积分</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiValue} style={{ color: 'var(--accent)' }}>
              {assets.available_coupons?.length || 0}
            </span>
            <span className={styles.kpiLabel}>可用券</span>
          </div>
        </div>
      )}

      {/* 偏好标签 */}
      {!compact && preferences && (
        <div className={styles.section}>
          {milestones?.birthday_upcoming && (
            <ZTag variant="warn">本周生日</ZTag>
          )}
          {preferences.favorite_dishes?.slice(0, 3).map((d) => (
            <ZTag key={d.name}>❤️ {d.name}</ZTag>
          ))}
          {preferences.dietary_restrictions?.map((r) => (
            <ZTag key={r} variant="danger">⚠️ {r}</ZTag>
          ))}
        </div>
      )}

      {/* AI 话术 */}
      {!compact && ai_script && (
        <div className={styles.aiScript}>
          <div className={styles.aiLabel}>AI 服务话术</div>
          <div className={styles.aiText}>{ai_script}</div>
        </div>
      )}

      {/* 操作按钮 */}
      {onIssueCoupon && (
        <div className={styles.actions}>
          <ZButton
            variant="primary"
            onClick={() => onIssueCoupon(profile.consumer_id)}
          >
            发券
          </ZButton>
        </div>
      )}
    </div>
  );
}
