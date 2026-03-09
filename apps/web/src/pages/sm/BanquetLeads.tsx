/**
 * SM 全部线索页
 * 路由：/sm/banquet-leads
 * 数据：GET /api/v1/banquet-agent/stores/{id}/leads?stage=
 *      PATCH /api/v1/banquet-agent/stores/{id}/leads/{lead_id}/stage
 *      POST /api/v1/banquet-agent/stores/{id}/customers  (新建客户)
 *      GET  /api/v1/banquet-agent/stores/{id}/customers?q= (搜索客户)
 *      POST /api/v1/banquet-agent/stores/{id}/leads       (新建线索)
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

const BANQUET_TYPE_OPTIONS = [
  { value: 'wedding',  label: '婚宴' },
  { value: 'birthday', label: '生日宴' },
  { value: 'business', label: '商务宴' },
  { value: 'other',    label: '其他' },
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

interface CustomerResult {
  id:           string;
  name:         string;
  phone:        string;
  customer_type?: string;
}

export default function SmBanquetLeads() {
  const navigate = useNavigate();

  const [stageFilter, setStageFilter]   = useState('');
  const [leads,       setLeads]         = useState<LeadItem[]>([]);
  const [loading,     setLoading]       = useState(true);

  // 推进阶段 Modal state
  const [modalLead,   setModalLead]     = useState<LeadItem | null>(null);
  const [targetStage, setTargetStage]   = useState('');
  const [followup,    setFollowup]      = useState('');
  const [submitting,  setSubmitting]    = useState(false);

  // 新建线索 Modal state
  const [newLeadStep,    setNewLeadStep]    = useState<0 | 1 | 2>(0); // 0=closed,1=search,2=form
  const [searchPhone,    setSearchPhone]    = useState('');
  const [searchName,     setSearchName]     = useState('');
  const [searching,      setSearching]      = useState(false);
  const [foundCustomer,  setFoundCustomer]  = useState<CustomerResult | null>(null);
  const [customerError,  setCustomerError]  = useState('');
  // Step 2 fields
  const [nlBanquetType,  setNlBanquetType]  = useState('wedding');
  const [nlExpectedDate, setNlExpectedDate] = useState('');
  const [nlPeople,       setNlPeople]       = useState('');
  const [nlBudget,       setNlBudget]       = useState('');
  const [nlSource,       setNlSource]       = useState('');
  const [nlSubmitting,   setNlSubmitting]   = useState(false);

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

  // ── 新建线索 ──────────────────────────────────────────────────────────────
  const openNewLead = () => {
    setNewLeadStep(1);
    setSearchPhone('');
    setSearchName('');
    setFoundCustomer(null);
    setCustomerError('');
  };

  const closeNewLead = () => {
    setNewLeadStep(0);
    setFoundCustomer(null);
    setCustomerError('');
    setNlBanquetType('wedding');
    setNlExpectedDate('');
    setNlPeople('');
    setNlBudget('');
    setNlSource('');
  };

  const handleSearchCustomer = async () => {
    if (!searchPhone.trim() && !searchName.trim()) return;
    setSearching(true);
    setCustomerError('');
    try {
      const q = searchPhone.trim() || searchName.trim();
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/customers`,
        { params: { q } },
      );
      const items: CustomerResult[] = resp.data?.items ?? resp.data ?? [];
      if (items.length > 0) {
        setFoundCustomer(items[0]);
      } else {
        setFoundCustomer(null);
        setCustomerError('未找到客户，将自动新建');
      }
    } catch {
      setCustomerError('搜索失败，将自动新建');
      setFoundCustomer(null);
    } finally {
      setSearching(false);
    }
  };

  const handleProceedToStep2 = async () => {
    // If no customer found, create one first
    let customer = foundCustomer;
    if (!customer) {
      if (!searchPhone.trim()) {
        setCustomerError('请输入手机号以新建客户');
        return;
      }
      try {
        setSearching(true);
        const resp = await apiClient.post(
          `/api/v1/banquet-agent/stores/${STORE_ID}/customers`,
          {
            name: searchName.trim() || searchPhone.trim(),
            phone: searchPhone.trim(),
            customer_type: 'individual',
          },
        );
        customer = { id: resp.data.id, name: resp.data.name ?? searchName.trim(), phone: searchPhone.trim() };
        setFoundCustomer(customer);
      } catch (e) {
        handleApiError(e, '新建客户失败');
        return;
      } finally {
        setSearching(false);
      }
    }
    setNewLeadStep(2);
  };

  const handleCreateLead = async () => {
    if (!foundCustomer || !nlBanquetType) return;
    setNlSubmitting(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads`,
        {
          customer_id:            foundCustomer.id,
          banquet_type:           nlBanquetType,
          expected_date:          nlExpectedDate || null,
          expected_people_count:  nlPeople ? parseInt(nlPeople, 10) : null,
          expected_budget_yuan:   nlBudget ? parseFloat(nlBudget) : null,
          source_channel:         nlSource || null,
        },
      );
      closeNewLead();
      loadLeads(stageFilter);
    } catch (e) {
      handleApiError(e, '创建线索失败');
    } finally {
      setNlSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>全部线索</div>
        <ZButton variant="primary" size="sm" onClick={openNewLead} style={{ marginLeft: 'auto' }}>
          ＋ 新建线索
        </ZButton>
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

      {/* 新建线索 Step 1：搜索/新建客户 */}
      <ZModal
        open={newLeadStep === 1}
        title="新建线索 — 第 1 步：选择客户"
        onClose={closeNewLead}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={closeNewLead}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleProceedToStep2}
              disabled={searching || (!searchPhone.trim() && !searchName.trim())}
            >
              {searching ? '处理中…' : '下一步'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.field}>
            <label className={styles.label}>手机号</label>
            <ZInput
              value={searchPhone}
              onChange={e => setSearchPhone(e.target.value)}
              placeholder="输入手机号搜索客户"
              type="tel"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>姓名（选填）</label>
            <ZInput
              value={searchName}
              onChange={e => setSearchName(e.target.value)}
              placeholder="客户姓名"
            />
          </div>
          <ZButton
            variant="ghost"
            size="sm"
            onClick={handleSearchCustomer}
            disabled={searching || (!searchPhone.trim() && !searchName.trim())}
          >
            {searching ? '搜索中…' : '搜索客户'}
          </ZButton>
          {foundCustomer && (
            <div className={styles.customerFound}>
              <span className={styles.customerFoundIcon}>✓</span>
              找到客户：<strong>{foundCustomer.name}</strong>（{foundCustomer.phone}）
            </div>
          )}
          {customerError && (
            <div className={styles.customerHint}>{customerError}</div>
          )}
        </div>
      </ZModal>

      {/* 新建线索 Step 2：填写线索信息 */}
      <ZModal
        open={newLeadStep === 2}
        title="新建线索 — 第 2 步：线索详情"
        onClose={closeNewLead}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setNewLeadStep(1)}>上一步</ZButton>
            <ZButton
              variant="primary"
              onClick={handleCreateLead}
              disabled={nlSubmitting || !nlBanquetType}
            >
              {nlSubmitting ? '提交中…' : '创建线索'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          {foundCustomer && (
            <div className={styles.customerFound}>
              客户：<strong>{foundCustomer.name}</strong>（{foundCustomer.phone}）
            </div>
          )}
          <div className={styles.field}>
            <label className={styles.label}>宴会类型</label>
            <ZSelect
              value={nlBanquetType}
              options={BANQUET_TYPE_OPTIONS}
              onChange={v => setNlBanquetType(v as string)}
              placeholder="请选择宴会类型"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>预期日期（选填）</label>
            <ZInput
              value={nlExpectedDate}
              onChange={e => setNlExpectedDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              type="date"
            />
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>预计人数</label>
              <ZInput
                value={nlPeople}
                onChange={e => setNlPeople(e.target.value)}
                placeholder="例：200"
                type="number"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>预算（元）</label>
              <ZInput
                value={nlBudget}
                onChange={e => setNlBudget(e.target.value)}
                placeholder="例：60000"
                type="number"
              />
            </div>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>来源渠道（选填）</label>
            <ZInput
              value={nlSource}
              onChange={e => setNlSource(e.target.value)}
              placeholder="如：口碑推荐、美团、自然到访"
            />
          </div>
        </div>
      </ZModal>
    </div>
  );
}
