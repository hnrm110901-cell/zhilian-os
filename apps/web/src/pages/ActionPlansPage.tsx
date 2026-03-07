import React, { useState, useCallback, useEffect } from 'react';
import { Drawer, Modal, Form, Input, Select as AntSelect, message } from 'antd';
import {
  ReloadOutlined, EyeOutlined, CheckCircleOutlined, ArrowUpOutlined,
} from '@ant-design/icons';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable, ZInput, ZEmpty,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import styles from './ActionPlansPage.module.css';
import dayjs from 'dayjs';

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface ActionPlan {
  plan_id: string;
  store_id: string;
  report_date: string;
  dimension: string;
  severity: string;
  root_cause: string;
  confidence: number;
  dispatch_status: string;
  dispatched_at: string | null;
  dispatched_actions: string[] | null;
  outcome: string;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
  // 详情专属
  wechat_action_id?: string;
  task_id?: string;
  outcome_note?: string;
  kpi_delta?: Record<string, { before: number; after: number; delta: number }>;
}

interface PlatformStats {
  days: number;
  total_plans: number;
  dispatch_dist: Record<string, number>;
  outcome_dist: Record<string, number>;
  severity_dist: Record<string, number>;
  resolution_rate: number;
}

// ── 字典 ──────────────────────────────────────────────────────────────────────

const SEVERITY_BADGE: Record<string, 'critical' | 'warning' | 'info' | 'success' | 'default'> = {
  P1: 'critical', P2: 'warning', P3: 'info',
};
const OUTCOME_BADGE: Record<string, 'success' | 'warning' | 'critical' | 'info' | 'default'> = {
  resolved:  'success',
  escalated: 'warning',
  expired:   'critical',
  no_effect: 'default',
  cancelled: 'default',
  pending:   'info',
};
const DISPATCH_BADGE: Record<string, 'success' | 'warning' | 'critical' | 'info' | 'default'> = {
  dispatched: 'success',
  partial:    'warning',
  failed:     'critical',
  pending:    'info',
  skipped:    'default',
};

