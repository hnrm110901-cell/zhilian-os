/**
 * SM 推送通知页
 * 路由：/sm/banquet-push
 * 数据：POST /api/v1/banquet-agent/stores/{id}/push/scan
 *      GET  /api/v1/banquet-agent/stores/{id}/push/records
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetPush.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

const PUSH_TYPE_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  banquet_reminder: { text: '宴会提醒', type: 'info'    },
  task_overdue:     { text: '任务逾期', type: 'warning' },
  lead_stale:       { text: '线索停滞', type: 'default' },
};

interface PushRecord {
  record_id: string;
  push_type: string;
  target_id: string;
  content:   string;
  status:    string;
  sent_at:   string;
}

interface ScanResult {
  sent:    number;
  skipped: number;
  details: { type: string; content: string; status: string }[];
}

export default function SmBanquetPush() {
  const navigate = useNavigate();

  const [records,  setRecords]  = useState<PushRecord[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [scanning, setScanning] = useState(false);
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/push/records`,
      );
      setRecords(resp.data?.records ?? []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  const handleScan = async () => {
    setScanning(true);
    setLastScan(null);
    try {
      const resp = await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/push/scan`,
      );
      setLastScan(resp.data);
      await loadRecords();
    } catch (e) {
      handleApiError(e, '推送扫描失败');
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate('/sm/banquet')}>← 返回</button>
        <div className={styles.title}>推送通知</div>
      </div>

      <div className={styles.body}>
        {/* 操作卡 */}
        <ZCard>
          <div className={styles.scanHeader}>
            <div>
              <div className={styles.scanTitle}>宴会通知推送</div>
              <div className={styles.scanHint}>扫描 D-7/D-1 宴会提醒、逾期任务、停滞线索</div>
            </div>
            <ZButton variant="primary" onClick={handleScan} disabled={scanning}>
              {scanning ? '扫描中…' : '扫描并推送'}
            </ZButton>
          </div>
          {lastScan && (
            <div className={styles.scanResult}>
              <span className={styles.scanSent}>已推送 {lastScan.sent} 条</span>
              {lastScan.skipped > 0 && (
                <span className={styles.scanSkipped}>跳过 {lastScan.skipped} 条</span>
              )}
              {lastScan.sent === 0 && <span className={styles.scanEmpty}>暂无需推送的内容</span>}
            </div>
          )}
        </ZCard>

        {/* 推送记录 */}
        <ZCard>
          <div className={styles.sectionTitle}>推送记录（近30天）</div>
          {loading ? (
            <ZSkeleton rows={4} />
          ) : records.length === 0 ? (
            <ZEmpty title="暂无推送记录" description="点击「扫描并推送」发送通知" />
          ) : (
            <div className={styles.list}>
              {records.map(r => {
                const badge = PUSH_TYPE_BADGE[r.push_type] ?? { text: r.push_type, type: 'default' as const };
                return (
                  <div key={r.record_id} className={styles.row}>
                    <div className={styles.rowLeft}>
                      <ZBadge type={badge.type} text={badge.text} />
                      <div className={styles.content}>{r.content}</div>
                    </div>
                    <div className={styles.rowRight}>
                      <div className={styles.time}>
                        {dayjs(r.sent_at).format('MM-DD HH:mm')}
                      </div>
                      <ZBadge
                        type={r.status === 'sent' ? 'success' : 'default'}
                        text={r.status === 'sent' ? '已发送' : r.status}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ZCard>
      </div>
    </div>
  );
}
