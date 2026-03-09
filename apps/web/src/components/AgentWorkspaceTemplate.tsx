/**
 * AgentWorkspaceTemplate — Agent 工作台页面模板（Phase 3）
 *
 * 统一所有 Agent 工作台页面的壳层：
 *   - 页头：Agent 名称 + 图标 + 描述 + 状态徽章 + 刷新按钮 + 可选操作区
 *   - KPI 条：最多 6 个指标卡片，骨架屏降级
 *   - Tab 内容区：Ant Design Tabs + 可选右侧固定面板
 *   - 数据加载/错误状态统一处理
 *
 * 用法：
 * <AgentWorkspaceTemplate
 *   agentName="能耗 Agent"
 *   agentIcon="⚡"
 *   agentColor="#faad14"
 *   description="实时监控能耗异常，智能生成节能任务"
 *   status="running"
 *   kpis={[...]}
 *   tabs={[...]}
 *   loading={loading}
 *   onRefresh={loadAll}
 *   headerExtra={<Button>...</Button>}
 * />
 */
import React from 'react';
import { Tabs, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { ZBadge, ZButton, ZSkeleton } from '../design-system/components';
import styles from './AgentWorkspaceTemplate.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export type AgentStatus = 'running' | 'warning' | 'idle' | 'error';

export interface AgentKpi {
  label: string;
  value: string | number;
  /** 单位，显示在值后面 */
  unit?: string;
  /** 趋势文字或提示，显示在值下方 */
  sub?: string;
  /** 值颜色（默认继承） */
  valueColor?: string;
  /** 图标元素 */
  icon?: React.ReactNode;
}

export interface AgentTab {
  key: string;
  label: string;
  /** 未读/数量 badge */
  count?: number;
  children: React.ReactNode;
}

export interface AgentWorkspaceTemplateProps {
  agentName: string;
  /** emoji 或 ReactNode */
  agentIcon?: React.ReactNode;
  /** 主题色，用于页头图标背景 */
  agentColor?: string;
  description?: string;
  status?: AgentStatus;
  /** KPI 指标卡数组（最多 6 个） */
  kpis?: AgentKpi[];
  /** Tab 内容定义 */
  tabs?: AgentTab[];
  /** 默认激活的 tab key */
  defaultTab?: string;
  loading?: boolean;
  onRefresh?: () => void;
  /** 页头右侧额外操作区 */
  headerExtra?: React.ReactNode;
  /** 是否显示 KPI 骨架屏 */
  kpiLoading?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<AgentStatus, { label: string; type: 'success' | 'warning' | 'default' | 'critical' }> = {
  running: { label: '运行中', type: 'success'  },
  warning: { label: '需关注', type: 'warning'  },
  idle:    { label: '待机',   type: 'default'  },
  error:   { label: '异常',   type: 'critical' },
};

// ── Component ─────────────────────────────────────────────────────────────────

const AgentWorkspaceTemplate: React.FC<AgentWorkspaceTemplateProps> = ({
  agentName,
  agentIcon,
  agentColor = '#1677ff',
  description,
  status = 'idle',
  kpis = [],
  tabs = [],
  defaultTab,
  loading = false,
  onRefresh,
  headerExtra,
  kpiLoading,
  className,
  style,
}) => {
  const statusCfg = STATUS_CONFIG[status];
  const isKpiLoading = kpiLoading ?? loading;

  return (
    <div className={`${styles.root} ${className ?? ''}`} style={style}>
      {/* ── Page header ──────────────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          {agentIcon && (
            <div
              className={styles.agentIcon}
              style={{ background: `${agentColor}18`, color: agentColor }}
            >
              {agentIcon}
            </div>
          )}
          <div className={styles.headerMeta}>
            <div className={styles.titleRow}>
              <span className={styles.agentName}>{agentName}</span>
              <ZBadge type={statusCfg.type}>{statusCfg.label}</ZBadge>
            </div>
            {description && (
              <p className={styles.description}>{description}</p>
            )}
          </div>
        </div>
        <div className={styles.headerRight}>
          {headerExtra}
          {onRefresh && (
            <ZButton
              size="small"
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={onRefresh}
            >
              刷新
            </ZButton>
          )}
        </div>
      </div>

      {/* ── KPI strip ────────────────────────────────────────────────── */}
      {kpis.length > 0 && (
        <div className={styles.kpiStrip}>
          {isKpiLoading
            ? Array.from({ length: Math.min(kpis.length || 4, 6) }).map((_, i) => (
                <div key={i} className={styles.kpiCard}>
                  <ZSkeleton active rows={2} />
                </div>
              ))
            : kpis.slice(0, 6).map((kpi, i) => (
                <div key={i} className={styles.kpiCard}>
                  <div className={styles.kpiTop}>
                    {kpi.icon && (
                      <span className={styles.kpiIcon}>{kpi.icon}</span>
                    )}
                    <span className={styles.kpiLabel}>{kpi.label}</span>
                  </div>
                  <div
                    className={styles.kpiValue}
                    style={{ color: kpi.valueColor }}
                  >
                    {kpi.value}
                    {kpi.unit && (
                      <span className={styles.kpiUnit}>{kpi.unit}</span>
                    )}
                  </div>
                  {kpi.sub && (
                    <div className={styles.kpiSub}>{kpi.sub}</div>
                  )}
                </div>
              ))
          }
        </div>
      )}

      {/* ── Tab content ──────────────────────────────────────────────── */}
      {tabs.length > 0 && (
        <div className={styles.tabsWrapper}>
          <Spin spinning={loading && kpis.length === 0}>
            <Tabs
              defaultActiveKey={defaultTab ?? tabs[0]?.key}
              size="small"
              items={tabs.map(t => ({
                key:      t.key,
                label: (
                  <span>
                    {t.label}
                    {t.count != null && t.count > 0 && (
                      <span className={styles.tabCount}>{t.count}</span>
                    )}
                  </span>
                ),
                children: t.children,
              }))}
            />
          </Spin>
        </div>
      )}
    </div>
  );
};

export default AgentWorkspaceTemplate;
