/**
 * 提成管理页面
 * 路由: /commission
 * 功能: 提成规则配置 + 月度提成记录查看
 */
import React, { useCallback, useEffect, useState } from 'react';
import { hrService } from '../../services/hrService';
import type { CommissionRuleItem, CommissionRecordItem } from '../../services/hrService';
import styles from './CommissionPage.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';

const TYPE_LABELS: Record<string, string> = {
  sales_amount: '按营业额', dish_count: '按菜品销量',
  service_fee: '按服务费', membership: '会员转化', custom: '自定义',
};

const METHOD_LABELS: Record<string, string> = {
  fixed_per_unit: '固定金额/单', percentage: '按比例', tiered: '阶梯式',
};

const CommissionPage: React.FC = () => {
  const [rules, setRules] = useState<CommissionRuleItem[]>([]);
  const [records, setRecords] = useState<CommissionRecordItem[]>([]);
  const [tab, setTab] = useState<'rules' | 'records'>('rules');
  const [payMonth, setPayMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [loading, setLoading] = useState(true);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getCommissionRules(STORE_ID);
      setRules(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getCommissionRecords(STORE_ID, payMonth);
      setRecords(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [payMonth]);

  useEffect(() => {
    if (tab === 'rules') loadRules();
    else loadRecords();
  }, [tab, loadRules, loadRecords]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>提成管理</h1>
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'rules' ? styles.tabActive : ''}`}
            onClick={() => setTab('rules')}
          >规则配置</button>
          <button
            className={`${styles.tab} ${tab === 'records' ? styles.tabActive : ''}`}
            onClick={() => setTab('records')}
          >提成记录</button>
        </div>
      </div>

      {tab === 'records' && (
        <div className={styles.filterRow}>
          <input
            type="month"
            value={payMonth}
            onChange={e => setPayMonth(e.target.value)}
            className={styles.monthInput}
          />
        </div>
      )}

      {loading ? (
        <div className={styles.empty}>加载中...</div>
      ) : tab === 'rules' ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>规则名称</th>
                <th>类型</th>
                <th>计算方式</th>
                <th>金额/比例</th>
                <th>适用岗位</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <tr><td colSpan={6} className={styles.empty}>暂无提成规则</td></tr>
              ) : rules.map(r => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>{TYPE_LABELS[r.commission_type] || r.commission_type}</td>
                  <td>{METHOD_LABELS[r.calc_method] || r.calc_method}</td>
                  <td>
                    {r.calc_method === 'percentage'
                      ? `${r.rate_pct}%`
                      : `${r.fixed_amount_yuan.toFixed(2)}元/单`}
                  </td>
                  <td>{r.applicable_positions?.join(', ') || '全岗位'}</td>
                  <td>
                    <span className={r.is_active ? styles.badgeActive : styles.badgeInactive}>
                      {r.is_active ? '启用' : '停用'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>员工</th>
                <th>月份</th>
                <th>计算基数(元)</th>
                <th>数量</th>
                <th>提成金额(元)</th>
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr><td colSpan={5} className={styles.empty}>暂无提成记录</td></tr>
              ) : records.map(r => (
                <tr key={r.id}>
                  <td>{r.employee_name}</td>
                  <td>{r.pay_month}</td>
                  <td>{r.base_amount_yuan.toFixed(2)}</td>
                  <td>{r.base_quantity}</td>
                  <td className={styles.amount}>{r.commission_yuan.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CommissionPage;
