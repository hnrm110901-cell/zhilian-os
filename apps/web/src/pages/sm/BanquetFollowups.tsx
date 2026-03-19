/**
 * SM 跟进提醒页
 * 路由：/sm/banquet-followups
 * 数据：GET  /api/v1/banquet-agent/stores/{id}/followups
 *      POST /api/v1/banquet-agent/stores/{id}/followups/{lead_id}/log
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZSelect, ZInput,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetFollowups.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

const STAGE_OPTIONS = [
  { value: 'contacted',        label: '已联系' },
  { value: 'visit_scheduled',  label: '预约看厅' },
  { value: 'quoted',           label: '已报价' },
  { value: 'waiting_decision', label: '等待决策' },
  { value: 'deposit_pending',  label: '待付定金' },
  { value: 'won',              label: '成交' },
];

const STAGE_BADGE_TYPE: Record<string, 'info' | 'warning' | 'success' | 'default'> = {
  new:              'info',
  contacted:        'info',
  visit_scheduled:  'info',
  quoted:           'warning',
  waiting_decision: 'warning',
  deposit_pending:  'warning',
  won:              'success',
  lost:             'default',
};

interface FollowupLead {
  lead_id:           string;
  banquet_type:      string;
  current_stage:     string;
  expected_date:     string | null;
  last_followup_at:  string | null;
  next_followup_at:  string | null;
  is_overdue:        boolean;
  customer_id:       string;
}

interface FollowupDueResp {
  due_today: FollowupLead[];
  overdue:   FollowupLead[];
  total:     number;
}

export default function SmBanquetFollowups() {
  const navigate = useNavigate();

  const [data,    setData]    = useState<FollowupDueResp | null>(null);
  const [loading, setLoading] = useState(true);

  // 推进阶段 modal
  const [advanceLead,   setAdvanceLead]   = useState<FollowupLead | null>(null);
  const [targetStage,   setTargetStage]   = useState('');
  const [followupNote,  setFollowupNote]  = useState('');
  const [advancing,     setAdvancing]     = useState(false);

  // 标记流失 modal
  const [lostLead,      setLostLead]      = useState<FollowupLead | null>(null);
  const [lostReason,    setLostReason]    = useState('');
  const [lostNote,      setLostNote]      = useState('');
  const [marking,       setMarking]       = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/followups`,
        { params: { days: 7 } },
      );
      // Adapt phase-20 shape to existing component structure
      const items = resp.data?.items ?? [];
      setData({
        due_today: items.filter((i: { next_followup_at: string }) => {
          const d = i.next_followup_at?.slice(0, 10);
          return d === new Date().toISOString().slice(0, 10);
        }),
        overdue:   [],
        total:     resp.data?.total ?? 0,
      });
    } catch {
      setData({ due_today: [], overdue: [], total: 0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  /* 已联系：保持当前 stage，仅更新 last_followup_at */
  const markContacted = async (lead: FollowupLead) => {
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${lead.lead_id}/stage`,
        { stage: lead.current_stage, followup_note: '已联系' },
      );
      load();
    } catch (e) {
      handleApiError(e, '操作失败');
    }
  };

  const openAdvance = (lead: FollowupLead) => {
    setAdvanceLead(lead);
    setTargetStage('');
    setFollowupNote('');
  };

  const handleAdvance = async () => {
    if (!advanceLead || !targetStage) return;
    setAdvancing(true);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${advanceLead.lead_id}/stage`,
        { stage: targetStage, followup_note: followupNote || null },
      );
      setAdvanceLead(null);
      load();
    } catch (e) {
      handleApiError(e, '推进阶段失败');
    } finally {
      setAdvancing(false);
    }
  };

  const openLost = (lead: FollowupLead) => {
    setLostLead(lead);
    setLostReason('');
    setLostNote('');
  };

  const handleMarkLost = async () => {
    if (!lostLead || !lostReason.trim()) return;
    setMarking(true);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${lostLead.lead_id}/lost`,
        { lost_reason: lostReason.trim(), followup_note: lostNote || null },
      );
      setLostLead(null);
      load();
    } catch (e) {
      handleApiError(e, '标记流失失败');
    } finally {
      setMarking(false);
    }
  };

  const totalOverdue = data
    ? data.overdue.length + data.due_today.filter(l => l.is_overdue).length
    : 0;

  const renderLead = (lead: FollowupLead) => (
    <div key={lead.lead_id} className={`${styles.row} ${lead.is_overdue ? styles.rowOverdue : ''}`}>
      <div className={styles.left}>
        <div className={styles.leadType}>
          {lead.banquet_type}
          {lead.is_overdue && <span className={styles.overdueTag}>逾期</span>}
        </div>
        <div className={styles.leadMeta}>
          {lead.expected_date ? dayjs(lead.expected_date).format('MM-DD') : '日期未定'}
          {' · '}
          <ZBadge type={STAGE_BADGE_TYPE[lead.current_stage] ?? 'default'} text={lead.current_stage} />
        </div>
        {lead.next_followup_at && (
          <div className={styles.nextAt}>
            跟进：{dayjs(lead.next_followup_at).format('MM-DD HH:mm')}
          </div>
        )}
        {!lead.next_followup_at && lead.last_followup_at && (
          <div className={styles.lastAt}>
            上次：{dayjs(lead.last_followup_at).format('MM-DD')}
          </div>
        )}
      </div>
      <div className={styles.actions}>
        <ZButton variant="ghost" size="sm" onClick={() => markContacted(lead)}>
          已联系
        </ZButton>
        <ZButton variant="ghost" size="sm" onClick={() => openAdvance(lead)}>
          推进
        </ZButton>
        <ZButton variant="ghost" size="sm" onClick={() => openLost(lead)}>
          流失
        </ZButton>
        <ZButton
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/sm/banquet-leads/${lead.lead_id}`)}
        >
          详情
        </ZButton>
      </div>
    </div>
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>跟进提醒</div>
        {totalOverdue > 0 && (
          <ZBadge type="warning" text={String(totalOverdue)} />
        )}
      </div>

      <div className={styles.body}>
        {loading ? (
          <ZSkeleton rows={5} />
        ) : !data || data.total === 0 ? (
          <ZEmpty title="暂无待跟进线索" description="所有线索均已及时跟进" />
        ) : (
          <>
            {data.due_today.length > 0 && (
              <ZCard title={`今日到期（${data.due_today.length}）`}>
                <div className={styles.list}>
                  {data.due_today.map(renderLead)}
                </div>
              </ZCard>
            )}
            {data.overdue.length > 0 && (
              <ZCard title={`已逾期（${data.overdue.length}）`}>
                <div className={styles.list}>
                  {data.overdue.map(renderLead)}
                </div>
              </ZCard>
            )}
          </>
        )}
      </div>

      {/* 推进阶段 Modal */}
      <ZModal
        open={!!advanceLead}
        title={`推进：${advanceLead?.banquet_type ?? ''}`}
        onClose={() => setAdvanceLead(null)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setAdvanceLead(null)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleAdvance}
              disabled={!targetStage || advancing}
            >
              {advancing ? '提交中…' : '确认推进'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.field}>
            <label className={styles.label}>目标阶段</label>
            <ZSelect
              value={targetStage}
              options={STAGE_OPTIONS}
              onChange={v => setTargetStage(v as string)}
              placeholder="请选择目标阶段"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>跟进内容（选填）</label>
            <ZInput
              value={followupNote}
              onChange={v => setFollowupNote(v)}
              placeholder="本次跟进情况…"
            />
          </div>
        </div>
      </ZModal>

      {/* 标记流失 Modal */}
      <ZModal
        open={!!lostLead}
        title={`标记流失：${lostLead?.banquet_type ?? ''}`}
        onClose={() => setLostLead(null)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setLostLead(null)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleMarkLost}
              disabled={!lostReason.trim() || marking}
            >
              {marking ? '提交中…' : '确认流失'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.field}>
            <label className={styles.label}>流失原因</label>
            <ZInput
              value={lostReason}
              onChange={v => setLostReason(v)}
              placeholder="如：价格太高、竞品抢单、日期冲突…"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>备注（选填）</label>
            <ZInput
              value={lostNote}
              onChange={v => setLostNote(v)}
              placeholder="补充说明…"
            />
          </div>
        </div>
      </ZModal>
    </div>
  );
}
