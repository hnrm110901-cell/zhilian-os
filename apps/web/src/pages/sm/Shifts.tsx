import React, { useCallback, useEffect, useState } from 'react';
import dayjs from 'dayjs';
import { CalendarOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { ZBadge, ZButton, ZCard, ZEmpty, ZSkeleton } from '../../design-system/components';
import { checkInShift, checkOutShift } from '../../services/mobile.mutation.service';
import { queryShiftSummary } from '../../services/mobile.query.service';
import type { MobileShift, ShiftSummaryResponse } from '../../services/mobile.types';
import { showError, showSuccess, handleApiError } from '../../utils/message';
import styles from './Shifts.module.css';

const ATTENDANCE_TEXT: Record<string, string> = {
  not_checked_in: '待打卡',
  checked_in: '已打卡',
  checked_out: '已下班',
  late: '迟到',
  abnormal: '异常',
  absent: '缺勤',
};

export default function SmShifts() {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [data, setData] = useState<ShiftSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await queryShiftSummary(date);
      setData(resp);
    } catch (err) {
      handleApiError(err, '加载班次失败');
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    load();
  }, [load]);

  const doCheckIn = async (item: MobileShift) => {
    setActionLoadingId(item.shift_id);
    const result = await checkInShift(item.shift_id);
    setActionLoadingId(null);
    if (!result.ok) return showError(result.message);
    showSuccess(result.message);
    load();
  };

  const doCheckOut = async (item: MobileShift) => {
    setActionLoadingId(item.shift_id);
    const result = await checkOutShift(item.shift_id);
    setActionLoadingId(null);
    if (!result.ok) return showError(result.message);
    showSuccess(result.message);
    load();
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>班次页</div>
        <div className={styles.actions}>
          <ZButton size="sm" variant="ghost" onClick={() => setDate(dayjs(date).subtract(1, 'day').format('YYYY-MM-DD'))}>前一天</ZButton>
          <span className={styles.date}>{date}</span>
          <ZButton size="sm" variant="ghost" onClick={() => setDate(dayjs(date).add(1, 'day').format('YYYY-MM-DD'))}>后一天</ZButton>
        </div>
      </div>

      <div className={styles.body}>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : !data?.shifts?.length ? (
          <ZEmpty title="今日无班次" description="请联系店长确认排班" />
        ) : (
          data.shifts.map((item) => (
            <ZCard key={item.shift_id}>
              <div className={styles.rowTop}>
                <div>
                  <div className={styles.shiftName}>{item.shift_name}</div>
                  <div className={styles.meta}><ClockCircleOutlined /> {item.start_time} - {item.end_time}</div>
                  <div className={styles.meta}><CalendarOutlined /> {item.position_name}</div>
                </div>
                <ZBadge type={item.attendance_status === 'checked_in' ? 'success' : 'info'} text={ATTENDANCE_TEXT[item.attendance_status] || item.attendance_status} />
              </div>
              <div className={styles.footer}>
                <span>关联任务 {item.related_task_count} 项</span>
                <div className={styles.footerActions}>
                  {item.can_check_in && (
                    <ZButton size="sm" loading={actionLoadingId === item.shift_id} onClick={() => doCheckIn(item)}>去打卡</ZButton>
                  )}
                  {item.can_check_out && (
                    <ZButton size="sm" variant="ghost" loading={actionLoadingId === item.shift_id} onClick={() => doCheckOut(item)}>下班打卡</ZButton>
                  )}
                </div>
              </div>
            </ZCard>
          ))
        )}
      </div>
    </div>
  );
}
