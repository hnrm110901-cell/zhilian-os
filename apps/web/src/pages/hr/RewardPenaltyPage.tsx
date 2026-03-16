/**
 * 奖惩管理页面
 * 路由: /reward-penalty
 * 功能: 奖惩记录列表 + 提交 + 审批
 */
import React, { useCallback, useEffect, useState } from 'react';
import { hrService } from '../../services/hrService';
import type { RewardPenaltyItem } from '../../services/hrService';
import styles from './RewardPenaltyPage.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'STORE_001';

const CATEGORY_LABELS: Record<string, string> = {
  service_excellence: '服务之星', sales_champion: '销售冠军',
  zero_waste: '零损耗奖', innovation: '创新奖',
  attendance_perfect: '全勤奖', team_contribution: '团队贡献',
  customer_praise: '顾客表扬',
  food_safety: '食品安全违规', hygiene: '卫生违规',
  discipline: '纪律违规', customer_complaint: '顾客投诉',
  equipment_damage: '设备损坏', waste_excess: '超额损耗',
  other: '其他',
};

const STATUS_LABELS: Record<string, string> = {
  pending: '待审批', approved: '已批准', rejected: '已驳回', cancelled: '已取消',
};

const RewardPenaltyPage: React.FC = () => {
  const [items, setItems] = useState<RewardPenaltyItem[]>([]);
  const [filter, setFilter] = useState<'all' | 'reward' | 'penalty'>('all');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: { rp_type?: string } = {};
      if (filter !== 'all') params.rp_type = filter;
      const data = await hrService.getRewardPenalties(STORE_ID, params);
      setItems(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id: string) => {
    try {
      await hrService.approveRewardPenalty(id);
      load();
    } catch { /* silent */ }
  };

  const handleReject = async (id: string) => {
    try {
      await hrService.rejectRewardPenalty(id, '管理员驳回');
      load();
    } catch { /* silent */ }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>奖惩管理</h1>
        <div className={styles.tabs}>
          {(['all', 'reward', 'penalty'] as const).map(t => (
            <button
              key={t}
              className={`${styles.tab} ${filter === t ? styles.tabActive : ''}`}
              onClick={() => setFilter(t)}
            >
              {t === 'all' ? '全部' : t === 'reward' ? '奖励' : '罚款'}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className={styles.empty}>加载中...</div>
      ) : items.length === 0 ? (
        <div className={styles.empty}>暂无奖惩记录</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>员工</th>
                <th>类型</th>
                <th>分类</th>
                <th>金额(元)</th>
                <th>事件日期</th>
                <th>描述</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(r => (
                <tr key={r.id}>
                  <td>{r.employee_name}</td>
                  <td>
                    <span className={r.rp_type === 'reward' ? styles.tagReward : styles.tagPenalty}>
                      {r.rp_type === 'reward' ? '奖励' : '罚款'}
                    </span>
                  </td>
                  <td>{CATEGORY_LABELS[r.category] || r.category}</td>
                  <td className={r.rp_type === 'reward' ? styles.amountGreen : styles.amountRed}>
                    {r.rp_type === 'reward' ? '+' : '-'}{r.amount_yuan.toFixed(2)}
                  </td>
                  <td>{r.incident_date}</td>
                  <td className={styles.desc}>{r.description}</td>
                  <td>
                    <span className={styles[`status_${r.status}`] || ''}>
                      {STATUS_LABELS[r.status] || r.status}
                    </span>
                  </td>
                  <td>
                    {r.status === 'pending' && (
                      <div className={styles.actions}>
                        <button className={styles.btnApprove} onClick={() => handleApprove(r.id)}>
                          批准
                        </button>
                        <button className={styles.btnReject} onClick={() => handleReject(r.id)}>
                          驳回
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default RewardPenaltyPage;
