/**
 * SM 线索详情页
 * 路由：/sm/banquet-leads/:leadId
 * 数据：GET /api/v1/banquet-agent/stores/{id}/leads/{lead_id}
 *      PATCH /api/v1/banquet-agent/stores/{id}/leads/{lead_id}/quotes/{quote_id}/accept
 *      POST /api/v1/banquet-agent/stores/{id}/orders  (转为订单)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZInput, ZSelect,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetLeadDetail.module.css';
const STORE_ID = localStorage.getItem('store_id') || '';

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

const FOLLOWUP_TYPE_LABELS: Record<string, string> = {
  call:    '电话',
  visit:   '到访',
  wechat:  '微信',
  email:   '邮件',
  other:   '其他',
};

interface FollowupRecord {
  followup_id:      string;
  followup_type:    string;
  content:          string;
  stage_before:     string | null;
  stage_after:      string | null;
  next_followup_at: string | null;
  created_at:       string | null;
}

interface QuoteRecord {
  quote_id:           string;
  people_count:       number;
  table_count:        number;
  quoted_amount_yuan: number;
  valid_until:        string | null;
  is_accepted:        boolean;
  package_id:         string | null;
  created_at:         string | null;
}

interface LeadDetail {
  lead_id:                string;
  customer_id:            string;
  banquet_type:           string;
  expected_date:          string | null;
  expected_people_count:  number | null;
  expected_budget_yuan:   number;
  preferred_hall_type:    string | null;
  source_channel:         string | null;
  current_stage:          string;
  stage_label:            string;
  owner_user_id:          string | null;
  last_followup_at:       string | null;
  converted_order_id:     string | null;
  contact_name:           string | null;
  contact_phone:          string | null;
  followups:              FollowupRecord[];
  quotes:                 QuoteRecord[];
}

export default function SmBanquetLeadDetail() {
  const navigate = useNavigate();
  const { leadId } = useParams<{ leadId: string }>();

  const [lead,       setLead]       = useState<LeadDetail | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [accepting,  setAccepting]  = useState<string | null>(null);

  // 转为订单 Modal state
  const [convertOpen,    setConvertOpen]    = useState(false);
  const [cvBanquetDate,  setCvBanquetDate]  = useState('');
  const [cvTableCount,   setCvTableCount]   = useState('');
  const [cvTotalAmount,  setCvTotalAmount]  = useState('');
  const [cvDeposit,      setCvDeposit]      = useState('');
  const [cvContactName,  setCvContactName]  = useState('');
  const [cvContactPhone, setCvContactPhone] = useState('');
  const [cvRemark,       setCvRemark]       = useState('');
  const [converting,     setConverting]     = useState(false);

  // 标记流失 Modal state
  const [lostOpen,    setLostOpen]    = useState(false);
  const [lostReason,  setLostReason]  = useState('');
  const [lostNote,    setLostNote]    = useState('');
  const [marking,     setMarking]     = useState(false);

  // 新建报价 Modal state
  const [quoteOpen,      setQuoteOpen]      = useState(false);
  const [qPeople,        setQPeople]        = useState('');
  const [qTables,        setQTables]        = useState('');
  const [qAmount,        setQAmount]        = useState('');
  const [qValidDays,     setQValidDays]     = useState('7');
  const [qPackageId,     setQPackageId]     = useState('');
  const [packages,       setPackages]       = useState<{ id: string; name: string }[]>([]);
  const [creatingQuote,  setCreatingQuote]  = useState(false);

  const loadLead = useCallback(async () => {
    if (!leadId) return;
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${leadId}`,
      );
      setLead(resp.data);
    } catch {
      setLead(null);
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => { loadLead(); }, [loadLead]);

  // 加载套餐选项
  useEffect(() => {
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/packages`)
      .then(r => setPackages(r.data?.packages ?? r.data ?? []))
      .catch(() => setPackages([]));
  }, []);

  const acceptQuote = async (quoteId: string) => {
    setAccepting(quoteId);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${leadId}/quotes/${quoteId}/accept`,
      );
      await loadLead();
    } catch (e) {
      handleApiError(e, '接受报价失败');
    } finally {
      setAccepting(null);
    }
  };

  const openConvertModal = () => {
    if (!lead) return;
    setCvBanquetDate(lead.expected_date ?? '');
    setCvTableCount(lead.expected_people_count ? String(Math.ceil(lead.expected_people_count / 10)) : '');
    setCvTotalAmount(lead.expected_budget_yuan > 0 ? String(lead.expected_budget_yuan) : '');
    setCvDeposit('');
    setCvContactName(lead.contact_name ?? '');
    setCvContactPhone(lead.contact_phone ?? '');
    setCvRemark('');
    setConvertOpen(true);
  };

  const handleConvertToOrder = async () => {
    if (!lead || !cvBanquetDate || !cvTableCount || !cvTotalAmount) return;
    setConverting(true);
    try {
      const resp = await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders`,
        {
          lead_id:           leadId,
          customer_id:       lead.customer_id,
          banquet_type:      lead.banquet_type,
          banquet_date:      cvBanquetDate,
          people_count:      lead.expected_people_count ?? parseInt(cvTableCount, 10) * 10,
          table_count:       parseInt(cvTableCount, 10),
          total_amount_yuan: parseFloat(cvTotalAmount),
          deposit_yuan:      cvDeposit ? parseFloat(cvDeposit) : null,
          contact_name:      cvContactName || null,
          contact_phone:     cvContactPhone || null,
          remark:            cvRemark || null,
        },
      );
      setConvertOpen(false);
      navigate(`/sm/banquet-orders/${resp.data.id}`);
    } catch (e) {
      handleApiError(e, '转化订单失败');
    } finally {
      setConverting(false);
    }
  };

  const handleMarkLost = async () => {
    if (!lostReason.trim()) return;
    setMarking(true);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${leadId}/lost`,
        { lost_reason: lostReason.trim(), followup_note: lostNote || null },
      );
      setLostOpen(false);
      await loadLead();
    } catch (e) {
      handleApiError(e, '标记流失失败');
    } finally {
      setMarking(false);
    }
  };

  const openQuoteModal = () => {
    if (!lead) return;
    setQPeople(lead.expected_people_count ? String(lead.expected_people_count) : '');
    setQTables(lead.expected_people_count ? String(Math.ceil(lead.expected_people_count / 10)) : '');
    setQAmount(lead.expected_budget_yuan > 0 ? String(lead.expected_budget_yuan) : '');
    setQValidDays('7');
    setQPackageId('');
    setQuoteOpen(true);
  };

  const handleCreateQuote = async () => {
    if (!qPeople || !qTables || !qAmount) return;
    setCreatingQuote(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/leads/${leadId}/quotes`,
        {
          people_count:       parseInt(qPeople, 10),
          table_count:        parseInt(qTables, 10),
          quoted_amount_yuan: parseFloat(qAmount),
          valid_days:         parseInt(qValidDays, 10) || 7,
          package_id:         qPackageId || null,
        },
      );
      setQuoteOpen(false);
      await loadLead();
    } catch (e) {
      handleApiError(e, '创建报价失败');
    } finally {
      setCreatingQuote(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
          <div className={styles.title}>线索详情</div>
        </div>
        <div className={styles.body}><ZSkeleton rows={6} /></div>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
          <div className={styles.title}>线索详情</div>
        </div>
        <div className={styles.body}>
          <ZEmpty title="线索不存在" description="请返回重试" />
        </div>
      </div>
    );
  }

  const stageBadgeType = STAGE_BADGE_TYPE[lead.current_stage] ?? 'default';
  const today = dayjs();

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
        <div className={styles.title}>线索详情</div>
      </div>

      <div className={styles.body}>
        {/* 客户信息 */}
        <ZCard>
          <div className={styles.sectionTitle}>客户信息</div>
          <div className={styles.infoGrid}>
            {lead.contact_name && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>联系人</span>
                <span className={styles.infoValue}>{lead.contact_name}</span>
              </div>
            )}
            {lead.contact_phone && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>电话</span>
                <span className={styles.infoValue}>{lead.contact_phone}</span>
              </div>
            )}
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>宴会类型</span>
              <span className={styles.infoValue}>{lead.banquet_type}</span>
            </div>
            {lead.expected_date && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>预期日期</span>
                <span className={styles.infoValue}>{dayjs(lead.expected_date).format('YYYY-MM-DD')}</span>
              </div>
            )}
            {lead.expected_people_count != null && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>预计人数</span>
                <span className={styles.infoValue}>{lead.expected_people_count}人</span>
              </div>
            )}
            {lead.expected_budget_yuan > 0 && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>预算</span>
                <span className={styles.infoValue}>¥{lead.expected_budget_yuan.toLocaleString()}</span>
              </div>
            )}
            {lead.source_channel && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>来源渠道</span>
                <span className={styles.infoValue}>{lead.source_channel}</span>
              </div>
            )}
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>当前阶段</span>
              <ZBadge type={stageBadgeType} text={lead.stage_label} />
            </div>
          </div>
          {lead.converted_order_id && (
            <div className={styles.convertedBanner}>
              已转化订单：
              <button
                className={styles.linkBtn}
                onClick={() => navigate(`/sm/banquet-orders/${lead.converted_order_id}`)}
              >
                查看订单 →
              </button>
            </div>
          )}
          {lead.current_stage === 'won' && !lead.converted_order_id && (
            <div className={styles.convertRow}>
              <ZButton variant="primary" size="sm" onClick={openConvertModal}>
                转为订单
              </ZButton>
            </div>
          )}
          {lead.current_stage !== 'won' && lead.current_stage !== 'lost' && (
            <div className={styles.convertRow}>
              <ZButton
                variant="ghost"
                size="sm"
                onClick={() => { setLostReason(''); setLostNote(''); setLostOpen(true); }}
              >
                标记流失
              </ZButton>
            </div>
          )}
        </ZCard>

        {/* 报价记录 */}
        <ZCard>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>报价记录</div>
            {lead.current_stage !== 'won' && lead.current_stage !== 'lost' && (
              <ZButton variant="ghost" size="sm" onClick={openQuoteModal}>＋ 新建报价</ZButton>
            )}
          </div>
          {lead.quotes.length === 0 ? (
            <ZEmpty title="暂无报价" description="尚未生成报价单" />
          ) : (
            <div className={styles.quoteList}>
              {lead.quotes.map(q => {
                const expired = q.valid_until ? dayjs(q.valid_until).isBefore(today) : false;
                const canAccept = !q.is_accepted && !expired;
                return (
                  <div key={q.quote_id} className={`${styles.quoteCard} ${q.is_accepted ? styles.quotedAccepted : ''}`}>
                    <div className={styles.quoteHeader}>
                      <span className={styles.quoteAmount}>¥{q.quoted_amount_yuan.toLocaleString()}</span>
                      {q.is_accepted && <ZBadge type="success" text="已接受" />}
                      {!q.is_accepted && expired && <ZBadge type="default" text="已过期" />}
                      {!q.is_accepted && !expired && <ZBadge type="warning" text="待确认" />}
                    </div>
                    <div className={styles.quoteMeta}>
                      {q.people_count}人 · {q.table_count}桌
                      {q.valid_until ? ` · 有效至${dayjs(q.valid_until).format('MM-DD')}` : ''}
                    </div>
                    {canAccept && (
                      <ZButton
                        variant="primary"
                        size="sm"
                        onClick={() => acceptQuote(q.quote_id)}
                        disabled={accepting === q.quote_id}
                      >
                        {accepting === q.quote_id ? '处理中…' : '接受此报价'}
                      </ZButton>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </ZCard>

        {/* 跟进时间线 */}
        <ZCard>
          <div className={styles.sectionTitle}>跟进记录</div>
          {lead.followups.length === 0 ? (
            <ZEmpty title="暂无跟进记录" description="阶段变更后自动生成" />
          ) : (
            <div className={styles.timeline}>
              {lead.followups.map(f => (
                <div key={f.followup_id} className={styles.timelineItem}>
                  <div className={styles.timelineDot} />
                  <div className={styles.timelineContent}>
                    <div className={styles.timelineHeader}>
                      <ZBadge type="info" text={FOLLOWUP_TYPE_LABELS[f.followup_type] ?? f.followup_type} />
                      {f.stage_before && f.stage_after && (
                        <span className={styles.stageChange}>
                          {f.stage_before} → {f.stage_after}
                        </span>
                      )}
                      <span className={styles.timelineTime}>
                        {f.created_at ? dayjs(f.created_at).format('MM-DD HH:mm') : ''}
                      </span>
                    </div>
                    <div className={styles.timelineText}>{f.content}</div>
                    {f.next_followup_at && (
                      <div className={styles.nextFollowup}>
                        下次跟进：{dayjs(f.next_followup_at).format('MM-DD HH:mm')}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>
      </div>

      {/* 转为订单 Modal */}
      <ZModal
        open={convertOpen}
        title="转为订单"
        onClose={() => setConvertOpen(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setConvertOpen(false)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleConvertToOrder}
              disabled={converting || !cvBanquetDate || !cvTableCount || !cvTotalAmount}
            >
              {converting ? '创建中…' : '创建订单'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>宴会日期</label>
              <ZInput
                type="date"
                value={cvBanquetDate}
                onChange={v => setCvBanquetDate(v)}
                placeholder="YYYY-MM-DD"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>桌数</label>
              <ZInput
                type="number"
                value={cvTableCount}
                onChange={v => setCvTableCount(v)}
                placeholder="如：20"
              />
            </div>
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>合同总额（元）</label>
              <ZInput
                type="number"
                value={cvTotalAmount}
                onChange={v => setCvTotalAmount(v)}
                placeholder="如：50000"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>定金（元，选填）</label>
              <ZInput
                type="number"
                value={cvDeposit}
                onChange={v => setCvDeposit(v)}
                placeholder="如：10000"
              />
            </div>
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>联系人</label>
              <ZInput
                value={cvContactName}
                onChange={v => setCvContactName(v)}
                placeholder="姓名"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>联系电话</label>
              <ZInput
                type="tel"
                value={cvContactPhone}
                onChange={v => setCvContactPhone(v)}
                placeholder="手机号"
              />
            </div>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>备注（选填）</label>
            <ZInput
              value={cvRemark}
              onChange={v => setCvRemark(v)}
              placeholder="特殊要求…"
            />
          </div>
        </div>
      </ZModal>
      {/* 标记流失 Modal */}
      <ZModal
        open={lostOpen}
        title="标记线索流失"
        onClose={() => setLostOpen(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setLostOpen(false)}>取消</ZButton>
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
      {/* 新建报价 Modal */}
      <ZModal
        open={quoteOpen}
        title="新建报价"
        onClose={() => setQuoteOpen(false)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="ghost" onClick={() => setQuoteOpen(false)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleCreateQuote}
              disabled={creatingQuote || !qPeople || !qTables || !qAmount}
            >
              {creatingQuote ? '创建中…' : '创建报价'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.modalBody}>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>人数</label>
              <ZInput
                type="number"
                value={qPeople}
                onChange={v => setQPeople(v)}
                placeholder="如：200"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>桌数</label>
              <ZInput
                type="number"
                value={qTables}
                onChange={v => setQTables(v)}
                placeholder="如：20"
              />
            </div>
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label className={styles.label}>报价金额（元）</label>
              <ZInput
                type="number"
                value={qAmount}
                onChange={v => setQAmount(v)}
                placeholder="如：50000"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>有效天数</label>
              <ZInput
                type="number"
                value={qValidDays}
                onChange={v => setQValidDays(v)}
                placeholder="如：7"
              />
            </div>
          </div>
          {packages.length > 0 && (
            <div className={styles.field}>
              <label className={styles.label}>套餐（选填）</label>
              <ZSelect
                value={qPackageId}
                onChange={v => setQPackageId(v)}
                options={[
                  { value: '', label: '不绑定套餐' },
                  ...packages.map(p => ({ value: p.id, label: p.name })),
                ]}
              />
            </div>
          )}
        </div>
      </ZModal>
    </div>
  );
}
