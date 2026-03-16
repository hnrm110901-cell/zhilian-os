import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface ContractItem {
  id: string;
  employee_id: string;
  employee_name: string;
  contract_no: string;
  contract_type: string;
  status: string;
  start_date: string;
  end_date: string | null;
  position: string;
  renewal_count: number;
}

interface ExpiringItem {
  id: string;
  employee_id: string;
  employee_name: string;
  end_date: string;
  days_remaining: number;
  renewal_count: number;
}

const TYPE_LABELS: Record<string, string> = {
  fixed_term: '固定期限', open_ended: '无固定期限',
  part_time: '兼职', internship: '实习', probation: '试用',
};

const STATUS_COLORS: Record<string, string> = {
  active: '#27AE60', expiring: '#F2994A',
  expired: '#EB5757', terminated: '#EB5757',
  draft: 'rgba(255,255,255,0.38)', renewed: '#2D9CDB',
};

const ContractManagementPage: React.FC = () => {
  const [storeId] = useState('STORE_001');
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [expiring, setExpiring] = useState<ExpiringItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, expRes] = await Promise.all([
        apiClient.get(`/api/v1/hr/contracts?store_id=${storeId}`),
        apiClient.get(`/api/v1/hr/contracts/expiring?store_id=${storeId}&days=60`),
      ]);
      setContracts(listRes.items || []);
      setExpiring(expRes.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>合同管理</h1>
          <p className={styles.pageDesc}>劳动合同、到期提醒与续签管理</p>
        </div>
      </div>

      {/* 即将到期提醒 */}
      {expiring.length > 0 && (
        <div className={styles.alertSection}>
          <div className={styles.alertTitle}>合同即将到期提醒（60天内）</div>
          <div className={styles.alertList}>
            {expiring.map(item => (
              <div key={item.id} className={styles.alertItem}>
                <span className={styles.alertName}>{item.employee_name}</span>
                <span className={styles.alertDate}>到期: {item.end_date}</span>
                <span className={styles.alertDays} style={{
                  color: item.days_remaining <= 15 ? '#EB5757' : '#F2994A',
                }}>
                  剩余 {item.days_remaining} 天
                </span>
                <span className={styles.alertRenewal}>
                  已续签 {item.renewal_count} 次
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 合同列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>合同列表</div>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>员工</th>
                  <th>合同编号</th>
                  <th>类型</th>
                  <th>生效日期</th>
                  <th>到期日期</th>
                  <th>续签次数</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map(c => (
                  <tr key={c.id}>
                    <td className={styles.cellName}>{c.employee_name}</td>
                    <td>{c.contract_no || '-'}</td>
                    <td>{TYPE_LABELS[c.contract_type] || c.contract_type}</td>
                    <td>{c.start_date}</td>
                    <td>{c.end_date || '无固定期限'}</td>
                    <td>{c.renewal_count}</td>
                    <td>
                      <span className={styles.badge} style={{
                        color: STATUS_COLORS[c.status] || 'rgba(255,255,255,0.38)',
                        borderColor: STATUS_COLORS[c.status] || 'rgba(255,255,255,0.12)',
                      }}>
                        {c.status === 'active' ? '生效中' : c.status === 'expiring' ? '即将到期' : c.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ContractManagementPage;
