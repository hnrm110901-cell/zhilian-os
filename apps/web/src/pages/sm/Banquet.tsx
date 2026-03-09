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
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
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
  }, [loadTodayCheck, loadLeads]);

  const tc = todayCheck;

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
    </div>
  );
}
