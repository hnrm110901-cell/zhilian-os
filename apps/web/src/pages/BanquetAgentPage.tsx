import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';

import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZButton, ZCard, ZKpi, ZSkeleton, ZEmpty } from '../design-system/components';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';

const { Text } = Typography;

const STORE_ID = localStorage.getItem('store_id') || 'STORE001';

type LeadStage =
  | 'new'
  | 'contacted'
  | 'visit_scheduled'
  | 'quoted'
  | 'waiting_decision'
  | 'deposit_pending'
  | 'won'
  | 'lost';

interface DashboardResp {
  store_id: string;
  year: number;
  month: number;
  revenue_yuan: number;
  gross_profit_yuan: number;
  order_count: number;
  lead_count: number;
  conversion_rate_pct: number;
  hall_utilization_pct: number;
  summary: string;
}

interface LeadItem {
  id: string;
  banquet_type: string;
  expected_date: string | null;
  expected_people_count: number | null;
  expected_budget_yuan: number;
  current_stage: LeadStage;
  owner_user_id: string | null;
  last_followup_at: string | null;
}

interface LeadListResp {
  total: number;
  items: LeadItem[];
}

interface OrderItem {
  id: string;
  banquet_type: string;
  banquet_date: string;
  people_count: number;
  table_count: number;
  order_status: string;
  deposit_status: string;
  total_amount_yuan: number;
  paid_yuan: number;
  balance_yuan: number;
}

interface OrderListResp {
  total: number;
  items: OrderItem[];
}

interface FollowupScanResp {
  stale_lead_count: number;
  items: Array<{ lead_id: string; summary?: string; suggestion?: string }>;
}

interface QuoteRecommendResp {
  items?: Array<{ package_id?: string; package_name?: string; total_amount_yuan?: number; gross_profit_yuan?: number }>;
  [key: string]: unknown;
}

interface HallRecommendResp {
  items?: Array<{ hall_id?: string; hall_name?: string; slot_name?: string; score?: number; reason?: string }>;
  [key: string]: unknown;
}

const STAGE_LABEL: Record<LeadStage, string> = {
  new: '新建',
  contacted: '已联系',
  visit_scheduled: '已预约到店',
  quoted: '已报价',
  waiting_decision: '待决策',
  deposit_pending: '待定金',
  won: '赢单',
  lost: '丢单',
};

const STAGE_COLOR: Record<LeadStage, string> = {
  new: 'blue',
  contacted: 'cyan',
  visit_scheduled: 'purple',
  quoted: 'orange',
  waiting_decision: 'gold',
  deposit_pending: 'magenta',
  won: 'green',
  lost: 'red',
};

