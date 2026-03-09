/**
 * 店长今日宴会页（移动端）
 * 路由：/sm/banquet
 * 数据：GET /api/v1/banquet/{id}/today-check
 *      GET /api/v1/banquet-agent/stores/{id}/agent/followup-scan
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './Banquet.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';
const TODAY = dayjs().format('YYYY-MM-DD');

interface TodayCheck {
  store_id:                  string;
  date:                      string;
  is_auspicious_day:         boolean;
  banquets_total:            number;
  expected_guest_count:      number | null;
  circuit_breaker_triggered: boolean;
  notes:                     string | null;
}

interface LeadItem {
  banquet_id:    string;
  banquet_type:  string;
  expected_date: string;
  budget_yuan:   number | null;
  stage:         string;
  stage_label:   string;
  contact_name:  string | null;
}

export default function SmBanquet() {
  const navigate = useNavigate();
  const [todayCheck,      setTodayCheck]      = useState<TodayCheck | null>(null);
  const [leads,           setLeads]           = useState<LeadItem[]>([]);
  const [loadingToday,    setLoadingToday]    = useState(true);
  const [loadingLeads,    setLoadingLeads]    = useState(true);

  // 预警订单
  interface AtRiskOrder {
    order_id:     string;
    banquet_date: string;
    banquet_type: string;
    risk_score:   number;
    risk_reasons: string[];
  }
  const [atRiskOrders, setAtRiskOrders] = useState<AtRiskOrder[]>([]);

  // Phase 16: 客户触达
  interface AnniversaryItem {
    customer_id:       string;
    name:              string;
    phone:             string | null;
    last_banquet_type: string;
    anniversary_date:  string;
    days_until:        number;
  }
  interface WinBackItem {
    customer_id:    string;
    name:           string;
    phone:          string | null;
    last_order_date: string;
    days_since:     number;
    total_orders:   number;
    total_yuan:     number;
  }
  const [anniversaries,     setAnniversaries]     = useState<AnniversaryItem[]>([]);
  const [winBackCandidates, setWinBackCandidates] = useState<WinBackItem[]>([]);
  const [outreachMsg,       setOutreachMsg]       = useState<string | null>(null);
  const [sendingOutreach,   setSendingOutreach]   = useState<string | null>(null);

  const loadTodayCheck = useCallback(async () => {
    setLoadingToday(true);
    try {
      const resp = await apiClient.get(`/api/v1/banquet/${STORE_ID}/today-check`);
      setTodayCheck(resp.data);
    } catch (e) {
      handleApiError(e, '今日宴会状态加载失败');
      setTodayCheck(null);
    } finally {
      setLoadingToday(false);
    }
  }, []);

  const loadLeads = useCallback(async () => {
    setLoadingLeads(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/agent/followup-scan`,
      );
      const raw = resp.data;
      setLeads(Array.isArray(raw) ? raw : (raw?.leads ?? raw?.items ?? []));
    } catch {
      setLeads([]);
    } finally {
      setLoadingLeads(false);
    }
  }, []);

  useEffect(() => {
    loadTodayCheck();
    loadLeads();
    // 加载预警订单
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/orders/at-risk`)
      .then(r => setAtRiskOrders(Array.isArray(r.data) ? r.data : []))
      .catch(() => {});
    // Phase 16: 周年提醒 + 赢回候选
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/customers/upcoming-anniversaries`, { params: { days: 7 } })
      .then(r => setAnniversaries(r.data?.items ?? []))
      .catch(() => {});
    apiClient.get(`/api/v1/banquet-agent/stores/${STORE_ID}/customers/win-back-candidates`, { params: { months: 12 } })
      .then(r => setWinBackCandidates((r.data?.items ?? []).slice(0, 3)))
      .catch(() => {});
  }, [loadTodayCheck, loadLeads]);

  const tc = todayCheck;

  const handleAnniversary = async (cid: string) => {
    setSendingOutreach(cid);
    try {
      const r = await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/customers/${cid}/anniversary-message`,
      );
      setOutreachMsg(r.data?.message ?? '话术已生成');
    } catch (e) {
      handleApiError(e, '生成话术失败');
    } finally {
      setSendingOutreach(null);
    }
  };

  const handleWinBack = async (cid: string) => {
    setSendingOutreach(cid);
    try {
      const r = await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/customers/${cid}/win-back-message`,
      );
      setOutreachMsg(r.data?.message ?? '话术已生成');
    } catch (e) {
      handleApiError(e, '生成赢回话术失败');
    } finally {
      setSendingOutreach(null);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>今日宴会</div>
          <div className={styles.subtitle}>{TODAY}</div>
        </div>
        <button className={styles.searchBtn} onClick={() => navigate('/sm/banquet-search')} aria-label="搜索">
          🔍
        </button>
      </div>

      <div className={styles.body}>
        {/* 预警横幅 */}
        {atRiskOrders.length > 0 && (
          <div className={styles.riskBanner}>
            <span className={styles.riskIcon}>⚠️</span>
            <span className={styles.riskText}>
              {atRiskOrders.length} 个订单存在风险：{atRiskOrders.map(o => o.banquet_date).join('、')}
            </span>
          </div>
        )}
        {/* 今日状态卡 */}
        <ZCard title="今日状态">
          {loadingToday ? (
            <ZSkeleton rows={3} />
          ) : !tc ? (
            <ZEmpty title="暂无今日数据" description="请确认后端宴会服务已启动" />
          ) : (
            <div className={styles.statusGrid}>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>日期属性</span>
                <ZBadge
                  type={tc.is_auspicious_day ? 'success' : 'default'}
                  text={tc.is_auspicious_day ? '🎊 吉日' : '普通日'}
                />
              </div>
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>今日宴会</span>
                <ZKpi value={tc.banquets_total} label="" unit="场" size="sm" />
              </div>
              {tc.expected_guest_count != null && (
                <div className={styles.statusItem}>
                  <span className={styles.statusLabel}>预计宾客</span>
                  <ZKpi value={tc.expected_guest_count} label="" unit="人" size="sm" />
                </div>
              )}
              <div className={styles.statusItem}>
                <span className={styles.statusLabel}>熔断状态</span>
                <ZBadge
                  type={tc.circuit_breaker_triggered ? 'warning' : 'success'}
                  text={tc.circuit_breaker_triggered ? '⚠️ 已触发' : '✅ 正常'}
                />
              </div>
            </div>
          )}
        </ZCard>

        {/* 待跟进线索 */}
        <ZCard
          title="待跟进线索"
          extra={
            !loadingLeads && leads.length > 0
              ? <ZBadge type="warning" text={String(leads.length)} />
              : null
          }
        >
          {loadingLeads ? (
            <ZSkeleton rows={3} />
          ) : !leads.length ? (
            <ZEmpty title="暂无待跟进线索" description="线索扫描通常每2小时执行一次" />
          ) : (
            <div className={styles.leadList}>
              {leads.map((lead) => (
                <div key={lead.banquet_id} className={styles.leadRow}>
                  <div className={styles.leadInfo}>
                    <div className={styles.leadType}>{lead.banquet_type}</div>
                    <div className={styles.leadMeta}>
                      {dayjs(lead.expected_date).format('MM-DD')}
                      {lead.contact_name ? ` · ${lead.contact_name}` : ''}
                    </div>
                  </div>
                  <div className={styles.leadRight}>
                    {lead.budget_yuan != null && (
                      <span className={styles.leadBudget}>
                        ¥{lead.budget_yuan.toLocaleString()}
                      </span>
                    )}
                    <ZBadge type="info" text={lead.stage_label ?? lead.stage} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>

        {/* Phase 16: 客户触达 */}
        {(anniversaries.length > 0 || winBackCandidates.length > 0) && (
          <ZCard title="客户触达提醒">
            {anniversaries.length > 0 && (
              <div className={styles.outreachSection}>
                <div className={styles.outreachLabel}>周年/生日 · 近7天</div>
                {anniversaries.map(a => (
                  <div key={a.customer_id} className={styles.outreachRow}>
                    <div className={styles.outreachInfo}>
                      <div className={styles.outreachName}>{a.name}</div>
                      <div className={styles.outreachMeta}>
                        {a.last_banquet_type} · {a.days_until === 0 ? '今天' : `${a.days_until}天后`}
                      </div>
                    </div>
                    <ZButton
                      variant="ghost"
                      size="sm"
                      onClick={() => handleAnniversary(a.customer_id)}
                      disabled={sendingOutreach === a.customer_id}
                    >
                      {sendingOutreach === a.customer_id ? '…' : '发送祝福'}
                    </ZButton>
                  </div>
                ))}
              </div>
            )}
            {winBackCandidates.length > 0 && (
              <div className={styles.outreachSection}>
                <div className={styles.outreachLabel}>流失预警 · Top3</div>
                {winBackCandidates.map(c => (
                  <div key={c.customer_id} className={styles.outreachRow}>
                    <div className={styles.outreachInfo}>
                      <div className={styles.outreachName}>{c.name}</div>
                      <div className={styles.outreachMeta}>
                        失联 {c.days_since} 天 · 历史消费 ¥{c.total_yuan.toLocaleString()}
                      </div>
                    </div>
                    <ZButton
                      variant="ghost"
                      size="sm"
                      onClick={() => handleWinBack(c.customer_id)}
                      disabled={sendingOutreach === c.customer_id}
                    >
                      {sendingOutreach === c.customer_id ? '…' : '发送话术'}
                    </ZButton>
                  </div>
                ))}
              </div>
            )}
          </ZCard>
        )}

        {/* 快捷入口 */}
        <ZCard title="快捷操作">
          <div className={styles.actionRow}>
            <ZButton
              variant="ghost"
              onClick={() => navigate('/sm/banquet-leads')}
            >
              查看全部线索
            </ZButton>
            <ZButton
              variant="ghost"
              onClick={() => navigate('/sm/banquet-orders')}
            >
              查看全部订单
            </ZButton>
            <ZButton
              variant="ghost"
              onClick={() => navigate('/sm/banquet-tasks')}
            >
              执行任务
            </ZButton>
            <ZButton
              variant="ghost"
              onClick={() => navigate('/sm/banquet-followups')}
            >
              跟进提醒
            </ZButton>
            <ZButton
              variant="ghost"
              onClick={() => navigate('/sm/banquet-push')}
            >
              推送通知
            </ZButton>
          </div>
        </ZCard>
      </div>

      {/* 话术展示 Modal */}
      <ZModal
        open={!!outreachMsg}
        title="触达话术"
        onClose={() => setOutreachMsg(null)}
        footer={
          <div className={styles.modalFooter}>
            <ZButton variant="primary" onClick={() => setOutreachMsg(null)}>关闭</ZButton>
          </div>
        }
      >
        <div className={styles.outreachMsgBody}>{outreachMsg}</div>
      </ZModal>
    </div>
  );
}
