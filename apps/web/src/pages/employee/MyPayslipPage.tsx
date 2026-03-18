/**
 * 我的工资条 — 员工H5端
 * 路由：/emp/payslip
 * 功能：月份选择、收入/扣除明细、确认工资条、历史列表
 */
import React, { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../services/api';
import styles from './MyPayslipPage.module.css';

const EMP_ID = localStorage.getItem('employee_id') || 'EMP_001';
const STORE_ID = localStorage.getItem('store_id') || '';

interface PayslipItem {
  item_name: string;
  item_category: string;
  amount_yuan: number;
}

interface PayslipDetail {
  pay_month: string;
  items: PayslipItem[];
  total_income_yuan: number;
  total_deduction_yuan: number;
  net_salary_yuan: number;
  confirmed: boolean;
  confirmed_at: string | null;
}

interface PayslipHistory {
  pay_month: string;
  net_salary_yuan: number;
  confirmed: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  base: '基本工资', income: '收入', allowance: '补贴',
  bonus: '奖金', commission: '提成',
  deduction: '扣除', social_insurance: '社保', tax: '个税',
  housing_fund: '公积金', other_deduction: '其他扣除',
};

const INCOME_CATEGORIES = new Set(['base', 'income', 'allowance', 'bonus', 'commission']);

function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return months;
}

const MyPayslipPage: React.FC = () => {
  const monthOptions = getMonthOptions();
  const [selectedMonth, setSelectedMonth] = useState(monthOptions[0]);
  const [detail, setDetail] = useState<PayslipDetail | null>(null);
  const [history, setHistory] = useState<PayslipHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);

  const loadDetail = useCallback(async (month: string) => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ code: number; data: PayslipDetail }>(
        `/api/v1/hr/self-service/my-payslip/${month}?employee_id=${EMP_ID}&store_id=${STORE_ID}`
      );
      setDetail(res.data);
    } catch {
      setDetail(null);
    }
    setLoading(false);
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await apiClient.get<{ code: number; data: PayslipHistory[] }>(
        `/api/v1/hr/self-service/my-payslips?employee_id=${EMP_ID}`
      );
      setHistory(res.data || []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { loadDetail(selectedMonth); }, [selectedMonth, loadDetail]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await apiClient.post(`/api/v1/hr/self-service/my-payslip/${selectedMonth}/confirm?employee_id=${EMP_ID}`, {
        store_id: STORE_ID,
      });
      await loadDetail(selectedMonth);
      await loadHistory();
    } catch { /* silent */ }
    setConfirming(false);
  };

  const incomeItems = detail?.items.filter(i => INCOME_CATEGORIES.has(i.item_category)) || [];
  const deductionItems = detail?.items.filter(i => !INCOME_CATEGORIES.has(i.item_category)) || [];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>我的工资条</h1>
        <select
          className={styles.monthSelect}
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(e.target.value)}
        >
          {monthOptions.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className={styles.loading}>加载中...</div>
      ) : !detail || detail.items.length === 0 ? (
        <div className={styles.emptyCard}>
          <div className={styles.emptyIcon}>📄</div>
          <div className={styles.emptyText}>该月暂无工资条数据</div>
        </div>
      ) : (
        <>
          {/* 实发工资大字 */}
          <div className={styles.totalCard}>
            <div className={styles.totalLabel}>实发工资</div>
            <div className={styles.totalAmount}>
              <span className={styles.currency}>¥</span>
              {detail.net_salary_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
            </div>
            <div className={styles.totalSub}>
              应发 ¥{detail.total_income_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              {' · '}
              扣除 ¥{detail.total_deduction_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
            </div>
            {detail.confirmed ? (
              <div className={styles.confirmedBadge}>已确认</div>
            ) : (
              <button
                className={styles.confirmBtn}
                onClick={handleConfirm}
                disabled={confirming}
              >
                {confirming ? '确认中...' : '确认工资条'}
              </button>
            )}
          </div>

          {/* 收入明细 */}
          <div className={styles.card}>
            <div className={styles.cardTitle}>
              <span className={styles.dotGreen} />
              收入项
            </div>
            {incomeItems.map((item, idx) => (
              <div key={idx} className={styles.itemRow}>
                <span className={styles.itemName}>
                  {CATEGORY_LABELS[item.item_category] || item.item_category}
                  {item.item_name !== item.item_category ? ` - ${item.item_name}` : ''}
                </span>
                <span className={styles.itemAmountGreen}>
                  +¥{item.amount_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            ))}
            <div className={styles.itemRowTotal}>
              <span>小计</span>
              <span className={styles.itemAmountGreen}>
                ¥{detail.total_income_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* 扣除明细 */}
          <div className={styles.card}>
            <div className={styles.cardTitle}>
              <span className={styles.dotRed} />
              扣除项
            </div>
            {deductionItems.map((item, idx) => (
              <div key={idx} className={styles.itemRow}>
                <span className={styles.itemName}>
                  {CATEGORY_LABELS[item.item_category] || item.item_category}
                  {item.item_name !== item.item_category ? ` - ${item.item_name}` : ''}
                </span>
                <span className={styles.itemAmountRed}>
                  -¥{item.amount_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            ))}
            <div className={styles.itemRowTotal}>
              <span>小计</span>
              <span className={styles.itemAmountRed}>
                ¥{detail.total_deduction_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </>
      )}

      {/* 历史列表 */}
      {history.length > 0 && (
        <div className={styles.card}>
          <div className={styles.cardTitle}>历史记录</div>
          {history.map((h) => (
            <div
              key={h.pay_month}
              className={styles.historyRow}
              onClick={() => setSelectedMonth(h.pay_month)}
            >
              <span className={styles.historyMonth}>{h.pay_month}</span>
              <span className={styles.historyAmount}>
                ¥{h.net_salary_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </span>
              <span className={h.confirmed ? styles.statusConfirmed : styles.statusPending}>
                {h.confirmed ? '已确认' : '待确认'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MyPayslipPage;
