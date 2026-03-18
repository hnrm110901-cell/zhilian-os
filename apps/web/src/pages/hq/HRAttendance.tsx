import React, { useCallback, useEffect, useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRAttendance.module.css';

interface AttendanceSummary {
  assignment_id: string;
  year: number;
  month: number;
  total_days: number;
  normal_days: number;
  late_count: number;
  early_leave_count: number;
  absent_count: number;
  total_work_hours: number;
  total_overtime_hours: number;
}

const COLS: ZTableColumn[] = [
  { key: 'assignment_id_short', title: '员工' },
  { key: 'total_days', title: '出勤天数' },
  { key: 'normal_days', title: '正常' },
  { key: 'late_badge', title: '迟到' },
  { key: 'absent_badge', title: '缺勤' },
  { key: 'total_work_hours', title: '工时(h)' },
  { key: 'overtime_badge', title: '加班(h)' },
];

export default function HRAttendance() {
  const [rows, setRows] = useState<AttendanceSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [year] = useState(new Date().getFullYear());
  const [month] = useState(new Date().getMonth() + 1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/hr/attendance/monthly?assignment_id=ALL&year=${year}&month=${month}`
      );
      const items = (resp as any).items ?? (resp as any).assignment_id ? [resp] : [];
      setRows(items);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => { load(); }, [load]);

  const totalLate = rows.reduce((s, r) => s + r.late_count, 0);
  const totalAbsent = rows.reduce((s, r) => s + r.absent_count, 0);
  const avgWorkHours = rows.length > 0
    ? (rows.reduce((s, r) => s + r.total_work_hours, 0) / rows.length).toFixed(1)
    : '—';

  const tableRows = rows.map((r) => ({
    ...r,
    assignment_id_short: r.assignment_id.slice(0, 8) + '…',
    late_badge: r.late_count > 0
      ? <ZBadge type="warning" text={`${r.late_count}次`} />
      : <ZBadge type="success" text="0" />,
    absent_badge: r.absent_count > 0
      ? <ZBadge type="critical" text={`${r.absent_count}次`} />
      : <ZBadge type="success" text="0" />,
    overtime_badge: r.total_overtime_hours > 0
      ? <ZBadge type="info" text={`${r.total_overtime_hours}h`} />
      : <span>0</span>,
  }));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>考勤报表 · {year}年{month}月</span>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      <div className={styles.kpiRow}>
        <ZCard><ZKpi value={rows.length} label="在岗人数" unit="人" /></ZCard>
        <ZCard><ZKpi value={avgWorkHours} label="人均工时" unit="h/月" /></ZCard>
        <ZCard><ZKpi value={totalLate} label="迟到" unit="人次" /></ZCard>
        <ZCard><ZKpi value={totalAbsent} label="缺勤" unit="人次" /></ZCard>
      </div>

      <ZCard title="月度考勤明细">
        {loading ? (
          <ZSkeleton rows={4} />
        ) : rows.length === 0 ? (
          <ZEmpty title="暂无考勤数据" description="本月考勤数据尚未生成，Celery每日00:30自动计算" />
        ) : (
          <ZTable columns={COLS} data={tableRows} />
        )}
      </ZCard>
    </div>
  );
}
