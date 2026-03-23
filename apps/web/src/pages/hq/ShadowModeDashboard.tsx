/**
 * Shadow Mode 仪表盘 — 影子模式切换监控
 * 路由：/hq/shadow-mode
 * 数据：GET /api/v1/shadow/bff/hq/{brand_id}
 *
 * 展示：
 * - 顶部 KPI：活跃影子会话数、平均一致性、canary+ 模块数、累计通过天数
 * - 模块切换状态表：每个模块的阶段、通过天数、健康门禁、canary 百分比、操作
 * - 影子会话列表：门店名、来源系统、一致性率、状态
 */
import React, { useState, useEffect, useCallback } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZEmpty } from '../../design-system/components';
import { message } from 'antd';
import apiClient from '../../services/api';
import styles from './ShadowModeDashboard.module.css';

// ── 类型定义 ──────────────────────────────────────────────────────────────────

type Phase = 'shadow' | 'canary' | 'primary' | 'sole';

interface ModuleCutover {
  module_name: string;
  module_label: string;
  phase: Phase;
  pass_days: number;
  health_gate: 'pass' | 'fail' | 'pending';
  canary_pct: number;
}

interface ShadowSession {
  session_id: string;
  store_name: string;
  source_system: string;
  consistency_rate: number;
  status: string;
}

interface ShadowBffData {
  active_sessions: number;
  avg_consistency_rate: number;
  modules_in_canary_plus: number;
  total_pass_days: number;
  modules: ModuleCutover[];
  sessions: ShadowSession[];
}

// ── 阶段配置 ──────────────────────────────────────────────────────────────────

const PHASE_CONFIG: Record<Phase, { label: string; className: string }> = {
  shadow:  { label: '影子',   className: styles.phaseShadow },
  canary:  { label: '灰度',   className: styles.phaseCanary },
  primary: { label: '主切',   className: styles.phasePrimary },
  sole:    { label: '独占',   className: styles.phaseSole },
};

