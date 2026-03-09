import React, { useCallback, useEffect, useState } from 'react';
import {
  UserAddOutlined,
  ReloadOutlined,
  TeamOutlined,
  RiseOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZSelect, DetailDrawer } from '../design-system/components';
import css from './CrmHubPage.module.css';

// ── Types ───────────────────────────────────────────────────────────────────

interface MemberStats {
  total_members: number;
  new_this_month: number;
  repurchase_rate: number;   // 0-100
  dormant_count: number;
  stored_value_yuan: number;
  reach_rate: number;        // 0-100, 私域触达率
}

interface RfmSegment {
  segment: string;   // new / repurchase / dormant / high_value / churn_risk
  label: string;
  count: number;
  pct: number;       // 0-100
}

interface GrowthSignal {
  signal_id: string;
  signal_type: string;
  title: string;
  description: string;
  urgency: 'high' | 'medium' | 'low';
  created_at: string;
  recommended_action?: string;
}

interface ChurnUser {
  customer_id: string;
  name: string;
  days_since_visit: number;
  risk_level: 'high' | 'medium';
}

// ── Segment meta ─────────────────────────────────────────────────────────────

const SEGMENT_META: Record<string, { color: string; label: string; order: number }> = {
  new:        { color: '#52c41a', label: '新客',     order: 0 },
  repurchase: { color: '#1890ff', label: '复购客',   order: 1 },
  high_value: { color: '#722ed1', label: '高价值客', order: 2 },
  dormant:    { color: '#fa8c16', label: '沉睡客',   order: 3 },
  churn_risk: { color: '#f5222d', label: '流失预警', order: 4 },
};

const SIGNAL_TYPE_LABEL: Record<string, string> = {
  dormant_reactivation: '唤醒沉睡',
  repurchase_prompt:    '复购促进',
  high_value_care:      '高价值关怀',
  new_member_welcome:   '新客欢迎',
  birthday_care:        '生日关怀',
  churn_prevention:     '流失挽回',
};

const SIGNAL_URGENCY_TYPE: Record<string, 'critical' | 'warning' | 'default'> = {
  high:   'critical',
  medium: 'warning',
  low:    'default',
};

// ── Quick nav ─────────────────────────────────────────────────────────────────

const QUICK_NAV = [
  { icon: '👥', label: '会员中心',   route: '/members' },
  { icon: '🔍', label: '客户360',   route: '/customer360' },
  { icon: '📱', label: '私域运营',   route: '/private-domain' },
  { icon: '📊', label: '渠道毛利',   route: '/channel-profit' },
  { icon: '💡', label: '推荐引擎',   route: '/recommendations' },
  { icon: '💬', label: '企微触发器', route: '/wechat-triggers' },
];

// ── Demo fallback data ────────────────────────────────────────────────────────

const DEMO_STATS: MemberStats = {
  total_members: 8640,
  new_this_month: 312,
  repurchase_rate: 38.5,
  dormant_count: 1280,
  stored_value_yuan: 256800,
  reach_rate: 62.3,
};

const DEMO_SEGMENTS: RfmSegment[] = [
  { segment: 'new',        label: '新客',     count: 1850, pct: 21 },
  { segment: 'repurchase', label: '复购客',   count: 3920, pct: 45 },
  { segment: 'high_value', label: '高价值客', count: 640,  pct: 7  },
  { segment: 'dormant',    label: '沉睡客',   count: 1280, pct: 15 },
  { segment: 'churn_risk', label: '流失预警', count: 950,  pct: 11 },
];

const DEMO_SIGNALS: GrowthSignal[] = [
  {
    signal_id: 's1', signal_type: 'dormant_reactivation',
    title: '1280 名沉睡客可唤醒',
    description: '近 60 天未到店，建议发放"回头客专属 8 折券"，预测转化 15%。',
    urgency: 'high', created_at: new Date().toISOString(),
    recommended_action: '一键触达',
  },
  {
    signal_id: 's2', signal_type: 'repurchase_prompt',
    title: '午市低频客群 320 人',
    description: '近 30 天仅到店 1 次，适合推送"工作日午市立减 10 元"活动。',
    urgency: 'medium', created_at: new Date().toISOString(),
    recommended_action: '生成文案',
  },
  {
    signal_id: 's3', signal_type: 'birthday_care',
    title: '本周 28 名会员生日',
    description: '生日关怀券核销率历史均值 43%，建议提前 1 天发放。',
    urgency: 'medium', created_at: new Date().toISOString(),
    recommended_action: '批量发券',
  },
  {
    signal_id: 's4', signal_type: 'high_value_care',
    title: '高价值客 VIP 关怀',
    description: '12 名月消费 ≥¥800 客户近 14 天未到店，建议专属电话问候。',
    urgency: 'low', created_at: new Date().toISOString(),
    recommended_action: '查看名单',
  },
];

