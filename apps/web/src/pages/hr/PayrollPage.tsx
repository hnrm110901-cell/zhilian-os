import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import { hrService } from '../../services/hrService';
import type { PayrollDetailResult, SalaryItemDetail } from '../../services/hrService';
import styles from './HRPages.module.css';

interface PayrollItem {
  id: string;
  employee_id: string;
  employee_name: string;
  position: string;
  pay_month: string;
  status: string;
  gross_salary_yuan: number;
  total_deduction_yuan: number;
  net_salary_yuan: number;
  tax_yuan: number;
  attendance_days: number;
  overtime_hours: number;
  paid_at: string | null;
}

interface PayrollSummary {
  employee_count: number;
  total_gross_yuan: number;
  total_net_yuan: number;
  total_tax_yuan: number;
  total_social_insurance_yuan: number;
  total_housing_fund_yuan: number;
  total_overtime_pay_yuan: number;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#F2994A' },
  confirmed: { label: '已确认', color: '#2D9CDB' },
  paid: { label: '已发放', color: '#27AE60' },
  cancelled: { label: '已作废', color: '#EB5757' },
};

const PayrollPage: React.FC = () => {
  const [storeId] = useState(localStorage.getItem('store_id') || '');
  const [payMonth, setPayMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [items, setItems] = useState<PayrollItem[]>([]);
  const [summary, setSummary] = useState<PayrollSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [detailEmpId, setDetailEmpId] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<PayrollDetailResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadDetail = async (employeeId: string) => {
    setDetailEmpId(employeeId);
    setDetailLoading(true);
    try {
      const data = await hrService.getPayrollDetail(employeeId, payMonth);
      setDetailData(data);
    } catch { setDetailData(null); }
    setDetailLoading(false);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, sumRes] = await Promise.all([
        apiClient.get(`/api/v1/payroll/list?store_id=${storeId}&pay_month=${payMonth}`),
        apiClient.get(`/api/v1/payroll/summary?store_id=${storeId}&pay_month=${payMonth}`),
      ]);
      setItems(listRes.items || []);
      setSummary(sumRes);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, payMonth]);

  useEffect(() => { load(); }, [load]);

  const handleBatchCalc = async () => {
    setCalculating(true);
    try {
      await apiClient.post('/api/v1/payroll/batch-calculate', {
        store_id: storeId,
        pay_month: payMonth,
      });
      await load();
    } catch { /* silent */ }
    setCalculating(false);
  };

  const handleMarkPaid = async () => {
    try {
      await apiClient.post('/api/v1/payroll/mark-paid', {
        store_id: storeId,
        pay_month: payMonth,
      });
      await load();
    } catch { /* silent */ }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>薪酬管理</h1>
          <p className={styles.pageDesc}>月度工资计算、发放与统计</p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="month"
            value={payMonth}
            onChange={e => setPayMonth(e.target.value)}
            className={styles.monthPicker}
          />
          <button className={styles.btnPrimary} onClick={handleBatchCalc} disabled={calculating}>
            {calculating ? '计算中...' : '一键算薪'}
          </button>
          <button className={styles.btnSecondary} onClick={handleMarkPaid}>
            标记发放
          </button>
        </div>
      </div>

      {/* 汇总卡片 */}
      {summary && (
        <div className={styles.statGrid}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>在薪人数</div>
            <div className={styles.statValue}>{summary.employee_count}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>应发合计</div>
            <div className={styles.statValue}>¥{summary.total_gross_yuan.toLocaleString()}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>实发合计</div>
            <div className={styles.statValueMint}>¥{summary.total_net_yuan.toLocaleString()}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>个税合计</div>
            <div className={styles.statValue}>¥{summary.total_tax_yuan.toLocaleString()}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>社保合计</div>
            <div className={styles.statValue}>¥{summary.total_social_insurance_yuan.toLocaleString()}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>加班费合计</div>
            <div className={styles.statValue}>¥{summary.total_overtime_pay_yuan.toLocaleString()}</div>
          </div>
        </div>
      )}

      {/* 工资表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>月度工资表 — {payMonth}</div>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : items.length === 0 ? (
          <div className={styles.emptyWrap}>暂无工资数据，请先执行"一键算薪"</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>员工</th>
                  <th>岗位</th>
                  <th>出勤</th>
                  <th>加班</th>
                  <th>应发(元)</th>
                  <th>扣款(元)</th>
                  <th>个税(元)</th>
                  <th>实发(元)</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => {
                  const st = STATUS_MAP[item.status] || STATUS_MAP.draft;
                  return (
                    <tr key={item.id} onClick={() => loadDetail(item.employee_id)} style={{ cursor: 'pointer' }}>
                      <td className={styles.cellName}>{item.employee_name}</td>
                      <td>{item.position || '-'}</td>
                      <td>{item.attendance_days}天</td>
                      <td>{item.overtime_hours}h</td>
                      <td>¥{item.gross_salary_yuan.toLocaleString()}</td>
                      <td>¥{item.total_deduction_yuan.toLocaleString()}</td>
                      <td>¥{item.tax_yuan.toLocaleString()}</td>
                      <td className={styles.cellMint}>¥{item.net_salary_yuan.toLocaleString()}</td>
                      <td>
                        <span className={styles.badge} style={{ color: st.color, borderColor: st.color }}>
                          {st.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {/* 薪酬明细侧边栏 */}
      {detailEmpId && (
        <div style={{
          position: 'fixed', top: 0, right: 0, width: 440, height: '100vh',
          background: '#0D2029', borderLeft: '1px solid rgba(255,255,255,0.08)',
          zIndex: 1000, overflowY: 'auto', padding: '20px 24px',
          boxShadow: '-4px 0 20px rgba(0,0,0,0.3)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ color: 'rgba(255,255,255,0.92)', margin: 0 }}>
              薪酬明细 — {items.find(i => i.employee_id === detailEmpId)?.employee_name || detailEmpId}
            </h3>
            <button onClick={() => { setDetailEmpId(null); setDetailData(null); }} style={{
              background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
              fontSize: 20, cursor: 'pointer',
            }}>✕</button>
          </div>

          {detailLoading ? (
            <div style={{ color: 'rgba(255,255,255,0.5)', textAlign: 'center', marginTop: 40 }}>加载中...</div>
          ) : detailData ? (
            <>
              <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                <div style={{ flex: 1, background: 'rgba(39,174,96,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>应发</div>
                  <div style={{ fontSize: 18, color: '#27AE60', fontWeight: 600 }}>¥{(detailData.total_income_yuan ?? 0).toLocaleString()}</div>
                </div>
                <div style={{ flex: 1, background: 'rgba(10,175,154,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>实发</div>
                  <div style={{ fontSize: 18, color: '#0AAF9A', fontWeight: 600 }}>¥{(detailData.net_salary_yuan ?? 0).toLocaleString()}</div>
                </div>
              </div>

              {['income', 'deduction', 'subsidy', 'tax'].map(cat => {
                const catItems = (detailData.items || []).filter((i: SalaryItemDetail) => i.item_category === cat);
                if (catItems.length === 0) return null;
                const catLabel: Record<string, string> = { income: '收入项', deduction: '扣除项', subsidy: '补贴项', tax: '税项' };
                return (
                  <div key={cat} style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 13, color: '#0AAF9A', marginBottom: 6, fontWeight: 500 }}>
                      {catLabel[cat] || cat}
                    </div>
                    {catItems.map((item: SalaryItemDetail, idx: number) => (
                      <div key={idx} style={{
                        display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                        borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: 13,
                      }}>
                        <span style={{ color: 'rgba(255,255,255,0.7)' }}>{item.item_name}</span>
                        <span style={{ color: cat === 'deduction' || cat === 'tax' ? '#EB5757' : 'rgba(255,255,255,0.85)' }}>
                          {cat === 'deduction' || cat === 'tax' ? '-' : ''}¥{item.amount_yuan.toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </>
          ) : (
            <div style={{ color: 'rgba(255,255,255,0.5)', textAlign: 'center', marginTop: 40 }}>暂无明细数据</div>
          )}
        </div>
      )}
    </div>
  );
};

export default PayrollPage;