const HEALTH_GATE_LABEL: Record<string, string> = {
  pass: '通过',
  fail: '未通过',
  pending: '检测中',
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function ShadowModeDashboard() {
  const [data, setData] = useState<ShadowBffData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const brandId = 'current_brand'; // 从全局状态获取

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/shadow/bff/hq/${brandId}`);
      setData(resp.data);
    } catch {
      message.error('加载影子模式数据失败');
    } finally {
      setLoading(false);
    }
  }, [brandId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 推进阶段
  const handleAdvance = useCallback(async (moduleName: string) => {
    setActionLoading(`advance-${moduleName}`);
    try {
      await apiClient.post(`/api/v1/shadow/modules/${moduleName}/advance`, {
        brand_id: brandId,
      });
      message.success('阶段推进成功');
      fetchData();
    } catch {
      message.error('阶段推进失败，请检查健康门禁状态');
    } finally {
      setActionLoading(null);
    }
  }, [brandId, fetchData]);

  // 回滚阶段
  const handleRollback = useCallback(async (moduleName: string) => {
    setActionLoading(`rollback-${moduleName}`);
    try {
      await apiClient.post(`/api/v1/shadow/modules/${moduleName}/rollback`, {
        brand_id: brandId,
      });
      message.success('阶段回滚成功');
      fetchData();
    } catch {
      message.error('阶段回滚失败');
    } finally {
      setActionLoading(null);
    }
  }, [brandId, fetchData]);

  // 阶段徽章
  const renderPhaseBadge = (phase: Phase) => {
    const config = PHASE_CONFIG[phase];
    return (
      <span className={`${styles.phaseBadge} ${config.className}`}>
        {config.label}
      </span>
    );
  };

  // 健康门禁文字
  const renderGateStatus = (gate: string) => {
    const cls = gate === 'pass'
      ? styles.gatePass
      : gate === 'fail'
        ? styles.gateFail
        : styles.gatePending;
    return <span className={cls}>{HEALTH_GATE_LABEL[gate] || gate}</span>;
  };

  // 一致性率颜色
  const rateClass = (rate: number) =>
    rate >= 95 ? styles.sessionRateGood : styles.sessionRateWarn;

  // ── 加载态 ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingWrap}>
          <ZEmpty description="正在加载影子模式数据..." />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingWrap}>
          <ZEmpty description="暂无影子模式数据" />
        </div>
      </div>
    );
  }

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <div className={styles.title}>影子模式监控</div>
        <div className={styles.subtitle}>
          监控各模块从影子模式到独占模式的切换进度，确保数据一致性达标后再推进
        </div>
      </div>

      {/* 顶部 KPI 行 */}
      <div className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <ZKpi
            label="活跃影子会话"
            value={data.active_sessions}
            unit="个"
          />
        </div>
        <div className={styles.kpiCard}>
          <ZKpi
            label="平均一致性"
            value={data.avg_consistency_rate.toFixed(1)}
            unit="%"
          />
        </div>
        <div className={styles.kpiCard}>
          <ZKpi
            label="灰度及以上模块"
            value={data.modules_in_canary_plus}
            unit="个"
          />
        </div>
        <div className={styles.kpiCard}>
          <ZKpi
            label="累计通过天数"
            value={data.total_pass_days}
            unit="天"
          />
        </div>
      </div>

      {/* 模块切换状态表 */}
      <ZCard
        title="模块切换状态"
        extra={<ZButton onClick={fetchData}>刷新</ZButton>}
      >
        {data.modules.length === 0 ? (
          <ZEmpty description="暂无模块切换记录" />
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>模块</th>
                  <th>当前阶段</th>
                  <th>通过天数</th>
                  <th>健康门禁</th>
                  <th>灰度比例</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.modules.map((mod) => (
                  <tr key={mod.module_name}>
                    <td>{mod.module_label}</td>
                    <td>{renderPhaseBadge(mod.phase)}</td>
                    <td>
                      <span className={styles.passDays}>{mod.pass_days}天</span>
                    </td>
                    <td>{renderGateStatus(mod.health_gate)}</td>
                    <td>
                      <span className={styles.canaryPct}>{mod.canary_pct}%</span>
                    </td>
                    <td>
                      <div className={styles.tableActions}>
                        {mod.phase !== 'sole' && (
                          <ZButton
                            type="primary"
                            size="small"
                            disabled={mod.health_gate !== 'pass'}
                            loading={actionLoading === `advance-${mod.module_name}`}
                            onClick={() => handleAdvance(mod.module_name)}
                          >
                            推进
                          </ZButton>
                        )}
                        {mod.phase !== 'shadow' && (
                          <ZButton
                            size="small"
                            loading={actionLoading === `rollback-${mod.module_name}`}
                            onClick={() => handleRollback(mod.module_name)}
                          >
                            回滚
                          </ZButton>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ZCard>

      {/* 一致性时间线图表区域 */}
      <ZCard title="一致性趋势">
        <div className={styles.chartArea}>
          <div className={styles.chartPlaceholder}>
            一致性时间线图表（接入后端数据后渲染 ECharts 趋势图）
          </div>
        </div>
      </ZCard>

      {/* 影子会话列表 */}
      <ZCard title="影子会话列表">
        {data.sessions.length === 0 ? (
          <ZEmpty description="暂无活跃的影子会话" />
        ) : (
          <div className={styles.sessionList}>
            {data.sessions.map((session) => (
              <div key={session.session_id} className={styles.sessionItem}>
                <div className={styles.sessionStore}>
                  <div className={styles.sessionStoreName}>{session.store_name}</div>
                  <div className={styles.sessionSource}>
                    来源：{session.source_system}
                  </div>
                </div>
                <ZBadge
                  type={session.status === 'active' ? 'success' : 'default'}
                  text={session.status === 'active' ? '运行中' : '已暂停'}
                />
                <div className={`${styles.sessionRate} ${rateClass(session.consistency_rate)}`}>
                  {session.consistency_rate.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        )}
      </ZCard>
    </div>
  );
}
