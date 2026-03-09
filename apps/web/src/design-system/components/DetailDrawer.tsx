/**
 * DetailDrawer — 侧边详情抽屉（设计系统通用组件）
 *
 * 特性：
 * - mask={false}，不遮挡主内容，右侧滑入
 * - 支持状态 Badge、操作按钮、多 Section 内容
 * - 标准化布局：头部 → 指标行 → 内容区（灵活 sections）→ 底部操作
 *
 * 用法示例：
 * <DetailDrawer
 *   open={!!selected}
 *   title="任务详情"
 *   status={{ label: '待处理', type: 'warning' }}
 *   metrics={[{ label: '预期节省', value: '¥320' }, { label: '置信度', value: '82%' }]}
 *   sections={[
 *     { title: '建议行动', content: <p>{task.action}</p> },
 *     { title: '相关数据', content: <InfoList items={...} /> },
 *   ]}
 *   actions={[
 *     { label: '派发执行', type: 'primary', onClick: handleDispatch },
 *     { label: '忽略',    type: 'default', onClick: handleIgnore  },
 *   ]}
 *   onClose={() => setSelected(null)}
 * />
 */
import React from 'react';
import { Drawer, Space } from 'antd';
import ZBadge from './ZBadge';
import ZButton from './ZButton';
import styles from './DetailDrawer.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DrawerMetric {
  label: string;
  value: React.ReactNode;
  /** 值颜色（可选），如 '#f5222d' */
  valueColor?: string;
}

export interface DrawerSection {
  title?: string;
  content: React.ReactNode;
  /** 是否折叠初始化（默认展开） */
  collapsible?: boolean;
}

export interface DrawerAction {
  key?: string;
  label: string;
  type?: 'primary' | 'default' | 'danger' | 'ghost';
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
}

export interface DetailDrawerProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  /** 副标题（如 ID 或时间） */
  subtitle?: React.ReactNode;
  /** 状态标签 */
  status?: {
    label: string;
    type: 'critical' | 'warning' | 'info' | 'success' | 'default';
  };
  /** 头部右侧额外内容 */
  extra?: React.ReactNode;
  /** 指标行（横排数字卡片），建议 2–4 个 */
  metrics?: DrawerMetric[];
  /** 内容区 sections */
  sections?: DrawerSection[];
  /** 直接传 children（与 sections 二选一） */
  children?: React.ReactNode;
  /** 底部操作按钮 */
  actions?: DrawerAction[];
  width?: number;
}

// ── Component ─────────────────────────────────────────────────────────────────

const DetailDrawer: React.FC<DetailDrawerProps> = ({
  open,
  onClose,
  title,
  subtitle,
  status,
  extra,
  metrics = [],
  sections = [],
  children,
  actions = [],
  width = 480,
}) => {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={width}
      mask={false}
      closable={true}
      style={{ boxShadow: '-4px 0 16px rgba(0,0,0,0.08)' }}
      styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: '100%' } }}
      title={
        <div className={styles.drawerHeader}>
          <div className={styles.titleRow}>
            <span className={styles.title}>{title}</span>
            {status && (
              <ZBadge type={status.type} label={status.label} />
            )}
          </div>
          {subtitle && (
            <div className={styles.subtitle}>{subtitle}</div>
          )}
          {extra && (
            <div className={styles.extra}>{extra}</div>
          )}
        </div>
      }
    >
      <div className={styles.body}>
        {/* ── 指标行 ──────────────────────────────────────────────── */}
        {metrics.length > 0 && (
          <div className={styles.metricsRow}>
            {metrics.map((m, i) => (
              <div key={i} className={styles.metricCell}>
                <div
                  className={styles.metricValue}
                  style={m.valueColor ? { color: m.valueColor } : undefined}
                >
                  {m.value}
                </div>
                <div className={styles.metricLabel}>{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* ── Sections / Children ─────────────────────────────────── */}
        <div className={styles.scrollArea}>
          {children ?? sections.map((s, i) => (
            <div key={i} className={styles.section}>
              {s.title && <div className={styles.sectionTitle}>{s.title}</div>}
              <div className={styles.sectionContent}>{s.content}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 底部操作区 ────────────────────────────────────────────── */}
      {actions.length > 0 && (
        <div className={styles.footer}>
          <Space size={8} style={{ width: '100%', justifyContent: 'flex-end' }}>
            {actions.map((a, i) => (
              <ZButton
                key={a.key ?? i}
                variant={a.type === 'primary' ? 'primary' : a.type === 'danger' ? 'danger' : 'secondary'}
                onClick={a.onClick}
                disabled={a.disabled}
                loading={a.loading}
                size="md"
              >
                {a.label}
              </ZButton>
            ))}
          </Space>
        </div>
      )}
    </Drawer>
  );
};

export default DetailDrawer;