const DEMO_CHURN: ChurnUser[] = [
  { customer_id: 'c1', name: '张**', days_since_visit: 75, risk_level: 'high' },
  { customer_id: 'c2', name: '李**', days_since_visit: 68, risk_level: 'high' },
  { customer_id: 'c3', name: '王**', days_since_visit: 62, risk_level: 'high' },
  { customer_id: 'c4', name: '刘**', days_since_visit: 58, risk_level: 'medium' },
  { customer_id: 'c5', name: '陈**', days_since_visit: 55, risk_level: 'medium' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtNum(n: number): string {
  return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n);
}

function fmtMoney(yuan: number): string {
  return yuan >= 10000 ? `${(yuan / 10000).toFixed(1)}万` : yuan.toFixed(0);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CrmHubPage() {
  const navigate = useNavigate();

  const [stats,    setStats]    = useState<MemberStats | null>(null);
  const [segments, setSegments] = useState<RfmSegment[] | null>(null);
  const [signals,  setSignals]  = useState<GrowthSignal[] | null>(null);
  const [churn,    setChurn]    = useState<ChurnUser[] | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [storeId,  setStoreId]  = useState('S001');
  const [selectedSignal, setSelectedSignal] = useState<GrowthSignal | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const resp = await apiClient.get('/api/v1/dashboard/member-stats');
      setStats(resp.data);
    } catch {
      setStats(null);
    }
  }, []);

  const loadSegments = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/private-domain/rfm/${storeId}?days=30`);
      const raw: Array<{ segment: string; count: number }> = resp.data?.segments ?? [];
      const total = raw.reduce((s, r) => s + (r.count ?? 0), 0) || 1;
      setSegments(
        raw.map(r => ({
          segment: r.segment,
          label: SEGMENT_META[r.segment]?.label ?? r.segment,
          count: r.count ?? 0,
          pct: Math.round(((r.count ?? 0) / total) * 100),
        }))
      );
    } catch {
      setSegments(null);
    }
  }, [storeId]);

  const loadSignals = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/private-domain/signals/${storeId}?limit=6`);
      setSignals(resp.data?.signals ?? []);
    } catch {
      setSignals(null);
    }
  }, [storeId]);

  const loadChurn = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/private-domain/churn-risks/${storeId}`);
      const users = (resp.data?.users ?? []).slice(0, 5).map((u: Record<string, unknown>) => ({
        customer_id: u.customer_id as string,
        name: (u.name as string) ?? '会员',
        days_since_visit: (u.days_since_visit as number) ?? 0,
        risk_level: (u.risk_level as 'high' | 'medium') ?? 'medium',
      }));
      setChurn(users);
    } catch {
      setChurn(null);
    }
  }, [storeId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadStats(), loadSegments(), loadSignals(), loadChurn()]);
    setLoading(false);
  }, [loadStats, loadSegments, loadSignals, loadChurn]);

  useEffect(() => { refresh(); }, [refresh]);

  // Resolve display data (API or demo)
  const d = stats ?? DEMO_STATS;
  const segs: RfmSegment[] = (segments && segments.length > 0 ? segments : DEMO_SEGMENTS)
    .sort((a, b) => (SEGMENT_META[a.segment]?.order ?? 9) - (SEGMENT_META[b.segment]?.order ?? 9));
  const sigs: GrowthSignal[] = signals && signals.length > 0 ? signals : DEMO_SIGNALS;
  const churnList: ChurnUser[] = churn && churn.length > 0 ? churn : DEMO_CHURN;
  const churnTotal = stats?.dormant_count ?? DEMO_STATS.dormant_count;

  const KPI_ITEMS = [
    { icon: '👥', bg: '#e6f4ff', label: '会员总量',   value: fmtNum(d.total_members),        unit: '人' },
    { icon: '🆕', bg: '#f6ffed', label: '本月新增',   value: `+${d.new_this_month}`,         unit: '人', sub: '较上月 +8%' },
    { icon: '🔄', bg: '#fff0f6', label: '复购率',     value: `${d.repurchase_rate.toFixed(1)}`, unit: '%' },
    { icon: '😴', bg: '#fff7e6', label: '沉睡会员',   value: fmtNum(d.dormant_count),        unit: '人', warn: '需唤醒' },
    { icon: '💰', bg: '#f9f0ff', label: '储值余额',   value: `¥${fmtMoney(d.stored_value_yuan)}` },
    { icon: '📡', bg: '#e6fffb', label: '私域触达率', value: `${d.reach_rate.toFixed(1)}`,   unit: '%' },
  ];

  return (
    <div className={css.page}>
      {/* Header */}
      <div className={css.pageHeader}>
        <div className={css.pageHeaderLeft}>
          <h4 className={css.pageTitle}>会员与增长中心</h4>
          <span className={css.pageSub}>会员数据 → 触达动作闭环</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <ZSelect
            value={storeId}
            onChange={(v) => setStoreId(v as string)}
            style={{ width: 110 }}
            options={[
              { value: 'S001', label: '旗舰店' },
              { value: 'S002', label: '万达店' },
              { value: 'S003', label: '中关村店' },
            ]}
          />
          <span title="刷新数据">
            <ZButton size="sm" icon={<ReloadOutlined />} onClick={refresh} loading={loading} />
          </span>
        </div>
      </div>

      {/* KPI Strip */}
      {loading ? (
        <ZSkeleton rows={2} block style={{ marginBottom: 16 }} />
      ) : (
        <div className={css.kpiStrip}>
          {KPI_ITEMS.map(k => (
            <div key={k.label} className={css.kpiItem}>
              <div className={css.kpiIconWrap} style={{ background: k.bg }}>{k.icon}</div>
              <div className={css.kpiBody}>
                <div className={css.kpiLabel}>{k.label}</div>
                <div className={css.kpiValue}>
                  {k.value}
                  {k.unit && <span className={css.kpiUnit}>{k.unit}</span>}
                </div>
                {k.sub  && <div className={css.kpiSub}>{k.sub}</div>}
                {k.warn && <div className={css.kpiSubWarn}>{k.warn}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 3-col main */}
      <div className={css.mainGrid}>
        {/* Col 1: 人群分层 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><TeamOutlined style={{ color: '#1890ff' }} /><span>人群分层</span></div>}
          extra={<a onClick={() => navigate('/members')} style={{ fontSize: 12 }}>会员中心</a>}
        >
          <div className={css.segmentList}>
            {segs.map(seg => {
              const meta = SEGMENT_META[seg.segment];
              const color = meta?.color ?? '#8c8c8c';
              return (
                <div key={seg.segment} className={css.segmentRow}>
                  <div className={css.segmentDot} style={{ background: color }} />
                  <span className={css.segmentName}>{seg.label}</span>
                  <div className={css.segmentBarTrack}>
                    <div className={css.segmentBarFill} style={{ width: `${seg.pct}%`, background: color }} />
                  </div>
                  <span className={css.segmentCount} style={{ color }}>{fmtNum(seg.count)}</span>
                  <span className={css.segmentPct}>{seg.pct}%</span>
                </div>
              );
            })}
          </div>
          <div className={css.segmentTotal}>
            <span className={css.segmentTotalLabel}>会员总量</span>
            <span className={css.segmentTotalValue}>{fmtNum(d.total_members)} 人</span>
          </div>
        </ZCard>

        {/* Col 2: 增长信号 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><RiseOutlined style={{ color: '#52c41a' }} /><span>AI 增长信号</span></div>}
          extra={<a onClick={() => navigate('/private-domain')} style={{ fontSize: 12 }}>私域运营</a>}
        >
          <div className={css.signalList}>
            {sigs.slice(0, 4).map(sig => (
              <div key={sig.signal_id} className={css.signalCard}
                style={{ cursor: 'pointer' }}
                onClick={() => setSelectedSignal(sig)}
              >
                <div className={css.signalCardTop}>
                  <span className={css.signalTitle}>{sig.title}</span>
                  {sig.recommended_action && (
                    <span className={css.signalAction} onClick={(e) => { e.stopPropagation(); navigate('/private-domain'); }}>
                      {sig.recommended_action} →
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <ZBadge
                    type={SIGNAL_URGENCY_TYPE[sig.urgency] ?? 'default'}
                    text={sig.urgency === 'high' ? '紧急' : sig.urgency === 'medium' ? '建议' : '参考'}
                  />
                  <span style={{ fontSize: 10, color: '#8c8c8c' }}>
                    {SIGNAL_TYPE_LABEL[sig.signal_type] ?? sig.signal_type}
                  </span>
                </div>
                <div className={css.signalDesc}>{sig.description}</div>
              </div>
            ))}
          </div>
        </ZCard>

        {/* Col 3: 流失预警 */}
        <ZCard
          title={<div style={{ display:'flex', alignItems:'center', gap:6 }}><WarningOutlined style={{ color: '#f5222d' }} /><span>流失预警</span></div>}
          extra={<a onClick={() => navigate('/customer360')} style={{ fontSize: 12 }}>客户360</a>}
        >
          <div className={css.churnSummaryRow}>
            <div>
              <div className={css.churnSummaryNum}>{fmtNum(churnTotal)}</div>
              <div className={css.churnSummaryDesc}>人有流失风险</div>
            </div>
            <ZButton
              variant="danger"
              size="sm"
              icon={<UserAddOutlined />}
              onClick={() => navigate('/private-domain')}
            >
              批量挽回
            </ZButton>
          </div>
          <div className={css.churnList}>
            {churnList.map(u => (
              <div key={u.customer_id} className={css.churnRow}>
                <div className={css.churnAvatar}>{u.name.charAt(0)}</div>
                <span className={css.churnName}>{u.name}</span>
                <ZBadge
                  type={u.risk_level === 'high' ? 'critical' : 'warning'}
                  text={u.risk_level === 'high' ? '高风险' : '中风险'}
                />
                <span className={css.churnDays}>{u.days_since_visit}天未到</span>
              </div>
            ))}
          </div>
        </ZCard>
      </div>

      {/* Quick Nav */}
      <ZCard title="快捷导航">
        <div className={css.quickNav}>
          {QUICK_NAV.map(n => (
            <button
              key={n.route}
              className={css.quickNavItem}
              onClick={() => navigate(n.route)}
            >
              <span className={css.quickNavIcon}>{n.icon}</span>
              <span className={css.quickNavLabel}>{n.label}</span>
            </button>
          ))}
        </div>
      </ZCard>

      {/* ── 增长信号详情抽屉 ──────────────────────────────────────────────────── */}
      <DetailDrawer
        open={!!selectedSignal}
        onClose={() => setSelectedSignal(null)}
        title={selectedSignal?.title ?? ''}
        subtitle={selectedSignal ? SIGNAL_TYPE_LABEL[selectedSignal.signal_type] ?? selectedSignal.signal_type : undefined}
        status={selectedSignal ? {
          label: selectedSignal.urgency === 'high' ? '紧急' : selectedSignal.urgency === 'medium' ? '建议' : '参考',
          type:  SIGNAL_URGENCY_TYPE[selectedSignal.urgency] ?? 'default',
        } : undefined}
        sections={selectedSignal ? [
          {
            title: '信号详情',
            content: <p style={{ margin: 0, lineHeight: 1.7 }}>{selectedSignal.description}</p>,
          },
          ...(selectedSignal.recommended_action ? [{
            title: '建议行动',
            content: (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ZBadge type="info" text={selectedSignal.recommended_action} />
                <span style={{ fontSize: 12, color: 'var(--t3)' }}>点击前往执行</span>
              </div>
            ),
          }] : []),
        ] : []}
        actions={selectedSignal ? [
          {
            label:   selectedSignal.recommended_action ?? '立即执行',
            type:    'primary',
            onClick: () => { navigate('/private-domain'); setSelectedSignal(null); },
          },
          {
            label:   '关闭',
            type:    'default',
            onClick: () => setSelectedSignal(null),
          },
        ] : []}
      />
    </div>
  );
}
