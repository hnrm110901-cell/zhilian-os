import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRMyAttendance.module.css';

interface MonthlyData {
  total_days: number;
  normal_days: number;
  late_count: number;
  early_leave_count: number;
  absent_count: number;
  total_work_hours: number;
  total_overtime_hours: number;
}

const DAY_NAMES = ['日', '一', '二', '三', '四', '五', '六'];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function getFirstDayOfWeek(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay();
}

export default function HRMyAttendance() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [data, setData] = useState<MonthlyData | null>(null);
  const [loading, setLoading] = useState(true);
  const assignmentId = localStorage.getItem('assignment_id') || '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/hr/attendance/monthly?assignment_id=${assignmentId}&year=${year}&month=${month}`
      );
      setData(resp as MonthlyData);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [assignmentId, year, month]);

  useEffect(() => { load(); }, [load]);

  const prevMonth = () => {
    if (month === 1) { setYear(y => y - 1); setMonth(12); }
    else { setMonth(m => m - 1); }
  };
  const nextMonth = () => {
    if (month === 12) { setYear(y => y + 1); setMonth(1); }
    else { setMonth(m => m + 1); }
  };

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfWeek(year, month);
  const today = new Date();
  const isCurrentMonth = year === today.getFullYear() && month === today.getMonth() + 1;

  return (
    <div className={styles.page}>
      <div className={styles.monthNav}>
        <button className={styles.navBtn} onClick={prevMonth}>&lt;</button>
        <span className={styles.monthLabel}>{year}年{month}月</span>
        <button className={styles.navBtn} onClick={nextMonth}>&gt;</button>
      </div>

      {/* 日历网格 */}
      <ZCard>
        <div className={styles.calGrid}>
          {DAY_NAMES.map(d => (
            <div key={d} className={styles.dayHeader}>{d}</div>
          ))}
          {Array.from({ length: firstDay }, (_, i) => (
            <div key={`empty-${i}`} className={styles.dayEmpty} />
          ))}
          {Array.from({ length: daysInMonth }, (_, i) => {
            const day = i + 1;
            const isToday = isCurrentMonth && day === today.getDate();
            const isPast = new Date(year, month - 1, day) < today;
            return (
              <div
                key={day}
                className={`${styles.dayCell} ${isToday ? styles.today : ''} ${isPast ? styles.past : ''}`}
              >
                {day}
              </div>
            );
          })}
        </div>

        <div className={styles.legend}>
          <span className={styles.legendItem}><span className={`${styles.dot} ${styles.dotNormal}`} />正常</span>
          <span className={styles.legendItem}><span className={`${styles.dot} ${styles.dotLate}`} />迟到</span>
          <span className={styles.legendItem}><span className={`${styles.dot} ${styles.dotAbsent}`} />缺勤</span>
          <span className={styles.legendItem}><span className={`${styles.dot} ${styles.dotLeave}`} />请假</span>
        </div>
      </ZCard>

      {/* 月度汇总 */}
      <ZCard title="月度汇总">
        {loading ? <ZSkeleton rows={2} /> : data ? (
          <div className={styles.summaryGrid}>
            <ZKpi value={data.total_days} label="出勤天数" unit="天" />
            <ZKpi value={data.normal_days} label="正常" unit="天" />
            <ZKpi value={data.late_count} label="迟到" unit="次" />
            <ZKpi value={data.absent_count} label="缺勤" unit="次" />
            <ZKpi value={data.total_work_hours} label="总工时" unit="h" />
            <ZKpi value={data.total_overtime_hours} label="加班" unit="h" />
          </div>
        ) : (
          <ZEmpty title="暂无数据" description="本月考勤数据待生成" />
        )}
      </ZCard>
    </div>
  );
}
