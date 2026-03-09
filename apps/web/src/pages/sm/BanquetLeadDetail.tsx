/**
 * SM 线索详情页
 * 路由：/sm/banquet-leads/:leadId
 * 数据：GET /api/v1/banquet-agent/stores/{id}/leads/{lead_id}
 *      PATCH /api/v1/banquet-agent/stores/{id}/leads/{lead_id}/quotes/{quote_id}/accept
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetLeadDetail.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

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
        </ZCard>

        {/* 报价记录 */}
        <ZCard>
          <div className={styles.sectionTitle}>报价记录</div>
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
    </div>
  );
}
