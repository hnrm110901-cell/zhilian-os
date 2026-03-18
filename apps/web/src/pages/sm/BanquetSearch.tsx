/**
 * SM 宴会全文搜索页
 * 路由：/sm/banquet-search
 * 数据：GET /api/v1/banquet-agent/stores/{id}/search?q=&type=
 */
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { ZBadge, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './BanquetSearch.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

const TYPE_CHIPS = [
  { value: 'all',   label: '全部' },
  { value: 'lead',  label: '线索' },
  { value: 'order', label: '订单' },
];

const LEAD_STAGE_LABELS: Record<string, string> = {
  new:              '初步询价',
  contacted:        '已联系',
  visit_scheduled:  '预约看厅',
  quoted:           '意向确认',
  waiting_decision: '等待决策',
  deposit_pending:  '锁台',
  won:              '已签约',
  lost:             '已流失',
};

const ORDER_STATUS_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  draft:     { text: '草稿',   type: 'default'  },
  confirmed: { text: '已确认', type: 'info'     },
  completed: { text: '已完成', type: 'success'  },
  cancelled: { text: '已取消', type: 'default'  },
};

const BANQUET_TYPE_LABELS: Record<string, string> = {
  wedding:    '婚宴',
  birthday:   '寿宴',
  business:   '商务宴',
  full_moon:  '满月酒',
  graduation: '升学宴',
  other:      '其他',
};

interface LeadResult {
  id:            string;
  type:          'lead';
  customer_name: string;
  phone:         string | null;
  banquet_type:  string | null;
  expected_date: string | null;
  stage:         string;
}

interface OrderResult {
  id:                  string;
  type:                'order';
  customer_name:       string;
  banquet_type:        string | null;
  banquet_date:        string | null;
  total_amount_yuan:   number;
  status:              string;
}

export default function SmBanquetSearch() {
  const navigate = useNavigate();
  const [q,       setQ]       = useState('');
  const [type,    setType]    = useState('all');
  const [leads,   setLeads]   = useState<LeadResult[]>([]);
  const [orders,  setOrders]  = useState<OrderResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (q.length < 2) {
      setLeads([]);
      setOrders([]);
      setSearched(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const resp = await apiClient.get(
          `/api/v1/banquet-agent/stores/${STORE_ID}/search`,
          { params: { q, type } },
        );
        setLeads(resp.data?.leads ?? []);
        setOrders(resp.data?.orders ?? []);
        setSearched(true);
      } catch {
        setLeads([]);
        setOrders([]);
      } finally {
        setLoading(false);
      }
    }, 500);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, type]);

  const visibleLeads  = type === 'order' ? [] : leads;
  const visibleOrders = type === 'lead'  ? [] : orders;
  const hasResults = visibleLeads.length > 0 || visibleOrders.length > 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.searchWrap}>
          <input
            className={styles.searchInput}
            placeholder="客户姓名 / 电话"
            value={q}
            onChange={e => setQ(e.target.value)}
            autoFocus
          />
        </div>
      </div>

      {/* 类型过滤 */}
      <div className={styles.chipBar}>
        {TYPE_CHIPS.map(c => (
          <button
            key={c.value}
            className={`${styles.chip} ${type === c.value ? styles.chipActive : ''}`}
            onClick={() => setType(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className={styles.body}>
        {q.length < 2 ? (
          <ZEmpty title="输入关键词开始搜索" description="支持客户姓名、电话" />
        ) : loading ? (
          <ZSkeleton rows={4} />
        ) : !hasResults && searched ? (
          <ZEmpty title="未找到相关记录" description={`关键词：${q}`} />
        ) : (
          <>
            {/* 线索结果 */}
            {visibleLeads.length > 0 && (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>线索（{visibleLeads.length}）</div>
                {visibleLeads.map(lead => (
                  <div
                    key={lead.id}
                    className={styles.row}
                    onClick={() => navigate(`/sm/banquet-lead-detail/${lead.id}`)}
                  >
                    <div className={styles.rowLeft}>
                      <div className={styles.name}>{lead.customer_name}</div>
                      <div className={styles.meta}>
                        {lead.phone ?? '—'}
                        {lead.banquet_type ? ` · ${BANQUET_TYPE_LABELS[lead.banquet_type] ?? lead.banquet_type}` : ''}
                        {lead.expected_date ? ` · ${dayjs(lead.expected_date).format('MM-DD')}` : ''}
                      </div>
                    </div>
                    <ZBadge type="info" text={LEAD_STAGE_LABELS[lead.stage] ?? lead.stage} />
                  </div>
                ))}
              </div>
            )}

            {/* 订单结果 */}
            {visibleOrders.length > 0 && (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>订单（{visibleOrders.length}）</div>
                {visibleOrders.map(order => {
                  const sb = ORDER_STATUS_BADGE[order.status] ?? { text: order.status, type: 'default' as const };
                  return (
                    <div
                      key={order.id}
                      className={styles.row}
                      onClick={() => navigate(`/sm/banquet-order-detail/${order.id}`)}
                    >
                      <div className={styles.rowLeft}>
                        <div className={styles.name}>{order.customer_name}</div>
                        <div className={styles.meta}>
                          {order.banquet_type ? (BANQUET_TYPE_LABELS[order.banquet_type] ?? order.banquet_type) : ''}
                          {order.banquet_date ? ` · ${dayjs(order.banquet_date).format('MM-DD')}` : ''}
                          {` · ¥${order.total_amount_yuan.toLocaleString()}`}
                        </div>
                      </div>
                      <ZBadge type={sb.type} text={sb.text} />
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