const OUTCOME_LABEL: Record<string, string> = {
  resolved:  '已解决', escalated: '已升级',
  expired:   '已超时', no_effect: '无效果',
  cancelled: '已取消', pending:   '待处理',
};
const DISPATCH_LABEL: Record<string, string> = {
  dispatched: '已派发', partial: '部分派发',
  failed: '失败', pending: '待派发', skipped: '已跳过',
};
const DIMENSION_LABEL: Record<string, string> = {
  waste: '损耗', efficiency: '效率', quality: '质量',
  cost: '成本', inventory: '库存', cross_store: '跨店',
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const ActionPlansPage: React.FC = () => {
  const storeId = localStorage.getItem('store_id') || 'STORE001';

  // 列表状态
  const [plans, setPlans]       = useState<ActionPlan[]>([]);
  const [loading, setLoading]   = useState(false);
  const [severity, setSeverity] = useState<string>('');
  const [outcome, setOutcome]   = useState<string>('');
  const [days, setDays]         = useState<number>(30);

  // 平台统计
  const [stats, setStats]       = useState<PlatformStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // 详情 Drawer
  const [detail, setDetail]     = useState<ActionPlan | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 结果登记 Modal
  const [outcomeModal, setOutcomeModal] = useState(false);
  const [targetPlan, setTargetPlan]     = useState<ActionPlan | null>(null);
  const [outcomeForm] = Form.useForm();
  const [submitting, setSubmitting]     = useState(false);

  // ── 数据加载 ───────────────────────────────────────────────────────────────

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { days };
      if (severity) params.severity = severity;
      if (outcome)  params.outcome  = outcome;
      const resp = await apiClient.get(`/api/v1/l5/stores/${storeId}/action-plans`, { params });
      setPlans(resp.data ?? []);
    } catch (e) {
      handleApiError(e, '加载行动计划失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, days, severity, outcome]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const resp = await apiClient.get('/api/v1/l5/reports/platform-stats', { params: { days: 7 } });
      setStats(resp.data);
    } catch (e) {
      // 统计加载失败静默处理
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => { loadPlans(); loadStats(); }, [loadPlans, loadStats]);

  // ── 详情 ───────────────────────────────────────────────────────────────────

  const openDetail = useCallback(async (planId: string) => {
    setDetailLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/l5/action-plans/${planId}`);
      setDetail(resp.data);
    } catch (e) {
      handleApiError(e, '加载行动计划详情失败');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // ── 结果登记 ───────────────────────────────────────────────────────────────

  const submitOutcome = useCallback(async () => {
    if (!targetPlan) return;
    try {
      const values = await outcomeForm.validateFields();
      setSubmitting(true);
      await apiClient.patch(`/api/v1/l5/action-plans/${targetPlan.plan_id}/outcome`, values);
      message.success('结果已登记，感谢反馈！');
      setOutcomeModal(false);
      outcomeForm.resetFields();
      loadPlans();
    } catch (e) {
      handleApiError(e, '登记失败');
    } finally {
      setSubmitting(false);
    }
  }, [targetPlan, outcomeForm, loadPlans]);

  // ── 表格列 ─────────────────────────────────────────────────────────────────

  const columns: ZTableColumn<ActionPlan>[] = [
    {
      title: '严重程度',
      dataIndex: 'severity',
      width: 90,
      render: (v: string) => (
        <ZBadge type={SEVERITY_BADGE[v] ?? 'default'} label={v} />
      ),
    },
    {
      title: '维度',
      dataIndex: 'dimension',
      width: 80,
      render: (v: string) => DIMENSION_LABEL[v] ?? v,
    },
    {
      title: '根因',
      dataIndex: 'root_cause',
      render: (v: string) => (
        <span className={styles.ellipsis} title={v}>{v || '—'}</span>
      ),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 80,
      render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '—',
    },
    {
      title: '派发状态',
      dataIndex: 'dispatch_status',
      width: 100,
      render: (v: string) => (
        <ZBadge type={DISPATCH_BADGE[v] ?? 'default'} label={DISPATCH_LABEL[v] ?? v} />
      ),
    },
    {
      title: '处理结果',
      dataIndex: 'outcome',
      width: 90,
      render: (v: string) => (
        <ZBadge type={OUTCOME_BADGE[v] ?? 'default'} label={OUTCOME_LABEL[v] ?? v} />
      ),
    },
    {
      title: '报告日期',
      dataIndex: 'report_date',
      width: 110,
      render: (v: string) => v ?? '—',
    },
    {
      title: '操作',
      dataIndex: 'plan_id',
      width: 120,
      render: (_: string, row: ActionPlan) => (
        <div style={{ display: 'flex', gap: 6 }}>
          <ZButton
            size="sm"
            variant="ghost"
            icon={<EyeOutlined />}
            onClick={() => openDetail(row.plan_id)}
          >
            详情
          </ZButton>
          {row.outcome === 'pending' && (
            <ZButton
              size="sm"
              variant="ghost"
              icon={<CheckCircleOutlined />}
              onClick={() => { setTargetPlan(row); setOutcomeModal(true); }}
            >
              登记
            </ZButton>
          )}
        </div>
      ),
    },
  ];

  // ── KPI 卡片数据 ───────────────────────────────────────────────────────────

  const totalP1   = stats?.severity_dist?.P1 ?? 0;
  const totalP2   = stats?.severity_dist?.P2 ?? 0;
  const resolved  = stats?.outcome_dist?.resolved ?? 0;
  const pending   = stats?.outcome_dist?.pending ?? 0;
  const resRate   = stats?.resolution_rate ?? 0;

  // ── 渲染 ───────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* KPI 卡片 */}
      <div className={styles.kpiGrid}>
        {statsLoading ? (
          Array.from({ length: 5 }).map((_, i) => <ZSkeleton key={i} height={80} />)
        ) : (
          <>
            <ZKpi label="近7天总行动" value={stats?.total_plans ?? 0} />
            <ZKpi label="P1 高危" value={totalP1} status={totalP1 > 0 ? 'critical' : 'good'} />
            <ZKpi label="P2 中等" value={totalP2} status={totalP2 > 5 ? 'warning' : 'good'} />
            <ZKpi label="已解决" value={resolved} status="good" />
            <ZKpi label="解决率" value={`${resRate}%`} status={resRate >= 80 ? 'good' : 'warning'} />
          </>
        )}
      </div>

      {/* 过滤行 */}
      <ZCard style={{ marginBottom: 14 }}>
        <div className={styles.filterRow}>
          <span className={styles.filterLabel}>严重程度：</span>
          <ZSelect
            value={severity}
            onChange={v => setSeverity(v as string)}
            style={{ width: 120 }}
            options={[
              { label: '全部', value: '' },
              { label: 'P1 高危', value: 'P1' },
              { label: 'P2 中等', value: 'P2' },
              { label: 'P3 低级', value: 'P3' },
            ]}
          />
          <span className={styles.filterLabel}>处理结果：</span>
          <ZSelect
            value={outcome}
            onChange={v => setOutcome(v as string)}
            style={{ width: 130 }}
            options={[
              { label: '全部', value: '' },
              { label: '待处理', value: 'pending' },
              { label: '已解决', value: 'resolved' },
              { label: '已升级', value: 'escalated' },
              { label: '已超时', value: 'expired' },
            ]}
          />
          <span className={styles.filterLabel}>近：</span>
          <ZSelect
            value={days}
            onChange={v => setDays(v as number)}
            style={{ width: 100 }}
            options={[
              { label: '7天', value: 7 },
              { label: '30天', value: 30 },
              { label: '90天', value: 90 },
            ]}
          />
          <ZButton
            icon={<ReloadOutlined />}
            onClick={loadPlans}
            loading={loading}
          >
            刷新
          </ZButton>
        </div>
      </ZCard>

      {/* 行动计划表格 */}
      <ZCard title="行动计划列表">
        {loading ? (
          <ZSkeleton height={200} />
        ) : plans.length === 0 ? (
          <ZEmpty description="暂无行动计划" />
        ) : (
          <ZTable
            columns={columns}
            dataSource={plans}
            rowKey="plan_id"
            size="small"
          />
        )}
      </ZCard>

      {/* 详情 Drawer */}
      <Drawer
        title="行动计划详情"
        width={520}
        open={!!detail}
        onClose={() => setDetail(null)}
        destroyOnClose
      >
        {detailLoading ? (
          <ZSkeleton height={400} />
        ) : detail ? (
          <div className={styles.drawerContent}>
            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionTitle}>基本信息</div>
              <dl className={styles.descList}>
                <div className={styles.descRow}><dt>严重程度</dt><dd><ZBadge type={SEVERITY_BADGE[detail.severity] ?? 'default'} label={detail.severity} /></dd></div>
                <div className={styles.descRow}><dt>维度</dt><dd>{DIMENSION_LABEL[detail.dimension] ?? detail.dimension}</dd></div>
                <div className={styles.descRow}><dt>根因</dt><dd>{detail.root_cause || '—'}</dd></div>
                <div className={styles.descRow}><dt>置信度</dt><dd>{detail.confidence != null ? `${(detail.confidence * 100).toFixed(0)}%` : '—'}</dd></div>
                <div className={styles.descRow}><dt>报告日期</dt><dd>{detail.report_date}</dd></div>
                <div className={styles.descRow}><dt>派发时间</dt><dd>{detail.dispatched_at ? dayjs(detail.dispatched_at).format('MM-DD HH:mm') : '—'}</dd></div>
                <div className={styles.descRow}><dt>派发行动</dt><dd>{(detail.dispatched_actions ?? []).join('、') || '—'}</dd></div>
                {detail.wechat_action_id && (
                  <div className={styles.descRow}><dt>WeChat ID</dt><dd style={{ fontFamily: 'monospace', fontSize: 12 }}>{detail.wechat_action_id}</dd></div>
                )}
              </dl>
            </div>

            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionTitle}>处理结果</div>
              <dl className={styles.descList}>
                <div className={styles.descRow}><dt>结果</dt><dd><ZBadge type={OUTCOME_BADGE[detail.outcome] ?? 'default'} label={OUTCOME_LABEL[detail.outcome] ?? detail.outcome} /></dd></div>
                <div className={styles.descRow}><dt>处理人</dt><dd>{detail.resolved_by || '—'}</dd></div>
                <div className={styles.descRow}><dt>处理时间</dt><dd>{detail.resolved_at ? dayjs(detail.resolved_at).format('MM-DD HH:mm') : '—'}</dd></div>
                {detail.outcome_note && (
                  <div className={styles.descRow}><dt>备注</dt><dd>{detail.outcome_note}</dd></div>
                )}
              </dl>
            </div>

            {detail.kpi_delta && Object.keys(detail.kpi_delta).length > 0 && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionTitle}>KPI 改善效果</div>
                <div className={styles.kpiDelta}>
                  {Object.entries(detail.kpi_delta).map(([metric, v]) => (
                    <div key={metric} className={styles.kpiDeltaRow}>
                      <span className={styles.kpiDeltaName}>{metric}</span>
                      <span>{v.before} → {v.after}</span>
                      <span className={v.delta < 0 ? styles.kpiDeltaImprove : styles.kpiDeltaWorsen}>
                        ({v.delta > 0 ? '+' : ''}{v.delta.toFixed(3)})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </Drawer>

      {/* 结果登记 Modal */}
      <Modal
        title="登记处理结果"
        open={outcomeModal}
        onOk={submitOutcome}
        onCancel={() => { setOutcomeModal(false); outcomeForm.resetFields(); }}
        confirmLoading={submitting}
        okText="提交"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={outcomeForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item
            name="outcome"
            label="处理结果"
            rules={[{ required: true, message: '请选择结果' }]}
          >
            <AntSelect>
              <AntSelect.Option value="resolved">已解决</AntSelect.Option>
              <AntSelect.Option value="escalated">已升级</AntSelect.Option>
              <AntSelect.Option value="no_effect">无效果</AntSelect.Option>
              <AntSelect.Option value="cancelled">已取消</AntSelect.Option>
            </AntSelect>
          </Form.Item>
          <Form.Item
            name="resolved_by"
            label="处理人"
            rules={[{ required: true, message: '请填写处理人' }]}
          >
            <Input placeholder="员工姓名或工号" />
          </Form.Item>
          <Form.Item name="outcome_note" label="备注说明">
            <Input.TextArea rows={3} placeholder="可选填写改善措施或说明" />
          </Form.Item>
        </Form>
      </Modal>

    </div>
  );
};

export default ActionPlansPage;
