/**
 * 能耗 Agent V1 前端
 * 4-Tab: 驾驶舱 / 异常中心 / 节能任务 / 跨店对标
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Table, Tag, Button, Space, Select, DatePicker,
  Modal, Form, Input, InputNumber, Typography, Statistic, Badge,
  Descriptions, Tooltip, Alert, message, Spin, Divider, Progress,
  Popconfirm,
} from 'antd';
import {
  ThunderboltOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  BulbOutlined,
  RiseOutlined,
  FallOutlined,
  ReloadOutlined,
  PlusOutlined,
  EyeOutlined,
  EnvironmentOutlined,
  BarChartOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import FilterToolbar from '../components/FilterToolbar';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';

const { Title, Text } = Typography;

// ── 常量 ────────────────────────────────────────────────────────────────────

const API = '/api/v1/energy';

// 演示用默认值
const DEFAULT_STORE_ID  = 'store_001';
const DEFAULT_BRAND_ID  = 'brand_001';

const DEVICE_TYPE_LABELS: Record<string, string> = {
  ac: '空调', kitchen: '厨设', cold_chain: '冷链', lighting: '照明', other: '其他',
};

const SEVERITY_CONFIG: Record<string, { color: string; label: string }> = {
  high:   { color: 'error',   label: '高危' },
  medium: { color: 'warning', label: '中危' },
  low:    { color: 'default', label: '低危' },
};

// ── 工具 ─────────────────────────────────────────────────────────────────────

const yuanFmt = (v?: number | null) =>
  v == null ? '—' : `¥${v.toFixed(2)}`;

const kwhFmt = (v?: number | null) =>
  v == null ? '—' : `${v.toFixed(1)} 度`;

// ═══════════════════════════════════════════════════════════════════════════
// Tab 1 — 驾驶舱
// ═══════════════════════════════════════════════════════════════════════════

interface DashboardData {
  store_id: string;
  today: {
    kwh?: number;
    cost_yuan?: number;
    non_business_kwh?: number;
    device_breakdown?: Record<string, number>;
  };
  avg_30d_kwh: number;
  trend_7d: Array<{
    date: string;
    total_kwh: number;
    cost_yuan: number;
    peak_kwh?: number;
    valley_kwh?: number;
  }>;
  anomaly_summary: {
    unresolved_count: number;
    top_high?: {
      title: string;
      severity: string;
      action_hint: string;
    };
  };
}

const DashboardTab: React.FC<{ storeId: string; brandId: string }> = ({ storeId, brandId }) => {
  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`${API}/stores/${storeId}/dashboard`, {
        params: { brand_id: brandId },
      });
      setData(resp.data);
    } catch {
      message.error('驾驶舱数据加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, brandId]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <Spin style={{ display: 'block', margin: '80px auto' }} />;

  const today     = data?.today;
  const anomaly   = data?.anomaly_summary;
  const breakdown = today?.device_breakdown ?? {};
  const trend     = data?.trend_7d ?? [];

  // 对比30日均值
  const vsAvg = today?.kwh && data?.avg_30d_kwh
    ? ((today.kwh - data.avg_30d_kwh) / data.avg_30d_kwh * 100).toFixed(1)
    : null;

  return (
    <div style={{ padding: '0 4px' }}>
      {/* 今日高危异常横幅 */}
      {anomaly?.top_high && (
        <Alert
          type="error"
          showIcon
          icon={<WarningOutlined />}
          message={anomaly.top_high.title}
          description={anomaly.top_high.action_hint}
          style={{ marginBottom: 16 }}
          action={
            <Tag color="red">{anomaly.unresolved_count} 条未处理</Tag>
          }
        />
      )}

      {/* KPI 卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="今日用电"
              value={today?.kwh ?? 0}
              suffix="度"
              precision={1}
              prefix={<ThunderboltOutlined style={{ color: '#faad14' }} />}
            />
            {vsAvg !== null && (
              <Text type={Number(vsAvg) > 0 ? 'danger' : 'success'} style={{ fontSize: 12 }}>
                {Number(vsAvg) > 0 ? <RiseOutlined /> : <FallOutlined />}
                {' '}{Math.abs(Number(vsAvg))}% vs 30日均值
              </Text>
            )}
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="今日电费估算"
              value={today?.cost_yuan ?? 0}
              prefix="¥"
              precision={2}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="非营业时段耗电"
              value={today?.non_business_kwh ?? 0}
              suffix="度"
              precision={1}
              valueStyle={{ color: (today?.non_business_kwh ?? 0) > 0 ? '#faad14' : undefined }}
            />
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="30日日均用电"
              value={data?.avg_30d_kwh ?? 0}
              suffix="度"
              precision={1}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        {/* 设备分类 */}
        <Col xs={24} sm={10}>
          <Card title="今日设备用电分布" size="small" style={{ height: '100%' }}>
            {Object.entries(DEVICE_TYPE_LABELS).map(([key, label]) => {
              const val = breakdown[key] ?? 0;
              const totalKwh = today?.kwh || 1;
              const pct = Math.round(val / totalKwh * 100);
              return (
                <div key={key} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                    <Text style={{ fontSize: 12 }}>{label}</Text>
                    <Text style={{ fontSize: 12 }}>{val.toFixed(1)} 度 ({pct}%)</Text>
                  </div>
                  <Progress percent={pct} size="small" showInfo={false} strokeColor={
                    key === 'ac' ? '#1890ff' : key === 'kitchen' ? '#fa8c16' :
                    key === 'cold_chain' ? '#13c2c2' : key === 'lighting' ? '#fadb14' : '#d9d9d9'
                  } />
                </div>
              );
            })}
          </Card>
        </Col>

        {/* 7日趋势表 */}
        <Col xs={24} sm={14}>
          <Card title="近7日用电趋势" size="small">
            <Table
              dataSource={trend.slice().reverse()}
              rowKey="date"
              pagination={false}
              size="small"
              columns={[
                { title: '日期',     dataIndex: 'date',      width: 100 },
                {
                  title: '用电(度)',
                  dataIndex: 'total_kwh',
                  width: 90,
                  render: v => v?.toFixed(1) ?? '—',
                },
                {
                  title: '峰段(度)',
                  dataIndex: 'peak_kwh',
                  width: 90,
                  render: v => <Text type="danger">{v?.toFixed(1) ?? '—'}</Text>,
                },
                {
                  title: '费用(¥)',
                  dataIndex: 'cost_yuan',
                  render: v => yuanFmt(v),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <div style={{ textAlign: 'right', marginTop: 8 }}>
        <Button size="small" icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Tab 2 — 异常中心
// ═══════════════════════════════════════════════════════════════════════════

interface Anomaly {
  anomaly_id: string;
  anomaly_type: string;
  severity: string;
  title: string;
  description: string;
  action_hint: string;
  stat_date?: string;
  detected_at?: string;
}

const ANOMALY_TYPE_LABELS: Record<string, string> = {
  non_business_waste: '非营业浪费',
  daily_spike:        '单日尖峰',
  cold_chain_alert:   '冷链温控',
  idle_waste:         '空转低耗',
  bill_spike:         '账单环比异常',
};

const AnomalyTab: React.FC<{ storeId: string; brandId: string }> = ({ storeId, brandId }) => {
  const [rows, setRows]         = useState<Anomaly[]>([]);
  const [loading, setLoading]   = useState(false);
  const [scanModal, setScanModal] = useState(false);
  const [scanDate, setScanDate]   = useState<dayjs.Dayjs>(dayjs());
  const [dryRun, setDryRun]       = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [filterValues, setFilterValues] = useState<Record<string, string | undefined>>({});
  const [searchText, setSearchText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`${API}/stores/${storeId}/anomalies`, { params: { limit: 100 } });
      setRows(resp.data);
    } catch {
      message.error('异常列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id: string) => {
    try {
      await apiClient.patch(`${API}/anomalies/${id}/resolve`);
      message.success('已标记处理');
      load();
    } catch {
      message.error('操作失败');
    }
  };

  const runScan = async () => {
    setScanLoading(true);
    try {
      const resp = await apiClient.post(`${API}/stores/${storeId}/anomaly-scan`, {
        store_id: storeId,
        brand_id: brandId,
        stat_date: scanDate.format('YYYY-MM-DD'),
        dry_run: dryRun,
      });
      const { total_found, high_count } = resp.data;
      message.success(`扫描完成：发现 ${total_found} 条异常（其中高危 ${high_count} 条）`);
      setScanModal(false);
      if (!dryRun) load();
    } catch {
      message.error('扫描失败');
    } finally {
      setScanLoading(false);
    }
  };

  const filteredRows = rows.filter(r => {
    if (filterValues.severity && r.severity !== filterValues.severity) return false;
    if (filterValues.anomaly_type && r.anomaly_type !== filterValues.anomaly_type) return false;
    if (searchText && !r.title.includes(searchText)) return false;
    return true;
  });

  const columns: ColumnsType<Anomaly> = [
    {
      title: '严重性',
      dataIndex: 'severity',
      width: 70,
      render: v => {
        const cfg = SEVERITY_CONFIG[v] ?? { color: 'default', label: v };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '类型',
      dataIndex: 'anomaly_type',
      width: 100,
      render: v => ANOMALY_TYPE_LABELS[v] ?? v,
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
    },
    {
      title: '日期',
      dataIndex: 'stat_date',
      width: 100,
      render: v => v ?? '—',
    },
    {
      title: '发现时间',
      dataIndex: 'detected_at',
      width: 150,
      render: v => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '操作',
      width: 80,
      render: (_, r) => (
        <Popconfirm title="标记为已处理？" onConfirm={() => resolve(r.anomaly_id)}>
          <Button type="link" size="small" icon={<CheckCircleOutlined />}>处理</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <FilterToolbar
        search={{ placeholder: '搜索异常标题…', onSearch: setSearchText }}
        filters={[
          {
            key: 'severity',
            label: '严重等级',
            width: 110,
            options: [
              { value: 'high',   label: '高危', color: 'red'     },
              { value: 'medium', label: '中危', color: 'orange'  },
              { value: 'low',    label: '低危', color: 'default' },
            ],
          },
          {
            key: 'anomaly_type',
            label: '异常类型',
            width: 130,
            options: Object.entries(ANOMALY_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l })),
          },
        ]}
        filterValues={filterValues}
        onFilterChange={(key, value) =>
          setFilterValues(prev => ({ ...prev, [key]: value as string | undefined }))
        }
        onReset={() => setFilterValues({})}
        summary={<Badge count={filteredRows.length} showZero><Text strong style={{ fontSize: 12 }}>未处理异常</Text></Badge>}
        onRefresh={load}
        refreshLoading={loading}
        actions={[
          {
            label: '触发扫描',
            icon: <ExclamationCircleOutlined />,
            type: 'primary',
            onClick: () => setScanModal(true),
          },
        ]}
        style={{ marginBottom: 8 }}
      />

      <Table
        dataSource={filteredRows}
        columns={columns}
        rowKey="anomaly_id"
        loading={loading}
        size="small"
        expandable={{
          expandedRowRender: r => (
            <Descriptions size="small" column={1} style={{ padding: '4px 0' }}>
              <Descriptions.Item label="详情">{r.description}</Descriptions.Item>
              <Descriptions.Item label="建议处置">{r.action_hint}</Descriptions.Item>
            </Descriptions>
          ),
        }}
      />

      <Modal
        title="触发异常扫描"
        open={scanModal}
        onOk={runScan}
        confirmLoading={scanLoading}
        onCancel={() => setScanModal(false)}
      >
        <Form layout="vertical">
          <Form.Item label="扫描日期">
            <DatePicker
              value={scanDate}
              onChange={d => d && setScanDate(d)}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item label="模式">
            <Select
              value={dryRun ? 'dry' : 'real'}
              onChange={v => setDryRun(v === 'dry')}
              options={[
                { value: 'real', label: '正式写库' },
                { value: 'dry',  label: '试运行（只返回结果，不写库）' },
              ]}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Tab 3 — 节能任务
// ═══════════════════════════════════════════════════════════════════════════

interface SavingTask {
  task_id: string;
  source_type: string;
  title: string;
  description?: string;
  expected_saving_yuan: number;
  actual_saving_yuan: number;
  status: string;
  due_date?: string;
  completed_at?: string;
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  pending:   { color: 'processing', label: '待处理' },
  completed: { color: 'success',    label: '已完成' },
  cancelled: { color: 'default',    label: '已取消' },
};

const SavingTasksTab: React.FC<{ storeId: string; brandId: string }> = ({ storeId, brandId }) => {
  const [rows, setRows]         = useState<SavingTask[]>([]);
  const [loading, setLoading]   = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [createModal, setCreateModal]   = useState(false);
  const [completeModal, setCompleteModal] = useState<SavingTask | null>(null);
  const [form]        = Form.useForm();
  const [completeForm] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`${API}/stores/${storeId}/saving-tasks`, {
        params: statusFilter ? { status: statusFilter } : {},
      });
      setRows(resp.data);
    } catch {
      message.error('任务列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const createTask = async () => {
    const vals = await form.validateFields();
    setSubmitLoading(true);
    try {
      await apiClient.post(`${API}/stores/${storeId}/saving-tasks`, {
        store_id: storeId,
        brand_id: brandId,
        ...vals,
        expected_saving_fen: Math.round((vals.expected_saving_yuan ?? 0) * 100),
        due_date: vals.due_date?.format('YYYY-MM-DD'),
      });
      message.success('任务已创建');
      setCreateModal(false);
      form.resetFields();
      load();
    } catch {
      message.error('创建失败');
    } finally {
      setSubmitLoading(false);
    }
  };

  const completeTask = async () => {
    if (!completeModal) return;
    const vals = await completeForm.validateFields();
    setSubmitLoading(true);
    try {
      await apiClient.patch(`${API}/saving-tasks/${completeModal.task_id}/complete`, {
        actual_saving_fen: Math.round((vals.actual_saving_yuan ?? 0) * 100),
      });
      message.success('任务已完成');
      setCompleteModal(null);
      completeForm.resetFields();
      load();
    } catch {
      message.error('操作失败');
    } finally {
      setSubmitLoading(false);
    }
  };

  const columns: ColumnsType<SavingTask> = [
    {
      title: '来源',
      dataIndex: 'source_type',
      width: 80,
      render: v => {
        const map: Record<string, string> = { prediction: '尖峰预测', anomaly: '异常检测', manual: '手动创建' };
        return <Tag>{map[v] ?? v}</Tag>;
      },
    },
    { title: '任务标题', dataIndex: 'title', ellipsis: true },
    {
      title: '预期节省',
      dataIndex: 'expected_saving_yuan',
      width: 100,
      render: v => <Text type="success">{yuanFmt(v)}</Text>,
    },
    {
      title: '实际节省',
      dataIndex: 'actual_saving_yuan',
      width: 100,
      render: v => v ? <Text type="success">{yuanFmt(v)}</Text> : '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: v => {
        const cfg = STATUS_CONFIG[v] ?? { color: 'default', label: v };
        return <Badge status={cfg.color as any} text={cfg.label} />;
      },
    },
    {
      title: '截止日期',
      dataIndex: 'due_date',
      width: 100,
      render: v => v ?? '—',
    },
    {
      title: '操作',
      width: 80,
      render: (_, r) => r.status === 'pending' ? (
        <Button type="link" size="small" onClick={() => { setCompleteModal(r); }}>
          完成
        </Button>
      ) : null,
    },
  ];

  return (
    <div>
      <FilterToolbar
        filters={[
          {
            key: 'status',
            label: '状态',
            width: 110,
            options: [
              { value: 'pending',   label: '待处理' },
              { value: 'completed', label: '已完成' },
              { value: 'cancelled', label: '已取消' },
            ],
          },
        ]}
        filterValues={statusFilter ? { status: statusFilter } : {}}
        onFilterChange={(_, value) => setStatusFilter(value as string | undefined)}
        onReset={() => setStatusFilter(undefined)}
        onRefresh={load}
        refreshLoading={loading}
        actions={[
          {
            label: '新建任务',
            icon: <PlusOutlined />,
            type: 'primary',
            onClick: () => setCreateModal(true),
          },
        ]}
        style={{ marginBottom: 8 }}
      />

      <Table
        dataSource={rows}
        columns={columns}
        rowKey="task_id"
        loading={loading}
        size="small"
        expandable={{
          expandedRowRender: r => r.description ? (
            <Text type="secondary" style={{ fontSize: 12 }}>{r.description}</Text>
          ) : null,
        }}
      />

      {/* 新建任务 Modal */}
      <Modal
        title="手动创建节能任务"
        open={createModal}
        onOk={createTask}
        confirmLoading={submitLoading}
        onCancel={() => { setCreateModal(false); form.resetFields(); }}
      >
        <Form form={form} layout="vertical" size="small">
          <Form.Item name="title" label="任务标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="expected_saving_yuan" label="预期节省(元)">
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="assigned_to" label="指派给">
            <Input placeholder="员工ID 或 姓名" />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 完成任务 Modal */}
      <Modal
        title="完成节能任务"
        open={!!completeModal}
        onOk={completeTask}
        confirmLoading={submitLoading}
        onCancel={() => { setCompleteModal(null); completeForm.resetFields(); }}
      >
        <Text style={{ display: 'block', marginBottom: 12 }}>{completeModal?.title}</Text>
        <Form form={completeForm} layout="vertical" size="small">
          <Form.Item name="actual_saving_yuan" label="实际节省金额(元)">
            <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="可不填" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Tab 4 — 跨店对标 & 总部汇总
// ═══════════════════════════════════════════════════════════════════════════

interface BenchmarkRow {
  device_type: string;
  p50_kwh_day: number;
  p75_kwh_day: number;
  p90_kwh_day: number;
  store_count: number;
}

interface HqStore {
  store_id: string;
  total_kwh: number;
  total_cost_yuan: number;
  avg_daily_kwh: number;
  unresolved_anomalies: number;
}

const BenchmarkTab: React.FC<{ storeId: string; brandId: string }> = ({ storeId, brandId }) => {
  const [bmRows, setBmRows]         = useState<BenchmarkRow[]>([]);
  const [hqRows, setHqRows]         = useState<HqStore[]>([]);
  const [bmLoading, setBmLoading]   = useState(false);
  const [hqLoading, setHqLoading]   = useState(false);
  const [period, setPeriod]         = useState(dayjs().format('YYYY-MM'));
  const [hqStart, setHqStart]       = useState(dayjs().startOf('month').format('YYYY-MM-DD'));
  const [hqEnd, setHqEnd]           = useState(dayjs().format('YYYY-MM-DD'));

  const loadBenchmark = useCallback(async () => {
    setBmLoading(true);
    try {
      const resp = await apiClient.get(`${API}/brands/${brandId}/benchmark`, { params: { period } });
      setBmRows(resp.data);
    } catch {
      message.error('对标数据加载失败');
    } finally {
      setBmLoading(false);
    }
  }, [brandId, period]);

  const loadHq = useCallback(async () => {
    setHqLoading(true);
    try {
      const resp = await apiClient.get(`${API}/brands/${brandId}/hq-summary`, {
        params: { start_date: hqStart, end_date: hqEnd },
      });
      setHqRows(resp.data.stores ?? []);
    } catch {
      message.error('总部汇总加载失败');
    } finally {
      setHqLoading(false);
    }
  }, [brandId, hqStart, hqEnd]);

  useEffect(() => { loadBenchmark(); }, [loadBenchmark]);
  useEffect(() => { loadHq(); }, [loadHq]);

  const bmColumns: ColumnsType<BenchmarkRow> = [
    { title: '设备类型', dataIndex: 'device_type', width: 90, render: v => DEVICE_TYPE_LABELS[v] ?? v },
    { title: 'P50 日均(度)', dataIndex: 'p50_kwh_day', render: v => v?.toFixed(1) },
    { title: 'P75 日均(度)', dataIndex: 'p75_kwh_day', render: v => v?.toFixed(1) },
    { title: 'P90 日均(度)', dataIndex: 'p90_kwh_day', render: v => <Text type="danger">{v?.toFixed(1)}</Text> },
    { title: '参与门店数', dataIndex: 'store_count', width: 90 },
  ];

  const hqColumns: ColumnsType<HqStore> = [
    { title: '门店', dataIndex: 'store_id', width: 120 },
    {
      title: '总用电(度)',
      dataIndex: 'total_kwh',
      sorter: (a, b) => (a.total_kwh ?? 0) - (b.total_kwh ?? 0),
      render: v => kwhFmt(v),
    },
    {
      title: '日均用电(度)',
      dataIndex: 'avg_daily_kwh',
      render: v => kwhFmt(v),
    },
    {
      title: '总费用',
      dataIndex: 'total_cost_yuan',
      sorter: (a, b) => (a.total_cost_yuan ?? 0) - (b.total_cost_yuan ?? 0),
      render: v => yuanFmt(v),
    },
    {
      title: '未处理异常',
      dataIndex: 'unresolved_anomalies',
      width: 100,
      render: v => v > 0 ? <Tag color="error">{v}</Tag> : <Tag color="success">0</Tag>,
    },
  ];

  return (
    <div>
      {/* 跨店对标 */}
      <Card
        title={<Space><BarChartOutlined /> 品牌跨店对标基准（P50/P75/P90）</Space>}
        size="small"
        style={{ marginBottom: 16 }}
        extra={
          <Space size="small">
            <DatePicker
              picker="month"
              value={dayjs(period)}
              onChange={d => d && setPeriod(d.format('YYYY-MM'))}
              size="small"
            />
            <Button size="small" onClick={loadBenchmark} icon={<ReloadOutlined />} />
          </Space>
        }
      >
        <Table
          dataSource={bmRows}
          columns={bmColumns}
          rowKey="device_type"
          loading={bmLoading}
          pagination={false}
          size="small"
        />
      </Card>

      {/* 总部多店汇总 */}
      <Card
        title={<Space><EnvironmentOutlined /> 总部多店能耗排名</Space>}
        size="small"
        extra={
          <Space size="small">
            <DatePicker
              value={dayjs(hqStart)}
              onChange={d => d && setHqStart(d.format('YYYY-MM-DD'))}
              size="small"
              placeholder="开始日期"
            />
            <DatePicker
              value={dayjs(hqEnd)}
              onChange={d => d && setHqEnd(d.format('YYYY-MM-DD'))}
              size="small"
              placeholder="结束日期"
            />
            <Button size="small" onClick={loadHq} icon={<ReloadOutlined />} />
          </Space>
        }
      >
        <Table
          dataSource={hqRows}
          columns={hqColumns}
          rowKey="store_id"
          loading={hqLoading}
          size="small"
        />
      </Card>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════════════════════════════════════

const EnergyPage: React.FC = () => {
  const [storeId] = useState(DEFAULT_STORE_ID);
  const [brandId] = useState(DEFAULT_BRAND_ID);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageDash, setPageDash] = useState<DashboardData | null>(null);

  const loadPageDash = useCallback(async () => {
    setPageLoading(true);
    try {
      const resp = await apiClient.get(`${API}/stores/${storeId}/dashboard`, {
        params: { brand_id: brandId },
      });
      setPageDash(resp.data);
    } catch { /* silent — DashboardTab shows its own error */ }
    finally { setPageLoading(false); }
  }, [storeId, brandId]);

  useEffect(() => { loadPageDash(); }, [loadPageDash]);

  const today = pageDash?.today;
  const vsAvg = today?.kwh && pageDash?.avg_30d_kwh
    ? ((today.kwh - pageDash.avg_30d_kwh) / pageDash.avg_30d_kwh * 100).toFixed(1)
    : null;

  const kpis = [
    {
      label: '今日用电',
      value: today?.kwh?.toFixed(1) ?? '—',
      unit: '度',
      icon: <ThunderboltOutlined style={{ color: '#faad14' }} />,
      sub: vsAvg !== null ? `${Number(vsAvg) > 0 ? '+' : ''}${vsAvg}% vs 30日均` : undefined,
      valueColor: undefined,
    },
    {
      label: '今日电费',
      value: today?.cost_yuan != null ? `¥${today.cost_yuan.toFixed(0)}` : '—',
      icon: <ThunderboltOutlined style={{ color: '#1890ff' }} />,
    },
    {
      label: '非营业耗电',
      value: today?.non_business_kwh?.toFixed(1) ?? '—',
      unit: '度',
      icon: <WarningOutlined style={{ color: '#fa8c16' }} />,
      valueColor: (today?.non_business_kwh ?? 0) > 0 ? '#fa8c16' : undefined,
    },
    {
      label: '未处理异常',
      value: pageDash?.anomaly_summary?.unresolved_count ?? '—',
      icon: <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />,
      valueColor: (pageDash?.anomaly_summary?.unresolved_count ?? 0) > 0 ? '#ff4d4f' : '#52c41a',
      sub: (pageDash?.anomaly_summary?.unresolved_count ?? 0) > 0 ? '需处理' : '一切正常',
    },
  ];

  const tabs = [
    {
      key:      'dashboard',
      label:    '驾驶舱',
      children: <DashboardTab storeId={storeId} brandId={brandId} />,
    },
    {
      key:      'anomalies',
      label:    '异常中心',
      count:    pageDash?.anomaly_summary?.unresolved_count,
      children: <AnomalyTab storeId={storeId} brandId={brandId} />,
    },
    {
      key:      'saving-tasks',
      label:    '节能任务',
      children: <SavingTasksTab storeId={storeId} brandId={brandId} />,
    },
    {
      key:      'benchmark',
      label:    '跨店对标',
      children: <BenchmarkTab storeId={storeId} brandId={brandId} />,
    },
  ];

  return (
    <AgentWorkspaceTemplate
      agentName="能耗 Agent"
      agentIcon="⚡"
      agentColor="#faad14"
      description="设备用电监控 · 异常识别 · 节能任务 · 跨店对标"
      status={
        (pageDash?.anomaly_summary?.unresolved_count ?? 0) > 0 ? 'warning' : 'running'
      }
      kpis={kpis}
      kpiLoading={pageLoading}
      tabs={tabs}
      defaultTab="dashboard"
      loading={pageLoading}
      onRefresh={loadPageDash}
    />
  );
};

export default EnergyPage;
