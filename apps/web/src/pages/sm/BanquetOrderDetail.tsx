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
  ZCard, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZInput, ZSelect,
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

  // BEO 执行单 Modal state
  const [beoOpen,    setBeoOpen]    = useState(false);
  const [beoData,    setBeoData]    = useState<{
    order_id: string;
    banquet_type: string;
    banquet_date: string;
    contact_name: string | null;
    contact_phone: string | null;
    people_count: number;
    table_count: number;
    hall_name: string | null;
    package_name: string | null;
    total_amount_yuan: number;
    paid_yuan: number;
    balance_yuan: number;
    tasks_by_role: Record<string, { task_id: string; task_name: string; due_time: string | null; status: string }[]>;
  } | null>(null);
  const [beoLoading, setBeoLoading] = useState(false);

  // 登记收款 Modal state
  const [payOpen,    setPayOpen]    = useState(false);
  const [payAmount,  setPayAmount]  = useState('');
  const [payType,    setPayType]    = useState('balance');
  const [payMethod,  setPayMethod]  = useState('');
  const [paying,     setPaying]     = useState(false);

  // 添加自定义任务 Modal state
  const [addTaskOpen,    setAddTaskOpen]    = useState(false);
  const [newTaskName,    setNewTaskName]    = useState('');
  const [newTaskRole,    setNewTaskRole]    = useState('kitchen');
  const [newTaskDueTime, setNewTaskDueTime] = useState('');
  const [addingTask,     setAddingTask]     = useState(false);

  // 订单时间轴 state
  interface TimelineEvent {
    time:       string;
    event_type: string;
    title:      string;
    detail:     string | null;
  }
  const [timeline,        setTimeline]        = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  // 上报异常 state
  interface ExceptionItem {
    id:             string;
    exception_type: string;
    description:    string;
    severity:       string;
    status:         string;
    created_at:     string;
  }
  const [exceptions,    setExceptions]    = useState<ExceptionItem[]>([]);
  const [excLoading,    setExcLoading]    = useState(false);
  const [excOpen,       setExcOpen]       = useState(false);
  const [excType,       setExcType]       = useState('late');
  const [excDesc,       setExcDesc]       = useState('');
  const [excSeverity,   setExcSeverity]   = useState('medium');
  const [reporting,     setReporting]     = useState(false);

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

  const loadTimeline = useCallback(async () => {
    if (!orderId) return;
    setTimelineLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/timeline`,
      );
      setTimeline(resp.data?.events ?? []);
    } catch {
      setTimeline([]);
    } finally {
      setTimelineLoading(false);
    }
  }, [orderId]);

  useEffect(() => { loadTimeline(); }, [loadTimeline]);

  const loadExceptions = useCallback(async () => {
    if (!orderId) return;
    setExcLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/exceptions`,
        { params: { order_id: orderId } },
      );
      setExceptions(Array.isArray(resp.data) ? resp.data : []);
    } catch {
      setExceptions([]);
    } finally {
      setExcLoading(false);
    }
  }, [orderId]);

  useEffect(() => { loadExceptions(); }, [loadExceptions]);

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

  const openBeo = async () => {
    setBeoOpen(true);
    if (beoData) return;  // already loaded
    setBeoLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/beo`,
      );
      setBeoData(resp.data);
    } catch (e) {
      handleApiError(e, '加载 BEO 失败');
    } finally {
      setBeoLoading(false);
    }
  };

  const PAYMENT_TYPE_OPTIONS = [
    { value: 'deposit', label: '定金' },
    { value: 'balance', label: '尾款' },
    { value: 'extra',   label: '附加款' },
  ];

  const PAYMENT_METHOD_OPTIONS = [
    { value: '',        label: '不指定' },
    { value: '现金',    label: '现金' },
    { value: '转账',    label: '转账' },
    { value: '微信',    label: '微信' },
    { value: '支付宝',  label: '支付宝' },
  ];

  const openPayModal = () => {
    setPayAmount(order?.balance_yuan ? String(order.balance_yuan) : '');
    setPayType('balance');
    setPayMethod('');
    setPayOpen(true);
  };

  const handlePayment = async () => {
    if (!payAmount) return;
    setPaying(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/payment`,
        {
          amount_yuan:    parseFloat(payAmount),
          payment_type:   payType,
          payment_method: payMethod || null,
        },
      );
      setPayOpen(false);
      setBeoData(null);  // invalidate cached BEO
      await loadOrder();
    } catch (e) {
      handleApiError(e, '登记收款失败');
    } finally {
      setPaying(false);
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

  const handleAddTask = async () => {
    if (!newTaskName || !newTaskDueTime) return;
    setAddingTask(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/tasks`,
        { task_name: newTaskName, owner_role: newTaskRole, due_time: newTaskDueTime },
      );
      setAddTaskOpen(false);
      setNewTaskName('');
      setNewTaskDueTime('');
      setNewTaskRole('kitchen');
      await loadOrder();
      await loadTimeline();
    } catch (e) {
      handleApiError(e, '添加任务失败');
    } finally {
      setAddingTask(false);
    }
  };

  const handleReportException = async () => {
    if (!excDesc.trim()) return;
    setReporting(true);
    try {
      await apiClient.post(
        `/api/v1/banquet-agent/stores/${STORE_ID}/orders/${orderId}/exceptions`,
        { exception_type: excType, description: excDesc.trim(), severity: excSeverity },
      );
      setExcOpen(false);
      setExcDesc('');
      setExcType('late');
      setExcSeverity('medium');
      await loadExceptions();
    } catch (e) {
      handleApiError(e, '上报异常失败');
    } finally {
      setReporting(false);
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
          <div className={styles.settleRow}>
            {order.status === 'draft' && (
              <ZButton
                variant="primary"
                size="sm"
                onClick={confirmOrder}
                disabled={confirming}
              >
                {confirming ? '确认中…' : '确认订单'}
              </ZButton>
            )}
            {order.status === 'completed' && (
              <ZButton variant="primary" size="sm" onClick={openSettleModal}>
                结算确认
              </ZButton>
            )}
            {['confirmed', 'preparing', 'in_progress', 'completed'].includes(order.status) && (
              <ZButton variant="ghost" size="sm" onClick={openBeo}>
                查看 BEO
              </ZButton>
            )}
          </div>
        </ZCard>

        {/* 执行任务 */}
        <ZCard>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>执行任务</div>
            <div className={styles.sectionHeaderRight}>
              <span className={styles.taskProgress}>{order.tasks_done}/{order.tasks_total}</span>
              {['confirmed', 'preparing', 'in_progress'].includes(order.status) && (
                <ZButton variant="ghost" size="sm" onClick={() => setAddTaskOpen(true)}>＋ 添加任务</ZButton>
              )}
            </div>
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
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>付款记录</div>
            {['confirmed', 'preparing', 'in_progress', 'completed'].includes(order.status) && order.balance_yuan > 0 && (
              <ZButton variant="ghost" size="sm" onClick={openPayModal}>＋ 登记收款</ZButton>
            )}
          </div>
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

        {/* 订单时间轴 */}
        <ZCard>
          <div className={styles.sectionTitle}>操作日志</div>
          {timelineLoading ? (
            <ZSkeleton rows={3} />
          ) : timeline.length === 0 ? (
            <ZEmpty title="暂无操作记录" description="收款或任务完成后显示" />
          ) : (
            <div className={styles.timeline}>
              {timeline.map((ev, i) => (
                <div key={i} className={styles.tlRow}>
                  <div className={styles.tlIcon}>
                    {ev.event_type === 'payment'   ? '💰' :
                     ev.event_type === 'task_done' ? '✅' : '🤖'}
                  </div>
                  <div className={styles.tlContent}>
                    <div className={styles.tlTitle}>{ev.title}</div>
                    {ev.detail && <div className={styles.tlDetail}>{ev.detail}</div>}
                    <div className={styles.tlTime}>{dayjs(ev.time).format('MM-DD HH:mm')}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ZCard>

        {/* 异常事件 */}
        <ZCard>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>异常事件</div>
            {['confirmed', 'preparing', 'in_progress'].includes(order.status) && (
              <ZButton variant="ghost" size="sm" onClick={() => setExcOpen(true)}>上报异常</ZButton>
            )}
          </div>
          {excLoading ? (
            <ZSkeleton rows={2} />
          ) : exceptions.length === 0 ? (
            <ZEmpty title="暂无异常" description="发现问题可在此上报" />
          ) : (
            <div className={styles.excList}>
              {exceptions.map(exc => (
                <div
                  key={exc.id}
                  className={`${styles.excRow} ${exc.severity === 'high' ? styles.excHigh : ''}`}
                >
                  <div className={styles.excLeft}>
                    <div className={styles.excType}>{exc.exception_type}</div>
                    <div className={styles.excDesc}>{exc.description}</div>
                    <div className={styles.excTime}>{dayjs(exc.created_at).format('MM-DD HH:mm')}</div>
                  </div>
                  <ZBadge
                    type={exc.status === 'resolved' ? 'success' : exc.severity === 'high' ? 'default' : 'warning'}
                    text={exc.status === 'resolved' ? '已处理' : exc.severity === 'high' ? '严重' : exc.severity === 'medium' ? '中度' : '轻微'}
                  />
                </div>
              ))}
            </div>
          )}
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

      {/* BEO 执行单 Modal */}
      <ZModal
        open={beoOpen}
        title="BEO 执行单"
        onClose={() => setBeoOpen(false)}
        footer={
          <div className={styles.settleFooter}>
            <ZButton variant="ghost" onClick={() => setBeoOpen(false)}>关闭</ZButton>
          </div>
        }
      >
        {beoLoading ? (
          <ZSkeleton rows={5} />
        ) : beoData ? (
          <div className={styles.beoBody}>
            {beoData.balance_yuan > 0 && (
              <div className={styles.beoAlert}>
                ⚠️ 未收尾款：¥{beoData.balance_yuan.toLocaleString()}
              </div>
            )}
            <div className={styles.beoMeta}>
              <span>{beoData.banquet_type} · {dayjs(beoData.banquet_date).format('YYYY-MM-DD')}</span>
              <span>{beoData.table_count}桌 · {beoData.people_count}人</span>
              {beoData.hall_name && <span>宴会厅：{beoData.hall_name}</span>}
              {beoData.package_name && <span>套餐：{beoData.package_name}</span>}
            </div>
            {Object.keys(beoData.tasks_by_role).length === 0 ? (
              <ZEmpty title="暂无任务" description="确认订单后自动生成" />
            ) : (
              Object.entries(beoData.tasks_by_role).map(([role, tasks]) => (
                <div key={role} className={styles.beoRoleGroup}>
                  <div className={styles.beoRoleTitle}>
                    {ROLE_LABELS[role] ?? role}（{tasks.length}）
                  </div>
                  {tasks.map(t => {
                    const tb = TASK_STATUS_BADGE[t.status] ?? { text: t.status, type: 'default' as const };
                    return (
                      <div key={t.task_id} className={styles.beoTaskRow}>
                        <span className={styles.beoTaskName}>{t.task_name}</span>
                        <div className={styles.beoTaskRight}>
                          {t.due_time && (
                            <span className={styles.beoTaskTime}>{dayjs(t.due_time).format('HH:mm')}</span>
                          )}
                          <ZBadge type={tb.type} text={tb.text} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        ) : (
          <ZEmpty title="加载失败" description="请关闭后重试" />
        )}
      </ZModal>

      {/* 登记收款 Modal */}
      <ZModal
        open={payOpen}
        title="登记收款"
        onClose={() => setPayOpen(false)}
        footer={
          <div className={styles.settleFooter}>
            <ZButton variant="ghost" onClick={() => setPayOpen(false)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handlePayment}
              disabled={paying || !payAmount}
            >
              {paying ? '提交中…' : '确认收款'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.settleForm}>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>收款金额（元）</label>
            <ZInput
              type="number"
              value={payAmount}
              onChange={e => setPayAmount(e.target.value)}
              placeholder="如：10000"
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>收款类型</label>
            <ZSelect
              value={payType}
              options={PAYMENT_TYPE_OPTIONS}
              onChange={v => setPayType(v as string)}
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>支付方式（选填）</label>
            <ZSelect
              value={payMethod}
              options={PAYMENT_METHOD_OPTIONS}
              onChange={v => setPayMethod(v as string)}
            />
          </div>
        </div>
      </ZModal>

      {/* 添加自定义任务 Modal */}
      <ZModal
        open={addTaskOpen}
        title="添加任务"
        onClose={() => setAddTaskOpen(false)}
        footer={
          <div className={styles.settleFooter}>
            <ZButton variant="ghost" onClick={() => setAddTaskOpen(false)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleAddTask}
              disabled={addingTask || !newTaskName || !newTaskDueTime}
            >
              {addingTask ? '添加中…' : '确认添加'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.settleForm}>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>任务名称</label>
            <ZInput
              value={newTaskName}
              onChange={e => setNewTaskName(e.target.value)}
              placeholder="如：额外备餐"
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>负责角色</label>
            <ZSelect
              value={newTaskRole}
              options={[
                { value: 'kitchen',  label: '厨房' },
                { value: 'service',  label: '服务' },
                { value: 'decor',    label: '布置' },
                { value: 'purchase', label: '采购' },
                { value: 'manager',  label: '店长' },
              ]}
              onChange={v => setNewTaskRole(v as string)}
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>截止时间</label>
            <ZInput
              type="datetime-local"
              value={newTaskDueTime}
              onChange={e => setNewTaskDueTime(e.target.value)}
            />
          </div>
        </div>
      </ZModal>
      {/* 上报异常 Modal */}
      <ZModal
        open={excOpen}
        title="上报异常事件"
        onClose={() => setExcOpen(false)}
        footer={
          <div className={styles.settleFooter}>
            <ZButton variant="ghost" onClick={() => setExcOpen(false)}>取消</ZButton>
            <ZButton
              variant="primary"
              onClick={handleReportException}
              disabled={reporting || !excDesc.trim()}
            >
              {reporting ? '提交中…' : '上报'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.settleForm}>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>异常类型</label>
            <ZSelect
              value={excType}
              options={[
                { value: 'late',      label: '迟到/延误' },
                { value: 'missing',   label: '物品缺失' },
                { value: 'quality',   label: '质量问题' },
                { value: 'complaint', label: '客诉' },
              ]}
              onChange={v => setExcType(v as string)}
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>异常描述</label>
            <ZInput
              value={excDesc}
              onChange={e => setExcDesc(e.target.value)}
              placeholder="描述具体情况…"
            />
          </div>
          <div className={styles.settleField}>
            <label className={styles.settleLabel}>严重程度</label>
            <ZSelect
              value={excSeverity}
              options={[
                { value: 'low',    label: '轻微' },
                { value: 'medium', label: '中度' },
                { value: 'high',   label: '严重' },
              ]}
              onChange={v => setExcSeverity(v as string)}
            />
          </div>
        </div>
      </ZModal>
    </div>
  );
}
