/**
 * SM 订单详情页
 * 路由：/sm/banquet-orders/:orderId
 * 数据：GET /api/v1/banquet-agent/stores/{id}/orders/{order_id}
 *      PATCH /api/v1/banquet-agent/stores/{id}/orders/{order_id}/tasks/{task_id}
 *      GET/POST /api/v1/banquet-agent/stores/{id}/orders/{order_id}/contract
 *      PATCH /api/v1/banquet-agent/stores/{id}/orders/{order_id}/contract/sign
 *      POST /api/v1/banquet-agent/stores/{id}/orders/{order_id}/settle
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZInput,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './BanquetOrderDetail.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

const STATUS_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  draft:       { text: '待确认', type: 'warning' },
  confirmed:   { text: '已确认', type: 'success' },
  preparing:   { text: '准备中', type: 'info'    },
  in_progress: { text: '进行中', type: 'info'    },
  completed:   { text: '已完成', type: 'info'    },
  settled:     { text: '已结算', type: 'success' },
  closed:      { text: '已关闭', type: 'default' },
  cancelled:   { text: '已取消', type: 'default' },
};

const TASK_STATUS_BADGE: Record<string, { text: string; type: 'success' | 'info' | 'warning' | 'default' }> = {
  pending:     { text: '待处理', type: 'warning' },
  in_progress: { text: '进行中', type: 'info'    },
  done:        { text: '已完成', type: 'success' },
  verified:    { text: '已核验', type: 'success' },
  overdue:     { text: '已逾期', type: 'default' },
  closed:      { text: '已关闭', type: 'default' },
};

const ROLE_LABELS: Record<string, string> = {
  kitchen:  '厨房',
  service:  '服务',
  decor:    '布置',
  purchase: '采购',
  manager:  '店长',
};

const PAYMENT_TYPE_LABELS: Record<string, string> = {
  deposit: '定金',
  balance: '尾款',
  extra:   '附加款',
};

interface Task {
  task_id:     string;
  task_name:   string;
  task_type:   string;
  owner_role:  string;
  due_time:    string | null;
  status:      string;
  completed_at: string | null;
  remark:      string | null;
}

interface Payment {
  payment_id:     string;
  payment_type:   string;
  amount_yuan:    number;
  payment_method: string | null;
  paid_at:        string | null;
  receipt_no:     string | null;
}

interface OrderDetail {
  order_id:          string;
  banquet_type:      string;
  banquet_date:      string;
  people_count:      number;
  table_count:       number;
  contact_name:      string | null;
  contact_phone:     string | null;
  status:            string;
  deposit_status:    string;
  total_amount_yuan: number;
  paid_yuan:         number;
  balance_yuan:      number;
  hall_name:         string | null;
  slot_name:         string | null;
  remark:            string | null;
  tasks:             Task[];
  tasks_done:        number;
  tasks_total:       number;
  payments:          Payment[];
}

export default function SmBanquetOrderDetail() {
  const navigate = useNavigate();
  const { orderId } = useParams<{ orderId: string }>();

  const [order,   setOrder]   = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing,     setCompleting]     = useState<string | null>(null);
  const [contract,       setContract]       = useState<{
    contract_id: string; contract_no: string; contract_status: string;
    signed_at: string | null; file_url: string | null;
  } | null | undefined>(undefined);   // undefined = not loaded yet
  const [contractLoading, setContractLoading] = useState(false);
  const [contractWorking, setContractWorking] = useState(false);

  // 结算 Modal 状态
  const [settleOpen,     setSettleOpen]     = useState(false);
  const [settleRevenue,  setSettleRevenue]  = useState('');
  const [settleIngred,   setSettleIngred]   = useState('');
  const [settleLabor,    setSettleLabor]    = useState('');
  const [settleOther,    setSettleOther]    = useState('');
  const [settling,       setSettling]       = useState(false);

  // 确认订单
  const [confirming,     setConfirming]     = useState(false);

  const loadOrder = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}`,
      );
      setOrder(resp.data);
    } catch {
      setOrder(null);
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => { loadOrder(); }, [loadOrder]);

  const loadContract = useCallback(async () => {
    if (!orderId) return;
    setContractLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/contract`,
      );
      setContract(resp.data?.contract ?? null);
    } catch {
      setContract(null);
    } finally {
      setContractLoading(false);
    }
  }, [orderId]);

  useEffect(() => { loadContract(); }, [loadContract]);

  const createContract = async () => {
    setContractWorking(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/contract`,
      );
      await loadContract();
    } catch (e) {
      handleApiError(e, '创建合同失败');
    } finally {
      setContractWorking(false);
    }
  };

  const signContract = async () => {
    setContractWorking(true);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/contract/sign`,
      );
      await loadContract();
    } catch (e) {
      handleApiError(e, '签约失败');
    } finally {
      setContractWorking(false);
    }
  };

  const toggleTask = async (task: Task) => {
    const newStatus = task.status === 'done' ? 'pending' : 'done';
    setCompleting(task.task_id);
    try {
      await apiClient.patch(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/tasks/${task.task_id}`,
        { status: newStatus },
      );
      await loadOrder();
    } catch (e) {
      handleApiError(e, '更新任务失败');
    } finally {
      setCompleting(null);
    }
  };

  const openSettleModal = () => {
    if (!order) return;
    setSettleRevenue(String(order.total_amount_yuan));
    setSettleIngred('');
    setSettleLabor('');
    setSettleOther('');
    setSettleOpen(true);
  };

  const confirmOrder = async () => {
    setConfirming(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/confirm`,
      );
      await loadOrder();
    } catch (e) {
      handleApiError(e, '确认订单失败');
    } finally {
      setConfirming(false);
    }
  };

  const handleSettle = async () => {
    setSettling(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/settle`,
        {
          revenue_yuan:         parseFloat(settleRevenue) || 0,
          ingredient_cost_yuan: parseFloat(settleIngred)  || 0,
          labor_cost_yuan:      parseFloat(settleLabor)   || 0,
          other_cost_yuan:      parseFloat(settleOther)   || 0,
        },
      );
      setSettleOpen(false);
      await loadOrder();
    } catch (e) {
      handleApiError(e, '结算失败');
    } finally {
      setSettling(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
          <div className={styles.title}>订单详情</div>
        </div>
        <div className={styles.body}><ZSkeleton rows={6} /></div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
          <div className={styles.title}>订单详情</div>
        </div>
        <div className={styles.body}>
          <ZEmpty title="订单不存在" description="请返回重试" />
        </div>
      </div>
    );
  }

  const statusBadge = STATUS_BADGE[order.status] ?? { text: order.status, type: 'default' as const };
  const donePct = order.tasks_total > 0
    ? Math.round(order.tasks_done / order.tasks_total * 100)
    : 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)}>← 返回</button>
        <div className={styles.title}>订单详情</div>
      </div>

      <div className={styles.body}>
        {/* 基本信息 */}
        <ZCard>
          <div className={styles.sectionTitle}>基本信息</div>
          <div className={styles.infoGrid}>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>宴会类型</span>
              <span className={styles.infoValue}>{order.banquet_type}</span>
            </div>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>宴会日期</span>
              <span className={styles.infoValue}>{dayjs(order.banquet_date).format('YYYY-MM-DD')}</span>
            </div>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>桌数/人数</span>
              <span className={styles.infoValue}>{order.table_count}桌 · {order.people_count}人</span>
            </div>
            {order.hall_name && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>宴会厅</span>
                <span className={styles.infoValue}>{order.hall_name}</span>
              </div>
            )}
            {order.contact_name && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>联系人</span>
                <span className={styles.infoValue}>{order.contact_name}</span>
              </div>
            )}
            {order.contact_phone && (
              <div className={styles.infoItem}>
                <span className={styles.infoLabel}>电话</span>
                <span className={styles.infoValue}>{order.contact_phone}</span>
              </div>
            )}
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>状态</span>
              <ZBadge type={statusBadge.type} text={statusBadge.text} />
            </div>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>合同总额</span>
              <span className={styles.infoValue}>¥{order.total_amount_yuan.toLocaleString()}</span>
            </div>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>已付</span>
              <span className={styles.infoValue}>¥{order.paid_yuan.toLocaleString()}</span>
            </div>
            <div className={styles.infoItem}>
              <span className={styles.infoLabel}>尾款</span>
              <span className={`${styles.infoValue} ${order.balance_yuan > 0 ? styles.balanceDue : ''}`}>
                ¥{order.balance_yuan.toLocaleString()}
              </span>
            </div>
          </div>
          {order.remark && <div className={styles.remark}>{order.remark}</div>}
          {order.status === 'draft' && (
            <div className={styles.settleRow}>
              <ZButton
                variant="primary"
                size="sm"
                onClick={confirmOrder}
                disabled={confirming}
              >
                {confirming ? '确认中…' : '确认订单'}
              </ZButton>
            </div>
          )}
          {order.status === 'completed' && (
            <div className={styles.settleRow}>
              <ZButton variant="primary" size="sm" onClick={openSettleModal}>
                结算确认
              </ZButton>
            </div>
          )}
        </ZCard>

        {/* 执行任务 */}
        <ZCard>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>执行任务</div>
            <span className={styles.taskProgress}>{order.tasks_done}/{order.tasks_total}</span>
          </div>
          {order.tasks_total > 0 && (
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${donePct}%` }} />
            </div>
          )}
          {order.tasks.length === 0 ? (
            <ZEmpty title="暂无执行任务" description="订单确认后自动生成" />
          ) : (
            <div className={styles.taskList}>
              {order.tasks.map(task => {
                const tb = TASK_STATUS_BADGE[task.status] ?? { text: task.status, type: 'default' as const };
                const isDone = task.status === 'done' || task.status === 'verified';
                return (
                  <div key={task.task_id} className={`${styles.taskRow} ${isDone ? styles.taskDone : ''}`}>
                    <div className={styles.taskLeft}>
                      <div className={styles.taskName}>{task.task_name}</div>
                      <div className={styles.taskMeta}>
                        {ROLE_LABELS[task.owner_role] ?? task.owner_role}
                        {task.due_time ? ` · ${dayjs(task.due_time).format('MM-DD HH:mm')}` : ''}
                      </div>
                    </div>
                    <div className={styles.taskRight}>
                      <ZBadge type={tb.type} text={tb.text} />
                      {!isDone && (
                        <ZButton
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleTask(task)}
                          disabled={completing === task.task_id}
                        >
                          {completing === task.task_id ? '…' : '完成'}
                        </ZButton>
                      )}
                      {isDone && (
                        <ZButton
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleTask(task)}
                          disabled={completing === task.task_id}
                        >
                          撤销
                        </ZButton>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ZCard>

        {/* 付款记录 */}
        <ZCard>
          <div className={styles.sectionTitle}>付款记录</div>
          {order.payments.length === 0 ? (
            <ZEmpty title="暂无付款记录" description="登记收款后显示" />
          ) : (
            <div className={styles.paymentList}>
              {order.payments.map(p => (
                <div key={p.payment_id} className={styles.paymentRow}>
                  <div className={styles.paymentLeft}>
                    <div className={styles.paymentType}>
                      {PAYMENT_TYPE_LABELS[p.payment_type] ?? p.payment_type}
                    </div>
                    <div className={styles.paymentMeta}>
                      {p.payment_method ?? ''}
                      {p.paid_at ? ` · ${dayjs(p.paid_at).format('MM-DD HH:mm')}` : ''}
                    </div>
                  </div>
                  <div className={styles.paymentAmount}>¥{p.amount_yuan.toLocaleString()}</div>
                </div>
              ))}
            </div>
          )}
        </ZCard>

        {/* 合同管理 */}
        <ZCard>
          <div className={styles.sectionTitle}>合同</div>
          {contractLoading ? (
            <ZSkeleton rows={2} />
          ) : contract === null ? (
            <div className={styles.contractEmpty}>
              <span className={styles.contractHint}>尚未创建合同</span>
              <ZButton variant="primary" size="sm" onClick={createContract} disabled={contractWorking}>
                {contractWorking ? '创建中…' : '创建合同'}
              </ZButton>
            </div>
          ) : contract ? (
            <div className={styles.contractInfo}>
              <div className={styles.contractRow}>
                <span className={styles.contractNo}>{contract.contract_no}</span>
                <ZBadge
                  type={contract.contract_status === 'signed' ? 'success' : 'warning'}
                  text={contract.contract_status === 'signed' ? '已签约' : contract.contract_status === 'void' ? '已作废' : '草稿'}
                />
              </div>
              {contract.signed_at && (
                <div className={styles.contractMeta}>
                  签约时间：{dayjs(contract.signed_at).format('YYYY-MM-DD HH:mm')}
                </div>
              )}
              {contract.contract_status === 'draft' && (
                <ZButton variant="primary" size="sm" onClick={signContract} disabled={contractWorking}>
                  {contractWorking ? '签约中…' : '确认签约'}
                </ZButton>
              )}
            </div>
          ) : null}
        </ZCard>
      </div>

      {/* 结算 Modal */}
      {order && (() => {
        const revenue  = parseFloat(settleRevenue)  || 0;
        const ingred   = parseFloat(settleIngred)   || 0;
        const labor    = parseFloat(settleLabor)    || 0;
        const other    = parseFloat(settleOther)    || 0;
        const profit   = revenue - ingred - labor - other;
        const margin   = revenue > 0 ? (profit / revenue * 100).toFixed(1) : '0.0';
        return (
          <ZModal
            open={settleOpen}
            title="宴会结算 — 录入利润数据"
            onClose={() => setSettleOpen(false)}
            footer={
              <div className={styles.settleFooter}>
                <ZButton variant="ghost" onClick={() => setSettleOpen(false)}>取消</ZButton>
                <ZButton
                  variant="primary"
                  onClick={handleSettle}
                  disabled={settling || !settleRevenue}
                >
                  {settling ? '结算中…' : '确认结算'}
                </ZButton>
              </div>
            }
          >
            <div className={styles.settleForm}>
              <div className={styles.settleField}>
                <label className={styles.settleLabel}>实收金额（元）</label>
                <ZInput
                  type="number"
                  value={settleRevenue}
                  onChange={e => setSettleRevenue(e.target.value)}
                  placeholder="如：50000"
                />
              </div>
              <div className={styles.settleField}>
                <label className={styles.settleLabel}>食材成本（元）</label>
                <ZInput
                  type="number"
                  value={settleIngred}
                  onChange={e => setSettleIngred(e.target.value)}
                  placeholder="如：15000"
                />
              </div>
              <div className={styles.settleField}>
                <label className={styles.settleLabel}>人工成本（元）</label>
                <ZInput
                  type="number"
                  value={settleLabor}
                  onChange={e => setSettleLabor(e.target.value)}
                  placeholder="如：5000"
                />
              </div>
              <div className={styles.settleField}>
                <label className={styles.settleLabel}>其他成本（元，选填）</label>
                <ZInput
                  type="number"
                  value={settleOther}
                  onChange={e => setSettleOther(e.target.value)}
                  placeholder="如：1000"
                />
              </div>
              <div className={styles.settleSummary}>
                <span>毛利：<strong className={profit >= 0 ? styles.settlePos : styles.settleNeg}>
                  ¥{profit.toLocaleString()}
                </strong></span>
                <span>毛利率：<strong>{margin}%</strong></span>
              </div>
            </div>
          </ZModal>
        );
      })()}
    </div>
  );
}
