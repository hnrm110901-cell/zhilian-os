/**
 * AISuggestionCard — 智能建议卡（设计系统组件）
 *
 * 统一所有 AI 决策/建议的展示格式：
 *   - 排名 badge + 来源 tag
 *   - 标题 + 建议行动
 *   - ¥ 节省 / 执行难度 / 决策窗口 三标签
 *   - AI 置信度进度条
 *   - 可选：派发/确认操作按钮
 *
 * 用法：
 * <AISuggestionCard
 *   rank={1}
 *   title="关闭空调 Zone-B"
 *   action="现在关闭 Zone-B 空调，预计节省电费"
 *   savingYuan={320}
 *   confidencePct={85}
 *   difficulty="easy"
 *   windowLabel="今日 16:00 前"
 *   source="energy"
 *   onDispatch={() => handleDispatch(decision)}
 * />
 */
import React from 'react';
import styles from './AISuggestionCard.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export type Difficulty = 'easy' | 'medium' | 'hard';

export interface AISuggestionCardProps {
  rank?: number;
  title: string;
  action?: string;
  savingYuan?: number;
  netBenefitYuan?: number;
  confidencePct?: number;
  difficulty?: Difficulty;
  windowLabel?: string;
  source?: string;
  /** 卡片左侧彩色条颜色（默认按 rank 推断） */
  accentColor?: string;
  /** 派发/执行按钮文案（不传则不显示按钮） */
  dispatchLabel?: string;
  onDispatch?: () => void;
  dispatchLoading?: boolean;
  style?: React.CSSProperties;
  className?: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const RANK_COLORS = ['#ff4d4f', '#fa8c16', '#1890ff', '#52c41a', '#722ed1'];

const DIFFICULTY_MAP: Record<Difficulty, { label: string; cls: string }> = {
  easy:   { label: '容易执行', cls: 'diffEasy'   },
  medium: { label: '中等难度', cls: 'diffMedium' },
  hard:   { label: '较难执行', cls: 'diffHard'   },
};

const SOURCE_LABELS: Record<string, string> = {
  energy:    '能耗',
  inventory: '库存',
  food_cost: '成本',
  waste:     '损耗',
  schedule:  '排班',
  service:   '服务',
  marketing: '营销',
};

// ── Component ─────────────────────────────────────────────────────────────────

const AISuggestionCard: React.FC<AISuggestionCardProps> = ({
  rank,
  title,
  action,
  savingYuan,
  netBenefitYuan,
  confidencePct,
  difficulty,
  windowLabel,
  source,
  accentColor,
  dispatchLabel,
  onDispatch,
  dispatchLoading,
  style,
  className,
}) => {
  const color  = accentColor ?? (rank != null ? RANK_COLORS[(rank - 1) % RANK_COLORS.length] : '#1890ff');
  const diff   = difficulty ? DIFFICULTY_MAP[difficulty] : null;
  const saving = savingYuan ?? netBenefitYuan;

  const confColor = confidencePct == null ? '#d9d9d9'
    : confidencePct > 75 ? '#52c41a'
    : confidencePct > 50 ? '#faad14' : '#ff4d4f';

  return (
    <div
      className={`${styles.card} ${className ?? ''}`}
      style={{ borderLeftColor: color, ...style }}
    >
      {/* ── Header row ─────────────────────────────────── */}
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          {rank != null && (
            <span className={styles.rankBadge} style={{ background: color }}>
              #{rank}
            </span>
          )}
          <span className={styles.title}>{title}</span>
        </div>
        {source && (
          <span className={styles.sourceTag}>
            {SOURCE_LABELS[source] ?? source}
          </span>
        )}
      </div>

      {/* ── Action text ─────────────────────────────────── */}
      {action && (
        <p className={styles.action}>{action}</p>
      )}

      {/* ── Tag row ─────────────────────────────────────── */}
      {(saving != null || windowLabel || diff) && (
        <div className={styles.tagRow}>
          {saving != null && (
            <span className={`${styles.tag} ${styles.tagGreen}`}>
              节省 ¥{saving.toFixed(0)}
            </span>
          )}
          {windowLabel && (
            <span className={`${styles.tag} ${styles.tagOrange}`}>
              {windowLabel}
            </span>
          )}
          {diff && (
            <span className={`${styles.tag} ${styles[diff.cls]}`}>
              {diff.label}
            </span>
          )}
        </div>
      )}

      {/* ── Confidence bar ──────────────────────────────── */}
      {confidencePct != null && (
        <div className={styles.confRow}>
          <span className={styles.confLabel}>AI 置信度</span>
          <div className={styles.confTrack}>
            <div
              className={styles.confFill}
              style={{ width: `${confidencePct}%`, background: confColor }}
            />
          </div>
          <span className={styles.confPct} style={{ color: confColor }}>
            {Math.round(confidencePct)}%
          </span>
        </div>
      )}

      {/* ── Dispatch button ──────────────────────────────── */}
      {dispatchLabel && onDispatch && (
        <button
          className={styles.dispatchBtn}
          onClick={onDispatch}
          disabled={dispatchLoading}
          style={{ opacity: dispatchLoading ? 0.6 : 1 }}
        >
          {dispatchLoading ? '处理中…' : dispatchLabel}
        </button>
      )}
    </div>
  );
};

export default AISuggestionCard;
