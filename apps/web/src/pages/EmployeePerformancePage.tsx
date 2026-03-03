/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Select, Statistic, Table, Tag, Button,
  Typography, Space, Spin, Modal, Form, InputNumber, Input,
  DatePicker, Progress, Badge, Tabs,
} from 'antd';
import { TrophyOutlined, ReloadOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Title } = Typography;
const { Option } = Select;

// ── 指标元数据 ─────────────────────────────────────────────────────────────────

const METRIC_LABELS: Record<string, string> = {
  revenue:          '月营收',
  profit:           '毛利率',
  labor_efficiency: '人效',
  waste_rate:       '损耗率',
  avg_per_table:    '桌均消费',
  order_count:      '订单数',
  avg_serve_time:   '出餐时效',
};

function fmtValue(metricId: string, v: number | null | undefined): string {
  if (v == null) return '—';
  if (['revenue', 'labor_efficiency', 'avg_per_table'].includes(metricId))
    return `¥${(v / 100).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`;
  if (['profit', 'waste_rate'].includes(metricId))
    return `${(v * 100).toFixed(1)}%`;
  if (metricId === 'avg_serve_time') return `${v.toFixed(1)} 分钟`;
  return v.toFixed(1);
}

function rateTag(r: number | null | undefined) {
  if (r == null) return <Tag>—</Tag>;
  const color = r >= 1.0 ? 'green' : r >= 0.8 ? 'orange' : 'red';
  return <Tag color={color}>{(r * 100).toFixed(0)}%</Tag>;
}

// ── 组件 ───────────────────────────────────────────────────────────────────────

