import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface AttendanceItem {
  employee_id: string;
  employee_name: string;
  position: string | null;
  total_records: number;
  normal_days: number;
  late_days: number;
  early_leave_days: number;
  absent_days: number;
  leave_days: number;
  total_late_minutes: number;
  total_actual_hours: number;
  total_overtime_hours: number;
  avg_daily_hours: number;
  attendance_rate_pct: number;
}

interface AttendanceSummary {
  total_employees: number;
  avg_attendance_rate_pct: number;
  total_overtime_hours: number;
  total_late_count: number;
  total_absent_count: number;
}

const AttendanceReportPage: React.FC = () => {
  const [storeId] = useState('STORE_001');
  const [items, setItems] = useState<AttendanceItem[]>([]);
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [loading, setLoading] = useState(true);

  // 默认本月
  const today = new Date();
  const defaultStart = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
  const defaultEnd = today.toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{
        summary: AttendanceSummary;
        items: AttendanceItem[];
      }>(`/api/v1/hr/attendance/report?store_id=${storeId}&start_date=${startDate}&end_date=${endDate}`);
      setSummary(res.summary || null);
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, startDate, endDate]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>考勤报表</h1>
          <p className={styles.pageDesc}>员工出勤统计 · 迟到/缺勤/加班分析</p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="date"
            className={styles.monthPicker}
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
          />
          <span style={{ color: 'rgba(255,255,255,0.38)', lineHeight: '36px' }}>至</span>
          <input
            type="date"
            className={styles.monthPicker}
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
          />
        </div>
      </div>

      {/* 汇总卡片 */}
      {summary && (
        <div className={styles.statGrid}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>在岗人数</div>
            <div className={styles.statValueLg}>{summary.total_employees}</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>平均出勤率</div>
            <div className={styles.statValueMint}>{summary.avg_attendance_rate_pct}%</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>总加班时数</div>
            <div className={styles.statValue}>{summary.total_overtime_hours}h</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>迟到总次数</div>
            <div className={styles.statValue} style={{
              color: summary.total_late_count > 0 ? '#F2994A' : 'rgba(255,255,255,0.92)',
            }}>
              {summary.total_late_count}
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>缺勤总次数</div>
            <div className={styles.statValue} style={{
              color: summary.total_absent_count > 0 ? '#EB5757' : 'rgba(255,255,255,0.92)',
            }}>
              {summary.total_absent_count}
            </div>
          </div>
        </div>
      )}

      {/* 考勤明细表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>员工考勤明细</div>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : items.length === 0 ? (
          <div className={styles.emptyWrap}>暂无考勤数据</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>员工</th>
                  <th>岗位</th>
                  <th>出勤天数</th>
                  <th>迟到</th>
                  <th>早退</th>
                  <th>缺勤</th>
                  <th>请假</th>
                  <th>加班(h)</th>
                  <th>均时(h)</th>
                  <th>出勤率</th>
                </tr>
              </thead>
              <tbody>
                {items.map(a => (
                  <tr key={a.employee_id}>
                    <td className={styles.cellName}>{a.employee_name}</td>
                    <td>{a.position || '-'}</td>
                    <td>{a.normal_days}</td>
                    <td style={{ color: a.late_days > 0 ? '#F2994A' : undefined }}>
                      {a.late_days}
                      {a.total_late_minutes > 0 && (
                        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginLeft: 4 }}>
                          ({a.total_late_minutes}min)
                        </span>
                      )}
                    </td>
                    <td style={{ color: a.early_leave_days > 0 ? '#F2994A' : undefined }}>
                      {a.early_leave_days}
                    </td>
                    <td style={{ color: a.absent_days > 0 ? '#EB5757' : undefined }}>
                      {a.absent_days}
                    </td>
                    <td>{a.leave_days}</td>
                    <td className={styles.cellMint}>{a.total_overtime_hours}</td>
                    <td>{a.avg_daily_hours}</td>
                    <td>
                      <span style={{
                        color: a.attendance_rate_pct >= 95 ? '#27AE60'
                             : a.attendance_rate_pct >= 85 ? '#F2994A'
                             : '#EB5757',
                        fontWeight: 600,
                      }}>
                        {a.attendance_rate_pct}%
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

export default AttendanceReportPage;