const BanquetAgentPage: React.FC = () => {
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [loading, setLoading] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardResp | null>(null);
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [leadStageFilter, setLeadStageFilter] = useState<LeadStage | 'all'>('all');
  const [scanLoading, setScanLoading] = useState(false);
  const [scanResult, setScanResult] = useState<FollowupScanResp | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteResult, setQuoteResult] = useState<QuoteRecommendResp | null>(null);
  const [quotePeople, setQuotePeople] = useState<number>(12);
  const [quoteBudget, setQuoteBudget] = useState<number>(12000);
  const [quoteType, setQuoteType] = useState<string | undefined>(undefined);
  const [hallLoading, setHallLoading] = useState(false);
  const [hallResult, setHallResult] = useState<HallRecommendResp | null>(null);
  const [hallDate, setHallDate] = useState<Dayjs>(dayjs().add(7, 'day'));
  const [hallSlot, setHallSlot] = useState<'lunch' | 'dinner' | 'all_day'>('all_day');
  const [hallPeople, setHallPeople] = useState<number>(12);

  const [advanceModal, setAdvanceModal] = useState(false);
  const [advanceTarget, setAdvanceTarget] = useState<LeadItem | null>(null);
  const [advanceSubmitting, setAdvanceSubmitting] = useState(false);
  const [advanceForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const monthStr = month.format('YYYY-MM');
      const leadsParams = leadStageFilter === 'all' ? {} : { stage: leadStageFilter };

      const [d, l, o] = await Promise.all([
        apiClient.get<DashboardResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/dashboard`, {
          params: { month: monthStr },
        }),
        apiClient.get<LeadListResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/leads`, {
          params: leadsParams,
        }),
        apiClient.get<OrderListResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/orders`),
      ]);
      setDashboard(d);
      setLeads(l.items || []);
      setOrders(o.items || []);
    } catch (err) {
      handleApiError(err, '加载宴会 Agent 数据失败');
    } finally {
      setLoading(false);
    }
  }, [month, leadStageFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const runFollowupScan = useCallback(async () => {
    setScanLoading(true);
    try {
      const resp = await apiClient.get<FollowupScanResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/agent/followup-scan`, {
        params: { dry_run: true },
      });
      setScanResult(resp);
      showSuccess(`扫描完成：发现 ${resp.stale_lead_count} 条停滞线索`);
    } catch (err) {
      handleApiError(err, '跟进扫描失败');
    } finally {
      setScanLoading(false);
    }
  }, []);

  const runQuoteRecommend = useCallback(async () => {
    setQuoteLoading(true);
    try {
      const resp = await apiClient.get<QuoteRecommendResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/agent/quote-recommend`, {
        params: {
          people_count: quotePeople,
          budget_yuan: quoteBudget,
          banquet_type: quoteType || undefined,
        },
      });
      setQuoteResult(resp);
    } catch (err) {
      handleApiError(err, '报价推荐失败');
    } finally {
      setQuoteLoading(false);
    }
  }, [quotePeople, quoteBudget, quoteType]);

  const runHallRecommend = useCallback(async () => {
    setHallLoading(true);
    try {
      const resp = await apiClient.get<HallRecommendResp>(`/api/v1/banquet-agent/stores/${STORE_ID}/agent/hall-recommend`, {
        params: {
          target_date: hallDate.format('YYYY-MM-DD'),
          slot_name: hallSlot,
          people_count: hallPeople,
        },
      });
      setHallResult(resp);
    } catch (err) {
      handleApiError(err, '排期推荐失败');
    } finally {
      setHallLoading(false);
    }
  }, [hallDate, hallPeople, hallSlot]);

  const submitAdvance = useCallback(async () => {
    if (!advanceTarget) return;
    try {
      const values = await advanceForm.validateFields();
      setAdvanceSubmitting(true);
      await apiClient.patch(`/api/v1/banquet-agent/stores/${STORE_ID}/leads/${advanceTarget.id}/stage`, {
        stage: values.stage,
        followup_content: values.followup_content,
        next_followup_days: values.next_followup_days,
      });
      showSuccess('线索阶段已更新');
      setAdvanceModal(false);
      advanceForm.resetFields();
      load();
    } catch (err) {
      handleApiError(err, '推进阶段失败');
    } finally {
      setAdvanceSubmitting(false);
    }
  }, [advanceForm, advanceTarget, load]);

  const kpis = useMemo(() => [
    { label: '本月宴会收入', value: dashboard ? `¥${Math.round(dashboard.revenue_yuan).toLocaleString()}` : '—' },
    { label: '本月毛利', value: dashboard ? `¥${Math.round(dashboard.gross_profit_yuan).toLocaleString()}` : '—' },
    { label: '线索转化率', value: dashboard ? dashboard.conversion_rate_pct.toFixed(1) : '—', unit: '%' },
    { label: '档期利用率', value: dashboard ? dashboard.hall_utilization_pct.toFixed(1) : '—', unit: '%' },
  ], [dashboard]);

  const leadColumns = [
    { title: '类型', dataIndex: 'banquet_type', key: 'banquet_type', width: 120 },
    { title: '日期', dataIndex: 'expected_date', key: 'expected_date', width: 110, render: (v: string | null) => v || '-' },
    { title: '人数', dataIndex: 'expected_people_count', key: 'expected_people_count', width: 80, render: (v: number | null) => v || '-' },
    { title: '预算', dataIndex: 'expected_budget_yuan', key: 'expected_budget_yuan', width: 120, render: (v: number) => `¥${Math.round(v || 0).toLocaleString()}` },
    {
      title: '阶段',
      dataIndex: 'current_stage',
      key: 'current_stage',
      width: 120,
      render: (v: LeadStage) => <Tag color={STAGE_COLOR[v]}>{STAGE_LABEL[v] || v}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, row: LeadItem) => (
        <ZButton
          size="sm"
          variant="ghost"
          icon={<CheckCircleOutlined />}
          onClick={() => {
            setAdvanceTarget(row);
            advanceForm.setFieldsValue({
              stage: row.current_stage,
              followup_content: '',
              next_followup_days: 3,
            });
            setAdvanceModal(true);
          }}
        >
          推进阶段
        </ZButton>
      ),
    },
  ];

  const orderColumns = [
    { title: '日期', dataIndex: 'banquet_date', key: 'banquet_date', width: 110 },
    { title: '类型', dataIndex: 'banquet_type', key: 'banquet_type', width: 110 },
    { title: '人数', dataIndex: 'people_count', key: 'people_count', width: 80 },
    { title: '状态', dataIndex: 'order_status', key: 'order_status', width: 110 },
    { title: '总金额', dataIndex: 'total_amount_yuan', key: 'total_amount_yuan', width: 120, render: (v: number) => `¥${Math.round(v || 0).toLocaleString()}` },
    { title: '已支付', dataIndex: 'paid_yuan', key: 'paid_yuan', width: 120, render: (v: number) => `¥${Math.round(v || 0).toLocaleString()}` },
    { title: '待支付', dataIndex: 'balance_yuan', key: 'balance_yuan', width: 120, render: (v: number) => `¥${Math.round(v || 0).toLocaleString()}` },
  ];

  const body = loading ? <ZSkeleton rows={8} /> : (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12, marginBottom: 12 }}>
        <ZCard><ZKpi label="本月宴会收入" value={dashboard?.revenue_yuan ?? 0} unit="¥" /></ZCard>
        <ZCard><ZKpi label="本月毛利" value={dashboard?.gross_profit_yuan ?? 0} unit="¥" /></ZCard>
        <ZCard><ZKpi label="转化率" value={dashboard?.conversion_rate_pct ?? 0} unit="%" /></ZCard>
        <ZCard><ZKpi label="档期利用率" value={dashboard?.hall_utilization_pct ?? 0} unit="%" /></ZCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 12, marginBottom: 12 }}>
        <ZCard
          title="宴会线索池"
          subtitle={`共 ${leads.length} 条`}
          extra={
            <Space>
              <Select value={leadStageFilter} onChange={(v) => setLeadStageFilter(v)} style={{ width: 180 }}>
                <Select.Option value="all">全部阶段</Select.Option>
                {(Object.keys(STAGE_LABEL) as LeadStage[]).map((s) => (
                  <Select.Option key={s} value={s}>{STAGE_LABEL[s]}</Select.Option>
                ))}
              </Select>
              <ZButton icon={<ReloadOutlined />} onClick={load}>刷新</ZButton>
            </Space>
          }
        >
          {leads.length === 0 ? (
            <ZEmpty title="暂无线索" />
          ) : (
            <Table rowKey="id" pagination={{ pageSize: 6 }} columns={leadColumns} dataSource={leads} size="small" />
          )}
        </ZCard>

        <div style={{ display: 'grid', gridTemplateRows: 'auto auto auto', gap: 12 }}>
          <ZCard
            title="Quotation Agent"
            subtitle="报价推荐"
            extra={<ZButton loading={quoteLoading} onClick={runQuoteRecommend}>生成推荐</ZButton>}
          >
            <Space wrap style={{ marginBottom: 8 }}>
              <InputNumber min={1} value={quotePeople} onChange={(v) => setQuotePeople(Number(v || 1))} addonBefore="人数" />
              <InputNumber min={1} value={quoteBudget} onChange={(v) => setQuoteBudget(Number(v || 1))} addonBefore="预算¥" />
              <Select allowClear placeholder="类型(可选)" value={quoteType} onChange={setQuoteType} style={{ width: 140 }}>
                <Select.Option value="birthday">生日宴</Select.Option>
                <Select.Option value="wedding">婚宴</Select.Option>
                <Select.Option value="business">商务宴</Select.Option>
              </Select>
            </Space>
            {!quoteResult ? (
              <Text type="secondary">填写人数与预算后点击“生成推荐”。</Text>
            ) : (
              <div style={{ maxHeight: 180, overflow: 'auto' }}>
                {(quoteResult.items || []).length > 0 ? (
                  (quoteResult.items || []).slice(0, 3).map((x, i) => (
                    <div key={`${x.package_id || i}`} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-color, #f0f0f0)' }}>
                      <div><Text strong>{x.package_name || x.package_id || `套餐${i + 1}`}</Text></div>
                      <div><Text type="secondary">总价 ¥{Math.round(Number(x.total_amount_yuan || 0)).toLocaleString()} · 预估毛利 ¥{Math.round(Number(x.gross_profit_yuan || 0)).toLocaleString()}</Text></div>
                    </div>
                  ))
                ) : (
                  <Text type="secondary">暂无可推荐套餐</Text>
                )}
              </div>
            )}
          </ZCard>

          <ZCard
            title="Scheduling Agent"
            subtitle="排期推荐"
            extra={<ZButton loading={hallLoading} onClick={runHallRecommend}>查询可用厅房</ZButton>}
          >
            <Space wrap style={{ marginBottom: 8 }}>
              <DatePicker value={hallDate} onChange={(d) => d && setHallDate(d)} />
              <Select value={hallSlot} onChange={setHallSlot} style={{ width: 120 }}>
                <Select.Option value="lunch">午市</Select.Option>
                <Select.Option value="dinner">晚市</Select.Option>
                <Select.Option value="all_day">全天</Select.Option>
              </Select>
              <InputNumber min={1} value={hallPeople} onChange={(v) => setHallPeople(Number(v || 1))} addonBefore="人数" />
            </Space>
            {!hallResult ? (
              <Text type="secondary">选择日期与人数后点击“查询可用厅房”。</Text>
            ) : (
              <div style={{ maxHeight: 180, overflow: 'auto' }}>
                {(hallResult.items || []).length > 0 ? (
                  (hallResult.items || []).slice(0, 3).map((x, i) => (
                    <div key={`${x.hall_id || i}`} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-color, #f0f0f0)' }}>
                      <div><Text strong>{x.hall_name || x.hall_id || `厅房${i + 1}`}</Text></div>
                      <div><Text type="secondary">档期 {x.slot_name || hallSlot} · 匹配分 {Number(x.score || 0).toFixed(2)}</Text></div>
                    </div>
                  ))
                ) : (
                  <Text type="secondary">当前暂无可用推荐厅房</Text>
                )}
              </div>
            )}
          </ZCard>

          <ZCard
            title="Followup Agent"
            subtitle="停滞线索扫描（dry-run）"
            extra={<ZButton loading={scanLoading} onClick={runFollowupScan}>执行扫描</ZButton>}
          >
            {!scanResult ? (
              <Text type="secondary">点击“执行扫描”查看停滞线索提醒结果。</Text>
            ) : (
              <>
                <div style={{ marginBottom: 8 }}>
                  <Tag color={scanResult.stale_lead_count > 0 ? 'orange' : 'green'}>
                    停滞线索 {scanResult.stale_lead_count}
                  </Tag>
                </div>
                <div style={{ maxHeight: 180, overflow: 'auto' }}>
                  {(scanResult.items || []).slice(0, 4).map((x, i) => (
                    <div key={`${x.lead_id}-${i}`} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-color, #f0f0f0)' }}>
                      <div><Text strong>{x.lead_id}</Text></div>
                      <div><Text type="secondary">{x.summary || x.suggestion || '建议尽快跟进'}</Text></div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </ZCard>
        </div>
      </div>

      <ZCard title="宴会订单列表" subtitle={`共 ${orders.length} 条`}>
        {orders.length === 0 ? (
          <ZEmpty title="暂无订单" />
        ) : (
          <Table rowKey="id" pagination={{ pageSize: 6 }} columns={orderColumns} dataSource={orders} size="small" />
        )}
      </ZCard>

      <div style={{ marginTop: 10 }}>
        <Text type="secondary">{dashboard?.summary || '暂无经营摘要'}</Text>
      </div>
    </>
  );

  return (
    <>
      <AgentWorkspaceTemplate
        agentName="宴会管理 Agent"
        agentIcon="🎉"
        agentColor="#7c3aed"
        description="CRM线索管理 · 阶段推进 · 宴会订单 · Agent扫描"
        status={loading ? 'idle' : 'running'}
        kpis={kpis}
        kpiLoading={loading}
        tabs={[{ key: 'banquet', label: '宴会工作台', children: body }]}
        defaultTab="banquet"
        loading={loading}
        onRefresh={load}
        headerExtra={
          <Space size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>统计月份</Text>
            <DatePicker picker="month" value={month} onChange={(d) => d && setMonth(d)} size="small" />
          </Space>
        }
      />

      <Modal
        title="推进线索阶段"
        open={advanceModal}
        onCancel={() => setAdvanceModal(false)}
        onOk={submitAdvance}
        confirmLoading={advanceSubmitting}
      >
        <Form form={advanceForm} layout="vertical">
          <Form.Item label="目标阶段" name="stage" rules={[{ required: true }]}> 
            <Select>
              {(Object.keys(STAGE_LABEL) as LeadStage[]).map((s) => (
                <Select.Option key={s} value={s}>{STAGE_LABEL[s]}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="跟进记录" name="followup_content" rules={[{ required: true, message: '请输入跟进内容' }]}> 
            <Input.TextArea rows={3} placeholder="输入本次沟通要点" />
          </Form.Item>
          <Form.Item label="下次跟进（天）" name="next_followup_days">
            <InputNumber min={1} max={30} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default BanquetAgentPage;
