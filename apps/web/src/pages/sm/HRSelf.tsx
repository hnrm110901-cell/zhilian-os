import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRSelf.module.css';

interface MonthlyData {
  total_days: number;
  normal_days: number;
  late_count: number;
  total_work_hours: number;
}

export default function HRSelf() {
  const navigate = useNavigate();
  const [monthly, setMonthly] = useState<MonthlyData | null>(null);
  const [loading, setLoading] = useState(true);
  const assignmentId = localStorage.getItem('assignment_id') || '';
  const year = new Date().getFullYear();
  const month = new Date().getMonth() + 1;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/hr/attendance/monthly?assignment_id=${assignmentId}&year=${year}&month=${month}`
      );
      setMonthly(resp as MonthlyData);
    } catch {
      setMonthly(null);
    } finally {
      setLoading(false);
    }
  }, [assignmentId, year, month]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.greeting}>
        <span className={styles.hi}>我的HR</span>
        <ZBadge type="info" text={`${year}年${month}月`} />
      </div>

      {/* 今日排班 */}
      <ZCard title="今日排班">
        <div className={styles.scheduleRow}>
          <span className={styles.scheduleTime}>09:00 — 22:00</span>
          <ZBadge type="success" text="正常班" />
        </div>
      </ZCard>

      {/* 本月出勤 */}
      <ZCard title="本月出勤">
        {loading ? <ZSkeleton rows={2} /> : (
          <div className={styles.kpiRow}>
            <ZKpi value={monthly?.total_days ?? 0} label="出勤" unit="天" />
            <ZKpi value={monthly?.late_count ?? 0} label="迟到" unit="次" />
            <ZKpi value={monthly?.total_work_hours ?? 0} label="工时" unit="h" />
          </div>
        )}
      </ZCard>

      {/* 快捷操作 */}
      <div className={styles.actions}>
        <button className={styles.actionBtn} onClick={() => navigate('/sm/hr/leave')}>
          <span className={styles.actionIcon}>📝</span>
          <span>请假</span>
        </button>
        <button className={styles.actionBtn} onClick={() => navigate('/sm/hr/my-attendance')}>
          <span className={styles.actionIcon}>📅</span>
          <span>考勤</span>
        </button>
        <button className={styles.actionBtn} onClick={() => navigate('/sm/hr/growth')}>
          <span className={styles.actionIcon}>📈</span>
          <span>成长</span>
        </button>
        <button className={styles.actionBtn} onClick={() => navigate('/sm/hr')}>
          <span className={styles.actionIcon}>👥</span>
          <span>团队</span>
        </button>
      </div>

      {/* 成长积分 */}
      <ZCard title="成长积分" extra={<ZBadge type="info" text="Lv.1" />}>
        <div className={styles.growthBar}>
          <div className={styles.growthFill} style={{ width: '35%' }} />
        </div>
        <span className={styles.growthLabel}>距下一等级还需 65 积分</span>
      </ZCard>
    </div>
  );
}
