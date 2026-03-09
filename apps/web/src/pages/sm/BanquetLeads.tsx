/**
 * SM 全部线索页
 * 路由：/sm/banquet-leads
 * 数据：GET /api/v1/banquet-agent/stores/{id}/leads?stage=
 *      PATCH /api/v1/banquet-agent/stores/{id}/leads/{lead_id}/stage
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZSelect, ZInput,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetLeads.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

const STAGE_FILTERS = [
  { value: '',                label: '全部' },
  { value: 'new',             label: '初步询价' },
  { value: 'quoted',          label: '意向确认' },
  { value: 'deposit_pending', label: '锁台' },
  { value: 'won',             label: '已签约' },
];

const STAGE_OPTIONS = [
  { value: 'contacted',        label: '已联系' },
  { value: 'visit_scheduled',  label: '预约看厅' },
  { value: 'quoted',           label: '已报价' },
  { value: 'waiting_decision', label: '等待决策' },
  { value: 'deposit_pending',  label: '待付定金' },
  { value: 'won',              label: '成交' },
  { value: 'lost',             label: '流失' },
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

interface LeadItem {
  banquet_id:    string;
  banquet_type:  string;
  expected_date: string;
  contact_name:  string | null;
  budget_yuan:   number | null;
  stage:         string;
  stage_label:   string;
}

export default function SmBanquetLeads() {
  const navigate = useNavigate();

  const [stageFilter, setStageFilter]   = useState('');
  const [leads,       setLeads]         = useState<LeadItem[]>([]);
  const [loading,     setLoading]       = useState(true);

  // Modal state
  const [modalLead,   setModalLead]     = useState<LeadItem | null>(null);
  const [targetStage, setTargetStage]   = useState('');
  const [followup,    setFollowup]      = useState('');
  const [submitting,  setSubmitting]    = useState(false);

  const loadLeads = useCallback(async (stage: string) => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads`,
        stage ? { params: { stage } } : undefined,
      );
      const raw = resp.data;
      setLeads(Array.isArray(raw) ? raw : (raw?.items ?? raw?.leads ?? []));
    } catch {
      setLeads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadLeads(stageFilter); }, [loadLeads, stageFilter]);

  const openModal = (lead: LeadItem) => {
    setModalLead(lead);
    setTargetStage('');
    setFollowup('');
  };

  const handleSubmit = async () => {
    if (!modalLead || !targetStage) return;
    setSubmitting(true);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${modalLead.banquet_id}/stage`,
        { stage: targetStage, followup_note: followup || null },
      );
      setModalLead(null);
      loadLeads(stageFilter);
    } catch (e) {
      handleApiError(e, '推进阶段失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>全部线索</div>
      </div>

      {/* 阶段 Chip 过滤行 */}
      <div className={styles.chipBar}>
        {STAGE_FILTERS.map(f => (
          <button
            key={f.value}
            className={`${styles.chip} ${stageFilter === f.value ? styles.chipActive : ''}`}
            onClick={() => setStageFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className={styles.body}>
        <ZCard>
          {loading ? (
            <ZSkeleton rows={4} />
          ) : !leads.length ? (
            <ZEmpty title="暂无线索" description="当前阶段下没有线索数据" />
          ) : (
            <div className={styles.list}>
              {leads.map(lead => (
                <div key={lead.banquet_id} className={styles.row}>
                  <div className={styles.info}>
                    <div className={styles.type}>{lead.banquet_type}</div>
                    <div className={styles.meta}>
                      {dayjs(lead.expected_date).format('MM-DD')}
                      {lead.contact_name ? ` · ${lead.contact_name}` : ''}
                    </div>
                  </div>
                  <div className={styles.right}>
                    {lead.budget_yuan != null && (
                      <span className={styles.budget}>¥{lead.budget_yuan.toLocaleString()}</span>
                    )}
                    <ZBadge
                      type={STAGE_BADGE_TYPE[lead.stage] ?? 'default'}
                      text={lead.stage_label ?? lead.stage}
                    />
                    <ZButton variant="ghost" size="sm" onClick={() => navigate(`/sm/banquet-leads/${lead.banquet_id}`)}>
                      详情
                    </ZButton>
                    <ZButton variant="ghost" size="sm" onClick={() => openModal(lead)}>
                      推进
                    </ZButton>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>
      </div>

      {/* 推进阶段 Modal */}
      <ZModal
        open={!!modalLead}
        title={`推进线索：${modalLead?.banquet_type ?? ''}`}
        onClose={() => setModalLead(null)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setModalLead(null)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleSubmit}
              disabled={!targetStage || submitting}
            >
              {submitting ? '提交中…' : '确认推进'}
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
              value={followup}
              onChange={e => setFollowup(e.target.value)}
              placeholder="填写本次跟进情况…"
            />
          </div>
        </div>
      </ZModal>
    </div>
  );
}
