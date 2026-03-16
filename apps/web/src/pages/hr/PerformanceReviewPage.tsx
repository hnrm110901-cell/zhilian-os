import React, { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../../services/api';
import styles from './HRPages.module.css';

interface ReviewItem {
  id: string;
  employee_id: string;
  employee_name: string;
  position: string;
  review_period: string;
  status: string;
  total_score: number;
  level: string | null;
  performance_coefficient: number;
}

const LEVEL_COLORS: Record<string, string> = {
  S: '#0AAF9A', A: '#27AE60', B: '#2D9CDB', C: '#F2994A', D: '#EB5757',
};

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', self_review: '自评中', manager: '上级评中',
  completed: '已完成', appealed: '申诉中',
};

const PerformanceReviewPage: React.FC = () => {
  const [storeId] = useState('STORE_001');
  const [period, setPeriod] = useState('2026-Q1');
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/hr/performance/reviews?store_id=${storeId}&period=${period}`
      );
      setItems(res.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [storeId, period]);

  useEffect(() => { load(); }, [load]);

  // 统计
  const completed = items.filter(i => i.status === 'completed');
  const avgScore = completed.length > 0
    ? (completed.reduce((s, i) => s + i.total_score, 0) / completed.length).toFixed(1)
    : '-';
  const levelDist = completed.reduce((acc, i) => {
    if (i.level) acc[i.level] = (acc[i.level] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>绩效考核</h1>
          <p className={styles.pageDesc}>考核评分、等级分布与绩效系数</p>
        </div>
        <div className={styles.headerActions}>
          <select className={styles.monthPicker} value={period} onChange={e => setPeriod(e.target.value)}>
            <option value="2026-Q1">2026年Q1</option>
            <option value="2026-Q2">2026年Q2</option>
            <option value="2026-03">2026年3月</option>
            <option value="2026-02">2026年2月</option>
          </select>
        </div>
      </div>

      {/* 统计 */}
      <div className={styles.statGrid}>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>考核总人数</div>
          <div className={styles.statValue}>{items.length}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>已完成</div>
          <div className={styles.statValueMint}>{completed.length}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>平均分</div>
          <div className={styles.statValue}>{avgScore}</div>
        </div>
        {['S', 'A', 'B', 'C', 'D'].map(l => (
          <div className={styles.statCard} key={l}>
            <div className={styles.statLabel}>{l}级</div>
            <div className={styles.statValue} style={{ color: LEVEL_COLORS[l] }}>
              {levelDist[l] || 0}
            </div>
          </div>
        ))}
      </div>

      {/* 列表 */}
      <div className={styles.section}>
        {loading ? (
          <div className={styles.loadingWrap}>加载中...</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>员工</th>
                  <th>岗位</th>
                  <th>考核期</th>
                  <th>状态</th>
                  <th>综合分</th>
                  <th>等级</th>
                  <th>绩效系数</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id}>
                    <td className={styles.cellName}>{item.employee_name}</td>
                    <td>{item.position || '-'}</td>
                    <td>{item.review_period}</td>
                    <td>{STATUS_LABELS[item.status] || item.status}</td>
                    <td>{item.total_score || '-'}</td>
                    <td>
                      {item.level && (
                        <span className={styles.levelBadge} style={{
                          color: LEVEL_COLORS[item.level],
                          borderColor: LEVEL_COLORS[item.level],
                        }}>
                          {item.level}
                        </span>
                      )}
                    </td>
                    <td>{item.performance_coefficient}x</td>
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

export default PerformanceReviewPage;