const EmployeePerformancePage: React.FC = () => {
  const [stores, setStores]           = useState<any[]>([]);
  const [storeId, setStoreId]         = useState('STORE001');
  const [period, setPeriod]           = useState<Dayjs>(dayjs().subtract(1, 'month'));
  const [loading, setLoading]         = useState(false);
  const [computing, setComputing]     = useState(false);
  const [employees, setEmployees]     = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [summary, setSummary]         = useState<any[]>([]);
  const [metrics, setMetrics]         = useState<any[]>([]);
  const [recordModal, setRecordModal] = useState(false);
  const [selectedEmp, setSelectedEmp] = useState<string | undefined>(undefined);
  const [form] = Form.useForm();

  const year  = period.year();
  const month = period.month() + 1; // dayjs month() 是 0-indexed

  // ── 数据加载 ─────────────────────────────────────────────────────────────────

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [empRes, lbRes, sumRes, metRes] = await Promise.all([
        apiClient.get('/employees', { params: { store_id: storeId } }),
        apiClient.get('/employees/performance/leaderboard', { params: { store_id: storeId } }),
        apiClient.get(`/api/v1/performance/${storeId}/summary`, { params: { year, month } }),
        apiClient.get(`/api/v1/performance/${storeId}/metrics`, { params: { year, month } }),
      ]);
      setEmployees(empRes.data || []);
      setLeaderboard(lbRes.data?.leaderboard || []);
      setSummary(sumRes.data || []);
      setMetrics(metRes.data || []);
    } catch (err: any) {
      handleApiError(err, '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, year, month]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadData(); }, [loadData]);

  // ── 触发绩效计算 ──────────────────────────────────────────────────────────────

  const triggerCompute = async () => {
    setComputing(true);
    try {
      const res = await apiClient.post('/api/v1/performance/compute', {
        store_id: storeId, year, month,
      });
      showSuccess(res.data.message || '计算完成');
      loadData();
    } catch (err: any) {
      handleApiError(err, '触发计算失败');
    } finally {
      setComputing(false);
    }
  };

  // ── 手动录入绩效 ──────────────────────────────────────────────────────────────

  const submitPerformance = async (values: any) => {
    try {
      await apiClient.post(`/employees/${selectedEmp}/performance`, {
        ...values,
        period: values.period?.format('YYYY-MM') || '',
      });
      showSuccess('绩效已录入');
      setRecordModal(false);
      form.resetFields();
      loadData();
    } catch (err: any) {
      handleApiError(err, '录入失败');
    }
  };

  // ── 统计卡片数值 ──────────────────────────────────────────────────────────────

  const activeEmpCount = employees.filter((e: any) => e.is_active).length;
  const avgAchievement = summary.length > 0
    ? (summary.reduce((s: number, r: any) => s + (r.avg_achievement_rate || 0), 0) / summary.length * 100).toFixed(1)
    : '--';

  // ── 表格列定义 ────────────────────────────────────────────────────────────────

  const lbColumns = [
    {
      title: '排名', dataIndex: 'rank', width: 60,
      render: (v: number) => (
        <span style={{ fontWeight: 'bold', color: v === 1 ? '#ffd700' : v === 2 ? '#c0c0c0' : v === 3 ? '#cd7f32' : undefined }}>
          {v <= 3 ? ['🥇', '🥈', '🥉'][v - 1] : v}
        </span>
      ),
    },
    { title: '姓名', dataIndex: 'name' },
    { title: '岗位', dataIndex: 'position', render: (v: string) => v || '-' },
    {
      title: '综合评分', dataIndex: 'performance_score',
      render: (v: number) => (
        <Progress percent={v} size="small"
          status={v >= 80 ? 'success' : v >= 60 ? 'normal' : 'exception'}
          format={(p) => `${p}`}
        />
      ),
    },
  ];

  const empColumns = [
    { title: '姓名', dataIndex: 'name' },
    { title: '岗位', dataIndex: 'position', render: (v: string) => v || '-' },
    {
      title: '当前评分', dataIndex: 'performance_score',
      render: (v: string) => v
        ? <Tag color={parseFloat(v) >= 80 ? 'green' : parseFloat(v) >= 60 ? 'orange' : 'red'}>{v}</Tag>
        : <Badge status="default" text="未评分" />,
    },
    {
      title: '状态', dataIndex: 'is_active',
      render: (v: boolean) => v ? <Tag color="green">在职</Tag> : <Tag>离职</Tag>,
    },
    {
      title: '操作',
      render: (_: any, record: any) => (
        <Button size="small" icon={<PlusOutlined />}
          onClick={() => { setSelectedEmp(record.id); setRecordModal(true); }}>
          录入
        </Button>
      ),
    },
  ];

  const summaryColumns = [
    {
      title: '指标', dataIndex: 'metric_id',
      render: (v: string) => METRIC_LABELS[v] || v,
    },
    {
      title: '均值', dataIndex: 'avg_value',
      render: (v: number, row: any) => fmtValue(row.metric_id, v),
    },
    {
      title: '平均达成率', dataIndex: 'avg_achievement_rate',
      render: (v: number) => (
        <Space>
          <Progress
            percent={Math.min(Math.round((v || 0) * 100), 100)}
            size="small" style={{ width: 80 }}
            status={v >= 1.0 ? 'success' : v >= 0.8 ? 'normal' : 'exception'}
            format={() => ''}
          />
          {rateTag(v)}
        </Space>
      ),
    },
    { title: '参与人数', dataIndex: 'employee_count', render: (v: number) => `${v} 人` },
  ];

  const metricsColumns = [
    { title: '员工', dataIndex: 'employee_name', render: (v: string) => v || '—' },
    {
      title: '指标', dataIndex: 'metric_id',
      render: (v: string) => METRIC_LABELS[v] || v,
    },
    { title: '实际值', render: (_: any, row: any) => fmtValue(row.metric_id, row.value) },
    { title: '目标值', render: (_: any, row: any) => fmtValue(row.metric_id, row.target) },
    { title: '达成率', dataIndex: 'achievement_rate', render: rateTag },
    { title: '数据来源', dataIndex: 'data_source', render: (v: string) => v || '—' },
  ];

  // ── 渲染 ───────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* 页头 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}><TrophyOutlined /> 员工绩效看板</Title>
        <Space wrap>
          <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
            {stores.length > 0
              ? stores.map((s: any) => <Option key={s.id || s.store_id} value={s.id || s.store_id}>{s.name}</Option>)
              : <Option value="STORE001">STORE001</Option>}
          </Select>
          <DatePicker
            picker="month"
            value={period}
            onChange={(d) => d && setPeriod(d)}
            allowClear={false}
            style={{ width: 120 }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={computing}
            onClick={triggerCompute}
          >
            触发计算
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* 概览卡片 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card><Statistic title="在职员工" value={activeEmpCount} suffix="人" /></Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="排行榜人数" value={leaderboard.length} suffix="人" /></Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="指标均达成率" value={avgAchievement} suffix="%" /></Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="已计算指标类型" value={summary.length} suffix="项" /></Card>
          </Col>
        </Row>

        {/* 三个标签页 */}
        <Tabs
          defaultActiveKey="leaderboard"
          items={[
            {
              key: 'leaderboard',
              label: '排行榜',
              children: (
                <Row gutter={16}>
                  <Col span={10}>
                    <Card title="绩效排行榜">
                      <Table dataSource={leaderboard} columns={lbColumns}
                        rowKey="employee_id" pagination={false} size="small" />
                    </Card>
                  </Col>
                  <Col span={14}>
                    <Card title="员工列表">
                      <Table dataSource={employees} columns={empColumns}
                        rowKey="id" size="small" pagination={{ pageSize: 10 }} />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'summary',
              label: `指标汇总${summary.length > 0 ? ` (${summary.length})` : ''}`,
              children: (
                <Card title={`${period.format('YYYY年MM月')} 绩效指标汇总`}>
                  <Table dataSource={summary} columns={summaryColumns}
                    rowKey="metric_id" size="small" pagination={false}
                    locale={{ emptyText: '暂无数据，请点击「触发计算」生成指标' }}
                  />
                </Card>
              ),
            },
            {
              key: 'metrics',
              label: `明细记录${metrics.length > 0 ? ` (${metrics.length})` : ''}`,
              children: (
                <Card title={`${period.format('YYYY年MM月')} 员工指标明细`}>
                  <Table dataSource={metrics} columns={metricsColumns}
                    rowKey="id" size="small" pagination={{ pageSize: 15 }}
                    locale={{ emptyText: '暂无数据，请点击「触发计算」生成指标' }}
                  />
                </Card>
              ),
            },
          ]}
        />
      </Spin>

      {/* 手动录入绩效弹窗 */}
      <Modal title="录入员工绩效" open={recordModal} onCancel={() => setRecordModal(false)} footer={null}>
        <Form form={form} layout="vertical" onFinish={submitPerformance}>
          <Form.Item name="period" label="考核周期" rules={[{ required: true }]}>
            <DatePicker picker="month" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="attendance_rate" label="出勤率 (0-100)">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="customer_rating" label="顾客评分 (1-5)">
            <InputNumber min={1} max={5} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="efficiency_score" label="效率评分 (0-100)">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="sales_amount" label="销售额 (元)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>提交</Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default EmployeePerformancePage;
