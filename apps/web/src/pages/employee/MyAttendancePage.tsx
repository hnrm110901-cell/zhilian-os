/**
 * 我的考勤 — 员工H5端
 * 路由：/emp/attendance
 * 功能：日历视图 + 月度统计 + 点击查看每日详情
 */
import React, { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../services/api';
import styles from './MyAttendancePage.module.css';

const EMP_ID = localStorage.getItem('employee_id') || 'EMP_001';

interface AttendanceRecord {
  work_date: string;
  status: string;
  clock_in: string | null;
  clock_out: string | null;
  late_minutes: number | null;
  early_leave_minutes: number | null;
  overtime_minutes: number | null;
}

interface AttendanceStats {
  total_days: number;
  normal: number;
  late: number;
  absent: number;
  leave: number;
}

interface AttendanceData {
  month: string;
  records: AttendanceRecord[];
  stats: AttendanceStats;
}

const STATUS_COLORS: Record<string, string> = {
  normal: '#27AE60',
  late: '#F2994A',
  absent: '#EB5757',
  leave: '#2D9CDB',
  rest: '#BDBDBD',
};

const STATUS_LABELS: Record<string, string> = {
  normal: '正常', late: '迟到', absent: '缺勤', leave: '请假', rest: '休息',
};

function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return months;
}

function getCalendarDays(yearMonth: string): (number | null)[] {
  const [y, m] = yearMonth.split('-').map(Number);
  const firstDay = new Date(y, m - 1, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(y, m, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  return cells;
}

const MyAttendancePage: React.FC = () => {
  const monthOptions = getMonthOptions();
  const [selectedMonth, setSelectedMonth] = useState(monthOptions[0]);
  const [data, setData] = useState<AttendanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<AttendanceRecord | null>(null);

  const load = useCallback(async (month: string) => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ code: number; data: AttendanceData }>(
        `/api/v1/hr/self-service/my-attendance/${month}?employee_id=${EMP_ID}`
      );
      setData(res.data);
    } catch {
      setData(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(selectedMonth); }, [selectedMonth, load]);

  const calendarDays = getCalendarDays(selectedMonth);
  const recordMap = new Map<number, AttendanceRecord>();
  if (data?.records) {
    for (const r of data.records) {
      const day = parseInt(r.work_date.split('-')[2] || r.work_date.slice(-2), 10);
      recordMap.set(day, r);
    }
  }

  const handleDayClick = (day: number | null) => {
    if (!day) return;
    const record = recordMap.get(day);
    setSelectedDate(record || null);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>我的考勤</h1>
        <select
          className={styles.monthSelect}
          value={selectedMonth}
          onChange={(e) => { setSelectedMonth(e.target.value); setSelectedDate(null); }}
        >
          {monthOptions.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className={styles.loading}>加载中...</div>
      ) : (
        <>
          {/* 统计卡片 */}
          {data?.stats && (
            <div className={styles.statsCard}>
              <div className={styles.statItem}>
                <div className={styles.statNum}>{data.stats.total_days}</div>
                <div className={styles.statLabel}>出勤天</div>
              </div>
              <div className={styles.statItem}>
                <div className={`${styles.statNum} ${styles.statGreen}`}>{data.stats.normal}</div>
                <div className={styles.statLabel}>正常</div>
              </div>
              <div className={styles.statItem}>
                <div className={`${styles.statNum} ${styles.statWarn}`}>{data.stats.late}</div>
                <div className={styles.statLabel}>迟到</div>
              </div>
              <div className={styles.statItem}>
                <div className={`${styles.statNum} ${styles.statDanger}`}>{data.stats.absent}</div>
                <div className={styles.statLabel}>缺勤</div>
              </div>
              <div className={styles.statItem}>
                <div className={`${styles.statNum} ${styles.statBlue}`}>{data.stats.leave}</div>
                <div className={styles.statLabel}>请假</div>
              </div>
            </div>
          )}

          {/* 日历视图 */}
          <div className={styles.calendarCard}>
            <div className={styles.weekHeader}>
              {['日', '一', '二', '三', '四', '五', '六'].map((d) => (
                <div key={d} className={styles.weekDay}>{d}</div>
              ))}
            </div>
            <div className={styles.calendarGrid}>
              {calendarDays.map((day, idx) => {
                const record = day ? recordMap.get(day) : null;
                const dotColor = record ? STATUS_COLORS[record.status] || '#BDBDBD' : undefined;
                return (
                  <div
                    key={idx}
                    className={`${styles.calendarCell} ${day ? styles.hasDay : ''}`}
                    onClick={() => handleDayClick(day)}
                  >
                    {day && (
                      <>
                        <span className={styles.dayNum}>{day}</span>
                        {dotColor && (
                          <span className={styles.dot} style={{ background: dotColor }} />
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            {/* 图例 */}
            <div className={styles.legend}>
              {Object.entries(STATUS_COLORS).filter(([k]) => k !== 'rest').map(([k, c]) => (
                <div key={k} className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: c }} />
                  <span className={styles.legendLabel}>{STATUS_LABELS[k]}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 选中日期详情 */}
          {selectedDate && (
            <div className={styles.detailCard}>
              <div className={styles.cardTitle}>
                {selectedDate.work_date} 考勤详情
              </div>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>状态</span>
                <span
                  className={styles.detailValue}
                  style={{ color: STATUS_COLORS[selectedDate.status] || '#333' }}
                >
                  {STATUS_LABELS[selectedDate.status] || selectedDate.status}
                </span>
              </div>
              {selectedDate.clock_in && (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>打卡上班</span>
                  <span className={styles.detailValue}>{selectedDate.clock_in}</span>
                </div>
              )}
              {selectedDate.clock_out && (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>打卡下班</span>
                  <span className={styles.detailValue}>{selectedDate.clock_out}</span>
                </div>
              )}
              {(selectedDate.late_minutes || 0) > 0 && (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>迟到</span>
                  <span className={styles.detailValue} style={{ color: '#F2994A' }}>
                    {selectedDate.late_minutes}分钟
                  </span>
                </div>
              )}
              {(selectedDate.overtime_minutes || 0) > 0 && (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>加班</span>
                  <span className={styles.detailValue}>{selectedDate.overtime_minutes}分钟</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MyAttendancePage;
